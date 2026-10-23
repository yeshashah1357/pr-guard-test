from app.services.diff import added_lines, annotate, is_safe_path

PATCH = """\
@@ -1,4 +1,5 @@
 import os
-import sys
+import subprocess
+import shlex

 def run(cmd):
@@ -10,2 +11,3 @@ def run(cmd):
     x = 1
+    return subprocess.call(cmd, shell=True)
 \\ No newline at end of file"""


def test_added_lines_track_new_file_numbers_across_hunks():
    assert added_lines(PATCH) == {2, 3, 12}


def test_annotate_numbers_new_lines_and_blanks_removed_ones():
    lines = annotate(PATCH).splitlines()
    assert lines[0] == "    1  import os"
    assert lines[1] == "      -import sys"
    assert lines[2] == "    2 +import subprocess"
    assert "   12 +    return subprocess.call(cmd, shell=True)" in lines


def test_is_safe_path():
    assert is_safe_path("src/app/main.py")
    for bad in ("", "/etc/passwd", "../secret.py", "a/../../b.py", "C:/x.py"):
        assert not is_safe_path(bad), bad
