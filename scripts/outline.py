#!/usr/bin/env python3
"""
outline.py

Prints code structure (defs, classes, exports) with line numbers and without
bodies, so agents can locate the right slice before reading any file content.

Examples:
  python outline.py app.py
  python outline.py src/ --max-files 40
"""

from __future__ import annotations

import argparse
import ast
import os
import re

from _agent_utils import iter_text_files, redact_text, truncate, truncate_line

# ponytail: Python uses ast (exact multi-line signatures); other languages use
# regex per language, not real parsers; upgrade to tree-sitter if precision matters
_PY = [r"^\s*(?:async\s+)?def\s+\w+", r"^\s*class\s+\w+"]
_JS = [
    r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?(?:async\s+)?function\b",
    r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+\w+",
    r"^\s*(?:export\s+)?(?:interface|enum)\s+\w+",
    r"^\s*(?:export\s+)?type\s+\w+\s*=",
    r"^\s*(?:export\s+)?(?:const|let|var)\s+\w+\s*=.*=>",
]
_GO = [r"^func\b", r"^type\s+\w+"]
_RS = [r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?(?:fn|struct|enum|trait|mod|impl)\b"]
_CSHARP_JAVA = [
    r"^\s*(?:\[[^\]]*\]\s*)?(?:@\w+\s+)?(?:public|private|protected|internal)\b",
    r"^\s*(?:static\s+|abstract\s+|sealed\s+|partial\s+)*(?:class|interface|struct|record|enum)\s+\w+",
]
_RUBY = [r"^\s*(?:def|class|module)\s"]
_PHP = [
    r"^\s*(?:abstract\s+|final\s+)?(?:public\s+|private\s+|protected\s+|static\s+)*function\s+\w+",
    r"^\s*(?:abstract\s+|final\s+)?(?:class|interface|trait|enum)\s+\w+",
]
_SHELL = [r"^\s*(?:function\s+)?[A-Za-z_][\w-]*\s*\(\)\s*\{", r"^\s*function\s+\w+"]
_GENERIC = [r"^\s*(?:async\s+)?(?:def|class|function|func|fn)\b"]

_LANGS = {
    (".py", ".pyi"): _PY,
    (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"): _JS,
    (".go",): _GO,
    (".rs",): _RS,
    (".cs", ".java", ".kt"): _CSHARP_JAVA,
    (".rb",): _RUBY,
    (".php",): _PHP,
    (".sh", ".bash", ".zsh"): _SHELL,
}

EXT_PATTERNS = {
    ext: [re.compile(p) for p in patterns]
    for exts, patterns in _LANGS.items()
    for ext in exts
}


def _py_ast_entries(source: str) -> list[tuple[int, int, str]]:
    entries: list[tuple[int, int, str]] = []

    def visit(node: ast.AST, depth: int) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                prefix = "async def" if isinstance(child, ast.AsyncFunctionDef) else "def"
                sig = f"{prefix} {child.name}({ast.unparse(child.args)})"
                if child.returns is not None:
                    sig += f" -> {ast.unparse(child.returns)}"
                entries.append((child.lineno, depth, sig + ":"))
                visit(child, depth + 1)
            elif isinstance(child, ast.ClassDef):
                bases = ", ".join(ast.unparse(base) for base in child.bases)
                sig = f"class {child.name}({bases}):" if bases else f"class {child.name}:"
                entries.append((child.lineno, depth, sig))
                visit(child, depth + 1)
            else:
                visit(child, depth)

    visit(ast.parse(source), 0)
    return entries


def outline_file(path: str, patterns, max_per_file: int, line_width: int) -> list[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            source = handle.read()
    except OSError as exc:
        return [f"== {path}", f"  Unreadable: {truncate_line(redact_text(str(exc)), line_width)}"]

    entries: list[tuple[int, int, str]] | None = None
    if os.path.splitext(path)[1].lower() in (".py", ".pyi"):
        try:
            entries = _py_ast_entries(source)
        except SyntaxError:
            entries = None
    if entries is None:
        entries = [
            (line_no, 0, text)
            for line_no, text in enumerate(source.splitlines(), 1)
            if any(pattern.search(text) for pattern in patterns)
        ]

    if not entries:
        return []
    lines = [
        f"  {line_no}: {'    ' * depth}{truncate_line(redact_text(text), line_width)}"
        for line_no, depth, text in entries[:max_per_file]
    ]
    if len(entries) > max_per_file:
        lines.append(f"  ...[{len(entries)} matches, rest omitted]")
    return [f"== {path} ({len(source.splitlines())} lines)", *lines]


def main() -> None:
    parser = argparse.ArgumentParser(description="Print code structure without bodies.")
    parser.add_argument("path", nargs="?", default=".", help="File or directory")
    parser.add_argument("--max-files", type=int, default=40)
    parser.add_argument("--max-per-file", type=int, default=200)
    parser.add_argument("--line-width", type=int, default=200)
    parser.add_argument("--max-chars", "--max-output-chars", dest="max_chars", type=int, default=12000)
    args = parser.parse_args()

    base = os.path.abspath(args.path)
    output = [f"Outline: {base}"]

    if os.path.isfile(base):
        ext = os.path.splitext(base)[1].lower()
        patterns = EXT_PATTERNS.get(ext, [re.compile(p) for p in _GENERIC])
        section = outline_file(base, patterns, args.max_per_file, args.line_width)
        output.extend(section or [f"== {base}", "  (no structure matched)"])
    else:
        shown = 0
        unmatched = 0
        for path in iter_text_files([base], allowed_exts=set(EXT_PATTERNS)):
            if shown >= args.max_files:
                output.append(f"...[--max-files {args.max_files} reached, rest omitted]")
                break
            rel = os.path.relpath(path, base)
            section = outline_file(path, EXT_PATTERNS[os.path.splitext(path)[1].lower()], args.max_per_file, args.line_width)
            if not section:
                unmatched += 1
                continue
            section[0] = section[0].replace(path, rel, 1)
            output.append("")
            output.extend(section)
            shown += 1
        if shown == 0:
            output.append("No code files with recognizable structure found.")
        if unmatched:
            output.append(f"\nFiles with no outline matches: {unmatched}")

    print(truncate("\n".join(output), args.max_chars))


if __name__ == "__main__":
    main()
