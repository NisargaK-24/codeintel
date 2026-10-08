from pathlib import Path
from typing import Set
from codeintel.config.settings import settings


class ExclusionManager:
    """Manages rules for skipping directories, binaries, caches, and oversized files."""

    def __init__(
        self,
        excluded_dirs: Set[str] = None,
        binary_extensions: Set[str] = None,
        max_file_size_bytes: int = None
    ):
        self.excluded_dirs = excluded_dirs if excluded_dirs is not None else settings.excluded_dirs
        self.binary_extensions = binary_extensions if binary_extensions is not None else settings.binary_extensions
        self.max_file_size_bytes = max_file_size_bytes if max_file_size_bytes is not None else settings.max_file_size_bytes

    def is_directory_excluded(self, dir_name: str) -> bool:
        """Check if a directory name matches excluded names (e.g. .git, node_modules, .venv)."""
        name = dir_name.lower().strip()
        # Direct exact match
        if name in {d.lower() for d in self.excluded_dirs}:
            return True
        # Virtualenv or cache patterns
        if name.startswith(".venv") or name.startswith("venv") or name.endswith(".egg-info"):
            return True
        return False

    def is_binary_file(self, file_path: Path) -> bool:
        """Check if a file is binary based on extension or by inspecting the initial byte content."""
        suffix = file_path.suffix.lower()
        if suffix in self.binary_extensions:
            return True

        # Fallback inspection: read first 1024 bytes to check for null byte
        try:
            with open(file_path, "rb") as f:
                chunk = f.read(1024)
                if b"\x00" in chunk:
                    return True
        except (OSError, PermissionError):
            return True

        return False

    def is_oversized(self, size_bytes: int) -> bool:
        """Check if a file exceeds the configured maximum scan size."""
        return size_bytes > self.max_file_size_bytes
