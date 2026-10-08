import hashlib
import os
from pathlib import Path
import time
from typing import Dict, List, Optional

from codeintel.config.settings import settings
from codeintel.models.repository import RepositoryInfo, ScannedFile, ScanResult, ScanStats
from codeintel.scanner.exclusions import ExclusionManager
from codeintel.scanner.gitignore import GitIgnoreMatcher

LANGUAGE_EXTENSION_MAP: Dict[str, str] = {
    ".py": "Python",
    ".pyw": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "SASS",
    ".json": "JSON",
    ".md": "Markdown",
    ".markdown": "Markdown",
    ".rst": "ReStructuredText",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".xml": "XML",
    ".sql": "SQL",
    ".sh": "Shell",
    ".bash": "Shell",
    ".ps1": "PowerShell",
    ".bat": "Batch",
    ".c": "C",
    ".h": "C/C++ Header",
    ".cpp": "C++",
    ".cc": "C++",
    ".hpp": "C++ Header",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".ini": "Config",
    ".cfg": "Config",
    ".conf": "Config",
}


def detect_language(file_path: Path) -> str:
    """Detect language based on extension or well-known filenames."""
    filename = file_path.name.lower()
    if filename in {"dockerfile", "containerfile"}:
        return "Dockerfile"
    if filename in {"makefile", "gnumakefile"}:
        return "Makefile"
    suffix = file_path.suffix.lower()
    return LANGUAGE_EXTENSION_MAP.get(suffix, "Unknown")


def compute_sha256(file_path: Path) -> str:
    """Calculate SHA-256 hash of a file without loading entire file into memory at once."""
    hasher = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (OSError, PermissionError):
        return ""


def count_lines_safely(file_path: Path) -> int:
    """Count text lines safely handling different encodings."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            count = sum(1 for _ in f)
        return count
    except (OSError, PermissionError):
        return 0


def detect_git_state(root_path: Path) -> tuple[bool, Optional[str]]:
    """Detect whether directory is a Git repository and determine current branch."""
    git_dir = root_path / ".git"
    if not git_dir.exists():
        return False, None

    branch: Optional[str] = None
    head_file = git_dir / "HEAD"
    if head_file.is_file():
        try:
            head_content = head_file.read_text(encoding="utf-8", errors="ignore").strip()
            if head_content.startswith("ref: refs/heads/"):
                branch = head_content[len("ref: refs/heads/"):]
            elif len(head_content) == 40:
                # Detached HEAD
                branch = head_content[:8]
        except OSError:
            pass

    return True, branch


class RepositoryScanner:
    """Scans repositories safely and recursively without executing any source code."""

    def __init__(
        self,
        exclusion_manager: Optional[ExclusionManager] = None,
        respect_gitignore: bool = True
    ):
        self.exclusions = exclusion_manager or ExclusionManager()
        self.respect_gitignore = respect_gitignore

    def scan(self, target_path: str | Path) -> ScanResult:
        """Perform a complete repository scan on the target path."""
        start_time = time.perf_counter()
        root = Path(target_path).resolve()

        if not root.exists():
            raise FileNotFoundError(f"Target repository path does not exist: {root}")
        if not root.is_dir():
            raise NotADirectoryError(f"Target path is not a directory: {root}")

        is_git, branch = detect_git_state(root)
        gitignore_matcher = GitIgnoreMatcher(root) if self.respect_gitignore else None

        scanned_files: List[ScannedFile] = []
        files_skipped = 0
        total_lines = 0
        total_size = 0
        language_counts: Dict[str, int] = {}

        # os.walk allows pruning directories in-place
        for current_root, dir_names, file_names in os.walk(root):
            curr_path = Path(current_root)

            # Filter directories in-place to prevent descending into excluded or gitignored dirs
            filtered_dirs = []
            for d in dir_names:
                dir_full_path = curr_path / d
                rel_dir = dir_full_path.relative_to(root).as_posix()
                if self.exclusions.is_directory_excluded(d):
                    continue
                if gitignore_matcher and gitignore_matcher.is_ignored(rel_dir + "/"):
                    continue
                filtered_dirs.append(d)
            dir_names[:] = filtered_dirs

            # Process files
            for f_name in file_names:
                file_path = curr_path / f_name
                rel_file = file_path.relative_to(root).as_posix()

                # Check gitignore
                if gitignore_matcher and gitignore_matcher.is_ignored(rel_file):
                    files_skipped += 1
                    continue

                try:
                    stat_info = file_path.stat()
                except (OSError, PermissionError):
                    files_skipped += 1
                    continue

                size_bytes = stat_info.st_size

                # Check oversized
                if self.exclusions.is_oversized(size_bytes):
                    files_skipped += 1
                    continue

                is_binary = self.exclusions.is_binary_file(file_path)
                language = "Binary" if is_binary else detect_language(file_path)
                line_count = 0 if is_binary else count_lines_safely(file_path)
                sha256 = compute_sha256(file_path)

                scanned_file = ScannedFile(
                    path=str(file_path),
                    relative_path=rel_file,
                    language=language,
                    size_bytes=size_bytes,
                    line_count=line_count,
                    sha256_hash=sha256,
                    modified_at=stat_info.st_mtime,
                    is_binary=is_binary
                )
                scanned_files.append(scanned_file)

                total_size += size_bytes
                total_lines += line_count
                language_counts[language] = language_counts.get(language, 0) + 1

        duration = time.perf_counter() - start_time

        stats = ScanStats(
            files_scanned=len(scanned_files),
            files_skipped=files_skipped,
            lines_total=total_lines,
            size_total=total_size,
            scan_duration_seconds=round(duration, 4)
        )

        repo_info = RepositoryInfo(
            root_path=str(root),
            is_git=is_git,
            branch=branch,
            total_files=len(scanned_files),
            total_lines=total_lines,
            total_size_bytes=total_size,
            languages=language_counts
        )

        return ScanResult(
            repository=repo_info,
            files=scanned_files,
            stats=stats
        )
