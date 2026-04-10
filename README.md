# DocuFlow Enterprise
**Word Processing Automation Module**  ·  PyQt6  ·  Cross-platform

---

## Setup

```bash
# Python 3.11+ required — no extra dependencies beyond the list below
pip install -r requirements.txt

python main.py
```

## Features

| Feature | Description |
|---|---|
| Align Left / Center / Right | Real Qt paragraph alignment — not space-padding |
| Remove Extra Spaces | Collapse spaces, trim lines |
| Add Separator at cursor | Inserts the horizontal rule **at the cursor line**, not at the bottom |
| UPPER / lower / Title / Sentence | Text case transforms |
| Find & Replace | Case-sensitive or insensitive |
| Import .docx | Load text from Word document |
| Import text / file (≤ 500 MB) | Load `.txt`, `.md`, `.csv`, `.html`, `.json`, `.xml`, `.log`, `.dfc` |
| Export .docx | Save to Word / Microsoft 365 |
| Export Compressed (.dfc) | Byte-level zlib compression — **not** a zip archive; preserves full fidelity |
| Sessions | Named workspaces |
| Backups | Save snapshots, preview & restore |
| Activity Log | Full history of all actions |
| Ctrl+Z | Undo last transformation |
| Scroll / cursor preserved | Transforms no longer jump the view back to the top |
| Responsive sidebar | Collapses to icon-strip on narrow windows (< 900 px) |

## Compression format (.dfc)

DocuFlow Compressed files use raw zlib deflate at level 9.
They are **not** zip archives — they cannot be opened with an archive tool.
Re-import them with "⬆ Text/File" and DocuFlow detects the magic header automatically.

Typical compression ratios:

| Content type | Reduction |
|---|---|
| Plain prose | 50 – 65 % |
| Repetitive / structured text | 70 – 85 % |
| Already-compressed content | 0 – 5 % |

## Package to executable

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "DocuFlow Enterprise" main.py
```

## Project layout

```
docuflow/
├── main.py
├── requirements.txt
├── core/
│   ├── db.py          # SQLite (sessions, backups, logs)
│   ├── processor.py   # Text transformations + compression helpers
│   └── docx_io.py     # Word import/export + text-file import + .dfc format
└── ui/
    ├── app.py         # All UI components (fixed + responsive)
    └── styles/
        └── theme.qss  # Enterprise green & white theme
```

## Changelog

### v1.1
- **Fix:** Center / Right align now use `QTextBlockFormat` — visual alignment is real, not space-padding
- **Fix:** "Add Separator" inserts at the **cursor position**, not always at the bottom
- **Fix:** All transforms preserve scroll position and cursor — no more jump-to-top
- **New:** Import any text file up to 500 MB (txt, md, csv, html, json, xml, log, dfc)
- **New:** Compressed export (.dfc) — byte-level zlib, ~50-85 % smaller than raw text
- **New:** Responsive sidebar — collapses to icon-strip below 900 px window width