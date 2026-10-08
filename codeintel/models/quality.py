from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Severity classification for a static code quality issue."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class QualityIssue(BaseModel):
    """Specific code smell, defect, or standards violation discovered."""
    language: str = Field(default="Python", description="Programming language of the source file")
    file: str = Field(description="Source file path where issue occurred")
    line: int = Field(description="Line number in source file")
    rule_id: str = Field(description="Identifier of rule triggered (e.g. CQ001)")
    severity: Severity = Field(description="Issue severity level")
    message: str = Field(description="Description of the quality issue")
    actual_value: Optional[str] = Field(default=None, description="Actual measured value")
    threshold: Optional[str] = Field(default=None, description="Configured acceptable limit")


class QualityReport(BaseModel):
    """Aggregated static code quality report across the repository."""
    issues: List[QualityIssue] = Field(default_factory=list, description="All identified quality issues")
    average_complexity: float = Field(default=0.0, description="Mean McCabe cyclomatic complexity across functions")
    max_complexity: int = Field(default=0, description="Highest cyclomatic complexity found in any function")
    average_function_length: float = Field(default=0.0, description="Mean lines of code per function")
    total_issues: int = Field(default=0, description="Total count of issues discovered")
    high_severity_count: int = Field(default=0, description="Count of HIGH severity issues")
    medium_severity_count: int = Field(default=0, description="Count of MEDIUM severity issues")
    low_severity_count: int = Field(default=0, description="Count of LOW severity issues")
    issues_by_rule: Dict[str, int] = Field(default_factory=dict, description="Counts of issues grouped by rule ID")
