# clawutils

一个围绕 OpenClaw 的小型工具箱，用来收集“顺手的小工具”：

- 网页抓取与内容规范化
- 文本增量补丁（在大文件中只改一小段）
- 知识库（Clawkb）相关的辅助脚本
- 文件系统维护（清理、重命名等）

目标是同时提供：

- 可通过 `import clawutils` 使用的 Python 库；
- 一个统一的 CLI 入口（例如 `clawutils web scrape <URL>`），方便人类和 Agent 在一个命名空间里发现这些工具。

> 当前状态：bootstrap 阶段，已经提供：
> - 一个基于 Playwright + Readability 的网页抓取器；
> - 一个安全的文本补丁工具，用于在文件头/尾或特定标记后插入文本。

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
- `clawutils text ...`  – 与文本相关的工具（补丁、转换）。

可以继续查看子命令帮助：

```bash
clawutils web --help
clawutils web scrape --help
clawutils text --help
clawutils text patch --help
```

---

## 3. 网页抓取 (`clawutils web scrape`)

将任意网页转换为规范化 Markdown，适合作为 Clawkb 等知识库的输入。

### 3.1 基本用法

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

### 4.1 模式

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

## 5. 与 OpenClaw Skills 的集成

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
