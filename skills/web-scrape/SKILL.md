---
name: web-scrape
description: Scrape any web page and extract high-quality, normalized Markdown. Supports a "GitHub Fast Path" for near-instant README retrieval. Use when the user provides a URL and asks for content, summaries, or analysis.
---

# Skill: Web Scrape

This skill uses the `clawutils` engine to transform chaotic web pages into clean, readable Markdown.

## Core Command
Execute via the Python CLI:
```bash
PYTHONPATH=src /opt/venv/bin/python -m clawutils.cli web scrape <URL>
```

## Features
- **Readability Engine**: Automatically strips ads, sidebars, and navigation noise.
- **GitHub Fast Path**: Detects GitHub URLs and fetches the raw README directly, bypassing browser rendering for speed and cost-efficiency.
- **Metadata Output**: Returns a standard header with Title, Author, and FinalURL.

## Typical Usage
When a user says: "What's in this link: https://example.com", call this tool first to get the context.
