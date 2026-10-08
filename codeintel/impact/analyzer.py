from typing import Dict, List, Optional, Set, Tuple
import networkx as nx

from codeintel.graph.graph_analyzer import GraphAnalyzer
from codeintel.models.code import CodeIndex, Symbol
from codeintel.models.git import FileChange, GitCommit
from codeintel.models.impact import AffectedComponent, ChangeImpact


def line_ranges_overlap(r1_start: int, r1_end: int, r2_start: int, r2_end: int) -> bool:
    """Check if two 1D line ranges overlap."""
    return max(r1_start, r2_start) <= min(r1_end, r2_end)


class ImpactAnalyzer:
    """Analyzes the blast radius and transitive ripple effects of commit changes."""

    def __init__(self, code_index: CodeIndex, graph_analyzer: GraphAnalyzer):
        self.code_index = code_index
        self.graph_analyzer = graph_analyzer
        self.call_subgraph = graph_analyzer.call_subgraph

    def analyze_commit(self, commit: GitCommit) -> ChangeImpact:
        """Calculate complete direct and transitive impact radius for a Git commit."""
        changed_files: List[str] = [fc.file_path for fc in commit.changes]
        changed_symbols: List[str] = []

        # 1. Map diff line ranges to AST symbols
        for fc in commit.changes:
            symbols_in_file = self._find_symbols_in_file(fc.file_path)
            for sym in symbols_in_file:
                # Check if any hunk overlaps with this symbol's line span
                if not fc.modified_line_ranges:
                    # If whole file changed or no specific hunks, all symbols in file considered modified
                    changed_symbols.append(sym.qualified_name)
                else:
                    for h_start, h_end in fc.modified_line_ranges:
                        if line_ranges_overlap(sym.line_number, sym.end_line_number, h_start, h_end):
                            changed_symbols.append(sym.qualified_name)
                            break

        changed_symbols = list(dict.fromkeys(changed_symbols))

        # 2. Track directly and indirectly affected components
        directly_affected: List[AffectedComponent] = []
        indirectly_affected: List[AffectedComponent] = []
        dependency_paths: Dict[str, List[str]] = {}
        visited_nodes: Set[str] = set(changed_symbols)

        # BFS / shortest-path traversal upstream in call graph
        for root_sym in changed_symbols:
            if not self.call_subgraph.has_node(root_sym):
                continue

            # Upstream ancestors (callers)
            upstream_callers = self.graph_analyzer.get_transitive_callers(root_sym)
            for caller in upstream_callers:
                if caller in visited_nodes:
                    continue

                # Find shortest path from caller down to root_sym (path of calls: caller -> ... -> root_sym)
                try:
                    path = nx.shortest_path(self.call_subgraph, source=caller, target=root_sym)
                except Exception:
                    path = [caller, root_sym]

                depth = len(path) - 1
                fan_in = self.graph_analyzer.get_fan_in(caller)
                file_path = self.code_index.symbols[caller].file_path if caller in self.code_index.symbols else ""

                affected = AffectedComponent(
                    symbol=caller,
                    file=file_path,
                    depth=depth,
                    relationship_type="calls",
                    dependency_path=path,
                    fan_in=fan_in,
                    importance_score=round(1.0 / depth + (fan_in * 0.2), 2)
                )

                dependency_paths[caller] = path
                visited_nodes.add(caller)

                if depth == 1:
                    directly_affected.append(affected)
                else:
                    indirectly_affected.append(affected)

        # 3. Identify highly connected / critical components (fan-in >= 2 or high importance)
        critical_components: List[str] = []
        for aff in directly_affected + indirectly_affected:
            if aff.fan_in >= 2:
                critical_components.append(aff.symbol)

        impact_radius = len(directly_affected) + len(indirectly_affected)

        return ChangeImpact(
            commit_hash=commit.hash,
            files_changed_count=len(changed_files),
            symbols_changed_count=len(changed_symbols),
            directly_affected_count=len(directly_affected),
            indirectly_affected_count=len(indirectly_affected),
            impact_radius=impact_radius,
            changed_files=changed_files,
            changed_symbols=changed_symbols,
            directly_affected=directly_affected,
            indirectly_affected=indirectly_affected,
            dependency_paths=dependency_paths,
            critical_components=critical_components
        )

    def _find_symbols_in_file(self, rel_path: str) -> List[Symbol]:
        """Collect all symbols defined within the specified file."""
        norm_path = rel_path.replace("\\", "/").lstrip("/")
        matching = []
        for qname, sym in self.code_index.symbols.items():
            sym_path = sym.file_path.replace("\\", "/").lstrip("/")
            if sym_path == norm_path or sym_path.endswith(norm_path) or norm_path.endswith(sym_path):
                # Don't include top-level module itself if functions/classes exist
                if sym.kind.value != "module":
                    matching.append(sym)
        return matching
