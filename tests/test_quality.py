from pathlib import Path
from codeintel.models.quality import Severity
from codeintel.parser.analyzer import CodeAnalyzer
from codeintel.quality.analyzer import QualityAnalyzer

FIXTURE_REPO_PATH = Path(__file__).parent / "fixtures" / "sample_repo"


class TestQuality:
    """Test suite for static code quality rules, metrics, and secret detection."""

    @classmethod
    def setup_class(cls):
        analyzer = CodeAnalyzer()
        cls.index = analyzer.analyze_repository(FIXTURE_REPO_PATH)
        quality_analyzer = QualityAnalyzer()
        cls.report = quality_analyzer.analyze(cls.index, FIXTURE_REPO_PATH)

    def test_unused_imports(self):
        cq001_issues = [i for i in self.report.issues if i.rule_id == "CQ001"]
        unused_symbols = {i.actual_value for i in cq001_issues}
        assert "math" in unused_symbols
        assert "sys" in unused_symbols

    def test_function_length_rule(self):
        cq002_issues = [i for i in self.report.issues if i.rule_id == "CQ002"]
        assert len(cq002_issues) >= 1
        assert any("very_lengthy_processing_function" in i.message for i in cq002_issues)

    def test_excessive_parameters_rule(self):
        cq003_issues = [i for i in self.report.issues if i.rule_id == "CQ003"]
        assert any("configure_system" in i.message for i in cq003_issues)

    def test_cyclomatic_complexity_rule(self):
        cq004_issues = [i for i in self.report.issues if i.rule_id == "CQ004"]
        assert any("evaluate_complex_rules" in i.message for i in cq004_issues)
        assert self.report.max_complexity >= 10

    def test_deep_nesting_rule(self):
        cq005_issues = [i for i in self.report.issues if i.rule_id == "CQ005"]
        assert len(cq005_issues) >= 1
        assert any("helpers.py" in i.file for i in cq005_issues)

    def test_naming_convention_violations(self):
        cq006_issues = [i for i in self.report.issues if i.rule_id == "CQ006"]
        assert any("badNamingStyleFunction" in i.message for i in cq006_issues)

    def test_missing_docstrings(self):
        cq007_issues = [i for i in self.report.issues if i.rule_id == "CQ007"]
        assert any("undocumented_public_function" in i.message for i in cq007_issues)

    def test_hardcoded_secrets_detection(self):
        cq008_issues = [i for i in self.report.issues if i.rule_id == "CQ008"]
        assert len(cq008_issues) >= 1
        assert any(i.severity == Severity.HIGH for i in cq008_issues)
        assert any("Hardcoded API key" in i.message for i in cq008_issues)

    def test_aggregate_quality_metrics(self):
        assert self.report.total_issues > 0
        assert self.report.high_severity_count >= 1
        assert self.report.medium_severity_count >= 1
        assert self.report.average_complexity > 1.0
        assert self.report.average_function_length > 1.0
