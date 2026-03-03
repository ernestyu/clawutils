"""Daily session log summarizer for OpenClaw.

Given a target date, this module:

1. Reads JSONL session logs for that day from the OpenClaw agent sessions dir.
2. Extracts human-readable messages (user/assistant text), with basic noise
   filtering.
3. Groups messages into segments (blocks). Segments are then clustered purely
   by content similarity so that thematically-related chunks (even far apart in
   time) end up in the same topic cluster.
4. Clusters segments by semantic similarity, preferring embeddings when
   available and falling back to a TF-IDF-style bag-of-words cosine similarity
   when embeddings are not configured or fail.
5. Summarizes each cluster and then the whole day via a configured summarizer
   provider (a small LLM when available; otherwise an outline-only fallback).

Design choices:

- `--date` always means "that date" (YYYY-MM-DD). No implicit "minus one day"
  magic. A higher-level scheduler (cron) can call this daily, usually to
  summarize "yesterday".
- When `--date` is omitted, we default to "yesterday" (UTC) for convenience.
- Time is used only as metadata (for timestamps) and as a very weak heuristic
  for segmentation; topic grouping is driven by content similarity.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

try:  # optional dependency; required only if you enable embedding/LLM summarization
    import httpx  # type: ignore
except Exception:  # pragma: no cover - handled via feature gating
    httpx = None  # type: ignore


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Message:
    timestamp: _dt.datetime
    role: str  # "user" | "assistant"
    text: str


@dataclass
class Segment:
    """A contiguous block of dialogue messages for clustering."""

    start: _dt.datetime
    end: _dt.datetime
    text: str


@dataclass
class Cluster:
    """A cluster of semantically similar segments."""

    id: int
    segments: List[Segment]


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _parse_iso(ts: str) -> Optional[_dt.datetime]:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            return _dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return _dt.datetime.fromisoformat(ts)
    except Exception:
        return None


def _yesterday_utc() -> str:
    today = _dt.datetime.utcnow().date()
    return str(today - _dt.timedelta(days=1))  # YYYY-MM-DD


# ---------------------------------------------------------------------------
# Step 1: load messages for a given date
# ---------------------------------------------------------------------------


def _iter_session_files(agent_dir: Path, *, reverse: bool = True) -> Iterable[Path]:
    """Yield session files in (optionally) reverse mtime order.

    We sort by modification time descending so that recent sessions are
    processed first. This allows us to short-circuit when looking for recent
    dates (e.g. "yesterday") and avoid scanning the entire history.
    """

    sessions_dir = agent_dir / "sessions"
    if not sessions_dir.exists():
        return []
    files = list(sessions_dir.glob("*.jsonl"))
    files.sort(key=lambda p: p.stat().st_mtime, reverse=reverse)
    return files


def _extract_messages_for_date(agent_dir: Path, date_str: str) -> List[Message]:
    """Scan all session JSONL files for messages on the given date (UTC).

    * Only `message.role` in {"user", "assistant"} are considered.
    * We only keep `.content[]` entries of type "text".
    """

    target_date = date_str
    out: List[Message] = []

    # Compute the target day's time window in UTC.
    try:
        day = _dt.date.fromisoformat(target_date)
    except Exception:
        day = None
    start_dt = _dt.datetime(day.year, day.month, day.day, tzinfo=_dt.timezone.utc) if day else None

    for path in _iter_session_files(agent_dir):
        # Short-circuit using filesystem mtime when possible: if the file was
        # last modified strictly before the target day starts, it cannot
        # contain messages for that date.
        if start_dt is not None:
            mtime = _dt.datetime.fromtimestamp(path.stat().st_mtime, tz=_dt.timezone.utc)
            if mtime < start_dt:
                # Because files are sorted by mtime desc, we can break early.
                break

        try:
            f = path.open("r", encoding="utf-8")
        except Exception:
            continue
        with f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue

                if obj.get("type") != "message":
                    continue
                msg = obj.get("message") or {}
                role = msg.get("role")
                if role not in {"user", "assistant"}:
                    continue
                ts = _parse_iso(obj.get("timestamp") or "")
                if not ts:
                    continue
                if str(ts.date()) != target_date:
                    continue

                # Flatten text content
                texts: List[str] = []
                for c in msg.get("content") or []:
                    if c.get("type") == "text" and c.get("text"):
                        texts.append(str(c["text"]))
                if not texts:
                    continue
                out.append(Message(timestamp=ts, role=role, text="\n".join(texts)))

    out.sort(key=lambda m: m.timestamp)
    return out


# ---------------------------------------------------------------------------
# Step 2: basic noise filtering
# ---------------------------------------------------------------------------


_SHELL_LIKE = re.compile(r"\b(pip|npm|git|ssh|ls|cd|docker|openclaw)\b", re.I)


def _is_mostly_shell_or_log(text: str) -> bool:
    """Heuristic: drop lines that are mostly shell/log noise.

    Very simple: if the text is short and dominated by shell-y keywords,
    treat it as noise for diary purposes.
    """

    t = (text or "").strip()
    if len(t) < 20 and _SHELL_LIKE.search(t):
        return True
    return False


def filter_messages(messages: List[Message]) -> List[Message]:
    out: List[Message] = []
    for m in messages:
        if _is_mostly_shell_or_log(m.text):
            continue
        out.append(m)
    return out


# ---------------------------------------------------------------------------
# Step 3: segment messages into blocks (lightweight)
# ---------------------------------------------------------------------------


def segment_messages(messages: List[Message]) -> List[Segment]:
    """Group messages into segments.

    We use a lightweight strategy here: aggregate messages in chronological
    order into reasonably sized text blocks. Topic grouping will later be done
    by semantic clustering, so time continuity is not used as a strong
    boundary — only to avoid creating extremely tiny or extremely huge units.
    """

    if not messages:
        return []

    segments: List[Segment] = []
    current_start = messages[0].timestamp
    current_end = messages[0].timestamp
    current_text_parts: List[str] = []

    max_chars = 2000

    for m in messages:
        # If adding this message would make the segment too large, start a new one.
        tentative = ("\n".join(current_text_parts + [m.text])).strip()
        if current_text_parts and len(tentative) > max_chars:
            segments.append(
                Segment(
                    start=current_start,
                    end=current_end,
                    text="\n".join(current_text_parts),
                )
            )
            current_start = m.timestamp
            current_text_parts = [m.text]
        else:
            if not current_text_parts:
                current_start = m.timestamp
            current_text_parts.append(m.text)
        current_end = m.timestamp

    if current_text_parts:
        segments.append(
            Segment(start=current_start, end=current_end, text="\n".join(current_text_parts))
        )
    return segments


# ---------------------------------------------------------------------------
# Step 4: similarity & clustering
# ---------------------------------------------------------------------------


def _normalize_text_for_bow(text: str) -> List[str]:
    """Simple tokenization for TF-IDF-like similarity.

    Lowercase, remove obvious punctuation, split on whitespace.
    This is intentionally simple; we do not depend on external NLP libs here.
    """

    t = (text or "").lower()
    t = re.sub(r"[\t\r\n]+", " ", t)
    t = re.sub(r"[^a-z0-9\u4e00-\u9fff ]+", " ", t)
    tokens = [p for p in t.split(" ") if p]
    return tokens


def _cosine_from_counts(c1: Counter, c2: Counter) -> float:
    if not c1 or not c2:
        return 0.0
    dot = 0.0
    for k, v in c1.items():
        if k in c2:
            dot += v * c2[k]
    if dot == 0.0:
        return 0.0
    n1 = math.sqrt(sum(v * v for v in c1.values()))
    n2 = math.sqrt(sum(v * v for v in c2.values()))
    if n1 == 0.0 or n2 == 0.0:
        return 0.0
    return dot / (n1 * n2)


def cluster_segments_tfidf(segments: List[Segment], threshold: float = 0.7) -> List[Cluster]:
    """Cluster segments using a simple bag-of-words cosine similarity.

    This is used as a fallback when embeddings are unavailable or fail.
    """

    if not segments:
        return []

    bow_vectors: List[Counter] = [Counter(_normalize_text_for_bow(s.text)) for s in segments]

    clusters: List[Cluster] = []
    centroids: List[Counter] = []  # simple average via sum; re-normalized implicitly

    for seg, vec in zip(segments, bow_vectors):
        if not clusters:
            clusters.append(Cluster(id=0, segments=[seg]))
            centroids.append(vec.copy())
            continue

        best_i = -1
        best_sim = 0.0
        for i, cvec in enumerate(centroids):
            sim = _cosine_from_counts(vec, cvec)
            if sim > best_sim:
                best_sim = sim
                best_i = i

        if best_i >= 0 and best_sim >= threshold:
            clusters[best_i].segments.append(seg)
            for k, v in vec.items():
                centroids[best_i][k] += v
        else:
            cid = len(clusters)
            clusters.append(Cluster(id=cid, segments=[seg]))
            centroids.append(vec.copy())

    return clusters


# ---- Embedding-based clustering ------------------------------------------------


def _embedding_config() -> Optional[tuple[str, str, str]]:
    base = os.environ.get("EMBEDDING_BASE_URL")
    model = os.environ.get("EMBEDDING_MODEL")
    key = os.environ.get("EMBEDDING_API_KEY")
    if base and model and key and httpx is not None:
        return base.rstrip("/"), model, key
    return None


def _get_embedding(text: str, max_chars: int = 2000) -> Optional[List[float]]:
    cfg = _embedding_config()
    if not cfg:
        return None
    base, model, key = cfg
    if not text:
        return None
    payload = {
        "model": model,
        "input": text[:max_chars],
    }
    try:
        resp = httpx.post(
            f"{base}/embeddings",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        emb = data["data"][0]["embedding"]
        return [float(x) for x in emb]
    except Exception:
        return None


def _cosine_vec(v1: List[float], v2: List[float]) -> float:
    if not v1 or not v2:
        return 0.0
    if len(v1) != len(v2):
        return 0.0
    dot = 0.0
    n1 = 0.0
    n2 = 0.0
    for a, b in zip(v1, v2):
        dot += a * b
        n1 += a * a
        n2 += b * b
    if dot == 0.0:
        return 0.0
    n1 = math.sqrt(n1)
    n2 = math.sqrt(n2)
    if n1 == 0.0 or n2 == 0.0:
        return 0.0
    return dot / (n1 * n2)


def cluster_segments_embedding(segments: List[Segment], threshold: float = 0.75) -> Optional[List[Cluster]]:
    """Cluster segments using embeddings.

    Returns None if embeddings are not configured or fail; caller should
    fall back to TF-IDF clustering.
    """

    cfg = _embedding_config()
    if not cfg or not segments:
        return None

    vectors: List[Optional[List[float]]] = []
    for s in segments:
        emb = _get_embedding(s.text)
        if emb is None:
            return None
        vectors.append(emb)

    clusters: List[Cluster] = []
    centroids: List[List[float]] = []

    for seg, vec in zip(segments, vectors):
        assert vec is not None
        if not clusters:
            clusters.append(Cluster(id=0, segments=[seg]))
            centroids.append(list(vec))
            continue

        best_i = -1
        best_sim = 0.0
        for i, cvec in enumerate(centroids):
            sim = _cosine_vec(vec, cvec)
            if sim > best_sim:
                best_sim = sim
                best_i = i

        if best_i >= 0 and best_sim >= threshold:
            clusters[best_i].segments.append(seg)
            # Update centroid with a simple running average (here, add vec)
            cvec = centroids[best_i]
            for j, val in enumerate(vec):
                cvec[j] += val
        else:
            cid = len(clusters)
            clusters.append(Cluster(id=cid, segments=[seg]))
            centroids.append(list(vec))

    return clusters


def cluster_segments(segments: List[Segment]) -> List[Cluster]:
    """Cluster segments by similarity.

    - If embeddings are configured and calls succeed, use embedding-based
      clustering.
    - Otherwise, fall back to TF-IDF-like bag-of-words clustering.
    """

    if not segments:
        return []

    # Try embedding-based clustering first.
    clusters = cluster_segments_embedding(segments)
    if clusters is not None:
        return clusters

    # Fallback: TF-IDF clustering.
    return cluster_segments_tfidf(segments)


# ---------------------------------------------------------------------------
# Step 5: summarization
# ---------------------------------------------------------------------------


def _small_llm_config() -> Optional[tuple[str, str, str]]:
    base = os.environ.get("SMALL_LLM_BASE_URL")
    model = os.environ.get("SMALL_LLM_MODEL")
    key = os.environ.get("SMALL_LLM_API_KEY")
    if base and model and key and httpx is not None:
        return base.rstrip("/"), model, key
    return None


def _call_small_llm(prompt: str) -> Optional[str]:
    cfg = _small_llm_config()
    if not cfg:
        return None
    base, model, key = cfg
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are an assistant that writes concise daily logs for the user."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }
    try:
        resp = httpx.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def _outline_from_clusters(clusters: List[Cluster], date_str: str) -> str:
    """Deterministic outline summary (no LLM).

    Used as a fallback when no LLM summarizer is configured.
    """

    lines: List[str] = []
    lines.append(f"Daily summary for {date_str}")

    if not clusters:
        lines.append("")
        lines.append("(No significant messages for this date.)")
        return "\n".join(lines)

    for c in clusters:
        lines.append("")
        lines.append(f"## Topic {c.id + 1}")
        first = c.segments[0].start
        last = c.segments[-1].end
        lines.append(f"Time span: {first.isoformat()} → {last.isoformat()}")
        sample = c.segments[0].text.replace("\n", " ")
        if len(sample) > 200:
            sample = sample[:200] + "..."
        lines.append(f"Sample: {sample}")

    return "\n".join(lines)


def summarize_clusters(clusters: List[Cluster], date_str: str, *, verbose: bool = False) -> str:
    """Summarize clusters into a diary-style text.

    Strategy:
    - If SMALL_LLM_* is configured, use the small LLM to summarize each
      cluster and then the whole day.
    - Otherwise, return a deterministic outline summary.
    """

    cfg = _small_llm_config()
    if cfg is None or httpx is None:
        if verbose:
            print("[logs/daily] SMALL_LLM_* not configured; using outline mode.")
        return _outline_from_clusters(clusters, date_str)

    if verbose:
        print("[logs/daily] Summarizing via small LLM...")

    # Build a per-cluster summary via the small LLM.
    cluster_summaries: List[str] = []
    base, model, _ = cfg
    for idx, c in enumerate(clusters):
        if verbose:
            print(f"[logs/daily]  - Summarizing topic {idx+1}/{len(clusters)} (provider={model})")
        pieces: List[str] = []
        for seg in c.segments:
            pieces.append(seg.text)
        cluster_text = "\n\n".join(pieces)
        # Hard truncate cluster_text to avoid extremely long prompts.
        if len(cluster_text) > 4000:
            cluster_text = cluster_text[:4000] + "..."
        prompt = (
            f"今天 ({date_str}) 的以下对话片段都属于同一个主题。\n"
            "请用简体中文写一个结构化小结，重点说明：\n"
            "- 这是关于什么主题？\n"
            "- 今天在这个主题上做了哪些决策、结论或重要想法？\n"
            "- 如果有 TODO 或后续行动，请列出来。\n\n"
            "对话内容如下：\n" + cluster_text
        )
        summary = _call_small_llm(prompt) or "(LLM summarization failed)"
        cluster_summaries.append(summary)

    # Now summarize the whole day from the cluster summaries.
    joined = "\n\n".join(
        f"[主题 {i+1}]\n{txt}" for i, txt in enumerate(cluster_summaries)
    )
    final_prompt = (
        f"下面是用户在 {date_str} 不同主题下的总结，请你将它们整合成一篇当日的日记。\n"
        "要求：\n"
        "- 用第一人称（“我”）叙述；\n"
        "- 按主题或事项分段；\n"
        "- 重点写清楚做了什么决策/形成了哪些结论/有哪些后续计划；\n"
        "- 语言简洁但信息完整。\n\n"
        "各主题小结如下：\n" + joined
    )

    final = _call_small_llm(final_prompt)
    if final:
        return final

    # If final summarization fails, fall back to concatenated cluster summaries.
    return joined


# ---------------------------------------------------------------------------
# CLI wrapper
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="clawutils logs daily",
        description="Summarize a day's OpenClaw session logs into a diary-style outline",
    )
    parser.add_argument(
        "--date",
        help="Target date (YYYY-MM-DD). If omitted, defaults to yesterday (UTC)",
    )
    parser.add_argument(
        "--agent-dir",
        help="Agent directory (default: ~/.openclaw/agents/main)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose progress output",
    )

    args = parser.parse_args(argv)

    date_str = args.date or _yesterday_utc()

    # Agent dir: default to the main agent directory for this container.
    if args.agent_dir:
        agent_dir = Path(args.agent_dir)
    else:
        home = Path(os.path.expanduser("~"))
        agent_dir = home / ".openclaw" / "agents" / "main"

    if args.verbose:
        print(f"[logs/daily] Target date: {date_str}")
        print(f"[logs/daily] Agent dir: {agent_dir}")

    if args.verbose:
        print("[1/4] Reading session messages...")
    messages = _extract_messages_for_date(agent_dir, date_str)
    if args.verbose:
        print(f"[1/4] Done. Messages: {len(messages)}")

    if args.verbose:
        print("[2/4] Filtering noise...")
    messages = filter_messages(messages)
    if args.verbose:
        print(f"[2/4] Done. Messages after filter: {len(messages)}")

    if args.verbose:
        print("[3/4] Building segments...")
    segments = segment_messages(messages)
    if args.verbose:
        print(f"[3/4] Done. Segments: {len(segments)}")

    if args.verbose:
        print("[4/4] Clustering topics...")
    clusters = cluster_segments(segments)
    if args.verbose:
        print(f"[4/4] Done. Clusters: {len(clusters)}")

    diary = summarize_clusters(clusters, date_str, verbose=args.verbose)
    print(diary)

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
