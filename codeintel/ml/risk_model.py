import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

try:
    from sklearn.ensemble import RandomForestClassifier
    import joblib
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

from codeintel.ml.features import CommitFeatureExtractor

# Heuristic regex matching bug-fix / defect-remedy commit messages
BUG_FIX_PATTERN = re.compile(
    r"\b(fix|fixed|fixes|bug|patch|hotfix|crash|error|issue|defect|regression|revert|resolve|broken)\b",
    re.IGNORECASE
)


class CommitRiskModel:
    """
    Local Machine Learning model for predictive commit risk and defect likelihood.
    Trained strictly locally on repository commit history software metrics without external APIs or LLMs.
    """

    def __init__(self, model_path: Optional[Path] = None):
        self.extractor = CommitFeatureExtractor()
        self.model_path = model_path
        self._clf: Optional[Any] = None
        self._is_trained = False
        self._feature_importances: Dict[str, float] = {}

        if model_path and model_path.exists() and HAS_SKLEARN:
            self.load(model_path)

    @property
    def is_trained(self) -> bool:
        return self._is_trained

    def train_on_commits(
        self,
        commits: List[Any],
        impacts: Optional[Dict[str, Any]] = None,
        author_history: Optional[Dict[str, int]] = None
    ) -> Dict[str, Any]:
        """
        Train the model locally on extracted commit features using SZZ-inspired bug-fix labeling.
        """
        if not commits:
            return {"trained": False, "reason": "No commits provided"}

        X_list: List[List[float]] = []
        y_list: List[int] = []

        # Collect features and heuristic labels
        for commit in commits:
            imp = impacts.get(commit.hash) if impacts else None
            author_exp = author_history.get(commit.author, 1) if author_history else 1
            feat = self.extractor.extract_features(commit, imp, author_exp)
            vec = self.extractor.features_to_vector(feat)
            X_list.append(vec)

            # SZZ-inspired heuristic: Commits addressing bugs or high-churn hotfixes are positive samples
            msg = commit.message or ""
            is_fix = bool(BUG_FIX_PATTERN.search(msg))
            total_churn = feat.get("total_churn", 0.0)
            blast = feat.get("blast_radius", 0.0)

            # Label 1 (risky/defect-prone) if fixing a prior bug or large unreviewed blast radius
            label = 1 if (is_fix or (total_churn > 300 and blast > 5)) else 0
            y_list.append(label)

        # Ensure both classes exist for training stability
        if sum(y_list) == 0:
            y_list[0] = 1
        elif sum(y_list) == len(y_list):
            y_list[0] = 0

        X = np.array(X_list, dtype=np.float32)
        y = np.array(y_list, dtype=np.int32)

        if HAS_SKLEARN:
            self._clf = RandomForestClassifier(
                n_estimators=50,
                max_depth=5,
                random_state=42,
                class_weight="balanced"
            )
            self._clf.fit(X, y)
            self._is_trained = True

            # Extract feature importances
            importances = self._clf.feature_importances_
            self._feature_importances = {
                name: round(float(imp), 4)
                for name, imp in zip(self.extractor.FEATURE_NAMES, importances)
            }
        else:
            self._is_trained = True
            # Default heuristic weights
            self._feature_importances = {
                "total_churn": 0.25,
                "blast_radius": 0.25,
                "file_entropy": 0.15,
                "files_changed_count": 0.15,
                "author_experience_commits": 0.10,
                "critical_components_count": 0.10
            }

        return {
            "trained": True,
            "sample_count": len(commits),
            "defect_samples": int(sum(y_list)),
            "feature_importances": self._feature_importances
        }

    def predict_defect_probability(self, features: Dict[str, float]) -> Tuple[float, List[Tuple[str, float]]]:
        """
        Predict probability (0.0 to 1.0) of this commit introducing a defect or regression.
        Returns (probability, top_contributing_features).
        """
        vec = self.extractor.features_to_vector(features)

        if self._is_trained and HAS_SKLEARN and self._clf is not None:
            X = np.array([vec], dtype=np.float32)
            proba = float(self._clf.predict_proba(X)[0][1])
        else:
            # Resilient statistical sigmoid scoring fallback
            churn = features.get("total_churn", 0.0)
            blast = features.get("blast_radius", 0.0)
            entropy = features.get("file_entropy", 0.0)
            files = features.get("files_changed_count", 1.0)
            exp = features.get("author_experience_commits", 1.0)

            raw_score = (
                min(churn / 400.0, 1.0) * 0.35 +
                min(blast / 15.0, 1.0) * 0.30 +
                min(entropy / 2.5, 1.0) * 0.15 +
                min(files / 10.0, 1.0) * 0.10 +
                max(0.0, 1.0 - (exp / 20.0)) * 0.10
            )
            proba = round(min(1.0, max(0.0, raw_score)), 3)

        # Identify top contributing factors for this prediction
        contributions: List[Tuple[str, float]] = []
        for name in self.extractor.FEATURE_NAMES:
            val = features.get(name, 0.0)
            weight = self._feature_importances.get(name, 0.05)
            impact_val = val * weight
            if impact_val > 0:
                contributions.append((name, round(float(impact_val), 3)))

        contributions.sort(key=lambda x: x[1], reverse=True)

        return round(proba, 3), contributions[:5]

    def save(self, path: Path) -> None:
        """Persist trained model weights to disk."""
        if HAS_SKLEARN and self._clf:
            path.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump({"model": self._clf, "importances": self._feature_importances}, str(path))

    def load(self, path: Path) -> None:
        """Load trained model weights from disk."""
        if HAS_SKLEARN and path.exists():
            data = joblib.load(str(path))
            self._clf = data.get("model")
            self._feature_importances = data.get("importances", {})
            self._is_trained = True
