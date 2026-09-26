r"""Text cleaner for Reddit evidence collection.

Preserves complete evidence without truncation while cleaning:
- HTML entities (&amp; -> &, &lt; -> <, etc.)
- Markdown formatting artifacts (Reddit <!-- SC_OFF --> comments, superscript \^, etc.)
- Excess whitespace normalization while preserving paragraph structures
- URLs and all substantive user description text
"""

from __future__ import annotations

import html
import re

# Markdown link regex: [anchor](url) -> anchor (url) or preserving text
_MD_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((https?://[^\)]+)\)")
# Reddit HTML comment wrappers
_HTML_COMMENTS = re.compile(r"<!--\s*SC_(?:OFF|ON)\s*-->")
# Excess blank lines (more than 2 consecutive newlines)
_CONSECUTIVE_NEWLINES = re.compile(r"\n{3,}")
# Trailing/leading spaces per line
_LINE_SPACES = re.compile(r"[ \t]+")


def clean_text(raw_text: str | None) -> str:
    """Clean Reddit text while preserving 100% of the evidence content.

    Args:
        raw_text: The original unedited text from the post or comment.

    Returns:
        Cleaned, normalized text string.
    """
    if not raw_text:
        return ""

    text = str(raw_text)

    # 1. Unescape HTML entities (e.g. &amp; -> &, &quot; -> ", &#x200B; -> zero-width space)
    # Run twice to handle double-escaped entities frequently found in RSS/Atom feeds (e.g. &amp;amp;)
    for _ in range(2):
        prev = text
        text = html.unescape(text)
        if text == prev:
            break

    # 2. Remove zero-width spaces and non-breaking spaces
    text = text.replace("\u200b", "").replace("\xa0", " ")

    # 3. Strip Reddit HTML comments
    text = _HTML_COMMENTS.sub("", text)

    # 4. Clean up Reddit markdown escapes (e.g. \* -> *, \^ -> ^, \_ -> _)
    text = re.sub(r"\\([*_`~^\\\[\]()])", r"\1", text)

    # 5. Normalize whitespace line by line
    lines = [_LINE_SPACES.sub(" ", line).strip() for line in text.splitlines()]
    normalized = "\n".join(lines)

    # 6. Collapse excessive blank lines (max 2 consecutive newlines for paragraph breaks)
    normalized = _CONSECUTIVE_NEWLINES.sub("\n\n", normalized)

    return normalized.strip()


def generate_preview(text: str | None, max_length: int = 150) -> str:
    """Generate a brief single-line preview for spreadsheet/table inspection.

    Does NOT replace full evidence; used strictly as a convenience field.

    Args:
        text: Text to preview.
        max_length: Maximum preview length.

    Returns:
        Single-line preview string with ellipsis if truncated.
    """
    if not text:
        return ""

    # Replace newlines with spaces for single-line display
    single_line = " ".join(text.split())
    if len(single_line) <= max_length:
        return single_line
    return single_line[:max_length].rstrip() + "..."
