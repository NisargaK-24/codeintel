from pathlib import Path
from codeintel.graph.dependency_graph import DependencyGraph
from codeintel.graph.graph_analyzer import GraphAnalyzer
from codeintel.parser.analyzer import CodeAnalyzer
from codeintel.zombie.detector import ZombieDetector, is_magic_method, is_test_component

FIXTURE_REPO_PATH = Path(__file__).parent / "fixtures" / "sample_repo"


class TestZombieDetector:
    """Test suite for Potential Zombie Code heuristics, scoring, and false-positive shields."""

    @classmethod
    def setup_class(cls):
        analyzer = CodeAnalyzer()
        cls.index = analyzer.analyze_repository(FIXTURE_REPO_PATH)
        cls.graph = DependencyGraph()
        cls.graph.build_from_index(cls.index)
        cls.graph_analyzer = GraphAnalyzer(cls.graph)

    def test_known_unused_functions_detected(self):
        detector = ZombieDetector(min_score=50)
        report = detector.analyze(self.index, self.graph_analyzer)

        candidate_symbols = {c.symbol for c in report.candidates}
        assert "payment.service.unused_payment_helper" in candidate_symbols
        assert "payment.calculator.abandoned_calculation_utility" in candidate_symbols
        assert "orders.processor.unused_cart_cleaner" in candidate_symbols

    def test_known_used_functions_have_lower_suspicion(self):
        detector = ZombieDetector(min_score=50)
        report = detector.analyze(self.index, self.graph_analyzer)
        candidate_symbols = {c.symbol for c in report.candidates}

        # calculate_tax is called by PaymentService.calculate_payment and tested in test_payment.py
        # Therefore it should have active callers and test discounts, not appearing as high candidate
        for c in report.candidates:
            if c.symbol == "payment.service.calculate_tax":
                assert any("ACTIVE_CALLERS" in e.rule_name for e in c.evidence)

    def test_entry_points_shielded(self):
        detector = ZombieDetector(min_score=10)  # low threshold
        report = detector.analyze(self.index, self.graph_analyzer)

        main_candidate = next((c for c in report.candidates if c.symbol == "api.entrypoint.main"), None)
        if main_candidate:
            assert any(e.rule_name == "ENTRY_POINT_INDICATOR" for e in main_candidate.evidence)
            assert any(e.score_delta < 0 for e in main_candidate.evidence)

    def test_magic_methods_immune(self):
        assert is_magic_method("__init__") is True
        assert is_magic_method("__str__") is True
        assert is_magic_method("__repr__") is True
        assert is_magic_method("not_magic") is False

        detector = ZombieDetector(min_score=0)
        report = detector.analyze(self.index, self.graph_analyzer)
        candidate_names = [c.symbol.split(".")[-1] for c in report.candidates]
        assert "__init__" not in candidate_names

    def test_test_functions_immune(self):
        assert is_test_component("tests/test_payment.py", "test_calculate_tax") is True
        assert is_test_component("payment/service.py", "calculate_tax") is False

        detector = ZombieDetector(min_score=0)
        report = detector.analyze(self.index, self.graph_analyzer)
        candidate_symbols = {c.symbol for c in report.candidates}
        assert "tests.test_payment.test_calculate_tax" not in candidate_symbols
        assert "tests.test_payment.test_payment_service" not in candidate_symbols
