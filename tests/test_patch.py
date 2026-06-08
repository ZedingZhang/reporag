from __future__ import annotations

from app.tools.patch import summarize_patch, validate_unified_diff


class TestValidateUnifiedDiff:
    def test_valid_diff(self) -> None:
        diff = """diff --git a/src/core.py b/src/core.py
index abc123..def456 100644
--- a/src/core.py
+++ b/src/core.py
@@ -10,6 +10,8 @@
 import os
+import sys

 def main():
-    pass
+    print('hello')
+    return 0
"""
        result = validate_unified_diff(diff)
        assert result.valid
        assert "src/core.py" in result.files
        assert result.file_count >= 1
        assert len(result.hunks) >= 1

    def test_valid_diff_with_multiple_files(self) -> None:
        diff = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,3 +1,4 @@
 x = 1
+y = 2
diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -1,3 +1,5 @@
 def f():
     pass
+
+def g():
+    pass
"""
        result = validate_unified_diff(diff)
        assert result.valid
        assert result.file_count == 2
        assert len(result.hunks) == 2

    def test_no_patch(self) -> None:
        result = validate_unified_diff("NO_PATCH: insufficient evidence")
        assert not result.valid
        assert "NO_PATCH" in result.reason

    def test_empty_diff(self) -> None:
        result = validate_unified_diff("")
        assert not result.valid
        assert "Empty" in result.reason

    def test_whitespace_only(self) -> None:
        result = validate_unified_diff("   \n  ")
        assert not result.valid

    def test_non_diff_text(self) -> None:
        result = validate_unified_diff("This is just a random text.")
        assert not result.valid

    def test_code_block_wrapped_diff(self) -> None:
        diff = """```diff
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,3 +1,4 @@
 x = 1
+y = 2
```"""
        result = validate_unified_diff(diff)
        assert result.valid
        assert "app.py" in result.files

    def test_diff_without_git_header(self) -> None:
        diff = """--- a/app.py
+++ b/app.py
@@ -1,3 +1,4 @@
 x = 1
+y = 2
"""
        result = validate_unified_diff(diff)
        assert result.valid


class TestSummarizePatch:
    def test_basic(self) -> None:
        diff = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,3 +1,5 @@
 x = 1
+y = 2
+
+z = 3
@@ -10,4 +12,3 @@
 a = 1
-b = 2
 c = 3
-d = 4
"""
        result = summarize_patch(diff)
        assert result.file_count == 1
        assert result.added_lines == 3
        assert result.removed_lines == 2
        assert "a.py" in result.files

    def test_no_patch(self) -> None:
        result = summarize_patch("NO_PATCH: cannot generate")
        assert result.is_no_patch

    def test_empty(self) -> None:
        result = summarize_patch("")
        assert result.file_count == 0
