#!/usr/bin/env python3
"""Merge toolkit content into an existing agents md without touching foreign content.

The toolkit content is wrapped in a managed section:
  <!-- agents-toolkit:start --> ... <!-- agents-toolkit:end -->

If DEST already has that section, only the section is replaced; everything
else (plugin blocks, MCP/skill notes, hand edits — any format) is preserved
verbatim in place.

If DEST has no managed section yet (legacy install), the output is the new
wrapped content plus any recognized plugin marker blocks from DEST:
  <!-- name:start --> ... <!-- name:end -->
  <!-- name --> ... <!-- name -->   (same comment opens and closes)

Usage: merge_md_blocks.py SRC DEST [OUT]
Writes merged content to OUT, or stdout if OUT is omitted.
"""
import re
import sys

MANAGED = "agents-toolkit"
START = f"<!-- {MANAGED}:start -->"
END = f"<!-- {MANAGED}:end -->"
MANAGED_RE = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)

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


def wrap(text):
    return START + "\n" + text.strip("\n") + "\n" + END


def merge(new_text, old_text):
    wrapped = wrap(new_text)
    if MANAGED_RE.search(old_text):
        return MANAGED_RE.sub(lambda _: wrapped, old_text, count=1)
    # Legacy dest without a managed section: adopt it, keeping plugin blocks.
    new_names = find_blocks(new_text)
    kept = [
        block
        for name, block in find_blocks(old_text).items()
        if name != MANAGED and name not in new_names
    ]
    if not kept:
        return wrapped + "\n"
    return wrapped + "\n\n" + "\n\n".join(kept) + "\n"


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
