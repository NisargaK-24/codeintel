import re
from typing import List, Tuple
from codeintel.models.git import ChangeType, FileChange, GitDiff

HUNK_HEADER_PATTERN = re.compile(r"^@@\s+-(?:\d+)(?:,\d+)?\s+\+(\d+)(?:,(\d+))?\s+@@")


def parse_unified_diff(raw_diff_text: str) -> List[FileChange]:
    """Parse unified diff text into structured FileChange objects with line ranges."""
    file_changes: List[FileChange] = []
    if not raw_diff_text or not raw_diff_text.strip():
        return file_changes

    # Split by file diff markers (diff --git or --- / +++)
    diff_sections = raw_diff_text.split("diff --git ")

    for section in diff_sections:
        if not section.strip():
            continue

        lines = section.splitlines()
        first_line = lines[0]
        # Example: "a/payment/service.py b/payment/service.py"
        parts = first_line.split()
        file_path = ""
        old_path = None
        if len(parts) >= 2:
            old_path = parts[0][2:] if parts[0].startswith("a/") else parts[0]
            file_path = parts[1][2:] if parts[1].startswith("b/") else parts[1]
        elif len(parts) == 1:
            file_path = parts[0]

        change_type = ChangeType.MODIFIED
        lines_added = 0
        lines_deleted = 0
        modified_ranges: List[Tuple[int, int]] = []

        for line in lines:
            if line.startswith("new file mode"):
                change_type = ChangeType.ADDED
            elif line.startswith("deleted file mode"):
                change_type = ChangeType.DELETED
            elif line.startswith("similarity index") or "rename to " in line:
                change_type = ChangeType.RENAMED

            # Check hunk header
            hunk_match = HUNK_HEADER_PATTERN.match(line)
            if hunk_match:
                start_line = int(hunk_match.group(1))
                line_count = int(hunk_match.group(2)) if hunk_match.group(2) is not None else 1
                end_line = start_line + max(0, line_count - 1)
                modified_ranges.append((start_line, end_line))
            elif line.startswith("+") and not line.startswith("+++"):
                lines_added += 1
            elif line.startswith("-") and not line.startswith("---"):
                lines_deleted += 1

        file_changes.append(FileChange(
            file_path=file_path.replace("\\", "/"),
            old_path=old_path.replace("\\", "/") if old_path else None,
            change_type=change_type,
            lines_added=lines_added,
            lines_deleted=lines_deleted,
            modified_line_ranges=modified_ranges,
            diff_text="\n".join(lines)
        ))

    return file_changes
