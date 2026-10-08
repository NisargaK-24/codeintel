from pathlib import Path
from codeintel.graph.dependency_graph import DependencyGraph
from codeintel.graph.graph_analyzer import GraphAnalyzer
from codeintel.models.code import CallInfo, CodeIndex, FunctionInfo
from codeintel.parser.analyzer import CodeAnalyzer

FIXTURE_REPO_PATH = Path(__file__).parent / "fixtures" / "sample_repo"


class TestGraph:
    """Test suite for NetworkX dependency and caller-callee graphs."""

    @classmethod
    def setup_class(cls):
        analyzer = CodeAnalyzer()
        cls.index = analyzer.analyze_repository(FIXTURE_REPO_PATH)
        cls.graph = DependencyGraph()
        cls.graph.build_from_index(cls.index)
        cls.analyzer = GraphAnalyzer(cls.graph)

    def test_direct_dependencies(self):
        callees = self.analyzer.get_direct_callees("orders.processor.OrderProcessor.process_order")
        assert any("apply_discount" in c for c in callees)

    def test_indirect_dependencies(self):
        # checkout -> process_order -> calculate_payment -> calculate_tax
        transitive = self.analyzer.get_transitive_callees("orders.processor.OrderProcessor.checkout")
        assert len(transitive) > 0
        assert "orders.processor.OrderProcessor.process_order" in transitive

    def test_fan_in_and_fan_out(self):
        checkout_metrics = self.analyzer.get_symbol_metrics("orders.processor.OrderProcessor.checkout")
        assert checkout_metrics.fan_out > 0

    def test_cycles_detection(self):
        # Build artificial cyclic graph
        mock_idx = CodeIndex()
        mock_idx.calls.append(CallInfo(caller_qualified_name="fn_a", callee_name="fn_b", resolved_callee="fn_b", line_number=1, file_path="a.py"))
        mock_idx.calls.append(CallInfo(caller_qualified_name="fn_b", callee_name="fn_c", resolved_callee="fn_c", line_number=2, file_path="b.py"))
        mock_idx.calls.append(CallInfo(caller_qualified_name="fn_c", callee_name="fn_a", resolved_callee="fn_a", line_number=3, file_path="c.py"))

        cyclic_graph = DependencyGraph()
        cyclic_graph.build_from_index(mock_idx)
        analyzer = GraphAnalyzer(cyclic_graph)
        cycles = analyzer.detect_cycles()

        assert len(cycles) == 1
        cycle = cycles[0]
        assert "fn_a" in cycle and "fn_b" in cycle and "fn_c" in cycle

    def test_dependency_paths(self):
        # In cyclic graph
        mock_idx = CodeIndex()
        mock_idx.calls.append(CallInfo(caller_qualified_name="start_fn", callee_name="mid_fn", resolved_callee="mid_fn", line_number=1, file_path="a.py"))
        mock_idx.calls.append(CallInfo(caller_qualified_name="mid_fn", callee_name="end_fn", resolved_callee="end_fn", line_number=2, file_path="b.py"))

        path_graph = DependencyGraph()
        path_graph.build_from_index(mock_idx)
        analyzer = GraphAnalyzer(path_graph)
        paths = analyzer.get_dependency_paths("start_fn", "end_fn")

        assert len(paths) == 1
        assert paths[0] == ["start_fn", "mid_fn", "end_fn"]
