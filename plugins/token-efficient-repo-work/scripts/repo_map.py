#!/usr/bin/env python3
"""
repo_map.py

Creates a compact repository map so Codex can understand the structure
without reading full files or huge directory trees.

Examples:
  python repo_map.py .
  python repo_map.py /path/to/repo --max-depth 4
"""

import argparse
import fnmatch
import os
import sys
from collections import defaultdict

from _agent_utils import DEFAULT_IGNORE_DIRS, DEFAULT_IGNORE_EXTS, is_binary_file, redact_text, truncate

STACK_INDICATORS = {
    'Python': ['pyproject.toml', 'requirements.txt', 'setup.py', 'setup.cfg', 'Pipfile', 'poetry.lock', 'manage.py', 'main.py', 'app.py'],
    'JavaScript/TypeScript': ['package.json', 'tsconfig.json', 'vite.config.ts', 'vite.config.js', 'next.config.js', 'nuxt.config.js', 'src/main.ts', 'src/main.tsx', 'src/index.ts', 'src/index.tsx'],
    '.NET': ['*.sln', '*.csproj', 'Program.cs', 'Startup.cs', 'appsettings.json'],
    'Docker/Infra': ['Dockerfile', 'docker-compose.yml', 'docker-compose.yaml', 'compose.yml', 'compose.yaml', 'kubernetes', 'helm', '.github/workflows'],
    'DB/ORM': ['prisma/schema.prisma', 'migrations', 'alembic', 'sequelize', 'typeorm']
}

EXTENSION_STACKS = {
    '.py': 'Python',
    '.js': 'JavaScript/TypeScript',
    '.jsx': 'JavaScript/TypeScript',
    '.ts': 'JavaScript/TypeScript',
    '.tsx': 'JavaScript/TypeScript',
    '.cs': '.NET',
    '.fs': '.NET',
    '.rs': 'Rust',
    '.go': 'Go',
    '.sh': 'Shell scripts',
    '.ps1': 'PowerShell scripts',
}

KEY_FILES = {
    'AGENTS.md', 'CLAUDE.md', 'README.md', 'README', 'pyproject.toml',
    'package.json', 'Cargo.toml', 'go.mod', 'requirements.txt', 'Dockerfile',
    'docker-compose.yml', 'docker-compose.yaml', 'compose.yml', 'compose.yaml',
}


def file_rank(path):
    name = os.path.basename(path)
    if name in KEY_FILES or path in KEY_FILES:
        return (0, path.count(os.sep), path)
    if path.startswith(('src/', 'scripts/', 'tests/', 'test/')):
        return (1, path.count(os.sep), path)
    return (2, path.count(os.sep), path)

def main():
    parser = argparse.ArgumentParser(description="Create a compact repository map.")
    parser.add_argument('path', nargs='?', default='.', help="Repository path")
    parser.add_argument('--max-depth', type=int, default=4)
    parser.add_argument('--max-files', type=int, default=120)
    parser.add_argument('--max-chars', '--max-output-chars', dest='max_chars', type=int, default=12000)
    parser.add_argument('--include-hidden', action='store_true', default=False)
    parser.add_argument('--show-large-files', action='store_true', default=False)
    parser.add_argument('--large-file-mb', type=float, default=1.0)
    args = parser.parse_args()

    base_path = os.path.abspath(args.path)
    output = [f"Repository Map for: {redact_text(base_path)}"]
    
    file_counts = defaultdict(int)
    stack_detected = set()
    ignored_dirs = set()
    large_files = []
    
    file_list = []
    
    for root, dirs, files in os.walk(base_path):
        dirs.sort()
        files.sort()
        rel_root = os.path.relpath(root, base_path)
        if rel_root == '.':
            depth = 0
            rel_root = ''
        else:
            depth = rel_root.count(os.sep) + 1
            
        dirs_to_keep = []
        for d in dirs:
            if not args.include_hidden and d.startswith('.'):
                ignored_dirs.add(d)
                continue
            if d in DEFAULT_IGNORE_DIRS:
                ignored_dirs.add(d)
                continue
            if depth >= args.max_depth:
                ignored_dirs.add(d)
                continue
            dirs_to_keep.append(d)
        dirs[:] = dirs_to_keep
        
        for f in files:
            if not args.include_hidden and f.startswith('.'): continue
            ext = os.path.splitext(f)[1].lower()
            if ext in DEFAULT_IGNORE_EXTS: continue
            if is_binary_file(os.path.join(root, f)): continue
            
            file_counts[ext] += 1
            rel_path = os.path.join(rel_root, f) if rel_root else f
            file_list.append(rel_path)
            
            try:
                size_mb = os.path.getsize(os.path.join(root, f)) / (1024 * 1024)
                if size_mb >= args.large_file_mb:
                    large_files.append((rel_path, size_mb))
            except Exception:
                pass

    for f in sorted(file_list):
        for stack, indicators in STACK_INDICATORS.items():
            for ind in indicators:
                if any(ch in ind for ch in '*?['):
                    if fnmatch.fnmatch(f, ind) or fnmatch.fnmatch(os.path.basename(f), ind):
                        stack_detected.add(stack)
                elif f == ind or f.endswith('/' + ind):
                    stack_detected.add(stack)
        stack = EXTENSION_STACKS.get(os.path.splitext(f)[1].lower())
        if stack:
            stack_detected.add(stack)
                     
    output.append(f"\nStack Detected: {', '.join(sorted(stack_detected)) if stack_detected else 'Unknown'}")
     
    output.append("\nTop Key Files:")
    for f in sorted(file_list, key=file_rank)[:args.max_files]:
        output.append(f"  {redact_text(f)}")
        
    output.append("\nFile Extension Counts:")
    for ext, count in sorted(file_counts.items(), key=lambda x: -x[1])[:10]:
        output.append(f"  {ext if ext else '[no ext]'}: {count}")
        
    if ignored_dirs:
        output.append(f"\nIgnored directories: {redact_text(', '.join(sorted(ignored_dirs)[:20]))}")
        
    if args.show_large_files and large_files:
        output.append("\nLarge Files:")
        for f, size in sorted(large_files, key=lambda x: -x[1])[:10]:
            output.append(f"  {redact_text(f)} ({size:.2f} MB)")
            
    final_output = truncate('\n'.join(output), args.max_chars)
    print(final_output)

if __name__ == "__main__":
    main()
