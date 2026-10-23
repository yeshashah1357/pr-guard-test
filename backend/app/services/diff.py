"""Unified-diff helpers for the `patch` field GitHub returns per changed file."""

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass
class ChangedFile:
    path: str
    patch: str
    added_lines: set[int] = field(default_factory=set)

    @classmethod
    def from_patch(cls, path: str, patch: str) -> "ChangedFile":
        return cls(path=path, patch=patch, added_lines=added_lines(patch))


def _walk(patch: str):
    """Yield (new_line_number | None, marker, text) for each diff line."""
    new_line = 0
    for raw in patch.splitlines():
        if match := HUNK_HEADER.match(raw):
            new_line = int(match.group(1))
            continue
        if raw.startswith("\\"):  # "\ No newline at end of file"
            continue
        marker, text = raw[:1], raw[1:]
        if marker == "-":
            yield None, marker, text
        else:
            yield new_line, marker, text
            new_line += 1


def added_lines(patch: str) -> set[int]:
    """New-file line numbers of lines the PR added. Findings are kept only on
    these: flagging untouched code would make every review noisy."""
    return {n for n, marker, _ in _walk(patch) if marker == "+"}


def annotate(patch: str) -> str:
    """Prefix each line with its new-file number so the LLM can cite exact lines."""
    out = []
    for n, marker, text in _walk(patch):
        label = f"{n:>5}" if n is not None else "     "
        out.append(f"{label} {marker}{text}")
    return "\n".join(out)


def is_safe_path(path: str) -> bool:
    """Reject absolute paths and '..' so a crafted filename can't escape the temp dir."""
    p = PurePosixPath(path)
    return bool(path) and not p.is_absolute() and ".." not in p.parts and ":" not in path
