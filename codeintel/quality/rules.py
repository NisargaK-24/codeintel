import ast
import re
from pathlib import Path
from typing import List, Optional, Set

from codeintel.config.settings import settings
from codeintel.models.code import ClassInfo, CodeIndex, FunctionInfo, MethodInfo
from codeintel.models.quality import QualityIssue, Severity

# Regex patterns for detecting hardcoded secrets, passwords, tokens, and keys
SECRET_PATTERNS = [
    (re.compile(r"""(?:api[_-]?key|apikey)\s*[:=]\s*['"][a-zA-Z0-9_\-]{16,}['"]""", re.IGNORECASE), "Hardcoded API key detected"),
    (re.compile(r"""(?:password|passwd|pwd)\s*[:=]\s*['"][^'"]{4,}['"]""", re.IGNORECASE), "Hardcoded password assignment detected"),
    (re.compile(r"""(?:secret[_-]?key|client[_-]?secret)\s*[:=]\s*['"][a-zA-Z0-9_\-]{16,}['"]""", re.IGNORECASE), "Hardcoded secret key detected"),
    (re.compile(r"""(?:access[_-]?token|bearer[_-]?token|auth[_-]?token)\s*[:=]\s*['"][a-zA-Z0-9_\-\.]{16,}['"]""", re.IGNORECASE), "Hardcoded auth/bearer token detected"),
    (re.compile(r"""AKIA[0-9A-Z]{16}"""), "AWS Access Key ID pattern detected"),
    (re.compile(r"""-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"""), "Hardcoded private key certificate detected"),
]

SNAKE_CASE_PATTERN = re.compile(r"^_?[a-z][a-z0-9_]*$")
PASCAL_CASE_PATTERN = re.compile(r"^[A-Z][a-zA-Z0-9]*$")
CAMEL_CASE_PATTERN = re.compile(r"^[a-z][a-zA-Z0-9]*$")


def check_unused_imports(index: CodeIndex) -> List[QualityIssue]:
    """Rule CQ001: Identify imports declared but never referenced in file body."""
    issues: List[QualityIssue] = []

    # Group imports by file
    imports_by_file: dict[str, list] = {}
    for imp in index.imports:
        imports_by_file.setdefault(imp.file_path, []).append(imp)

    # Group references by file
    refs_by_file: dict[str, Set[str]] = {}
    for ref in index.references:
        refs_by_file.setdefault(ref.file_path, set()).add(ref.symbol_name)

    for file_path, file_imports in imports_by_file.items():
        # Skip package index files as they often re-export symbols
        if file_path.endswith("__init__.py") or file_path.endswith("/index.ts") or file_path.endswith("/index.js"):
            continue

        file_refs = refs_by_file.get(file_path, set())

        for imp in file_imports:
            # Skip side-effect or namespace imports
            if imp.is_namespace or imp.imported_name in ("*", "React"):
                continue

            symbol_to_check = imp.alias or imp.imported_name
            if not imp.is_from and "." in symbol_to_check:
                symbol_to_check = symbol_to_check.split(".")[0]

            if symbol_to_check not in file_refs:
                issues.append(QualityIssue(
                    language=imp.language,
                    file=file_path,
                    line=imp.line_number,
                    rule_id="CQ001",
                    severity=Severity.MEDIUM,
                    message=f"Import '{imp.imported_name}' is unused in {file_path}",
                    actual_value=symbol_to_check,
                    threshold="0 references"
                ))

    return issues


def check_function_length(func: FunctionInfo | MethodInfo) -> Optional[QualityIssue]:
    """Rule CQ002: Function exceeds recommended line length limit."""
    limit = settings.max_function_length
    if func.length_lines > limit:
        severity = Severity.HIGH if func.length_lines > limit * 2 else Severity.MEDIUM
        return QualityIssue(
            language=getattr(func, "language", "Python"),
            file=func.file_path,
            line=func.line_number,
            rule_id="CQ002",
            severity=severity,
            message=f"Function '{func.name}' length ({func.length_lines} lines) exceeds threshold ({limit} lines)",
            actual_value=str(func.length_lines),
            threshold=str(limit)
        )
    return None


def check_excessive_parameters(func: FunctionInfo | MethodInfo) -> Optional[QualityIssue]:
    """Rule CQ003: Function has too many arguments/parameters."""
    limit = settings.max_function_params
    # Exclude standard receivers ('self', 'cls', 'this')
    params = [p for p in func.parameters if p not in ("self", "cls", "this")]
    if len(params) > limit:
        severity = Severity.HIGH if len(params) > limit + 3 else Severity.MEDIUM
        return QualityIssue(
            language=getattr(func, "language", "Python"),
            file=func.file_path,
            line=func.line_number,
            rule_id="CQ003",
            severity=severity,
            message=f"Function '{func.name}' has {len(params)} parameters, exceeding limit of {limit}",
            actual_value=str(len(params)),
            threshold=str(limit)
        )
    return None


def check_cyclomatic_complexity(func: FunctionInfo | MethodInfo) -> Optional[QualityIssue]:
    """Rule CQ004: Function exceeds McCabe cyclomatic complexity limit."""
    limit = settings.max_cyclomatic_complexity
    if func.cyclomatic_complexity > limit:
        severity = Severity.HIGH if func.cyclomatic_complexity > limit + 5 else Severity.MEDIUM
        return QualityIssue(
            language=getattr(func, "language", "Python"),
            file=func.file_path,
            line=func.line_number,
            rule_id="CQ004",
            severity=severity,
            message=f"Function '{func.name}' has McCabe cyclomatic complexity of {func.cyclomatic_complexity} (limit: {limit})",
            actual_value=str(func.cyclomatic_complexity),
            threshold=str(limit)
        )
    return None


def check_deep_nesting_python(tree: ast.AST, file_path: str) -> List[QualityIssue]:
    """Rule CQ005: Blocks with deeply nested control flow structures in Python."""
    limit = settings.max_nesting_depth
    issues: List[QualityIssue] = []

    def _walk_nesting(node: ast.AST, current_depth: int):
        new_depth = current_depth
        if isinstance(node, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.Try, ast.ExceptHandler, ast.With)):
            new_depth += 1
            if new_depth > limit:
                severity = Severity.HIGH if new_depth > limit + 2 else Severity.MEDIUM
                issues.append(QualityIssue(
                    language="Python",
                    file=file_path,
                    line=node.lineno,
                    rule_id="CQ005",
                    severity=severity,
                    message=f"Nesting depth of {new_depth} exceeds limit of {limit}",
                    actual_value=str(new_depth),
                    threshold=str(limit)
                ))

        for child in ast.iter_child_nodes(node):
            _walk_nesting(child, new_depth)

    _walk_nesting(tree, 0)
    return issues


def check_naming_conventions(index: CodeIndex) -> List[QualityIssue]:
    """Rule CQ006: Naming style violations (PEP 8 for Python, camelCase/PascalCase for TS/JS)."""
    issues: List[QualityIssue] = []

    # Check functions & methods
    for qname, func in index.functions.items():
        name = func.name
        lang = getattr(func, "language", "Python")

        if name.startswith("__") and name.endswith("__"):
            continue
        if name in ("constructor", "anonymous"):
            continue

        if lang == "Python":
            if not SNAKE_CASE_PATTERN.match(name):
                issues.append(QualityIssue(
                    language="Python",
                    file=func.file_path,
                    line=func.line_number,
                    rule_id="CQ006",
                    severity=Severity.LOW,
                    message=f"Function/method name '{name}' does not follow PEP-8 snake_case convention",
                    actual_value=name,
                    threshold="snake_case"
                ))
        elif lang in ("TypeScript", "JavaScript"):
            # In TS/JS, functions can be camelCase or PascalCase (React components)
            is_camel = bool(CAMEL_CASE_PATTERN.match(name))
            is_pascal = bool(PASCAL_CASE_PATTERN.match(name))
            if not (is_camel or is_pascal):
                issues.append(QualityIssue(
                    language=lang,
                    file=func.file_path,
                    line=func.line_number,
                    rule_id="CQ006",
                    severity=Severity.LOW,
                    message=f"Identifier '{name}' does not follow camelCase or PascalCase convention",
                    actual_value=name,
                    threshold="camelCase or PascalCase"
                ))

    # Check classes
    for qname, cls in index.classes.items():
        name = cls.name
        lang = getattr(cls, "language", "Python")
        if not PASCAL_CASE_PATTERN.match(name):
            issues.append(QualityIssue(
                language=lang,
                file=cls.file_path,
                line=cls.line_number,
                rule_id="CQ006",
                severity=Severity.LOW,
                message=f"Class name '{name}' does not follow PascalCase convention",
                actual_value=name,
                threshold="PascalCase"
            ))

    return issues


def check_missing_docstrings(index: CodeIndex) -> List[QualityIssue]:
    """Rule CQ007: Missing docstrings for public classes and public functions."""
    issues: List[QualityIssue] = []

    for qname, cls in index.classes.items():
        lang = getattr(cls, "language", "Python")
        if not cls.name.startswith("_") and not cls.docstring:
            issues.append(QualityIssue(
                language=lang,
                file=cls.file_path,
                line=cls.line_number,
                rule_id="CQ007",
                severity=Severity.LOW,
                message=f"Public class '{cls.name}' is missing a docstring",
                actual_value="No docstring",
                threshold="Docstring required"
            ))

    for qname, func in index.functions.items():
        name = func.name
        lang = getattr(func, "language", "Python")
        if name.startswith("_") or name.startswith("test_") or func.file_path.endswith("__init__.py"):
            continue
        if lang == "Python" and not func.docstring:
            issues.append(QualityIssue(
                language="Python",
                file=func.file_path,
                line=func.line_number,
                rule_id="CQ007",
                severity=Severity.LOW,
                message=f"Public function '{name}' is missing a docstring",
                actual_value="No docstring",
                threshold="Docstring required"
            ))

    return issues


def check_hardcoded_secrets(code: str, file_path: str, language: str = "Unknown") -> List[QualityIssue]:
    """Rule CQ008: Scan source text for hardcoded API keys, tokens, or credentials."""
    issues: List[QualityIssue] = []
    lines = code.splitlines()

    for line_idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("/*"):
            continue

        for pattern, desc in SECRET_PATTERNS:
            if pattern.search(line):
                issues.append(QualityIssue(
                    language=language,
                    file=file_path,
                    line=line_idx,
                    rule_id="CQ008",
                    severity=Severity.HIGH,
                    message=f"{desc} in line: '{line.strip()[:60]}...'",
                    actual_value="Credential pattern match",
                    threshold="No hardcoded secrets"
                ))
                break

    return issues


def check_class_complexity(cls: ClassInfo) -> Optional[QualityIssue]:
    """Rule CQ009: Excessive class complexity (too many methods or excessive lines)."""
    max_methods = settings.max_class_methods
    max_length = settings.max_class_length

    method_count = len(cls.method_names)
    if method_count > max_methods or cls.length_lines > max_length:
        reasons = []
        if method_count > max_methods:
            reasons.append(f"{method_count} methods (limit: {max_methods})")
        if cls.length_lines > max_length:
            reasons.append(f"{cls.length_lines} lines (limit: {max_length})")

        return QualityIssue(
            language=getattr(cls, "language", "Python"),
            file=cls.file_path,
            line=cls.line_number,
            rule_id="CQ009",
            severity=Severity.MEDIUM,
            message=f"Class '{cls.name}' has excessive complexity: {', '.join(reasons)}",
            actual_value=f"methods={method_count}, lines={cls.length_lines}",
            threshold=f"methods<={max_methods}, lines<={max_length}"
        )
    return None
