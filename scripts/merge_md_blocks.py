#!/usr/bin/env python3
"""Merge plugin-managed marker blocks from an existing agents md into new content.

Blocks recognized in the existing destination file:
  <!-- name:start --> ... <!-- name:end -->
  <!-- name --> ... <!-- name -->   (same comment opens and closes)

Any such block present in DEST but absent (by name) from SRC is appended to
the merged output, so reinstalling AGENTS.md never wipes what other plugins
(context7, codebase-memory-mcp, ...) injected.

Usage: merge_md_blocks.py SRC DEST [OUT]
Writes merged content to OUT, or stdout if OUT is omitted.
"""
import re
import sys

BLOCK_RE = re.compile(
    r"(?:<!--\s*([\w.-]+):start\s*-->.*?<!--\s*\1:end\s*-->)"
    r"|(?:<!--\s*([\w.-]+)\s*-->.*?<!--\s*\2\s*-->)",
    re.DOTALL,
)


def find_blocks(text):
    blocks = {}
    for match in BLOCK_RE.finditer(text):
        name = match.group(1) or match.group(2)
        blocks.setdefault(name, match.group(0))
    return blocks


def merge(new_text, old_text):
    new_names = find_blocks(new_text)
    kept = [
        block
        for name, block in find_blocks(old_text).items()
        if name not in new_names
    ]
    if not kept:
        return new_text
    return new_text.rstrip("\n") + "\n\n" + "\n\n".join(kept) + "\n"


def main(argv):
    if len(argv) < 3 or len(argv) > 4:
        print((__doc__ or "").strip(), file=sys.stderr)
        return 2
    src, dest = argv[1], argv[2]
    with open(src, encoding="utf-8") as fh:
        new_text = fh.read()
    try:
        with open(dest, encoding="utf-8") as fh:
            old_text = fh.read()
    except OSError:
        old_text = ""
    merged = merge(new_text, old_text)
    if len(argv) == 4:
        with open(argv[3], "w", encoding="utf-8") as fh:
            fh.write(merged)
    else:
        sys.stdout.write(merged)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
