# clawutils

一个围绕 OpenClaw 的小型命令行工具箱，主要做三件事：

- **网页抓取 → 规范化 Markdown**，方便丢给 Clawkb 等知识库；
- **文本安全补丁 → 增量修改已有文件**，而不是整篇重写；
- **按天日志摘要 → 把 OpenClaw 的聊天记录整理成大纲。**

你既可以：

- 通过 `import clawutils` 当作 Python 库使用；
- 也可以通过统一的 CLI 入口（例如 `clawutils web scrape <URL>`）直接在命令行或 Agent 里调用。

> 当前状态：已可在日常环境中使用，目前包含：
> - 基于 Playwright + Readability 的网页抓取器（`clawutils web scrape`）；
> - 安全的文本补丁工具（`clawutils text patch`），用于在文件头/尾或特定标记后插入文本；
> - OpenClaw 会话“按天日志总结”工具（`clawutils logs daily`）。

---

## 1. 安装与环境

clawutils 主要面向 OpenClaw 运行环境（Python + Node.js），也可以在类似的本地环境中使用。

### 1.1 Python

- 需要 Python 3.10+

开发环境建议使用 editable 安装：

```bash
cd clawutils
python -m pip install -e .
```

### 1.2 Node.js 与 npm 依赖

网页抓取部分用 Node.js 实现，依赖以下 npm 包：

- `playwright`
- `@mozilla/readability`
- `jsdom`
- `turndown`

在运行 `clawutils` 的环境下安装：

```bash
npm install playwright @mozilla/readability jsdom turndown
```

> 在 OpenClaw 官方容器中，Node.js 已经存在；只需安装上述 npm 依赖即可。

---

## 2. CLI 总览

安装完成后，可以通过：

```bash
clawutils --help
```

查看顶层帮助。

目前支持的顶层子命令：

- `clawutils web ...`   – 与网页相关的工具（抓取、清洗）；
- `clawutils text ...`  – 与文本相关的工具（补丁、转换）；
- `clawutils logs ...`  – 与日志相关的工具（按天摘要、检查等）。

可以继续查看子命令帮助：

```bash
clawutils web --help
clawutils web scrape --help
clawutils text --help
clawutils text patch --help
clawutils logs --help
clawutils logs daily --help
```

---

## 3. 网页抓取 (`clawutils web scrape`)

将任意网页转换为规范化 Markdown，适合作为 Clawkb 等知识库的输入。

### 3.1 快速上手

把网页保存成 Markdown 文件：

```bash
clawutils web scrape "https://example.com/article" > article.md
```

和 Clawkb 搭配使用的典型方式：

```bash
# 在 Clawkb 仓库目录
export CLAWKB_SCRAPE_CMD="clawutils web scrape {url}"
python -m clawkb ingest --url "https://example.com/article"
```

下面是更详细的说明。

### 3.2 基本用法

```bash
clawutils web scrape "https://example.com/article" > out.md
```

输出格式：

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

- `METADATA` 区块：包含标题、作者、最终 URL、提取模式等信息；
- `MARKDOWN` 区块：已经清洗过的正文 markdown。

### 3.2 特性

- **Readability 提取**：优先使用 `@mozilla/readability` 查找主体内容，去掉导航、广告等噪音；
- **多级回退**：当 Readability 失败时，依次尝试一系列容器选择器（`#js_content`、`article`、`main` 等），最后回退到 `document.body.innerText`；
- **GitHub 快速路径**：对于 `github.com` 链接，优先尝试直接获取原始 README（`README.md`、`README_zh.md` 等）而不启动浏览器，提高速度并降低资源消耗；
- **调试信息**：当内容过短或不可靠时，会输出调试信息，并尝试在 `/tmp/scrape-fail-<ts>.png` 保存截图，方便排查问题。

### 3.3 与 Clawkb 集成（`CLAWKB_SCRAPE_CMD`）

clawutils 设计为 Clawkb 的默认抓取后端之一。

在 Clawkb 项目根目录下的 `.env` 中可以设置：

```env
CLAWKB_SCRAPE_CMD="clawutils web scrape {url}"
```

这样在执行：

```bash
python -m clawkb ingest --url "https://example.com/article"
```

时，Clawkb 会：

1. 调用 `clawutils web scrape <URL>`；
2. 解析 `METADATA` / `MARKDOWN`；
3. 写入 SQLite + Markdown 文件并同步索引。

你也可以在单次命令中显式覆盖：

```bash
python -m clawkb ingest \
  --url "https://example.com/article" \
  --scrape-cmd "clawutils web scrape {url}"
```

---

## 4. 文本补丁 (`clawutils text patch`)

在大文件中安全地做小范围修改，而不是整篇重写。

### 4.1 快速上手

在文件结尾追加一行：

```bash
clawutils text patch --file README.md --mode append --text "\nUpdated by clawutils.\n"
```

在某个标记行之后插入一段内容：

```bash
clawutils text patch \
  --file THESIS_PLAN.md \
  --mode after \
  --marker "## 3. Planned workstreams" \
  --text "\n- [ ] TODO: add more experiments.\n"
```

下面是具体模式说明。

### 4.2 模式

支持三种模式：

- `prepend`：在文件头插入；
- `append`：在文件尾追加；
- `after`：在某个标记行之后插入。

### 4.2 使用示例

**头部插入：**

```bash
clawutils text patch \
  --file README.md \
  --mode prepend \
  --text "# My Project"
```

**末尾追加：**

```bash
clawutils text patch \
  --file README.md \
  --mode append \
  --text "\n---\nUpdated via clawutils text patch"
```

**在标记后插入：**

```bash
clawutils text patch \
  --file README.md \
  --mode after \
  --marker "### Changelog" \
  --text "- Added clawutils text patch utility"
```

安全行为：

- 目标文件不存在时：输出错误并以非 0 状态退出；
- `--mode=after` 且找不到 marker 时：输出错误并以非 0 状态退出。

这一工具尤其适合在 Agent 管理的大文件中做“局部改动”：
Agent 只需生成要插入的那段文本，真正的文件定位与修改由 `clawutils` 完成。

---

## 5. 日志按天总结器 (`clawutils logs daily`)

`clawutils logs daily` 用于将某一天的 OpenClaw 会话日志整理成结构化大纲或“日记式”总结。

> 当前实现主要针对主 Agent 的 JSONL 会话日志目录：
> `~/.openclaw/agents/main/sessions`。

### 5.1 快速上手

对“昨天”的日志做摘要：

```bash
# 总结（UTC 意义上的）昨天
clawutils logs daily
```

显式指定日期和 agent 目录：

```bash
clawutils logs daily --date 2026-03-02

# 使用自定义 agent 目录并打开详细输出
clawutils logs daily --date 2026-03-02 \
  --agent-dir ~/.openclaw/agents/main \
  --verbose
```

输出是一份按主题聚类的大纲（主题、关键词、代表性语句），可以当“日记索引”，也可以作为后续工具的输入。

### 5.2 基本用法

关键参数：

- `--date YYYY-MM-DD` – 目标日期（UTC），不指定时默认是“昨天”；
- `--agent-dir PATH` – Agent 目录，默认 `~/.openclaw/agents/main`；
- `--verbose` – 打印详细的阶段进度（读取、过滤、分段、聚类等）；
- `--cluster-threshold FLOAT` – 覆盖 TF‑IDF 聚类的余弦阈值（0–1）。
  - 数值越低：越容易合并为少量粗主题；
  - 数值越高：主题保留得更细。

### 5.2 行为与设计

1. **会话文件扫描**
   - 扫描指定 `agent-dir` 下的 `sessions/*.jsonl`；
   - 按文件修改时间逆序处理（最新的先处理）；
   - 利用 `mtime` 做短路：当某个文件的修改时间早于目标日期起点时，停止继续扫描更旧文件。

2. **消息提取与清洗**
   - 只保留 `type == "message"` 且 `role` 在 `{user, assistant}` 的记录；
   - 将 `content[]` 中的 `type == "text"` 条目展平成纯文本；
   - 剥离明显的系统注入元数据块：
     - `Conversation info (untrusted metadata)`
     - `Forwarded message context (untrusted metadata)`
     以及它们后续的 JSON 代码块；
   - 过滤短小的 shell/log 噪音（如包含 `pip`、`npm`、`git`、`ls`、`cd`、`docker`、`openclaw` 且长度很短的命令行输出）。

3. **分段 (segment)**
   - 按时间顺序累积消息，形成文本段落；
   - 当加入下一条消息会导致段落长度超过约 2000 字符时，开启新段；
   - 这样既避免极小片段，又避免单段过大；真正的话题归类交给后续聚类完成。

4. **聚类（话题）**
   - 若配置了向量服务（`EMBEDDING_*` 环境变量）且可用，则优先采用向量余弦相似做聚类；
   - 否则采用 TF‑IDF 风格的 bag‑of‑words 余弦相似作为降级路径：
     - 默认阈值为 `0.6`；
     - 可以通过 `--cluster-threshold` 覆盖；
   - 目标是把语义相近的段落聚到一起，即使它们在时间上彼此相隔较远。

5. **总结模式**
   - 若配置了小模型网关（`SMALL_LLM_*` 环境变量）且 `httpx` 可用：
     - 为每个话题 Cluster 调用小模型生成结构化小结；
     - 再让小模型基于这些小结生成一篇完整的“当日日记”；
   - 否则启用确定性的 **大纲模式**：
     - 每个话题输出关键词、统计信息和一行代表性句子。

### 5.3 大纲模式（无 LLM）输出结构

在未配置 small LLM 时，输出大致类似：

```text
Daily summary for 2026-03-02

## 1. [clawutils, daily, logs] (15 msgs | 42.3 min)
> 代表性的那一句话……

## 2. [Clawkb, maintenance, delete] (8 msgs | 21.5 min)
> Another representative sentence...
```

具体说明：

- **话题编号**：使用 `1.`、`2.` 等递增编号，方便在对话中直接引用“第 3 个话题”；
- **关键词指纹**：每个话题通过 `jieba.analyse.textrank`（如可用）提取若干关键词（并有简单的 BOW 降级方案），一眼即可看出该话题的核心内容；
- **紧凑统计**：`(<N> msgs | <M> min)` 展示该话题的消息数量和时间跨度；
- **代表性句子**：每个话题选取一行 `> ...` 作为引用，基于粗略的“信噪比”（token 密度）选择信息量较高的句子，而不是盲目使用第一条消息。

该模式不依赖任何外部 LLM，在离线或“无 API” 环境下也能为人工/Agent 提供可用的语义索引。

### 5.4 小模型加持的“日记模式”

当 `SMALL_LLM_BASE_URL`、`SMALL_LLM_MODEL`、`SMALL_LLM_API_KEY` 均已配置且可访问时：

1. 对每个话题 Cluster 调用小模型生成简短的结构化小结；
2. 再用同一个小模型将这些小结整合成一篇当日日记：
   - 采用第一人称（“我”）视角；
   - 按主题/事项分段；
   - 重点突出当天的决策、结论和 TODO。

如果任何一步 LLM 调用失败，则自动回退到上面的纯大纲模式。

---

## 6. 与 OpenClaw Skills 的集成

clawutils 自带两份示例 Skill 定义，位于 `skills/` 目录：

- `skills/web-scrape/SKILL.md`
- `skills/text-patch/SKILL.md`

如果你希望在自己的 OpenClaw 工作空间中让 Agent 直接调用这些工具，可以通过软链接方式接入：

```bash
# 在你的主 OpenClaw 工作空间中
cd /home/node/.openclaw/workspace

ln -s ./clawutils/skills/web-scrape ./skills/web-scrape
ln -s ./clawutils/skills/text-patch ./skills/text-patch
```

Skill 文件中给出了典型调用方式，例如：

```bash
PYTHONPATH=src /opt/venv/bin/python -m clawutils.cli web scrape <URL>
PYTHONPATH=src /opt/venv/bin/python -m clawutils.cli text patch [...]
```

---

## License

MIT © Ernest Yu
