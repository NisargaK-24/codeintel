from pathlib import Path
from typing import List, Optional
import pathspec


class GitIgnoreMatcher:
    """Matches file paths against .gitignore patterns using pathspec."""

    def __init__(self, root_path: Path):
        self.root_path = root_path.resolve()
        self.spec: Optional[pathspec.PathSpec] = None
        self._load_root_gitignore()

    def _load_root_gitignore(self) -> None:
        """Loads and compiles patterns from the root .gitignore if present."""
        gitignore_path = self.root_path / ".gitignore"
        lines: List[str] = []
        if gitignore_path.is_file():
            try:
                with open(gitignore_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
            except OSError:
                pass

        if lines:
            self.spec = pathspec.PathSpec.from_lines("gitignore", lines)

    def is_ignored(self, relative_path_str: str) -> bool:
        """Check if relative file path is matched by gitignore patterns."""
        if not self.spec:
            return False
        # Normalize to forward slashes as expected by gitwildmatch
        normalized = relative_path_str.replace("\\", "/")
        return self.spec.match_file(normalized)
