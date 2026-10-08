from pathlib import Path
from codeintel.git.diff import parse_unified_diff
from codeintel.git.repository import GitRepository

FIXTURE_REPO_PATH = Path(__file__).parent / "fixtures" / "sample_repo"


class TestGitAnalysis:
    """Test suite for local Git repository inspection, commit churn, and diff parsing."""

    def test_git_repository_state(self):
        git_repo = GitRepository(FIXTURE_REPO_PATH)
        assert git_repo.is_git is True

        state = git_repo.get_repository_state()
        assert state.is_git is True
        assert state.branch == "master"
        assert state.current_commit is not None
        assert state.total_commits >= 2

    def test_git_commit_history(self):
        git_repo = GitRepository(FIXTURE_REPO_PATH)
        commits = git_repo.get_commit_history(limit=5)

        assert len(commits) >= 2
        head_commit = commits[0]
        assert head_commit.hash is not None
        assert "PaymentService" in head_commit.message
        assert head_commit.author_name == "Developer"
        assert head_commit.author_email == "dev@codeintel.local"
        assert head_commit.files_changed > 0
        assert head_commit.lines_added > 0

    def test_git_commit_churn_metrics(self):
        git_repo = GitRepository(FIXTURE_REPO_PATH)
        commits = git_repo.get_commit_history()

        head_commit = commits[0]
        assert head_commit.source_files_changed >= 1
        assert head_commit.lines_added > 0
        assert head_commit.lines_deleted == 0

    def test_git_diff_parsing(self):
        sample_diff = """diff --git a/payment/service.py b/payment/service.py
index 1234567..89abcdef 100644
--- a/payment/service.py
+++ b/payment/service.py
@@ -10,6 +10,12 @@ def calculate_tax(amount: float, rate: float) -> float:
     if rate < 0:
         raise ValueError("Rate must be positive")
+    # Added line 1
+    # Added line 2
     return round(amount * rate, 2)
"""
        file_changes = parse_unified_diff(sample_diff)
        assert len(file_changes) == 1
        fc = file_changes[0]
        assert fc.file_path == "payment/service.py"
        assert fc.lines_added == 2
        assert len(fc.modified_line_ranges) == 1
        assert fc.modified_line_ranges[0] == (10, 21)
