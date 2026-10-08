from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from codeintel.models.git import ChangeType, FileChange, GitCommit
from codeintel.models.impact import ChangeImpact
from codeintel.models.risk import RiskTier
from codeintel.risk.engine import CommitRiskEngine
from codeintel.web.app import create_app

FIXTURE_REPO_PATH = Path(__file__).parent / "fixtures" / "sample_repo"


def make_test_commit(h: str, msg: str, files: list[str], lines_add: int, lines_del: int) -> GitCommit:
    return GitCommit(
        hash=h,
        author_name="Alice",
        author_email="alice@test.com",
        timestamp=1700000000,
        message=msg,
        lines_added=lines_add,
        lines_deleted=lines_del,
        files_changed=len(files),
        changes=[
            FileChange(
                file_path=fp,
                change_type=ChangeType.MODIFIED,
                lines_added=lines_add // max(1, len(files)),
                lines_deleted=lines_del // max(1, len(files)),
                modified_line_ranges=[(1, 10)]
            )
            for fp in files
        ]
    )


class TestCommitRiskEngine:
    """Test suite for predictive commit risk evaluation and web portal API."""

    def test_low_risk_commit_evaluation(self):
        engine = CommitRiskEngine()
        commit = make_test_commit("c101", "docs: update install notes", ["docs/setup.md"], lines_add=5, lines_del=1)
        impact = ChangeImpact(
            commit_hash="c101",
            files_changed_count=1,
            symbols_changed_count=0,
            directly_affected_count=0,
            indirectly_affected_count=0,
            impact_radius=0,
            changed_files=["docs/setup.md"]
        )

        report = engine.evaluate_commit(commit, impact=impact, author_commit_count=20)
        assert report.risk_score < 40.0
        assert report.risk_tier in (RiskTier.LOW, RiskTier.MEDIUM)
        assert len(report.recommendations) > 0

    def test_high_risk_commit_evaluation(self):
        engine = CommitRiskEngine()
        commit = make_test_commit(
            "c999",
            "fix: refactor payments core engine and dispatchers",
            ["src/payment.py", "src/auth.py", "src/db.py", "src/api.py", "src/notify.py", "src/queue.py"],
            lines_add=650,
            lines_del=200
        )
        impact = ChangeImpact(
            commit_hash="c999",
            files_changed_count=6,
            symbols_changed_count=10,
            directly_affected_count=8,
            indirectly_affected_count=15,
            impact_radius=23,
            changed_files=["src/payment.py", "src/auth.py"],
            critical_components=["payment.process_charge", "auth.verify"]
        )

        report = engine.evaluate_commit(commit, impact=impact, author_commit_count=1)
        assert report.risk_score >= 50.0
        assert report.risk_tier in (RiskTier.HIGH, RiskTier.CRITICAL)

        factor_names = {f.name for f in report.top_risk_factors}
        assert "CRITICAL_BLAST_RADIUS" in factor_names or "ELEVATED_BLAST_RADIUS" in factor_names
        assert "MASSIVE_CHURN" in factor_names or "HIGH_CHURN" in factor_names

    def test_repository_risk_summary(self):
        engine = CommitRiskEngine()
        commits = [
            make_test_commit("h1", "fix bug", ["src/a.py"], 20, 5),
            make_test_commit("h2", "add feature", ["src/b.py", "src/c.py"], 550, 100),
            make_test_commit("h3", "style tweak", ["src/a.py"], 2, 2)
        ]
        summary = engine.evaluate_repository_commits(commits)
        assert summary.total_commits_evaluated == 3
        assert summary.average_risk_score > 0.0
        assert summary.risk_distribution[RiskTier.LOW.value] >= 0

    def test_web_portal_endpoints(self):
        app = create_app(str(FIXTURE_REPO_PATH))
        client = TestClient(app)

        # GET /
        resp_home = client.get("/")
        assert resp_home.status_code == 200
        assert "CodeIntel" in resp_home.text

        # GET /api/overview
        resp_overview = client.get("/api/overview")
        assert resp_overview.status_code == 200
        data = resp_overview.json()
        assert "total_files" in data
        assert "health_score" in data
        assert data["health_score"] > 0

        # GET /api/zombies
        resp_zombies = client.get("/api/zombies")
        assert resp_zombies.status_code == 200

        # GET /api/quality
        resp_quality = client.get("/api/quality")
        assert resp_quality.status_code == 200
        assert "total_issues" in resp_quality.json()

        # GET /api/graph
        resp_graph = client.get("/api/graph")
        assert resp_graph.status_code == 200
        assert "summary" in resp_graph.json()

        # GET /api/risk
        resp_risk = client.get("/api/risk")
        assert resp_risk.status_code == 200

        # GET /api/commits
        resp_commits = client.get("/api/commits")
        assert resp_commits.status_code == 200
