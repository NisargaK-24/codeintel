from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class AffectedComponent(BaseModel):
    """A symbol or file impacted upstream by code changes."""
    symbol: str = Field(description="Qualified symbol name or file path of affected component")
    file: str = Field(description="File containing the affected component")
    depth: int = Field(default=1, description="Distance from origin change (1 = direct caller, 2+ = indirect)")
    relationship_type: str = Field(default="calls", description="Nature of linkage (calls, imports, inherits)")
    dependency_path: List[str] = Field(default_factory=list, description="Chain of calls/imports from change to component")
    fan_in: int = Field(default=0, description="Incoming edge count (dependent popularity)")
    importance_score: float = Field(default=0.0, description="Topological centrality or risk weighting")


class ChangeImpact(BaseModel):
    """Complete impact analysis report for a specific commit or diff."""
    commit_hash: str = Field(description="Analyzed commit hash or 'WORKING_TREE'")
    files_changed_count: int = Field(default=0, description="Total files changed")
    symbols_changed_count: int = Field(default=0, description="Total functions/classes directly modified")
    directly_affected_count: int = Field(default=0, description="Count of immediate dependents (depth 1)")
    indirectly_affected_count: int = Field(default=0, description="Count of transitive dependents (depth > 1)")
    impact_radius: int = Field(default=0, description="Total blast radius (directly + indirectly affected)")
    changed_files: List[str] = Field(default_factory=list, description="List of modified file paths")
    changed_symbols: List[str] = Field(default_factory=list, description="List of modified symbol names")
    directly_affected: List[AffectedComponent] = Field(default_factory=list, description="Immediate dependents")
    indirectly_affected: List[AffectedComponent] = Field(default_factory=list, description="Transitive dependents")
    dependency_paths: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Path trace explaining why each component is affected (component -> [step, ...])"
    )
    critical_components: List[str] = Field(
        default_factory=list,
        description="Highly connected components affected by this change"
    )
