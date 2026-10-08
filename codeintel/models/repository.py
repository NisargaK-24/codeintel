from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ScannedFile(BaseModel):
    """Metadata for a single file discovered during repository scan."""
    path: str = Field(description="Absolute path to the file")
    relative_path: str = Field(description="Path relative to the repository root")
    language: str = Field(default="Unknown", description="Detected programming or markup language")
    size_bytes: int = Field(default=0, description="File size in bytes")
    line_count: int = Field(default=0, description="Total number of text lines")
    sha256_hash: str = Field(default="", description="Cryptographic SHA-256 hash of file contents")
    modified_at: float = Field(default=0.0, description="Last modification timestamp (epoch seconds)")
    is_binary: bool = Field(default=False, description="Whether the file is binary")


class ScanStats(BaseModel):
    """Statistical summary of repository scanning."""
    files_scanned: int = Field(default=0, description="Total files successfully scanned")
    files_skipped: int = Field(default=0, description="Total files skipped due to size or exclusions")
    lines_total: int = Field(default=0, description="Total lines across scanned text files")
    size_total: int = Field(default=0, description="Total size in bytes across scanned files")
    scan_duration_seconds: float = Field(default=0.0, description="Time taken to scan in seconds")


class RepositoryInfo(BaseModel):
    """Metadata describing the scanned repository root and environment."""
    root_path: str = Field(description="Absolute path to the repository root")
    is_git: bool = Field(default=False, description="Whether the repository is a Git repository")
    branch: Optional[str] = Field(default=None, description="Active Git branch if applicable")
    total_files: int = Field(default=0, description="Total files scanned")
    total_lines: int = Field(default=0, description="Total lines of code/text")
    total_size_bytes: int = Field(default=0, description="Total size in bytes")
    languages: Dict[str, int] = Field(default_factory=dict, description="File counts by detected language")


class ScanResult(BaseModel):
    """Complete result of a repository scan."""
    repository: RepositoryInfo
    files: List[ScannedFile] = Field(default_factory=list)
    stats: ScanStats = Field(default_factory=ScanStats)
