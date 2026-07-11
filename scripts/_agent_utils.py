#!/usr/bin/env python3
"""Shared helpers for token-saving agent utilities."""

from __future__ import annotations

import os
import re
import sys
from collections import deque
from contextlib import contextmanager, nullcontext
from typing import Iterable, Iterator, Optional

DEFAULT_MAX_CHARS = 12000
DEFAULT_LINE_WIDTH = 240

DEFAULT_IGNORE_DIRS = {
    "node_modules", ".venv", "venv", "env", "dist", "build", "coverage",
    ".next", ".nuxt", "target", "bin", "obj", ".git", ".cache",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "archive",
    "vendor", "logs/archive", "tmp", "temp",
}

DEFAULT_IGNORE_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip",
    ".tar", ".gz", ".bz2", ".7z", ".rar", ".exe", ".dll", ".so",
    ".dylib", ".bin", ".db", ".sqlite", ".sqlite3", ".parquet", ".pyc",
    ".pyo", ".class", ".o", ".lock",
}

SENSITIVE_KEY_PARTS = (
    "password", "passwd", "pwd", "secret", "token", "api_key", "apikey",
    "authorization", "auth", "cookie", "session", "private", "credential",
    "access_key", "refresh_token", "client_secret", "private_key",
)

SECRET_LINE_PATTERNS = (
    (
        re.compile(
            r"(?i)\b([A-Z0-9_.-]*(?:password|passwd|pwd|secret|token|api[_-]?key|authorization|cookie|session|credential|private[_-]?key)[A-Z0-9_.-]*\s*[:=]\s*)(.+)"
        ),
        lambda match: match.group(1) + "****",
    ),
    (
        re.compile(r"(?i)\b((?:bearer|basic)\s+)([A-Za-z0-9._~+/=-]{12,})"),
        lambda match: match.group(1) + "****",
    ),
    (
        re.compile(r"(?i)(://[^:\s/@]+:)([^@\s/]+)(@)"),
        lambda match: match.group(1) + "****" + match.group(3),
    ),
)

PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)


def truncate(text: object, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    value = str(text)
    marker = "\n...[TRUNCATED]"
    if max_chars <= 0:
        return ""
    if len(value) > max_chars:
        if max_chars <= len(marker):
            return value[:max_chars]
        return value[: max_chars - len(marker)] + marker
    return value


def truncate_line(line: object, length: int = DEFAULT_LINE_WIDTH) -> str:
    value = str(line)
    return value if len(value) <= length else value[:length] + "..."


def is_sensitive_key(key: object) -> bool:
    lowered = str(key).lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def redact_text(text: object) -> str:
    value = str(text)
    value = PRIVATE_KEY_RE.sub("-----BEGIN PRIVATE KEY-----\n****\n-----END PRIVATE KEY-----", value)
    for pattern, replacement in SECRET_LINE_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def format_snippet_line(
    line_no: int,
    line: str,
    *,
    line_width: int = DEFAULT_LINE_WIDTH,
    match: bool = False,
    line_numbers: bool = True,
    show_secrets: bool = False,
) -> str:
    text = line.rstrip("\n")
    if not show_secrets:
        text = redact_text(text)
    text = truncate_line(text, line_width)
    if not line_numbers:
        return text
    marker = ">>" if match else "  "
    return f"{marker} {line_no}: {text}"


def collect_match_snippets(
    numbered_lines: Iterable[tuple[int, str]],
    matches_line,
    *,
    context: int = 0,
    limit: int = 50,
    line_width: int = DEFAULT_LINE_WIDTH,
    line_numbers: bool = True,
    show_secrets: bool = False,
) -> list[list[str]]:
    if limit <= 0:
        return []

    snippets: list[list[str]] = []
    previous: deque[tuple[int, str]] = deque(maxlen=context)
    after_remaining = 0
    active: list[str] = []

    for line_no, line in numbered_lines:
        if after_remaining > 0:
            is_match = matches_line(line)
            active.append(
                format_snippet_line(
                    line_no,
                    line,
                    line_width=line_width,
                    match=is_match,
                    line_numbers=line_numbers,
                    show_secrets=show_secrets,
                )
            )
            after_remaining = context if is_match else after_remaining - 1
            if after_remaining == 0:
                snippets.append(active)
                active = []
                if len(snippets) >= limit:
                    break
            previous.append((line_no, line))
            continue

        if matches_line(line):
            active = [
                format_snippet_line(
                    prev_no,
                    prev_line,
                    line_width=line_width,
                    line_numbers=line_numbers,
                    show_secrets=show_secrets,
                )
                for prev_no, prev_line in previous
            ]
            active.append(
                format_snippet_line(
                    line_no,
                    line,
                    line_width=line_width,
                    match=True,
                    line_numbers=line_numbers,
                    show_secrets=show_secrets,
                )
            )
            after_remaining = context
            if after_remaining == 0:
                snippets.append(active)
                active = []
                if len(snippets) >= limit:
                    break
            previous.clear()
        else:
            previous.append((line_no, line))

    if active and len(snippets) < limit:
        snippets.append(active)
    return snippets


@contextmanager
def open_text_source(path: str):
    if path == "-":
        with nullcontext(sys.stdin) as source:
            yield source
        return
    with open(path, "r", encoding="utf-8", errors="ignore") as source:
        yield source


def numbered_lines(lines: Iterable[str]) -> Iterator[tuple[int, str]]:
    for idx, line in enumerate(lines, 1):
        yield idx, line


def compact_error(path: str, exc: BaseException) -> str:
    return truncate_line(redact_text(f"{path}: {exc}"), DEFAULT_LINE_WIDTH)


def redact_obj(value: object, max_string: int = 120) -> object:
    if isinstance(value, dict):
        return {
            key: "****" if is_sensitive_key(key) else redact_obj(item, max_string)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_obj(item, max_string) for item in value]
    if isinstance(value, str):
        return truncate_line(redact_text(value), max_string)
    return value


def is_binary_file(path: str, sample_size: int = 4096) -> bool:
    try:
        with open(path, "rb") as handle:
            sample = handle.read(sample_size)
    except OSError:
        return True
    return b"\0" in sample


def normalize_exts(extensions: Optional[str]) -> Optional[set[str]]:
    if not extensions:
        return None
    normalized = set()
    for ext in extensions.split(","):
        item = ext.strip().lower()
        if not item:
            continue
        normalized.add(item if item.startswith(".") else f".{item}")
    return normalized


def iter_text_files(
    paths: Iterable[str],
    *,
    allowed_exts: Optional[set[str]] = None,
    max_file_mb: float = 10.0,
    include_hidden: bool = False,
    ignore_dirs: Optional[set[str]] = None,
    ignore_exts: Optional[set[str]] = None,
) -> Iterator[str]:
    ignored_dirs = ignore_dirs or DEFAULT_IGNORE_DIRS
    ignored_exts = ignore_exts or DEFAULT_IGNORE_EXTS
    max_bytes = max_file_mb * 1024 * 1024

    for path in paths:
        absolute = os.path.abspath(path)
        if os.path.isfile(absolute):
            if _is_text_candidate(absolute, allowed_exts, max_bytes, include_hidden, ignored_exts):
                yield absolute
            continue
        if not os.path.isdir(absolute):
            continue
        for root, dirs, files in os.walk(absolute):
            dirs[:] = [
                d for d in dirs
                if (include_hidden or not d.startswith("."))
                and d not in ignored_dirs
                and os.path.join(os.path.relpath(root, absolute), d).strip("./") not in ignored_dirs
            ]
            for filename in files:
                full_path = os.path.join(root, filename)
                if _is_text_candidate(full_path, allowed_exts, max_bytes, include_hidden, ignored_exts):
                    yield full_path


def _is_text_candidate(
    path: str,
    allowed_exts: Optional[set[str]],
    max_bytes: float,
    include_hidden: bool,
    ignored_exts: set[str],
) -> bool:
    name = os.path.basename(path)
    if not include_hidden and name.startswith("."):
        return False
    ext = os.path.splitext(name)[1].lower()
    if allowed_exts and ext not in allowed_exts:
        return False
    if ext in ignored_exts:
        return False
    try:
        if os.path.getsize(path) > max_bytes:
            return False
    except OSError:
        return False
    return not is_binary_file(path)
