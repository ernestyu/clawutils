# clawutils(1)

## NAME
**clawutils** — CLI utilities around OpenClaw (web scraping, text patching, daily logs summarization)

## SYNOPSIS
```bash
clawutils [GLOBAL OPTIONS] <command> [COMMAND OPTIONS]
PYTHONPATH=src python -m clawutils.cli [GLOBAL OPTIONS] <command> [COMMAND OPTIONS]
```

## DESCRIPTION
clawutils 是围绕 OpenClaw 打造的一组“小而实用”的命令行工具，目前聚焦三个方向：

- 从网页中提取干净的 Markdown（适合 Clawkb 等知识库使用）；
- 在现有文本文件中安全地做增量补丁（头插、尾插或标记后插入）；
- 按天总结 OpenClaw Agent 的会话日志（可配合 small LLM 输出“日记式”总结）。

本文件以“类 man 手册”的形式，对每个子命令的用法、参数与典型场景做集中说明。

---

## GLOBAL OPTIONS

顶层命令的帮助如下：

```text
usage: clawutils [-h] {web,text,logs} ...

CLI utilities around OpenClaw (web, text, kb, fs)

positional arguments:
  {web,text,logs}
    web            Web-related utilities (scrapers, cleaners)
    text           Text utilities (patch, transform)
    logs           Logs/session utilities (daily summaries, inspections)

options:
  -h, --help       show this help message and exit
```

目前没有全局级别的额外选项，所有有意义的参数都在各自子命令中声明。


---

## web(1)

### NAME
**clawutils web** — 与网页抓取/清洗相关的工具

### SUBCOMMANDS

```text
usage: clawutils web [-h] {scrape} ...

positional arguments:
  {scrape}
    scrape    Scrape a web page and print normalized markdown

options:
  -h, --help  show this help message and exit
```

目前仅实现了 `web scrape`，后续可扩展更多清洗/转换类工具。


### web scrape(1)

#### NAME
**clawutils web scrape** — 抓取网页并输出规范化 Markdown

#### SYNOPSIS
```bash
clawutils web scrape <URL>
PYTHONPATH=src python -m clawutils.cli web scrape <URL>
```

#### DESCRIPTION

- 使用 Playwright 驱动无头浏览器加载页面；
- 使用 `@mozilla/readability` 计算主体内容区块；
- 通过 `jsdom` + `turndown` 将 HTML 结构转换为 Markdown；
- 对 GitHub 仓库页面做“原始 README 快速路径”优化，避免不必要的浏览器启动。

输出分为两个部分：

```text
--- METADATA ---
Title: ...
Author: ...
Site: ...
FinalURL: ...
Extraction: readability|fallback-container|body-innerText|github-raw-fast-path
FallbackSelector: ...   # 仅在 Extraction != readability 时出现
--- MARKDOWN ---
<markdown 正文>
```

- `METADATA` 区块：提供标题、作者、站点、最终 URL 和抽取方式等信息；
- `MARKDOWN` 区块：已经清洗好的正文内容，适合直接写入 Clawkb 文章文件。

#### OPTIONS

```text
usage: clawutils web scrape [-h] url

positional arguments:
  url         URL to scrape

options:
  -h, --help  show this help message and exit
```

#### EXAMPLES

```bash
# 将网页抓取为 markdown 文件
clawutils web scrape "https://example.com/article" > out.md

# 搭配 Clawkb 使用（在 .env 中）
CLAWKB_SCRAPE_CMD="clawutils web scrape {url}"
```

---

## text(1)

### NAME
**clawutils text** — 文本补丁/转换相关工具

### SUBCOMMANDS

```text
usage: clawutils text [-h] {patch} ...

positional arguments:
  {patch}
    patch     Patch a text file (prepend/append/after marker)

options:
  -h, --help  show this help message and exit
```


### text patch(1)

#### NAME
**clawutils text patch** — 在文本文件中做安全的增量补丁

#### SYNOPSIS
```bash
clawutils text patch --file FILE --text TEXT --mode {prepend,append,after} [--marker MARKER]
```

#### DESCRIPTION

为 OpenClaw/Agent 提供一个“可靠的写入后端”：在大文件中只改一小段，而不是整篇重写。

支持三种模式：

- `prepend`：在文件开头插入；
- `append`：在文件末尾追加；
- `after`：在第一个匹配到的 marker 行之后插入。

错误处理：

- 目标文件不存在 → 输出错误并以非 0 状态退出；
- `--mode=after` 且未提供或未找到 `--marker` → 输出错误并以非 0 状态退出。

#### OPTIONS

```text
usage: clawutils text patch [-h] --file FILE --text TEXT --mode
                            {prepend,append,after} [--marker MARKER]

options:
  -h, --help            show this help message and exit
  --file FILE           Target file path
  --text TEXT           Text to insert
  --mode {prepend,append,after}
                        Patch mode
  --marker MARKER       Marker for 'after' mode (required when --mode=after)
```

#### EXAMPLES

```bash
# 在 README 头部插入标题
clawutils text patch \
  --file README.md \
  --mode prepend \
  --text "# My Project"

# 在文件末尾追加一段 changelog
clawutils text patch \
  --file README.md \
  --mode append \
  --text "\n---\nUpdated via clawutils text patch"

# 在 "### Changelog" 标题之后插入一行
clawutils text patch \
  --file README.md \
  --mode after \
  --marker "### Changelog" \
  --text "- Added clawutils text patch utility"
```

---

## logs(1)

### NAME
**clawutils logs** — OpenClaw 会话日志相关工具

### SUBCOMMANDS

```text
usage: clawutils logs [-h] {daily} ...

positional arguments:
  {daily}
    daily     Summarize a day's OpenClaw session logs into a diary-style
              outline

options:
  -h, --help  show this help message and exit
```


### logs daily(1)

#### NAME
**clawutils logs daily** — 按天总结 OpenClaw 会话日志，输出大纲或“日记”

#### SYNOPSIS
```bash
clawutils logs daily [--date YYYY-MM-DD] [--agent-dir PATH]
                     [--verbose]
                     [--cluster-threshold FLOAT]
```

#### DESCRIPTION

该命令从 OpenClaw Agent 的 JSONL 会话日志中提取指定日期的对话记录，
按照主题进行聚类，并以两种模式之一输出：

- 纯大纲模式：不依赖任何 LLM，可以在离线/无 API 环境使用；
- 小模型日记模式：在配置了 SMALL_LLM_* 后，生成“第一人称日记式”总结。

核心流程：

1. **文件扫描**：
   - 在指定 `agent-dir` 下的 `sessions/*.jsonl` 中查找；
   - 按 mtime 逆序遍历（新文件优先）；
   - 一旦某个文件的 mtime 早于目标日期起点，直接停止继续向前扫描。

2. **消息提取与清洗**：
   - 仅保留 `type == "message"` 且角色为 `user`/`assistant` 的记录；
   - 将 `content[]` 中的文本条目展平为一段字符串；
   - 剥离显式的系统元数据块（如 "Conversation info (untrusted metadata)"、
     "Forwarded message context" 及其后续 JSON）；
   - 过滤极短的 shell/log 命令行噪音（`pip`、`npm`、`git` 等）。

3. **分段 (segment)**：
   - 按时间顺序累积消息构成段落；
   - 每个段落大小控制在约 2000 字符以内，过长则切分成多个段；
   - 这些段落构成聚类的基本单元。

4. **聚类（话题）**：
   - 如果配置了 embedding（`EMBEDDING_BASE_URL` 等），优先用向量余弦相似对段落做聚类；
   - 否则使用 TF‑IDF 风格的 bag‑of‑words 余弦相似：
     - 默认阈值为 0.6；
     - 可通过 `--cluster-threshold` 调整（数值越低，话题越粗）。

5. **输出模式**：
   - 若 `SMALL_LLM_*` 未配置或不可用 → 进入大纲模式；
   - 若 `SMALL_LLM_*` 已配置 → 对每个话题调用小模型生成小结，再合成为当日日记。

#### OPTIONS

```text
usage: clawutils logs daily [-h] [--date DATE] [--agent-dir AGENT_DIR]
                            [--verbose]
                            [--cluster-threshold CLUSTER_THRESHOLD]

options:
  -h, --help            show this help message and exit
  --date DATE           Target date (YYYY-MM-DD). If omitted, defaults to
                        yesterday (UTC)
  --agent-dir AGENT_DIR
                        Agent directory (default: ~/.openclaw/agents/main)
  --verbose             Verbose progress output
  --cluster-threshold CLUSTER_THRESHOLD
                        Override TF-IDF cosine threshold for clustering (0-1).
                        Lower = fewer, broader topics
```

#### OUTLINE MODE FORMAT

在未配置 small LLM 时，输出结构类似：

```text
Daily summary for 2026-03-02

## 1. [clawutils, daily, logs] (15 msgs | 42.3 min)
> 代表性的那一句话……

## 2. [Clawkb, maintenance, delete] (8 msgs | 21.5 min)
> Another representative sentence...
```

- 话题编号：`1.`, `2.`，方便引用；
- 关键词指纹：通过 `jieba.analyse.textrank`（可用时）提取关键词，或退化为简单的 BOW 统计算法；
- 统计信息：`(<N> msgs | <M> min)` 显示消息数量和时间跨度；
- 代表句：使用简单的“信噪比”指标（token 密度）从各行中挑选信息量最高的一句。

#### LLM MODE

当 SMALL_LLM_* 已配置且可访问时：

1. 为每个话题 Cluster 调用小模型生成结构化小结；
2. 再将所有小结合成为一篇“当日工作/实验日记”，采用第一人称视角并突出决策、结论与 TODO；
3. 若任一调用失败，则自动回退到大纲模式。

---

## SEE ALSO

- `README.md` / `README_zh.md` — 项目介绍与背景说明；
- OpenClaw 官方文档中关于 session logs 与 agents 的章节。
