from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class EdgeType(str, Enum):
    """Relationship category between two graph nodes."""
    CALLS = "calls"
    IMPORTS = "imports"
    CONTAINS = "contains"
    INHERITS = "inherits"


class GraphNode(BaseModel):
    """Node in the multi-relational code dependency graph."""
    id: str = Field(description="Unique node identifier (usually qualified name or file path)")
    name: str = Field(description="Display name")
    kind: str = Field(description="Node type (function, method, class, module, file)")
    file_path: Optional[str] = Field(default=None, description="Source file path")
    line_number: Optional[int] = Field(default=None, description="Source line number")


class GraphEdge(BaseModel):
    """Directed edge in the code dependency graph."""
    source: str = Field(description="Source node ID")
    target: str = Field(description="Target node ID")
    edge_type: EdgeType = Field(default=EdgeType.CALLS, description="Relationship type")
    weight: float = Field(default=1.0, description="Edge weight")


class SymbolMetrics(BaseModel):
    """Topological and structural metrics for a specific symbol."""
    symbol: str = Field(description="Qualified name of the symbol")
    fan_in: int = Field(default=0, description="Incoming edge count (direct dependents/callers)")
    fan_out: int = Field(default=0, description="Outgoing edge count (direct dependencies/callees)")
    direct_callers: List[str] = Field(default_factory=list, description="Direct calling symbols")
    direct_callees: List[str] = Field(default_factory=list, description="Direct called symbols")
    transitive_callers_count: int = Field(default=0, description="Count of upstream transitive callers")
    transitive_callees_count: int = Field(default=0, description="Count of downstream transitive callees")
    is_in_cycle: bool = Field(default=False, description="Whether symbol participates in a circular dependency")


class GraphSummary(BaseModel):
    """Aggregate statistics for the entire dependency graph."""
    total_nodes: int = Field(default=0, description="Total nodes in graph")
    total_edges: int = Field(default=0, description="Total edges in graph")
    call_edges_count: int = Field(default=0, description="Number of caller->callee edges")
    import_edges_count: int = Field(default=0, description="Number of file/module import edges")
    cyclic_dependencies_count: int = Field(default=0, description="Number of detected cycles")
    cycles: List[List[str]] = Field(default_factory=list, description="Detected circular dependency loops")
