"""Daily session log summarizer for OpenClaw.

Given a target date, this module:

1. Reads JSONL session logs for that day from the OpenClaw agent sessions dir.
2. Extracts human-readable messages (user/assistant text), with basic noise filtering.
3. Groups messages into segments (blocks) based on time gaps.
4. Clusters segments by semantic similarity (embedding when available, falling
   back to a TF-IDF-like bag-of-words cosine similarity when embeddings fail).
5. Summarizes each cluster and then the whole day via a configured summarizer
   provider (small LLM when available, falling back to the main model).
6. Returns a final diary-style summary string (writing to a file is left to
   the caller or a wrapper CLI).

The overall design is intentionally conservative and explicit:

- `--date` always means "that date" (YYYY-MM-DD). No implicit "minus one day"
  magic. A higher-level scheduler (cron) can call this daily, usually to
  summarize "yesterday".
- When `--date` is omitted, we default to "yesterday" for convenience.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import re
from collections import Counter


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
    """A contiguous block of dialogue messages for clustering.

    We keep a simple representation: concatenated text + time span.
    """

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


def _iter_session_files(agent_dir: Path) -> Iterable[Path]:
    sessions_dir = agent_dir / "sessions"
    if not sessions_dir.exists():
        return []
    return sorted(sessions_dir.glob("*.jsonl"))


def _extract_messages_for_date(agent_dir: Path, date_str: str) -> List[Message]:
    """Scan all session JSONL files for messages on the given date (UTC).

    * Only `message.role` in {"user", "assistant"} are considered.
    * We only keep `.content[]` entries of type "text".
    """

    target_date = date_str
    out: List[Message] = []

    for path in _iter_session_files(agent_dir):
        with path.open("r", encoding="utf-8") as f:
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

    # Sort by time
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
# Step 3: segment messages into blocks
# ---------------------------------------------------------------------------


def segment_messages(messages: List[Message], max_gap_minutes: int = 30) -> List[Segment]:
    """Group messages into contiguous segments based on time gaps.

    A new segment starts when the gap between consecutive messages exceeds
    `max_gap_minutes`.
    """

    if not messages:
        return []

    segments: List[Segment] = []
    current_start = messages[0].timestamp
    current_end = messages[0].timestamp
    current_text_parts: List[str] = [messages[0].text]

    gap = _dt.timedelta(minutes=max_gap_minutes)

    for prev, m in zip(messages, messages[1:]):
        if m.timestamp - prev.timestamp > gap:
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
            current_text_parts.append(m.text)
        current_end = m.timestamp

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
    # Dot product
    dot = 0.0
    for k, v in c1.items():
        if k in c2:
            dot += v * c2[k]
    if dot == 0.0:
        return 0.0
    # Norms
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

    for idx, (seg, vec) in enumerate(zip(segments, bow_vectors)):
        if not clusters:
            clusters.append(Cluster(id=0, segments=[seg]))
            centroids.append(vec.copy())
            continue

        # Find best matching cluster
        best_i = -1
        best_sim = 0.0
        for i, cvec in enumerate(centroids):
            sim = _cosine_from_counts(vec, cvec)
            if sim > best_sim:
                best_sim = sim
                best_i = i

        if best_i >= 0 and best_sim >= threshold:
            clusters[best_i].segments.append(seg)
            # Update centroid by adding counts
            for k, v in vec.items():
                centroids[best_i][k] += v
        else:
            cid = len(clusters)
            clusters.append(Cluster(id=cid, segments=[seg]))
            centroids.append(vec.copy())

    return clusters


# Placeholder for embedding-based clustering. In this environment we do not
# call external embedding services directly, but the structure is left here
# in case an embedding client is wired in later.


def cluster_segments(segments: List[Segment], use_embedding: bool = False) -> List[Cluster]:
    """Cluster segments by similarity.

    - If `use_embedding` is True and an embedding client is available, this is
      where embedding-based clustering would be implemented.
    - For now we always fall back to TF-IDF-like bag-of-words clustering.
    """

    # TODO: integrate with an embedding client when available.
    return cluster_segments_tfidf(segments)


# ---------------------------------------------------------------------------
# Step 5: summarization (placeholder)
# ---------------------------------------------------------------------------


def summarize_clusters(clusters: List[Cluster], date_str: str) -> str:
    """Summarize clusters into a diary-style text.

    For now this is a placeholder that produces a simple structured outline
    without calling any LLM. It can be replaced with calls to a small LLM or
    the main OpenClaw model later.
    """

    lines: List[str] = []
    lines.append(f"Daily summary for {date_str}")
    lines.append("".rstrip())

    if not clusters:
        lines.append("(No significant messages for this date.)")
        return "\n".join(lines)

    for c in clusters:
        lines.append("")
        lines.append(f"## Topic {c.id + 1}")
        first = c.segments[0].start
        last = c.segments[-1].end
        lines.append(f"Time span: {first.isoformat()} → {last.isoformat()}")
        # Include a small excerpt (first 200 chars) as a hint
        sample = c.segments[0].text.replace("\n", " ")
        if len(sample) > 200:
            sample = sample[:200] + "..."
        lines.append(f"Sample: {sample}")

    return "\n".join(lines)


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
        help="Agent sessions directory (default: ~/.openclaw/agents/<current>/sessions/..)",
    )

    args = parser.parse_args(argv)

    date_str = args.date or _yesterday_utc()

    # Agent dir: for now we default to the main agent directory for this container.
    # In many setups this will be ~/.openclaw/agents/main/, but we avoid hardcoding
    # the agent id and instead let the caller pass --agent-dir when needed.
    agent_dir = None
    if args.agent_dir:
        agent_dir = Path(args.agent_dir)
    else:
        home = Path(os.path.expanduser("~"))
        agent_dir = home / ".openclaw" / "agents" / "main"

    messages = _extract_messages_for_date(agent_dir, date_str)
    messages = filter_messages(messages)
    segments = segment_messages(messages)
    clusters = cluster_segments(segments)

    diary = summarize_clusters(clusters, date_str)
    print(diary)

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
