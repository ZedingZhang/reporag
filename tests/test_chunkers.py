from __future__ import annotations

import pytest

from app.ingestion.chunkers import (
    _build_code_url,
    chunk_code_file,
    chunk_markdown,
    chunk_text_blocks,
)


class TestMarkdownChunker:
    def test_splits_by_heading_level(self, sample_markdown: str) -> None:
        chunks = chunk_markdown(
            sample_markdown,
            "README.md",
            "abc123",
            "https://github.com/o/r/blob/abc123/README.md",
        )

        assert len(chunks) >= 4, f"Expected at least 4 sections, got {len(chunks)}"

        titles = [c.symbol_name for c in chunks]
        assert "Project Title" in titles
        assert "Installation" in titles
        assert "Usage" in titles

    def test_heading_metadata(self) -> None:
        md = "## Section A\n\nContent A.\n\n### Sub A.1\n\nSub content."
        chunks = chunk_markdown(
            md, "doc.md", "abc123", "https://github.com/o/r/blob/abc123/doc.md"
        )

        sub_chunk = next(c for c in chunks if c.symbol_name == "Sub A.1")
        assert sub_chunk.metadata["heading_level"] == 3
        assert "Section A" in sub_chunk.metadata["heading_path"]
        assert "Sub A.1" in sub_chunk.metadata["heading_path"]

    def test_preserves_content(self) -> None:
        md = "## Usage\n\n```python\nprint('hello')\n```\n\nEnd."
        chunks = chunk_markdown(
            md, "doc.md", "abc123", "https://github.com/o/r/blob/abc123/doc.md"
        )

        assert len(chunks) == 1
        assert "```python" in chunks[0].content
        assert "print('hello')" in chunks[0].content

    def test_empty_text_produces_no_chunks(self) -> None:
        chunks = chunk_markdown(
            "", "empty.md", "abc123", "https://github.com/o/r/blob/abc123/empty.md"
        )
        assert len(chunks) == 0



class TestPythonChunker:
    def test_extracts_functions(self, sample_python_code: str) -> None:
        chunks = chunk_code_file(
            sample_python_code, "test.py", "abc123", "https://github.com/o/r/blob/abc123/test.py"
        )

        names = [c.symbol_name for c in chunks if c.metadata.get("symbol_type") == "function"]
        assert "helper" in names
        assert "standalone_async" in names

    def test_extracts_classes(self, sample_python_code: str) -> None:
        chunks = chunk_code_file(
            sample_python_code, "test.py", "abc123", "https://github.com/o/r/blob/abc123/test.py"
        )

        class_chunks = [c for c in chunks if c.metadata.get("symbol_type") == "class"]
        assert len(class_chunks) >= 1
        assert class_chunks[0].symbol_name == "MyClass"

    def test_line_numbers_are_correct(self, sample_python_code: str) -> None:
        chunks = chunk_code_file(
            sample_python_code, "test.py", "abc123", "https://github.com/o/r/blob/abc123/test.py"
        )

        helper = next(c for c in chunks if c.symbol_name == "helper")
        assert helper.line_start is not None
        assert helper.line_end is not None
        assert helper.line_start <= helper.line_end

        class_chunk = next(c for c in chunks if c.symbol_name == "MyClass")
        assert class_chunk.line_start is not None
        assert class_chunk.line_end is not None

    def test_methods_have_parent_class_metadata(self, sample_python_code: str) -> None:
        chunks = chunk_code_file(
            sample_python_code, "test.py", "abc123", "https://github.com/o/r/blob/abc123/test.py"
        )

        methods = [c for c in chunks if c.metadata.get("parent_class")]
        assert len(methods) >= 2
        for m in methods:
            assert m.metadata["parent_class"] == "MyClass"

    def test_syntax_error_fallback(self) -> None:
        invalid_py = "def broken(:\n    return 1"
        chunks = chunk_code_file(
            invalid_py, "broken.py", "abc123", "https://github.com/o/r/blob/abc123/broken.py"
        )
        assert len(chunks) > 0
        assert chunks[0].chunk_type == "code_symbol"


class TestJSChunker:
    def test_extracts_js_functions(self, sample_js_code: str) -> None:
        chunks = chunk_code_file(
            sample_js_code, "test.js", "abc123", "https://github.com/o/r/blob/abc123/test.js"
        )

        assert len(chunks) >= 3, f"Expected at least 3 symbols, got {len(chunks)}"

        names = [c.symbol_name for c in chunks]
        assert "Hello" in names or any("Component" in n for n in names)

    def test_js_line_numbers(self, sample_js_code: str) -> None:
        chunks = chunk_code_file(
            sample_js_code, "test.js", "abc123", "https://github.com/o/r/blob/abc123/test.js"
        )

        for c in chunks:
            assert c.line_start is not None
            assert c.line_end is not None
            assert c.line_start >= 1
            assert c.line_end >= c.line_start


class TestTextBlockChunker:
    def test_short_text_single_chunk(self) -> None:
        text = "This is a short text about an issue."
        chunks = chunk_text_blocks(text, None, "https://github.com/o/r/issues/1", "issue_comment")
        assert len(chunks) == 1
        assert chunks[0].chunk_type == "issue_comment"
        assert chunks[0].github_url == "https://github.com/o/r/issues/1"

    def test_long_text_splits(self) -> None:
        text = "Paragraph. " * 2000
        chunks = chunk_text_blocks(text, None, "https://example.com", "pr_description")
        assert len(chunks) > 1
        for c in chunks:
            assert c.chunk_type == "pr_description"


class TestBuildCodeUrl:
    def test_url_with_lines(self) -> None:
        base = "https://github.com/o/r/blob/abc/src/main.py"
        url = _build_code_url(base, "src/main.py", 10, 25)
        assert url == "https://github.com/o/r/blob/abc/src/main.py#L10-L25"

    def test_url_single_line(self) -> None:
        base = "https://github.com/o/r/blob/abc/src/main.py"
        url = _build_code_url(base, "src/main.py", 10, 10)
        assert url == "https://github.com/o/r/blob/abc/src/main.py#L10"

    def test_url_no_lines(self) -> None:
        base = "https://github.com/o/r/blob/abc/src/main.py"
        url = _build_code_url(base, "src/main.py", None, None)
        assert url == "https://github.com/o/r/blob/abc/src/main.py"

    def test_url_empty_base(self) -> None:
        url = _build_code_url("", "src/main.py", 5, 10)
        assert url == ""
