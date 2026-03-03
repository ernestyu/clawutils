# clawutils

**Languages:** English | [中文说明](README_zh.md)

A small toolbox of CLI utilities and helpers around OpenClaw.

This repo is intended to collect reusable, script‑friendly tools that are
useful for:

- Web scraping and content normalization
- Text patching / incremental edits
- Knowledge base (Clawkb) helpers
- Filesystem maintenance (cleanup, renames, etc.)

The long‑term goal is to provide both:

- A Python library (`clawutils`) you can import, and
- A unified CLI entrypoint (e.g. `clawutils web scrape <URL>`) so humans and
  agents can discover and call tools in a structured way.

> Status: bootstrap phase. Initial focus: a robust web scraping pipeline and
> a safe text patcher for incremental edits.

---

## 1. Installation & Environment

clawutils is designed to run inside the OpenClaw runtime, but can also be used
in a similar Python + Node.js environment.

### 1.1 Python

- Python 3.10+

Install clawutils itself (editable/local install for development):

```bash
cd clawutils
python -m pip install -e .
```

### 1.2 Node.js & npm dependencies

The web scraper is implemented in Node.js and relies on:

- `playwright`
- `@mozilla/readability`
- `jsdom`
- `turndown`

Install them in the same environment where you will run `clawutils`:

```bash
npm install playwright @mozilla/readability jsdom turndown
```

> Note: In an OpenClaw container, Node.js is already available; you only need
> to install these npm packages.

---

## 2. CLI Overview

After installation, the main entrypoint is:

```bash
clawutils --help
```

Current top‑level commands:

- `clawutils web ...`   – Web‑related utilities (scrapers, cleaners)
- `clawutils text ...`  – Text utilities (patch, transform)
- `clawutils logs ...`  – Logs/session utilities (daily summaries, inspections)

Use `--help` on each subcommand for details:

```bash
clawutils web --help
clawutils web scrape --help
clawutils text --help
clawutils text patch --help
clawutils logs --help
clawutils logs daily --help
```

---

## 3. Web Scraper (`clawutils web scrape`)

The web scraper turns arbitrary web pages into clean, normalized Markdown that
is suitable for ingest into Clawkb or other knowledge bases.

### 3.1 Basic usage

```bash
clawutils web scrape "https://example.com/article" > out.md
```

Output format:

```text
--- METADATA ---
Title: ...
Author: ...
Site: ...
FinalURL: ...
Extraction: readability|fallback-container|body-innerText|github-raw-fast-path
FallbackSelector: ...   # only when Extraction != readability
--- MARKDOWN ---
<markdown body>
```

- `METADATA` block contains basic fields for downstream tools.
- `MARKDOWN` section is the cleaned article body.

### 3.2 Features

- **Readability‑based extraction**: uses `@mozilla/readability` to locate the
  main article content and strip navigation/ads/noise.
- **Fallback heuristics**: if Readability fails, falls back to likely content
  containers (`#js_content`, `article`, `main`, etc.), then to
  `document.body.innerText` as a last resort.
- **GitHub Fast Path**: for `github.com` URLs, tries to fetch raw README
  (e.g. `README.md`, `README_zh.md`) directly via HTTP without launching a
  browser, for speed and lower resource usage.
- **Metadata & debugging**:
  - Includes `Extraction` mode and optional `FallbackSelector`.
  - When content is too short, emits debug info and a screenshot
    (`/tmp/scrape-fail-<ts>.png`) to help diagnose issues.

### 3.3 Integrating with Clawkb (`CLAWKB_SCRAPE_CMD`)

clawutils is designed to be a drop‑in scraper for Clawkb.

In your Clawkb project, set in `.env`:

```env
CLAWKB_SCRAPE_CMD="clawutils web scrape {url}"
```

Clawkb's `ingest --url` will then:

1. Call `clawutils web scrape <URL>`;
2. Parse the `METADATA` and `MARKDOWN` sections;
3. Store the article in SQLite + Markdown as usual.

You can still override `--scrape-cmd` per call if needed:

```bash
python -m clawkb ingest \
  --url "https://example.com/article" \
  --scrape-cmd "clawutils web scrape {url}"
```

---

## 4. Text Patcher (`clawutils text patch`)

The text patcher provides a small, safe tool for incremental edits to text
files. It is designed to avoid whole‑file rewrites when only small changes are
needed.

### 4.1 Modes

Supported modes:

- `prepend` – insert at the very beginning
- `append`  – append at the end
- `after`   – insert immediately after a marker substring

### 4.2 Usage examples

#### Prepend

```bash
clawutils text patch \
  --file README.md \
  --mode prepend \
  --text "# My Project"
```

#### Append

```bash
clawutils text patch \
  --file README.md \
  --mode append \
  --text "\n---\nUpdated via clawutils text patch"
```

#### After marker

```bash
clawutils text patch \
  --file README.md \
  --mode after \
  --marker "### Changelog" \
  --text "- Added clawutils text patch utility"
```

Safety behavior:

- If the file does not exist → prints `ERROR: File not found` and exits with
  code 1.
- If `--mode=after` and marker is missing → prints a clear error and exits
  with code 1.

This tool is particularly useful when large files are managed by an AI agent:
let the agent generate only the small piece of new text, and let `clawutils`
handle the insertion on disk.

---

## 5. Daily Logs Summarizer (`clawutils logs daily`)

The logs summarizer turns a day's worth of OpenClaw session logs into a
structured outline or diary‑style summary.

> The current implementation focuses on the main agent's session JSONL files
> under `~/.openclaw/agents/main/sessions`.

### 5.1 Basic usage

```bash
# Summarize yesterday (UTC) for the main agent
clawutils logs daily

# Summarize a specific date
clawutils logs daily --date 2026-03-02

# Summarize using a custom agent directory
clawutils logs daily --date 2026-03-02 \
  --agent-dir ~/.openclaw/agents/main \
  --verbose
```

Key options:

- `--date YYYY-MM-DD` – Target date (UTC). If omitted, defaults to yesterday.
- `--agent-dir PATH` – Agent directory; defaults to
  `~/.openclaw/agents/main`.
- `--verbose` – Print detailed progress logs (phases, counts, clustering).
- `--cluster-threshold FLOAT` – Override TF‑IDF cosine threshold when
  embeddings are not used. Lower values merge more segments into fewer,
  broader topics; higher values keep clusters more granular.

### 5.2 Behavior & design

1. **Session scanning**
   - Scans `sessions/*.jsonl` under the chosen `agent-dir`.
   - Files are processed in **reverse mtime order** (newest first).
   - Uses file modification time to short‑circuit: once a file's `mtime` is
     strictly before the start of the target date, older files are skipped.

2. **Message extraction & cleaning**
   - Keeps only `type == "message"` with `role` in `{user, assistant}`.
   - Flattens `content[]` into plain text (`type == "text"`).
   - Strips obvious system metadata blocks:
     - `Conversation info (untrusted metadata)`
     - `Forwarded message context (untrusted metadata)`
     and their following JSON blocks.
   - Filters out short shell/log‑like noise (e.g. one‑liners containing
     `pip`, `npm`, `git`, `ls`, `cd`, `docker`, `openclaw`).

3. **Segmentation**
   - Messages are grouped into segments in chronological order.
   - A new segment starts when adding another message would exceed a size
     limit (currently ~2000 characters).
   - This avoids both extremely small and extremely large segments; topic
     grouping is handled by clustering.

4. **Clustering (topics)**
   - If embeddings are configured (`EMBEDDING_*` env vars) and available,
     segments are clustered via embedding‑based cosine similarity.
   - Otherwise, a TF‑IDF‑style bag‑of‑words cosine similarity is used as a
     fallback:
     - Default threshold is `0.6`.
     - You can override with `--cluster-threshold`.
   - The goal is to group semantically related segments into topic clusters,
     even if they are far apart in time.

5. **Summarization modes**
   - If `SMALL_LLM_*` env vars are configured and `httpx` is available:
     - Each topic cluster is summarized via a small LLM.
     - A final "daily diary" is generated from the per‑cluster summaries.
   - Otherwise, a deterministic **outline mode** is used:
     - Each topic is printed with keywords, stats, and a representative
       sample line.

### 5.3 Outline mode format (no LLM)

When no small LLM is configured, the output looks roughly like this:

```text
Daily summary for 2026-03-02

## 1. [clawutils, daily, logs] (15 msgs | 42.3 min)
> 代表性的那一句话……

## 2. [Clawkb, maintenance, delete] (8 msgs | 21.5 min)
> Another representative sentence...
```

Details:

- **Topic numbering**: topics are numbered `1.`, `2.`, ... to make them easy
  to reference in conversation.
- **Keyword fingerprint**: keywords are extracted per topic via
  `jieba.analyse.textrank` (when available), with a simple bag‑of‑words
  fallback. This makes the topic's core content visible at a glance.
- **Compact stats**: `(<N> msgs | <M> min)` shows approximate message count
  and time span.
- **Representative sample**: a single quoted line (`> ...`) is chosen per
  topic using a rough signal‑to‑noise ratio heuristic (token density), so
  that high‑information sentences are preferred.

This mode requires no external LLMs and is designed to be useful even in
offline or "no‑API" environments.

### 5.4 LLM‑backed diary mode

When `SMALL_LLM_BASE_URL`, `SMALL_LLM_MODEL`, and `SMALL_LLM_API_KEY` are
set and reachable, `clawutils logs daily` will:

1. Generate a short structured summary for each topic cluster via the small
   LLM.
2. Ask the small LLM to merge those topic summaries into a single daily
   diary, using a first‑person style and emphasizing decisions, conclusions,
   and follow‑up TODOs.

If any LLM call fails, the command falls back to the outline mode described
above.

---

## 6. Skills Integration (OpenClaw)

clawutils ships with example skills for OpenClaw agents under `skills/`:

- `skills/web-scrape/SKILL.md`
- `skills/text-patch/SKILL.md`

You can symlink them into your main OpenClaw workspace if you want agents to
call these tools as first‑class skills, for example:

```bash
# In your main OpenClaw workspace
cd /home/node/.openclaw/workspace

ln -s ./clawutils/skills/web-scrape ./skills/web-scrape
ln -s ./clawutils/skills/text-patch ./skills/text-patch
```

Each SKILL.md documents how to invoke the underlying CLI, typically using:

```bash
PYTHONPATH=src /opt/venv/bin/python -m clawutils.cli web scrape <URL>
PYTHONPATH=src /opt/venv/bin/python -m clawutils.cli text patch [...]
```

---

## License

MIT © Ernest Yu
