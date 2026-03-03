---
name: text-patch
description: Perform precision "surgical" edits on text files (prepend, append, or insert after markers). Use this instead of whole-file overwrites to save tokens and prevent data loss, especially for metadata tags or reading notes.
---

# Skill: Text Patch

This skill provides an incremental editing interface for local text files.

## Available Modes

### 1. Prepend (Head Insertion)
Add tags or IDs to the very beginning of a file.
```bash
PYTHONPATH=src /opt/venv/bin/python -m clawutils.cli text patch --file <path> --mode prepend --text "Your Text"
```

### 2. Append (Tail Insertion)
Append summaries or notes to the end of a file.
```bash
PYTHONPATH=src /opt/venv/bin/python -m clawutils.cli text patch --file <path> --mode append --text "Your Text"
```

### 3. After Marker (Contextual Insertion)
Insert text immediately after a specific line (e.g., after "--- MARKDOWN ---").
```bash
PYTHONPATH=src /opt/venv/bin/python -m clawutils.cli text patch --file <path> --mode after --marker "<Marker>" --text "Inserted Content"
```

## Safety Rule
Always use this for small edits to large files to ensure the integrity of the original content.
