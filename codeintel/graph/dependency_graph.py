from typing import Any, Dict, List, Optional
import networkx as nx

from codeintel.models.code import CodeIndex
from codeintel.models.graph import EdgeType, GraphEdge, GraphNode, GraphSummary


class DependencyGraph:
    """Multi-relational directed code dependency graph powered by NetworkX."""

    def __init__(self):
        self.nx_graph: nx.DiGraph = nx.DiGraph()

    def build_from_index(self, index: CodeIndex) -> None:
        """Populate the graph from parsed CodeIndex symbols, imports, classes, and calls."""
        self.nx_graph.clear()

        # 1. Add all symbols as nodes
        for qname, symbol in index.symbols.items():
            self.nx_graph.add_node(
                qname,
                name=symbol.name,
                kind=symbol.kind.value,
                file_path=symbol.file_path,
                line_number=symbol.line_number
            )

        # 2. Add containment edges (module contains class/function, class contains method)
        for qname, symbol in index.symbols.items():
            if symbol.parent_qualified_name and symbol.parent_qualified_name in self.nx_graph:
                self.nx_graph.add_edge(
                    symbol.parent_qualified_name,
                    qname,
                    edge_type=EdgeType.CONTAINS.value,
                    weight=1.0
                )

        # 3. Add inheritance edges (subclass -> base_class, class -> interface)
        for class_qname, class_info in index.classes.items():
            for base in class_info.base_classes:
                matched_base = None
                for candidate in index.classes:
                    if candidate == base or candidate.endswith(f".{base}"):
                        matched_base = candidate
                        break
                target = matched_base or base
                if not self.nx_graph.has_node(target):
                    self.nx_graph.add_node(target, name=base, kind="class", file_path=None, line_number=None)
                self.nx_graph.add_edge(
                    class_qname,
                    target,
                    edge_type=EdgeType.INHERITS.value,
                    weight=1.0
                )

            # Implemented interfaces (TypeScript)
            for iface in class_info.implemented_interfaces:
                matched_iface = None
                for candidate in index.interfaces:
                    if candidate == iface or candidate.endswith(f".{iface}"):
                        matched_iface = candidate
                        break
                target = matched_iface or iface
                if not self.nx_graph.has_node(target):
                    self.nx_graph.add_node(target, name=iface, kind="interface", file_path=None, line_number=None)
                self.nx_graph.add_edge(
                    class_qname,
                    target,
                    edge_type=EdgeType.INHERITS.value,
                    weight=1.0
                )

        # 4. Add import edges (importing_module -> imported_module or symbol)
        for imp in index.imports:
            src_file = imp.file_path
            src_mod = None
            for qname, sym in index.symbols.items():
                if sym.kind.value == "module" and sym.file_path == src_file:
                    src_mod = qname
                    break
            if not src_mod:
                src_mod = imp.file_path

            # Target module: if resolved, find module for resolved_path
            target_mod = None
            if imp.is_resolved and imp.resolved_path:
                for qname, sym in index.symbols.items():
                    if sym.kind.value == "module" and sym.file_path == imp.resolved_path:
                        target_mod = qname
                        break

            target = target_mod or (f"{imp.module}.{imp.imported_name}" if imp.is_from else imp.module)
            if not self.nx_graph.has_node(src_mod):
                self.nx_graph.add_node(src_mod, name=src_mod.split(".")[-1], kind="module", file_path=src_file, line_number=None)
            if not self.nx_graph.has_node(target):
                self.nx_graph.add_node(target, name=target.split(".")[-1], kind="external", file_path=None, line_number=None)

            self.nx_graph.add_edge(
                src_mod,
                target,
                edge_type=EdgeType.IMPORTS.value,
                weight=1.0
            )

        # 5. Add call edges (caller -> callee)
        for call in index.calls:
            caller = call.caller_qualified_name
            callee = call.resolved_callee or call.callee_name

            if not self.nx_graph.has_node(caller):
                self.nx_graph.add_node(caller, name=caller.split(".")[-1], kind="function", file_path=call.file_path, line_number=call.line_number)
            if not self.nx_graph.has_node(callee):
                self.nx_graph.add_node(callee, name=callee.split(".")[-1], kind="function", file_path=None, line_number=None)

            self.nx_graph.add_edge(
                caller,
                callee,
                edge_type=EdgeType.CALLS.value,
                weight=1.0
            )

    def get_summary(self) -> GraphSummary:
        """Compute aggregate graph metrics and cycles."""
        call_edges = sum(1 for _, _, d in self.nx_graph.edges(data=True) if d.get("edge_type") == EdgeType.CALLS.value)
        import_edges = sum(1 for _, _, d in self.nx_graph.edges(data=True) if d.get("edge_type") == EdgeType.IMPORTS.value)

        # Detect cycles in the call graph subgraph
        call_subgraph = nx.DiGraph()
        for u, v, d in self.nx_graph.edges(data=True):
            if d.get("edge_type") == EdgeType.CALLS.value:
                call_subgraph.add_edge(u, v)

        cycles: List[List[str]] = []
        try:
            cycles = list(nx.simple_cycles(call_subgraph))
        except Exception:
            pass

        return GraphSummary(
            total_nodes=self.nx_graph.number_of_nodes(),
            total_edges=self.nx_graph.number_of_edges(),
            call_edges_count=call_edges,
            import_edges_count=import_edges,
            cyclic_dependencies_count=len(cycles),
            cycles=cycles
        )
