import math
from pathlib import Path
from typing import Any, Dict, List, Optional
from codeintel.models.git import GitCommit
from codeintel.models.impact import ChangeImpact


def calculate_change_entropy(file_paths: List[str]) -> float:
    """
    Calculate Shannon entropy of modifications across directory modules.
    H = - sum(p_i * log2(p_i)) where p_i is the proportion of changes in directory i.
    Higher entropy indicates changes scattered across multiple decoupled subsystems.
    """
    if not file_paths or len(file_paths) <= 1:
        return 0.0

    dir_counts: Dict[str, int] = {}
    for fp in file_paths:
        parts = Path(fp.replace("\\", "/")).parts
        dir_key = "/".join(parts[:-1]) if len(parts) > 1 else "root"
        dir_counts[dir_key] = dir_counts.get(dir_key, 0) + 1

    total = len(file_paths)
    entropy = 0.0
    for count in dir_counts.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)

    return round(entropy, 3)


class CommitFeatureExtractor:
    """Extracts numerical and categorical feature vectors for commit defect and risk prediction."""

    FEATURE_NAMES = [
        "lines_added",
        "lines_deleted",
        "total_churn",
        "files_changed_count",
        "file_entropy",
        "blast_radius",
        "directly_affected_count",
        "indirectly_affected_count",
        "critical_components_count",
        "file_types_count",
        "is_merge_commit",
        "author_experience_commits",
        "commit_message_length"
    ]

    def extract_features(
        self,
        commit: GitCommit,
        impact: Optional[ChangeImpact] = None,
        author_commit_count: int = 1
    ) -> Dict[str, float]:
        """Extract a structured feature dictionary for a given commit."""
        lines_added = float(commit.lines_added)
        lines_deleted = float(commit.lines_deleted)
        total_churn = lines_added + lines_deleted

        file_paths = [fc.file_path for fc in commit.changes]
        files_count = float(len(file_paths))
        entropy = calculate_change_entropy(file_paths)

        # File extensions / languages touched
        extensions = {Path(fp).suffix.lower() for fp in file_paths if Path(fp).suffix}
        file_types_count = float(len(extensions)) if extensions else 1.0

        # Impact / Blast radius metrics
        blast_radius = float(impact.impact_radius) if impact else 0.0
        directly_affected = float(impact.directly_affected_count) if impact else 0.0
        indirectly_affected = float(impact.indirectly_affected_count) if impact else 0.0
        critical_count = float(len(impact.critical_components)) if impact else 0.0

        is_merge = 1.0 if getattr(commit, "is_merge", False) or len(getattr(commit, "parent_hashes", [])) > 1 else 0.0
        author_exp = float(max(1, author_commit_count))
        msg_len = float(len(commit.message.strip()))

        return {
            "lines_added": lines_added,
            "lines_deleted": lines_deleted,
            "total_churn": total_churn,
            "files_changed_count": files_count,
            "file_entropy": entropy,
            "blast_radius": blast_radius,
            "directly_affected_count": directly_affected,
            "indirectly_affected_count": indirectly_affected,
            "critical_components_count": critical_count,
            "file_types_count": file_types_count,
            "is_merge_commit": is_merge,
            "author_experience_commits": author_exp,
            "commit_message_length": msg_len
        }

    def features_to_vector(self, features: Dict[str, float]) -> List[float]:
        """Convert feature dictionary to an ordered numerical vector."""
        return [features.get(name, 0.0) for name in self.FEATURE_NAMES]
