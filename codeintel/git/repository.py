from pathlib import Path
from typing import List, Optional
from dulwich import porcelain
from dulwich.repo import Repo

from codeintel.git.history import extract_commit_data
from codeintel.models.git import GitCommit, GitRepositoryState


class GitRepository:
    """Local Git repository inspector without external AI or network calls."""

    def __init__(self, repo_path: str | Path):
        self.root_path = Path(repo_path).resolve()
        self._repo: Optional[Repo] = None
        self._is_git = (self.root_path / ".git").is_dir()

    @property
    def is_git(self) -> bool:
        return self._is_git

    def _get_repo(self) -> Repo:
        if not self._is_git:
            raise ValueError(f"Path '{self.root_path}' is not a Git repository.")
        if self._repo is None:
            self._repo = Repo(str(self.root_path))
        return self._repo

    def get_current_branch(self) -> Optional[str]:
        """Determine active branch name or None if detached/empty."""
        if not self._is_git:
            return None
        head_path = self.root_path / ".git" / "HEAD"
        if head_path.is_file():
            try:
                head_text = head_path.read_text(encoding="utf-8", errors="ignore").strip()
                if head_text.startswith("ref: refs/heads/"):
                    return head_text[len("ref: refs/heads/"):]
                elif len(head_text) == 40:
                    return head_text[:8]
            except OSError:
                pass
        return None

    def get_commit_history(self, limit: int = 50) -> List[GitCommit]:
        """Fetch chronological commit history starting from HEAD."""
        if not self._is_git:
            return []

        commits: List[GitCommit] = []
        try:
            repo = self._get_repo()
            walker = repo.get_walker(max_entries=limit)
            for entry in walker:
                commit_data = extract_commit_data(repo, entry.commit.id)
                if commit_data:
                    commits.append(commit_data)
        except Exception:
            pass

        return commits

    def get_commit(self, commit_hash: str) -> Optional[GitCommit]:
        """Retrieve details and diff for a specific commit hash (or prefix)."""
        if not self._is_git:
            return None
        try:
            repo = self._get_repo()
            # If short hash, search objects or refs
            target_sha = commit_hash.encode("utf-8")
            if len(commit_hash) < 40:
                for entry in repo.get_walker():
                    sha_str = entry.commit.id.decode("utf-8")
                    if sha_str.startswith(commit_hash):
                        target_sha = entry.commit.id
                        break
            return extract_commit_data(repo, target_sha)
        except Exception:
            return None

    def get_repository_state(self, limit_history: int = 10) -> GitRepositoryState:
        """Query working-tree cleanliness, untracked files, and recent history."""
        if not self._is_git:
            return GitRepositoryState(
                is_git=False,
                branch=None,
                current_commit=None,
                is_dirty=False,
                untracked_files=[],
                total_commits=0,
                commits=[]
            )

        branch = self.get_current_branch()
        repo = self._get_repo()

        current_commit: Optional[str] = None
        try:
            head_bytes = repo.head()
            current_commit = head_bytes.decode("utf-8")
        except Exception:
            pass

        # Check status (untracked and modified)
        untracked: List[str] = []
        is_dirty = False
        try:
            status = porcelain.status(str(self.root_path))
            # status has .untracked, .staged, .unstaged
            untracked = [p.decode("utf-8", errors="replace") if isinstance(p, bytes) else str(p) for p in status.untracked]
            has_staged = bool(status.staged.get("add") or status.staged.get("modify") or status.staged.get("delete"))
            has_unstaged = bool(status.unstaged)
            is_dirty = has_staged or has_unstaged
        except Exception:
            pass

        all_commits = self.get_commit_history(limit=limit_history)

        return GitRepositoryState(
            is_git=True,
            branch=branch,
            current_commit=current_commit,
            is_dirty=is_dirty,
            untracked_files=untracked,
            total_commits=len(all_commits),
            commits=all_commits
        )
