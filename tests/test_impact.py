from pathlib import Path
from codeintel.git.repository import GitRepository
from codeintel.graph.dependency_graph import DependencyGraph
from codeintel.graph.graph_analyzer import GraphAnalyzer
from codeintel.impact.analyzer import ImpactAnalyzer
from codeintel.parser.analyzer import CodeAnalyzer

FIXTURE_REPO_PATH = Path(__file__).parent / "fixtures" / "sample_repo"


class TestImpactAnalysis:
    """Test suite for Change Impact Analysis and blast radius computation."""

    @classmethod
    def setup_class(cls):
        analyzer = CodeAnalyzer()
        cls.index = analyzer.analyze_repository(FIXTURE_REPO_PATH)
        cls.graph = DependencyGraph()
        cls.graph.build_from_index(cls.index)
        cls.graph_analyzer = GraphAnalyzer(cls.graph)
        cls.impact_analyzer = ImpactAnalyzer(cls.index, cls.graph_analyzer)
        cls.git_repo = GitRepository(FIXTURE_REPO_PATH)

    def test_impact_analysis_for_head_commit(self):
        commits = self.git_repo.get_commit_history()
        assert len(commits) >= 1
        head = commits[0]

        impact = self.impact_analyzer.analyze_commit(head)

        assert impact.files_changed_count == 1
        assert "payment/service.py" in impact.changed_files
        assert impact.symbols_changed_count > 0

        # Check directly affected symbols
        assert impact.directly_affected_count > 0
        direct_symbols = {aff.symbol for aff in impact.directly_affected}
        # OrderProcessor or test functions call PaymentService or calculate_tax
        assert any("test_payment" in s or "OrderProcessor" in s for s in direct_symbols)

        # Check total impact radius
        assert impact.impact_radius >= impact.directly_affected_count

        # Check dependency paths showing WHY components are affected
        assert len(impact.dependency_paths) > 0
        for component, path in impact.dependency_paths.items():
            assert len(path) >= 2
            assert path[0] == component
