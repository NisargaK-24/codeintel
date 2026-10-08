import json
from pathlib import Path
from typer.testing import CliRunner

from codeintel.cli.app import app
from codeintel.git.repository import GitRepository

runner = CliRunner()
FIXTURE_REPO_PATH = str(Path(__file__).parent / "fixtures" / "sample_repo")


class TestCLI:
    """Test suite for Typer CLI commands and structured JSON output."""

    def test_cli_version(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.stdout

    def test_cli_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "scan" in result.stdout
        assert "graph" in result.stdout
        assert "zombie" in result.stdout
        assert "quality" in result.stdout
        assert "git" in result.stdout
        assert "impact" in result.stdout
        assert "analyze" in result.stdout

    def test_cli_scan_json(self):
        result = runner.invoke(app, ["scan", FIXTURE_REPO_PATH, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["repository"]["is_git"] is True
        assert data["stats"]["files_scanned"] >= 10

    def test_cli_graph_json(self):
        result = runner.invoke(app, ["graph", FIXTURE_REPO_PATH, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["total_nodes"] > 0
        assert data["total_edges"] > 0

    def test_cli_graph_symbol_json(self):
        sym = "orders.processor.OrderProcessor.checkout"
        result = runner.invoke(app, ["graph", FIXTURE_REPO_PATH, "--symbol", sym, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["symbol"] == sym
        assert "ascii_tree" in data

    def test_cli_zombie_json(self):
        result = runner.invoke(app, ["zombie", FIXTURE_REPO_PATH, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "candidates" in data
        assert data["total_functions_analyzed"] > 0

    def test_cli_quality_json(self):
        result = runner.invoke(app, ["quality", FIXTURE_REPO_PATH, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["total_issues"] > 0
        assert "issues" in data

    def test_cli_git_json(self):
        result = runner.invoke(app, ["git", FIXTURE_REPO_PATH, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["is_git"] is True
        assert len(data["commits"]) >= 2

    def test_cli_impact_json(self):
        git_repo = GitRepository(FIXTURE_REPO_PATH)
        head_commit = git_repo.get_commit_history()[0].hash

        result = runner.invoke(app, ["impact", FIXTURE_REPO_PATH, "--commit", head_commit, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["commit_hash"] == head_commit
        assert data["files_changed_count"] > 0
        assert "impact_radius" in data

    def test_cli_analyze_json(self):
        result = runner.invoke(app, ["analyze", FIXTURE_REPO_PATH, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "repository" in data
        assert "code_index_summary" in data
        assert "graph_summary" in data
        assert "zombie_summary" in data
        assert "quality_summary" in data
        assert "git_state" in data

    def test_cli_risk_json(self):
        result = runner.invoke(app, ["risk", FIXTURE_REPO_PATH, "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "total_commits_evaluated" in data
        assert "average_risk_score" in data
        assert len(data["commits"]) > 0

    def test_cli_risk_table(self):
        result = runner.invoke(app, ["risk", FIXTURE_REPO_PATH, "--limit", "2"])
        assert result.exit_code == 0
        assert "Predictive Commit Risk Summary" in result.stdout
