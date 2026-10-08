import pytest
from codeintel.ml.features import CommitFeatureExtractor, calculate_change_entropy
from codeintel.ml.risk_model import CommitRiskModel
from codeintel.models.git import ChangeType, FileChange, GitCommit
from codeintel.models.impact import ChangeImpact


def make_dummy_commit(h: str, msg: str, files: list[str], lines_add: int = 10, lines_del: int = 2) -> GitCommit:
    return GitCommit(
        hash=h,
        author_name="Dev",
        author_email="dev@test.com",
        timestamp=1700000000,
        message=msg,
        lines_added=lines_add,
        lines_deleted=lines_del,
        files_changed=len(files),
        changes=[
            FileChange(
                file_path=fp,
                change_type=ChangeType.MODIFIED,
                lines_added=lines_add // max(1, len(files)),
                lines_deleted=lines_del // max(1, len(files)),
                modified_line_ranges=[(1, 10)]
            )
            for fp in files
        ]
    )


class TestMLComponents:
    """Test suite for machine learning feature extraction and local risk classifier."""

    def test_shannon_entropy_calculation(self):
        # Single file has zero entropy
        assert calculate_change_entropy(["src/a.py"]) == 0.0

        # Files in the same folder have 0 entropy
        assert calculate_change_entropy(["src/models/a.py", "src/models/b.py"]) == 0.0

        # Files across different folders have high entropy
        multi_dir_entropy = calculate_change_entropy([
            "src/models/a.py",
            "src/views/b.py",
            "src/controllers/c.py",
            "src/utils/d.py"
        ])
        assert multi_dir_entropy > 1.5

    def test_commit_feature_extractor(self):
        extractor = CommitFeatureExtractor()
        commit = make_dummy_commit("c123", "fix bug in auth", ["src/auth.py", "src/db.py"], 80, 20)
        impact = ChangeImpact(
            commit_hash="c123",
            files_changed_count=2,
            symbols_changed_count=3,
            directly_affected_count=2,
            indirectly_affected_count=4,
            impact_radius=6,
            changed_files=["src/auth.py", "src/db.py"],
            changed_symbols=["auth.login"],
            critical_components=["auth.login"]
        )

        features = extractor.extract_features(commit, impact, author_commit_count=5)

        assert features["total_churn"] == 100.0
        assert features["files_changed_count"] == 2.0
        assert features["blast_radius"] == 6.0
        assert features["critical_components_count"] == 1.0
        assert features["author_experience_commits"] == 5.0

        vec = extractor.features_to_vector(features)
        assert len(vec) == len(CommitFeatureExtractor.FEATURE_NAMES)
        assert vec[0] == 80.0  # lines_added

    def test_commit_risk_model_training_and_prediction(self):
        model = CommitRiskModel()
        assert not model.is_trained

        commits = [
            make_dummy_commit("c1", "fix: critical security bug", ["src/auth.py"], 250, 80),
            make_dummy_commit("c2", "docs: update readme", ["README.md"], 5, 0),
            make_dummy_commit("c3", "feat: new dashboard", ["src/ui.py", "src/api.py"], 400, 10),
            make_dummy_commit("c4", "hotfix: resolve crash", ["src/core.py"], 30, 10),
            make_dummy_commit("c5", "style: format code", ["src/utils.py"], 12, 12)
        ]

        result = model.train_on_commits(commits)
        assert result["trained"] is True
        assert model.is_trained

        # Test prediction on high-churn bug fix
        features_high = {
            "lines_added": 600.0,
            "lines_deleted": 150.0,
            "total_churn": 750.0,
            "files_changed_count": 8.0,
            "file_entropy": 2.1,
            "blast_radius": 20.0,
            "critical_components_count": 3.0,
            "author_experience_commits": 1.0
        }
        prob_high, top_feats_high = model.predict_defect_probability(features_high)
        assert 0.0 <= prob_high <= 1.0
        assert len(top_feats_high) > 0

        # Test prediction on trivial documentation change
        features_low = {
            "lines_added": 2.0,
            "lines_deleted": 0.0,
            "total_churn": 2.0,
            "files_changed_count": 1.0,
            "file_entropy": 0.0,
            "blast_radius": 0.0,
            "critical_components_count": 0.0,
            "author_experience_commits": 50.0
        }
        prob_low, _ = model.predict_defect_probability(features_low)
        assert prob_low < prob_high
