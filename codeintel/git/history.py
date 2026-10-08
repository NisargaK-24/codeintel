import io
from pathlib import Path
from typing import List, Optional
from dulwich.patch import write_tree_diff
from dulwich.repo import Repo

from codeintel.git.diff import parse_unified_diff
from codeintel.models.git import GitCommit


def is_source_file(file_path: str) -> bool:
    """Check if file path is source code."""
    p = file_path.lower()
    return any(p.endswith(ext) for ext in [".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".c", ".cpp", ".cs"])


def is_test_file(file_path: str) -> bool:
    """Check if file path represents a test file."""
    p = file_path.lower().replace("\\", "/")
    parts = p.split("/")
    filename = Path(p).name
    return (
        any(part in {"tests", "test", "testing"} for part in parts) or
        filename.startswith("test_") or
        filename.endswith("_test.py") or
        filename.endswith(".test.js") or
        filename.endswith(".spec.ts")
    )


def extract_commit_data(repo: Repo, commit_sha: bytes | str) -> Optional[GitCommit]:
    """Extract structured GitCommit metadata and file diffs for a given commit SHA."""
    try:
        sha_bytes = commit_sha.encode("utf-8") if isinstance(commit_sha, str) else commit_sha
        commit = repo[sha_bytes]
    except Exception:
        return None

    commit_hash_str = commit.id.decode("utf-8")
    author_str = commit.author.decode("utf-8", errors="replace")
    # Author format: "Name <email@example.com>"
    author_name = author_str
    author_email = ""
    if "<" in author_str and ">" in author_str:
        author_name = author_str.split("<")[0].strip()
        author_email = author_str.split("<")[1].split(">")[0].strip()

    message = commit.message.decode("utf-8", errors="replace").strip()
    timestamp = commit.commit_time

    # Determine parent tree for diff
    parent_tree = None
    if commit.parents:
        parent_sha = commit.parents[0]
        try:
            parent_tree = repo[parent_sha].tree
        except Exception:
            parent_tree = None

    # Generate unified diff
    out = io.BytesIO()
    try:
        write_tree_diff(out, repo.object_store, parent_tree, commit.tree)
        raw_diff = out.getvalue().decode("utf-8", errors="replace")
    except Exception:
        raw_diff = ""

    file_changes = parse_unified_diff(raw_diff)

    total_added = sum(fc.lines_added for fc in file_changes)
    total_deleted = sum(fc.lines_deleted for fc in file_changes)
    source_count = sum(1 for fc in file_changes if is_source_file(fc.file_path))
    test_count = sum(1 for fc in file_changes if is_test_file(fc.file_path))

    return GitCommit(
        hash=commit_hash_str,
        author_name=author_name,
        author_email=author_email,
        timestamp=timestamp,
        message=message,
        files_changed=len(file_changes),
        lines_added=total_added,
        lines_deleted=total_deleted,
        source_files_changed=source_count,
        test_files_changed=test_count,
        changes=file_changes
    )
