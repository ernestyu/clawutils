# CLI Help Spec (generated from argparse)

## clawutils --help
usage: clawutils [-h] {web,text,logs} ...

CLI utilities around OpenClaw (web, text, kb, fs)

positional arguments:
  {web,text,logs}
    web            Web-related utilities (scrapers, cleaners)
    text           Text utilities (patch, transform)
    logs           Logs/session utilities (daily summaries, inspections)

options:
  -h, --help       show this help message and exit


## clawutils web --help
usage: clawutils web [-h] {scrape} ...

positional arguments:
  {scrape}
    scrape    Scrape a web page and print normalized markdown

options:
  -h, --help  show this help message and exit


## clawutils web scrape --help
usage: clawutils web scrape [-h] url

positional arguments:
  url         URL to scrape

options:
  -h, --help  show this help message and exit


## clawutils text --help
usage: clawutils text [-h] {patch} ...

positional arguments:
  {patch}
    patch     Patch a text file (prepend/append/after marker)

options:
  -h, --help  show this help message and exit


## clawutils text patch --help
usage: clawutils text patch [-h] --file FILE --text TEXT --mode
                            {prepend,append,after} [--marker MARKER]

options:
  -h, --help            show this help message and exit
  --file FILE           Target file path
  --text TEXT           Text to insert
  --mode {prepend,append,after}
                        Patch mode
  --marker MARKER       Marker for 'after' mode (required when --mode=after)


## clawutils logs --help
usage: clawutils logs [-h] {daily} ...

positional arguments:
  {daily}
    daily     Summarize a day's OpenClaw session logs into a diary-style
              outline

options:
  -h, --help  show this help message and exit


## clawutils logs daily --help
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
