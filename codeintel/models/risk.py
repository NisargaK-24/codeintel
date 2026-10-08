from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RiskTier(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskFactor(BaseModel):
    name: str
    score_contribution: float
    description: str
    category: str


class CommitRiskReport(BaseModel):
    commit_hash: str
    commit_message: str
    author: str
    risk_score: float = Field(ge=0.0, le=100.0)
    risk_tier: RiskTier
    ml_defect_probability: Optional[float] = None
    churn_metrics: Dict[str, Any] = Field(default_factory=dict)
    structural_metrics: Dict[str, Any] = Field(default_factory=dict)
    blast_radius_metrics: Dict[str, Any] = Field(default_factory=dict)
    quality_defect_metrics: Dict[str, Any] = Field(default_factory=dict)
    top_risk_factors: List[RiskFactor] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class RepositoryRiskSummary(BaseModel):
    repository_path: str
    total_commits_evaluated: int
    average_risk_score: float
    high_risk_commits_count: int
    critical_risk_commits_count: int
    risk_distribution: Dict[str, int] = Field(default_factory=dict)
    commits: List[CommitRiskReport] = Field(default_factory=list)
