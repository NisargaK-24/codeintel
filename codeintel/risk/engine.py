from typing import Any, Dict, List, Optional
from codeintel.ml.features import CommitFeatureExtractor
from codeintel.ml.risk_model import CommitRiskModel
from codeintel.models.code import CodeIndex
from codeintel.models.git import GitCommit
from codeintel.models.impact import ChangeImpact
from codeintel.models.quality import QualityReport, Severity
from codeintel.models.risk import (
    CommitRiskReport, RepositoryRiskSummary, RiskFactor, RiskTier
)


class CommitRiskEngine:
    """
    Intelligent Predictive Commit Risk Analysis Engine.
    Combines multi-factor software metrics (churn, blast radius, cyclomatic complexity,
    change entropy, defect density) with a local Random Forest ML model.
    """

    def __init__(self, ml_model: Optional[CommitRiskModel] = None):
        self.ml_model = ml_model or CommitRiskModel()
        self.extractor = CommitFeatureExtractor()

    def evaluate_commit(
        self,
        commit: GitCommit,
        impact: Optional[ChangeImpact] = None,
        code_index: Optional[CodeIndex] = None,
        quality_report: Optional[QualityReport] = None,
        author_commit_count: int = 1
    ) -> CommitRiskReport:
        """
        Evaluate full multi-dimensional risk for a given commit.
        """
        factors: List[RiskFactor] = []
        recommendations: List[str] = []
        rule_score = 0.0

        # Extract features
        features = self.extractor.extract_features(commit, impact, author_commit_count)
        total_churn = features["total_churn"]
        files_count = features["files_changed_count"]
        entropy = features["file_entropy"]
        blast_radius = features["blast_radius"]
        critical_count = features["critical_components_count"]

        # 1. Churn Factor (0 - 25 pts)
        if total_churn > 500:
            factors.append(RiskFactor(
                name="MASSIVE_CHURN",
                score_contribution=20.0,
                description=f"Massive code churn ({int(total_churn)} lines added/deleted) increases error injection likelihood",
                category="churn"
            ))
            rule_score += 20.0
            recommendations.append("Break down large commit (>500 lines) into smaller, reviewable logical units.")
        elif total_churn > 200:
            factors.append(RiskFactor(
                name="HIGH_CHURN",
                score_contribution=12.0,
                description=f"High code churn ({int(total_churn)} lines modified)",
                category="churn"
            ))
            rule_score += 12.0

        if files_count >= 8:
            factors.append(RiskFactor(
                name="BROAD_FILE_IMPACT",
                score_contribution=10.0,
                description=f"Commit modifies {int(files_count)} distinct files across repository",
                category="churn"
            ))
            rule_score += 10.0
            recommendations.append(f"Verify cross-file side effects across {int(files_count)} modified files.")
        elif files_count >= 4:
            rule_score += 5.0

        # 2. Blast Radius & Downstream Ripple (0 - 30 pts)
        if blast_radius >= 15:
            factors.append(RiskFactor(
                name="CRITICAL_BLAST_RADIUS",
                score_contribution=25.0,
                description=f"Extensive blast radius affecting {int(blast_radius)} downstream caller functions",
                category="impact"
            ))
            rule_score += 25.0
            recommendations.append(f"Execute comprehensive regression tests covering {int(blast_radius)} transitively affected callers.")
        elif blast_radius >= 5:
            factors.append(RiskFactor(
                name="ELEVATED_BLAST_RADIUS",
                score_contribution=15.0,
                description=f"Blast radius touches {int(blast_radius)} callers in call graph",
                category="impact"
            ))
            rule_score += 15.0

        if critical_count > 0:
            factors.append(RiskFactor(
                name="CRITICAL_COMPONENTS_TOUCHED",
                score_contribution=15.0,
                description=f"Changes affect {int(critical_count)} high-centrality components with fan-in >= 2",
                category="impact"
            ))
            rule_score += 15.0
            recommendations.append("Require two senior peer reviewers before merging changes to high fan-in core components.")

        # 3. Change Entropy / Subsystem Dispersion (0 - 15 pts)
        if entropy >= 1.5:
            factors.append(RiskFactor(
                name="HIGH_CHANGE_ENTROPY",
                score_contribution=15.0,
                description=f"High change entropy ({entropy:.2f}) indicates modifications scattered across decoupled subsystems",
                category="entropy"
            ))
            rule_score += 15.0
            recommendations.append("Review whether cross-subsystem changes introduce unintentional architectural coupling.")
        elif entropy >= 0.8:
            rule_score += 7.0

        # 4. Structural Complexity (0 - 20 pts)
        high_complexity_count = 0
        if code_index and impact:
            for sym_name in impact.changed_symbols:
                func = code_index.functions.get(sym_name)
                if func and getattr(func, "cyclomatic_complexity", 1) >= 12:
                    high_complexity_count += 1

        if high_complexity_count >= 2:
            factors.append(RiskFactor(
                name="COMPLEX_SYMBOLS_MODIFIED",
                score_contribution=15.0,
                description=f"Changes touch {high_complexity_count} functions with McCabe complexity >= 12",
                category="complexity"
            ))
            rule_score += 15.0
            recommendations.append(f"Add targeted branch coverage unit tests for {high_complexity_count} complex functions.")
        elif high_complexity_count == 1:
            rule_score += 8.0

        # 5. Defect Density in Changed Files (0 - 15 pts)
        changed_file_set = {fc.file_path.replace("\\", "/") for fc in commit.changes}
        quality_issues_in_commit = 0
        high_severity_in_commit = 0

        if quality_report:
            for issue in quality_report.issues:
                issue_path = issue.file.replace("\\", "/")
                if any(issue_path == cf or issue_path.endswith(cf) or cf.endswith(issue_path) for cf in changed_file_set):
                    quality_issues_in_commit += 1
                    if issue.severity == Severity.HIGH:
                        high_severity_in_commit += 1

        if high_severity_in_commit > 0:
            factors.append(RiskFactor(
                name="HIGH_SEVERITY_DEFECT_DETECTED",
                score_contribution=15.0,
                description=f"{high_severity_in_commit} high-severity code quality/security defect(s) detected in changed files",
                category="quality"
            ))
            rule_score += 15.0
            recommendations.append("Resolve high-severity static quality/security defects before committing.")
        elif quality_issues_in_commit >= 3:
            rule_score += 7.0

        # 6. ML Defect Probability (0.0 to 1.0)
        ml_prob, _ = self.ml_model.predict_defect_probability(features)

        # Blend rule score (0-100) and ML prediction (0-100)
        bounded_rule_score = min(100.0, max(0.0, rule_score))
        final_score = round(0.65 * bounded_rule_score + 0.35 * (ml_prob * 100.0), 1)
        final_score = min(100.0, max(0.0, final_score))

        # Determine Tier
        if final_score >= 75.0:
            tier = RiskTier.CRITICAL
        elif final_score >= 50.0:
            tier = RiskTier.HIGH
        elif final_score >= 25.0:
            tier = RiskTier.MEDIUM
        else:
            tier = RiskTier.LOW

        if not recommendations:
            recommendations.append("Standard peer review recommended. No critical risk spikes detected.")

        author_str = getattr(commit, "author_name", None) or getattr(commit, "author", "Unknown")
        return CommitRiskReport(
            commit_hash=commit.hash,
            commit_message=commit.message or "(No commit message)",
            author=author_str,
            risk_score=final_score,
            risk_tier=tier,
            ml_defect_probability=ml_prob,
            churn_metrics={
                "lines_added": commit.lines_added,
                "lines_deleted": commit.lines_deleted,
                "total_churn": int(total_churn),
                "files_changed": int(files_count),
                "file_entropy": entropy
            },
            structural_metrics={
                "high_complexity_symbols_count": high_complexity_count
            },
            blast_radius_metrics={
                "blast_radius": int(blast_radius),
                "critical_components_count": int(critical_count)
            },
            quality_defect_metrics={
                "issues_in_changed_files": quality_issues_in_commit,
                "high_severity_issues": high_severity_in_commit
            },
            top_risk_factors=factors,
            recommendations=recommendations
        )

    def evaluate_repository_commits(
        self,
        commits: List[GitCommit],
        impact_analyzer: Optional[Any] = None,
        code_index: Optional[CodeIndex] = None,
        quality_report: Optional[QualityReport] = None
    ) -> RepositoryRiskSummary:
        """Evaluate a historical list of commits and generate aggregate risk summary."""
        reports: List[CommitRiskReport] = []
        author_history: Dict[str, int] = {}

        # Precompute author history
        for c in reversed(commits):
            a_key = getattr(c, "author_name", None) or getattr(c, "author", "Unknown")
            author_history[a_key] = author_history.get(a_key, 0) + 1

        for commit in commits:
            impact = impact_analyzer.analyze_commit(commit) if impact_analyzer else None
            a_key = getattr(commit, "author_name", None) or getattr(commit, "author", "Unknown")
            rep = self.evaluate_commit(
                commit=commit,
                impact=impact,
                code_index=code_index,
                quality_report=quality_report,
                author_commit_count=author_history.get(a_key, 1)
            )
            reports.append(rep)

        total_evaluated = len(reports)
        avg_score = round(sum(r.risk_score for r in reports) / total_evaluated, 1) if total_evaluated > 0 else 0.0
        high_count = sum(1 for r in reports if r.risk_tier == RiskTier.HIGH)
        critical_count = sum(1 for r in reports if r.risk_tier == RiskTier.CRITICAL)

        distribution = {
            RiskTier.LOW.value: sum(1 for r in reports if r.risk_tier == RiskTier.LOW),
            RiskTier.MEDIUM.value: sum(1 for r in reports if r.risk_tier == RiskTier.MEDIUM),
            RiskTier.HIGH.value: high_count,
            RiskTier.CRITICAL.value: critical_count,
        }

        return RepositoryRiskSummary(
            repository_path="",
            total_commits_evaluated=total_evaluated,
            average_risk_score=avg_score,
            high_risk_commits_count=high_count,
            critical_risk_commits_count=critical_count,
            risk_distribution=distribution,
            commits=reports
        )
