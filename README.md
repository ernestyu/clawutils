# clawutils

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

> Status: bootstrap phase. Initial focus: robust web scraping pipeline
> that outputs normalized markdown suitable for Clawkb.

---

## License

MIT © Ernest Yu
