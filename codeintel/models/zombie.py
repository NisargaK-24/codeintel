from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class ConfidenceLevel(str, Enum):
    """Confidence tier for potential zombie code classification."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class EvidenceItem(BaseModel):
    """Specific piece of structural or heuristic evidence influencing suspicion score."""
    rule_name: str = Field(description="Name of rule evaluated")
    score_delta: float = Field(description="Points added or subtracted (-100 to +100)")
    reason: str = Field(description="Human-readable explanation of why this rule applied")
    category: str = Field(default="heuristic", description="Evidence category (e.g. callers, test, decorator, git)")


class ZombieCandidate(BaseModel):
    """Represents a function or method suspected of being potential zombie code."""
    symbol: str = Field(description="Qualified symbol name")
    file: str = Field(description="Source file containing symbol")
    score: float = Field(description="Suspicion score between 0.0 and 100.0")
    confidence: ConfidenceLevel = Field(description="Confidence level (LOW, MEDIUM, HIGH)")
    evidence: List[EvidenceItem] = Field(default_factory=list, description="Detailed evidence items")
    reasons: List[str] = Field(default_factory=list, description="Summary reasons explaining the score")
    line_number: Optional[int] = Field(default=None, description="Starting line number")
    is_public: bool = Field(default=True, description="Whether symbol is public")
    is_method: bool = Field(default=False, description="Whether symbol is a class method")


class ZombieReport(BaseModel):
    """Aggregated report of zombie code detection across the repository."""
    candidates: List[ZombieCandidate] = Field(default_factory=list, description="Detected potential zombie symbols")
    total_functions_analyzed: int = Field(default=0, description="Total functions and methods evaluated")
    potential_zombies_count: int = Field(default=0, description="Count of candidates exceeding threshold")
    high_confidence_count: int = Field(default=0, description="Count of HIGH confidence candidates")
