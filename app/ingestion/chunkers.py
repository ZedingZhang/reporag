from __future__ import annotations

import ast
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

CHUNK_TARGET_MIN = 400
CHUNK_TARGET_MAX = 1200


@dataclass
class ChunkingResult:
    content: str
    chunk_type: str
    path: str | None = None
    symbol_name: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    github_url: str | None = None
    summary: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _estimate_tokens(text: str) -> int:
    return len(text) // 3


def chunk_markdown(
    text: str, path: str | None, commit_sha: str, base_url: str
) -> list[ChunkingResult]:
    lines = text.split("\n")
    sections: list[dict[str, Any]] = []
    current_section: dict[str, Any] | None = None
    current_lines: list[str] = []
    heading_stack: list[tuple[int, str]] = []

    for i, line in enumerate(lines):
        heading_match = re.match(r"^(#{1,6})\s+(.+)", line)
        if heading_match:
            if current_section is not None and current_lines:
                current_section["content"] = "\n".join(current_lines)
                current_section["line_end"] = i
                sections.append(current_section)

            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))

            current_section = {
                "title": title,
                "heading_level": level,
                "heading_path": [h[1] for h in heading_stack],
                "line_start": i + 1,
                "line_end": None,
                "content": "",
            }
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_section is not None and current_lines:
        current_section["content"] = "\n".join(current_lines)
        current_section["line_end"] = len(lines)
        sections.append(current_section)

    if not sections and text.strip():
        sections = [
            {
                "title": path or "document",
                "heading_level": 1,
                "heading_path": [path or "document"],
                "line_start": 1,
                "line_end": len(lines),
                "content": text,
            }
        ]

    chunks: list[ChunkingResult] = []
    for sec in sections:
        content = sec["content"]
        token_est = _estimate_tokens(content)

        ls = sec["line_start"]
        le = sec["line_end"] or ls
        github_url = _build_code_url(base_url, path, ls, le) if (base_url and path) else ""

        if token_est <= CHUNK_TARGET_MAX * 2:
            chunks.append(
                ChunkingResult(
                    content=content,
                    chunk_type="markdown_section",
                    path=path,
                    symbol_name=sec["title"],
                    line_start=ls,
                    line_end=le,
                    github_url=github_url,
                    summary=sec["title"],
                    metadata={
                        "heading_level": sec["heading_level"],
                        "heading_path": sec["heading_path"],
                    },
                )
            )
        else:
            subs = _split_long_section(content, CHUNK_TARGET_MAX)
            for j, sub in enumerate(subs):
                chunks.append(
                    ChunkingResult(
                        content=sub,
                        chunk_type="markdown_section",
                        path=path,
                        symbol_name=f"{sec['title']} (part {j + 1})",
                        line_start=ls,
                        line_end=le,
                        github_url=github_url,
                        metadata={
                            "heading_level": sec["heading_level"],
                            "heading_path": sec["heading_path"],
                        },
                    )
                )

    return chunks


def chunk_code_file(
    text: str, path: str, commit_sha: str, base_url: str
) -> list[ChunkingResult]:
    ext = os.path.splitext(path)[1].lower() if path else ""

    if ext == ".py":
        return _chunk_python_ast(text, path, base_url)
    elif ext in (".ts", ".tsx", ".js", ".jsx"):
        return _chunk_js_fallback(text, path, base_url)
    else:
        return []


def chunk_text_blocks(
    text: str,
    path: str | None,
    base_url: str,
    chunk_type: str,
) -> list[ChunkingResult]:
    token_est = _estimate_tokens(text)
    if token_est <= CHUNK_TARGET_MAX:
        return [
            ChunkingResult(
                content=text,
                chunk_type=chunk_type,
                path=path,
                github_url=base_url or None,
            )
        ]

    blocks = _split_long_section(text, CHUNK_TARGET_MAX)
    results: list[ChunkingResult] = []
    for i, block in enumerate(blocks):
        results.append(
            ChunkingResult(
                content=block,
                chunk_type=chunk_type,
                path=path,
                github_url=base_url or None,
                summary=f"Part {i + 1}" if len(blocks) > 1 else None,
            )
        )
    return results


def _chunk_python_ast(
    text: str, path: str, base_url: str
) -> list[ChunkingResult]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        logger.debug("AST parse failed for %s, using line-based fallback", path)
        return _chunk_text_fallback(text, path, base_url, "code_symbol")

    results: list[ChunkingResult] = []
    lines = text.split("\n")

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            r = _extract_function_chunk(node, lines, path, base_url)
            if r:
                results.append(r)
        elif isinstance(node, ast.ClassDef):
            r = _extract_class_chunk(node, lines, path, base_url)
            if r:
                results.append(r)
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        cr = _extract_function_chunk(child, lines, path, base_url)
                        if cr:
                            cr.metadata["parent_class"] = node.name
                            results.append(cr)

    if not results:
        return _chunk_text_fallback(text, path, base_url, "code_symbol")

    return results


def _extract_function_chunk(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    lines: list[str],
    path: str,
    base_url: str,
) -> ChunkingResult | None:
    line_start = node.lineno
    line_end = node.end_lineno or line_start

    if line_start < 1 or line_end > len(lines):
        return None

    decorator_start = line_start
    if node.decorator_list:
        first_decorator = node.decorator_list[0]
        decorator_start = first_decorator.lineno

    prefix = ""
    if decorator_start > 1:
        prev_line = decorator_start - 2
        comments: list[str] = []
        while prev_line >= 0 and lines[prev_line].strip().startswith("#"):
            comments.insert(0, lines[prev_line].strip())
            prev_line -= 1
        if comments:
            prefix = "\n".join(comments) + "\n"
        if prev_line >= 0 and lines[prev_line].strip().startswith('"""'):
            doc_lines: list[str] = []
            while prev_line >= 0:
                doc_lines.insert(0, lines[prev_line])
                if prev_line != decorator_start - 2 and '"""' in lines[prev_line]:
                    break
                prev_line -= 1
            if doc_lines:
                prefix = "\n".join(doc_lines) + "\n" + prefix

    chunk_content = prefix + "\n".join(lines[decorator_start - 1 : line_end])
    name = node.name

    token_est = _estimate_tokens(chunk_content)
    if token_est > CHUNK_TARGET_MAX * 2:
        chunk_content = "\n".join(lines[line_start - 1 : line_end])

    return ChunkingResult(
        content=chunk_content,
        chunk_type="code_symbol",
        path=path,
        symbol_name=name,
        line_start=decorator_start,
        line_end=line_end,
        github_url=_build_code_url(base_url, path, decorator_start, line_end),
        summary=f"Function: {name}",
        metadata={"symbol_type": "function"},
    )


def _extract_class_chunk(
    node: ast.ClassDef,
    lines: list[str],
    path: str,
    base_url: str,
) -> ChunkingResult | None:
    line_start = node.lineno
    line_end = node.end_lineno or line_start

    if line_start < 1 or line_end > len(lines):
        return None

    decorator_start = line_start
    if node.decorator_list:
        first_decorator = node.decorator_list[0]
        decorator_start = first_decorator.lineno

    prefix = ""
    if decorator_start > 1:
        prev_line = decorator_start - 2
        if prev_line >= 0 and lines[prev_line].strip().startswith('"""'):
            doc_lines: list[str] = []
            while prev_line >= 0:
                doc_lines.insert(0, lines[prev_line])
                if prev_line != decorator_start - 2 and '"""' in lines[prev_line]:
                    break
                prev_line -= 1
            if doc_lines:
                prefix = "\n".join(doc_lines) + "\n"

    content = prefix + "\n".join(lines[decorator_start - 1 : line_end])

    return ChunkingResult(
        content=content,
        chunk_type="code_symbol",
        path=path,
        symbol_name=node.name,
        line_start=decorator_start,
        line_end=line_end,
        github_url=_build_code_url(base_url, path, decorator_start, line_end),
        summary=f"Class: {node.name}",
        metadata={"symbol_type": "class"},
    )


def _chunk_js_fallback(
    text: str, path: str, base_url: str
) -> list[ChunkingResult]:
    lines = text.split("\n")
    results: list[ChunkingResult] = []

    func_pattern = re.compile(
        r"^(export\s+)?(const\s+)?(async\s+)?(function\s+(\w+)|(\w+)\s*[:=]\s*(async\s+)?\(|(\w+)\s*=\s*(async\s+)?\()"
    )
    class_pattern = re.compile(r"^(export\s+)?class\s+(\w+)")

    i = 0
    while i < len(lines):
        func_match = func_pattern.match(lines[i].strip())
        if func_match:
            name = func_match.group(5) or func_match.group(6) or func_match.group(8) or "anonymous"
            brace_count = lines[i].count("{") - lines[i].count("}")
            end = i + 1
            while end < len(lines) and brace_count > 0:
                brace_count += lines[end].count("{") - lines[end].count("}")
                end += 1
            content = "\n".join(lines[i:end])
            results.append(
                ChunkingResult(
                    content=content,
                    chunk_type="code_symbol",
                    path=path,
                    symbol_name=name,
                    line_start=i + 1,
                    line_end=end,
                    github_url=_build_code_url(base_url, path, i + 1, end),
                    summary=f"Function: {name}",
                    metadata={"symbol_type": "function", "language": "js/ts"},
                )
            )
            i = end
            continue

        class_match = class_pattern.match(lines[i].strip())
        if class_match:
            name = class_match.group(2)
            brace_count = lines[i].count("{") - lines[i].count("}")
            end = i + 1
            while end < len(lines) and brace_count > 0:
                brace_count += lines[end].count("{") - lines[end].count("}")
                end += 1
            content = "\n".join(lines[i:end])
            results.append(
                ChunkingResult(
                    content=content,
                    chunk_type="code_symbol",
                    path=path,
                    symbol_name=name,
                    line_start=i + 1,
                    line_end=end,
                    github_url=_build_code_url(base_url, path, i + 1, end),
                    summary=f"Class: {name}",
                    metadata={"symbol_type": "class", "language": "js/ts"},
                )
            )
            i = end
            continue

        i += 1

    if not results:
        return _chunk_text_fallback(text, path, base_url, "code_symbol")

    return results


def _chunk_text_fallback(
    text: str, path: str, base_url: str, chunk_type: str
) -> list[ChunkingResult]:
    blocks = _split_long_section(text, CHUNK_TARGET_MAX)

    results: list[ChunkingResult] = []
    line_offset = 0
    for block in blocks:
        block_lines = block.split("\n")
        start = line_offset + 1
        end = line_offset + len(block_lines)
        results.append(
            ChunkingResult(
                content=block,
                chunk_type=chunk_type,
                path=path,
                line_start=start,
                line_end=end,
                github_url=_build_code_url(base_url, path, start, end),
                metadata={"fallback": True},
            )
        )
        line_offset += len(block_lines)

    return results


def _split_long_section(text: str, max_tokens: int) -> list[str]:
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = _estimate_tokens(para)
        if current_len + para_len > max_tokens and current:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0

        if para_len > max_tokens:
            sub_parts = _split_by_sentences(para, max_tokens)
            for part in sub_parts:
                part_len = _estimate_tokens(part)
                if current_len + part_len > max_tokens and current:
                    chunks.append("\n\n".join(current))
                    current = []
                    current_len = 0
                current.append(part)
                current_len += part_len
        else:
            current.append(para)
            current_len += para_len

    if current:
        chunks.append("\n\n".join(current))

    if not chunks and text.strip():
        chunks = [text.strip()]

    return chunks


def _split_by_sentences(text: str, max_tokens: int) -> list[str]:
    parts: list[str] = []
    current = ""
    for char in text:
        current += char
        if _estimate_tokens(current) >= max_tokens:
            parts.append(current)
            current = ""
    if current:
        parts.append(current)
    return parts or [text]


def _build_code_url(
    base_url: str, path: str, line_start: int | None, line_end: int | None
) -> str:
    if not base_url or not path:
        return ""
    if line_start and line_end and line_start != line_end:
        return f"{base_url}#L{line_start}-L{line_end}"
    elif line_start:
        return f"{base_url}#L{line_start}"
    return base_url
