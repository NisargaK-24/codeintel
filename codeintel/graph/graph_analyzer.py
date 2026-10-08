from typing import Dict, List, Optional, Set
import networkx as nx

from codeintel.graph.dependency_graph import DependencyGraph
from codeintel.models.graph import EdgeType, SymbolMetrics


class GraphAnalyzer:
    """Analyzes call hierarchies, connectivity, fan-in/fan-out, and dependency paths."""

    def __init__(self, dep_graph: DependencyGraph):
        self.dep_graph = dep_graph
        self.nx_graph = dep_graph.nx_graph
        self._call_subgraph: Optional[nx.DiGraph] = None

    @property
    def call_subgraph(self) -> nx.DiGraph:
        """Cached subgraph consisting strictly of CALLS edges."""
        if self._call_subgraph is None:
            g = nx.DiGraph()
            for u, v, d in self.nx_graph.edges(data=True):
                if d.get("edge_type") == EdgeType.CALLS.value:
                    g.add_edge(u, v)
            # Ensure all graph nodes are present
            for node in self.nx_graph.nodes:
                if not g.has_node(node):
                    g.add_node(node)
            self._call_subgraph = g
        return self._call_subgraph

    def get_direct_callers(self, symbol: str) -> List[str]:
        """Find immediate callers (predecessors in call subgraph)."""
        if not self.call_subgraph.has_node(symbol):
            return []
        return list(self.call_subgraph.predecessors(symbol))

    def get_direct_callees(self, symbol: str) -> List[str]:
        """Find immediate callees (successors in call subgraph)."""
        if not self.call_subgraph.has_node(symbol):
            return []
        return list(self.call_subgraph.successors(symbol))

    def get_transitive_callers(self, symbol: str) -> Set[str]:
        """Find all upstream ancestors that directly or indirectly call this symbol."""
        if not self.call_subgraph.has_node(symbol):
            return set()
        try:
            return nx.ancestors(self.call_subgraph, symbol)
        except Exception:
            return set()

    def get_transitive_callees(self, symbol: str) -> Set[str]:
        """Find all downstream descendants that this symbol directly or indirectly calls."""
        if not self.call_subgraph.has_node(symbol):
            return set()
        try:
            return nx.descendants(self.call_subgraph, symbol)
        except Exception:
            return set()

    def get_fan_in(self, symbol: str) -> int:
        """Count incoming call edges."""
        if not self.call_subgraph.has_node(symbol):
            return 0
        return self.call_subgraph.in_degree(symbol)

    def get_fan_out(self, symbol: str) -> int:
        """Count outgoing call edges."""
        if not self.call_subgraph.has_node(symbol):
            return 0
        return self.call_subgraph.out_degree(symbol)

    def get_dependency_paths(self, source: str, target: str, max_paths: int = 5) -> List[List[str]]:
        """Find simple directed paths from source to target in call graph."""
        if not self.call_subgraph.has_node(source) or not self.call_subgraph.has_node(target):
            return []
        try:
            paths = []
            for path in nx.all_simple_paths(self.call_subgraph, source=source, target=target, cutoff=10):
                paths.append(path)
                if len(paths) >= max_paths:
                    break
            return paths
        except Exception:
            return []

    def detect_cycles(self) -> List[List[str]]:
        """Find circular call loops."""
        try:
            return list(nx.simple_cycles(self.call_subgraph))
        except Exception:
            return []

    def get_symbol_metrics(self, symbol: str) -> SymbolMetrics:
        """Gather complete structural metrics for a given symbol."""
        direct_callers = self.get_direct_callers(symbol)
        direct_callees = self.get_direct_callees(symbol)
        transitive_callers = self.get_transitive_callers(symbol)
        transitive_callees = self.get_transitive_callees(symbol)

        # Check if in cycle
        is_in_cycle = False
        for cycle in self.detect_cycles():
            if symbol in cycle:
                is_in_cycle = True
                break

        return SymbolMetrics(
            symbol=symbol,
            fan_in=len(direct_callers),
            fan_out=len(direct_callees),
            direct_callers=direct_callers,
            direct_callees=direct_callees,
            transitive_callers_count=len(transitive_callers),
            transitive_callees_count=len(transitive_callees),
            is_in_cycle=is_in_cycle
        )

    def render_ascii_tree(self, symbol: str, depth: int = 4, visited: Optional[Set[str]] = None) -> str:
        """Render a formatted ASCII representation of downstream callees."""
        if visited is None:
            visited = set()

        lines = [f"{symbol}()"]
        visited.add(symbol)

        def _build_tree(node: str, current_depth: int, prefix: str):
            if current_depth > depth:
                return
            callees = self.get_direct_callees(node)
            for idx, callee in enumerate(callees):
                is_last = (idx == len(callees) - 1)
                branch = "\\-- " if is_last else "+-- "
                next_prefix = prefix + ("    " if is_last else "|   ")

                if callee in visited:
                    lines.append(f"{prefix}{branch}{callee}() [recursion/cycle]")
                else:
                    lines.append(f"{prefix}{branch}{callee}()")
                    visited.add(callee)
                    _build_tree(callee, current_depth + 1, next_prefix)

        _build_tree(symbol, 1, "")
        return "\n".join(lines)
