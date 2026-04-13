"""DocuFlow — Text processing."""
import re

SEPARATOR = "─" * 64


# ── Alignment ─────────────────────────────────────────────────────────────────
# Visual alignment is handled by Qt block-format in app.py.
# These functions only strip leading/trailing whitespace so the text is clean.

def align_left(text):
    return "\n".join(line.strip() for line in text.split("\n"))

def align_center(text):
    return "\n".join(line.strip() for line in text.split("\n"))

def align_right(text):
    return "\n".join(line.strip() for line in text.split("\n"))


# ── Clean ─────────────────────────────────────────────────────────────────────

PAGE_BREAK_MARKER = "◀━━━━━━━━━━━━━━━━━━━  PAGE BREAK  ━━━━━━━━━━━━━━━━━━━▶"

def remove_spaces(text):
    """
    Collapse spaces and trim lines.
    Any run of 2+ consecutive blank lines is treated as a page-break and
    replaced with PAGE_BREAK_MARKER so the transition is still visible.
    """
    lines = text.split("\n")
    out = []
    blanks = 0
    for line in lines:
        line = re.sub(r"[ \t]+", " ", line).strip()
        if not line:
            blanks += 1
        else:
            if blanks >= 2:
                # Multiple blank lines → page-break marker
                out.append(PAGE_BREAK_MARKER)
            elif blanks == 1:
                out.append("")
            blanks = 0
            out.append(line)
    # flush trailing blanks
    if blanks >= 2:
        out.append(PAGE_BREAK_MARKER)
    return "\n".join(out)

def add_separator(text):
    """Append separator at end — fallback. See add_separator_at()."""
    return text.rstrip("\n") + "\n" + SEPARATOR

def add_separator_at(text, line_index):
    """Insert a separator AFTER the given 0-based line index."""
    lines = text.split("\n")
    insert_at = min(line_index + 1, len(lines))
    lines.insert(insert_at, SEPARATOR)
    return "\n".join(lines)

def remove_separator(text):
    return "\n".join(l for l in text.split("\n") if l.strip() != SEPARATOR)


# ── Case transforms ───────────────────────────────────────────────────────────

def to_upper(text):    return text.upper()
def to_lower(text):    return text.lower()
def to_title(text):    return text.title()
def to_sentence(text):
    def cap(s): return s[:1].upper() + s[1:] if s else s
    return " ".join(cap(s) for s in re.split(r"(?<=[.!?])\s+", text))


# ── Find & Replace ────────────────────────────────────────────────────────────

def find_replace(text, find, replace, case=False):
    if not find:
        return text
    flags = 0 if case else re.IGNORECASE
    return re.sub(re.escape(find), replace, text, flags=flags)


# ── Stats ─────────────────────────────────────────────────────────────────────

def stats(text):
    words = len(text.split()) if text.strip() else 0
    return {"words": words, "chars": len(text), "lines": len(text.split("\n"))}