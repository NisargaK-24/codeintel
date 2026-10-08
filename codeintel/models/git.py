from enum import Enum
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field


class ChangeType(str, Enum):
    """Type of modification applied to a file in a commit."""
    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"
    RENAMED = "RENAMED"


class FileChange(BaseModel):
    """File modification details in a Git commit or working-tree diff."""
    file_path: str = Field(description="Relative path of file in repository")
    old_path: Optional[str] = Field(default=None, description="Previous path if renamed")
    change_type: ChangeType = Field(default=ChangeType.MODIFIED, description="Type of change")
    lines_added: int = Field(default=0, description="Count of added lines")
    lines_deleted: int = Field(default=0, description="Count of deleted lines")
    modified_line_ranges: List[Tuple[int, int]] = Field(
        default_factory=list,
        description="Ranges of modified lines (start_line, end_line) in new file"
    )
    diff_text: Optional[str] = Field(default=None, description="Raw unified diff text for this file")


class GitCommit(BaseModel):
    """Metadata and churn statistics for a specific Git commit."""
    hash: str = Field(description="Full or short SHA-1 commit hash")
    author_name: str = Field(default="", description="Name of commit author")
    author_email: str = Field(default="", description="Email of commit author")
    timestamp: int = Field(default=0, description="Commit timestamp (epoch seconds)")
    message: str = Field(default="", description="Commit message")
    files_changed: int = Field(default=0, description="Total files modified/added/deleted")
    lines_added: int = Field(default=0, description="Total lines added")
    lines_deleted: int = Field(default=0, description="Total lines deleted")
    source_files_changed: int = Field(default=0, description="Count of source code files modified (.py, etc.)")
    test_files_changed: int = Field(default=0, description="Count of test files modified (test_*.py, etc.)")
    changes: List[FileChange] = Field(default_factory=list, description="Per-file change details")


class GitDiff(BaseModel):
    """Detailed diff comparison between two commits or commit and parent."""
    commit_hash: str = Field(description="Target commit hash")
    parent_hash: Optional[str] = Field(default=None, description="Parent commit hash")
    file_changes: List[FileChange] = Field(default_factory=list, description="Individual file diffs")


class GitRepositoryState(BaseModel):
    """Current status and history summary of a local Git repository."""
    is_git: bool = Field(default=True, description="Whether path is a valid Git repository")
    branch: Optional[str] = Field(default=None, description="Active branch name")
    current_commit: Optional[str] = Field(default=None, description="Current HEAD commit SHA")
    is_dirty: bool = Field(default=False, description="Whether uncommitted changes exist")
    untracked_files: List[str] = Field(default_factory=list, description="Untracked file paths")
    total_commits: int = Field(default=0, description="Total number of commits in history")
    commits: List[GitCommit] = Field(default_factory=list, description="Recent commit history list")
