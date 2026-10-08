import ast
from pathlib import Path
from typing import Dict, List, Optional

from codeintel.config.settings import settings
from codeintel.models.code import CodeIndex
from codeintel.models.quality import QualityIssue, QualityReport, Severity
from codeintel.parser.tree_sitter_base import calculate_ts_nesting_depth
from codeintel.quality.rules import (
    check_class_complexity, check_cyclomatic_complexity, check_deep_nesting_python,
    check_excessive_parameters, check_function_length, check_hardcoded_secrets,
    check_missing_docstrings, check_naming_conventions, check_unused_imports
)
import tree_sitter_typescript as tst
import tree_sitter_javascript as tsj
from tree_sitter import Language, Parser


class QualityAnalyzer:
    """Orchestrates static code quality inspections, metric aggregation, and report generation."""

    def __init__(self):
        self._ts_parser = None
        self._js_parser = None

    def _get_ts_parser(self) -> Parser:
        if self._ts_parser is None:
            self._ts_parser = Parser(Language(tst.language_typescript()))
        return self._ts_parser

    def _get_js_parser(self) -> Parser:
        if self._js_parser is None:
            self._js_parser = Parser(Language(tsj.language()))
        return self._js_parser

    def analyze(self, index: CodeIndex, repo_root: Path) -> QualityReport:
        issues: List[QualityIssue] = []

        # 1. Unused imports
        issues.extend(check_unused_imports(index))

        # 2. Per-function checks: length, parameters, complexity
        all_funcs = list(index.functions.values())
        total_complexity = 0
        max_complexity = 0
        total_length = 0

        for func in all_funcs:
            total_complexity += func.cyclomatic_complexity
            if func.cyclomatic_complexity > max_complexity:
                max_complexity = func.cyclomatic_complexity
            total_length += func.length_lines

            # Rule checks
            issue_len = check_function_length(func)
            if issue_len:
                issues.append(issue_len)

            issue_params = check_excessive_parameters(func)
            if issue_params:
                issues.append(issue_params)

            issue_comp = check_cyclomatic_complexity(func)
            if issue_comp:
                issues.append(issue_comp)

        # 3. Class complexity
        for cls in index.classes.values():
            issue_cls = check_class_complexity(cls)
            if issue_cls:
                issues.append(issue_cls)

        # 4. Naming conventions
        issues.extend(check_naming_conventions(index))

        # 5. Missing docstrings
        issues.extend(check_missing_docstrings(index))

        # 6. File-level checks (deep nesting, secrets)
        limit = settings.max_nesting_depth
        for rel_file in index.files:
            file_path = repo_root / rel_file
            if not file_path.is_file():
                continue

            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    code = f.read()
            except OSError:
                continue

            # Determine language
            file_lang = "Python"
            if rel_file.endswith(".ts") or rel_file.endswith(".tsx"):
                file_lang = "TypeScript"
            elif rel_file.endswith(".js") or rel_file.endswith(".jsx"):
                file_lang = "JavaScript"

            # Hardcoded secrets
            issues.extend(check_hardcoded_secrets(code, rel_file, language=file_lang))

            # Deep nesting
            if file_lang == "Python":
                try:
                    tree = ast.parse(code, filename=str(file_path))
                    issues.extend(check_deep_nesting_python(tree, rel_file))
                except Exception:
                    pass
            elif file_lang in ("TypeScript", "JavaScript"):
                try:
                    parser = self._get_ts_parser() if file_lang == "TypeScript" else self._get_js_parser()
                    ts_tree = parser.parse(code.encode("utf-8"))
                    depth = calculate_ts_nesting_depth(ts_tree.root_node)
                    if depth > limit:
                        severity = Severity.HIGH if depth > limit + 2 else Severity.MEDIUM
                        issues.append(QualityIssue(
                            language=file_lang,
                            file=rel_file,
                            line=1,
                            rule_id="CQ005",
                            severity=severity,
                            message=f"Maximum block nesting depth of {depth} exceeds threshold of {limit}",
                            actual_value=str(depth),
                            threshold=str(limit)
                        ))
                except Exception:
                    pass

        # Calculate metrics
        func_count = len(all_funcs)
        avg_complexity = round(total_complexity / func_count, 2) if func_count > 0 else 0.0
        avg_length = round(total_length / func_count, 2) if func_count > 0 else 0.0

        high_count = sum(1 for i in issues if i.severity == Severity.HIGH)
        med_count = sum(1 for i in issues if i.severity == Severity.MEDIUM)
        low_count = sum(1 for i in issues if i.severity == Severity.LOW)

        issues_by_rule: Dict[str, int] = {}
        for i in issues:
            issues_by_rule[i.rule_id] = issues_by_rule.get(i.rule_id, 0) + 1

        return QualityReport(
            issues=issues,
            average_complexity=avg_complexity,
            max_complexity=max_complexity,
            average_function_length=avg_length,
            total_issues=len(issues),
            high_severity_count=high_count,
            medium_severity_count=med_count,
            low_severity_count=low_count,
            issues_by_rule=issues_by_rule
        )
