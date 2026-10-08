from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

from codeintel.config.settings import settings
from codeintel.graph.graph_analyzer import GraphAnalyzer
from codeintel.models.code import CodeIndex, FunctionInfo, MethodInfo
from codeintel.models.zombie import ConfidenceLevel, EvidenceItem, ZombieCandidate, ZombieReport

# Framework entry point names that are invoked by external drivers / CLI / runners
FRAMEWORK_ENTRY_POINTS = {
    "main", "cli", "run", "app", "handler", "lambda_handler",
    "setUp", "tearDown", "setUpClass", "tearDownClass", "default"
}

# Common framework entry point filenames for Python, TS, and JS
FRAMEWORK_ENTRY_FILENAMES = {
    "__main__.py", "main.py", "app.py", "wsgi.py", "asgi.py", "server.py",
    "index.ts", "index.tsx", "index.js", "index.jsx",
    "main.ts", "main.tsx", "main.js", "main.jsx",
    "app.ts", "app.tsx", "app.js", "app.jsx",
    "server.ts", "server.js",
    "page.tsx", "page.jsx", "page.ts", "page.js",
    "layout.tsx", "layout.jsx",
    "route.ts", "route.js",
    "middleware.ts", "middleware.js"
}

# Decorators that indicate dynamic or framework dispatch
IMMUNE_DECORATORS = {
    "fixture", "pytest.fixture", "route", "app.route", "router.get", "router.post",
    "router.put", "router.delete", "command", "app.command", "cli.command",
    "property", "abstractmethod", "override", "validator", "field_validator",
    "classmethod", "staticmethod", "cached_property", "event_handler",
    "Injectable", "Component", "Directive", "Pipe", "Controller", "Get", "Post"
}


def is_magic_method(name: str) -> bool:
    """Check if method name is a Python dunder method or JS constructor."""
    if name == "constructor":
        return True
    return name.startswith("__") and name.endswith("__") and len(name) > 4


def is_test_component(file_path: str, symbol_name: str) -> bool:
    """Detect whether file or symbol represents unit/integration test code."""
    p = file_path.replace("\\", "/").lower()
    parts = p.split("/")
    if any(part in {"tests", "test", "testing", "__tests__"} for part in parts):
        return True
    filename = Path(p).name
    if filename.startswith("test_") or filename.endswith("_test.py"):
        return True
    if any(filename.endswith(ext) for ext in [".test.ts", ".test.tsx", ".test.js", ".test.jsx", ".spec.ts", ".spec.tsx", ".spec.js", ".spec.jsx"]):
        return True
    if symbol_name.startswith("test_") or symbol_name.startswith("Test"):
        return True
    return False


class ZombieDetector:
    """
    Evaluates functions and methods using multi-factor evidence heuristics
    to detect Potential Zombie Code with transparent confidence scoring.
    Supports Python, TypeScript, and JavaScript.
    """

    def __init__(self, min_score: Optional[int] = None):
        self.min_score = min_score if min_score is not None else settings.zombie_min_score

    def analyze(
        self,
        index: CodeIndex,
        graph_analyzer: GraphAnalyzer,
        file_mtimes: Optional[Dict[str, float]] = None
    ) -> ZombieReport:
        candidates: List[ZombieCandidate] = []
        all_functions = list(index.functions.values())

        # Collect all imported names across project
        imported_symbols: Set[str] = set()
        for imp in index.imports:
            imported_symbols.add(imp.imported_name)
            if imp.alias:
                imported_symbols.add(imp.alias)

        # Collect exported symbol names across project
        exported_symbols: Set[str] = {exp.name for exp in index.exports}

        # Collect references per symbol name
        reference_counts: Dict[str, int] = {}
        test_references: Set[str] = set()
        for ref in index.references:
            reference_counts[ref.symbol_name] = reference_counts.get(ref.symbol_name, 0) + 1
            if is_test_component(ref.file_path, ref.context_symbol):
                test_references.add(ref.symbol_name)

        now_epoch = datetime.now(timezone.utc).timestamp()

        for func in all_functions:
            candidate = self._evaluate_function(
                func=func,
                graph_analyzer=graph_analyzer,
                imported_symbols=imported_symbols,
                exported_symbols=exported_symbols,
                reference_counts=reference_counts,
                test_references=test_references,
                file_mtimes=file_mtimes or {},
                now_epoch=now_epoch
            )
            if candidate and candidate.score >= self.min_score:
                candidates.append(candidate)

        # Sort candidates descending by suspicion score
        candidates.sort(key=lambda c: c.score, reverse=True)

        high_count = sum(1 for c in candidates if c.confidence == ConfidenceLevel.HIGH)

        return ZombieReport(
            candidates=candidates,
            total_functions_analyzed=len(all_functions),
            potential_zombies_count=len(candidates),
            high_confidence_count=high_count
        )

    def _evaluate_function(
        self,
        func: FunctionInfo | MethodInfo,
        graph_analyzer: GraphAnalyzer,
        imported_symbols: Set[str],
        exported_symbols: Set[str],
        reference_counts: Dict[str, int],
        test_references: Set[str],
        file_mtimes: Dict[str, float],
        now_epoch: float
    ) -> Optional[ZombieCandidate]:
        evidence: List[EvidenceItem] = []
        reasons: List[str] = []
        score = 0.0

        qname = func.qualified_name
        name = func.name
        file_path = func.file_path
        lang = getattr(func, "language", "Python")
        is_method = getattr(func, "is_method", False)
        is_private = name.startswith("_") and not is_magic_method(name)
        is_exported = getattr(func, "is_exported", False) or (name in exported_symbols)

        # False-positive protection 1: Magic methods and constructors are immune
        if is_magic_method(name):
            return None

        # False-positive protection 2: Test functions are immune
        if is_test_component(file_path, name):
            return None

        # False-positive protection 3: Framework decorators
        has_immune_decorator = False
        for dec in func.decorators:
            dec_clean = dec.split("(")[0].strip()
            if any(dec_clean == d or dec_clean.endswith(f".{d}") for d in IMMUNE_DECORATORS):
                has_immune_decorator = True
                evidence.append(EvidenceItem(
                    rule_name="FRAMEWORK_DECORATOR",
                    score_delta=-50.0,
                    reason=f"Function has framework or structural decorator '@{dec}'",
                    category="decorator"
                ))
                score -= 50.0
                break

        # False-positive protection 4: Entry points
        file_basename = Path(file_path.replace("\\", "/")).name.lower()
        if name in FRAMEWORK_ENTRY_POINTS or file_basename in FRAMEWORK_ENTRY_FILENAMES:
            evidence.append(EvidenceItem(
                rule_name="ENTRY_POINT_INDICATOR",
                score_delta=-40.0,
                reason=f"Identified as application entry point in '{file_basename}'",
                category="entrypoint"
            ))
            score -= 40.0

        # False-positive protection 5: Exported module boundary API (especially TS/JS)
        if is_exported:
            if lang in ("TypeScript", "JavaScript"):
                evidence.append(EvidenceItem(
                    rule_name="EXPORTED_MODULE_API",
                    score_delta=-40.0,
                    reason="Exported from module as public API contract or UI component",
                    category="visibility"
                ))
                score -= 40.0
            else:
                evidence.append(EvidenceItem(
                    rule_name="EXPORTED_API",
                    score_delta=-20.0,
                    reason="Exported symbol intended for external module consumption",
                    category="visibility"
                ))
                score -= 20.0

        # False-positive protection 6: React component heuristics (PascalCase in TSX/JSX/TS/JS)
        if lang in ("TypeScript", "JavaScript"):
            if name and name[0].isupper() and not is_method:
                evidence.append(EvidenceItem(
                    rule_name="REACT_COMPONENT_INDICATOR",
                    score_delta=-35.0,
                    reason=f"PascalCase identifier '{name}' indicates React UI component",
                    category="framework"
                ))
                score -= 35.0
            elif name.startswith("use") and len(name) > 3 and name[3].isupper():
                evidence.append(EvidenceItem(
                    rule_name="REACT_HOOK_INDICATOR",
                    score_delta=-30.0,
                    reason=f"Identifier '{name}' follows React Hook naming convention",
                    category="framework"
                ))
                score -= 30.0

        # Heuristic 1: Call graph callers
        direct_callers = graph_analyzer.get_direct_callers(qname)
        caller_count = len(direct_callers)
        if caller_count == 0:
            evidence.append(EvidenceItem(
                rule_name="NO_DIRECT_CALLERS",
                score_delta=35.0,
                reason="No direct callers found in dependency call graph",
                category="callers"
            ))
            reasons.append("No direct callers in dependency graph")
            score += 35.0
        else:
            evidence.append(EvidenceItem(
                rule_name="ACTIVE_CALLERS",
                score_delta=-25.0 * min(3, caller_count),
                reason=f"Called by {caller_count} component(s) in codebase",
                category="callers"
            ))
            score -= 25.0 * min(3, caller_count)

        # Heuristic 2: Symbol references across repository
        ref_count = reference_counts.get(name, 0)
        if ref_count == 0:
            evidence.append(EvidenceItem(
                rule_name="ZERO_NAME_REFERENCES",
                score_delta=25.0,
                reason="Identifier is never referenced anywhere in repository code",
                category="references"
            ))
            reasons.append("Symbol identifier never referenced in codebase")
            score += 25.0

        # Heuristic 3: Imports across modules
        if not is_method and name not in imported_symbols:
            evidence.append(EvidenceItem(
                rule_name="NOT_IMPORTED",
                score_delta=15.0,
                reason="Function is never explicitly imported by other modules",
                category="imports"
            ))
            reasons.append("Never imported by other modules")
            score += 15.0

        # Heuristic 4: Test references
        if name in test_references:
            evidence.append(EvidenceItem(
                rule_name="TEST_REFERENCED",
                score_delta=-35.0,
                reason="Function is referenced within test files",
                category="test"
            ))
            score -= 35.0
        elif caller_count == 0 and not is_exported:
            evidence.append(EvidenceItem(
                rule_name="NO_TEST_REFERENCES",
                score_delta=10.0,
                reason="No test suite references found for uncalled function",
                category="test"
            ))
            reasons.append("No test references")
            score += 10.0

        # Heuristic 5: Private function without callers
        if is_private:
            if caller_count == 0:
                evidence.append(EvidenceItem(
                    rule_name="UNREFERENCED_PRIVATE_FUNCTION",
                    score_delta=15.0,
                    reason=f"Private helper '{name}' has no internal callers",
                    category="visibility"
                ))
                reasons.append("Private function with no internal callers")
                score += 15.0

        # Heuristic 6: Modification timestamp
        mtime = file_mtimes.get(file_path, 0.0)
        if mtime > 0:
            age_days = (now_epoch - mtime) / 86400.0
            if age_days > settings.zombie_age_days_suspicious:
                evidence.append(EvidenceItem(
                    rule_name="STALE_CODE",
                    score_delta=10.0,
                    reason=f"File not modified in {int(age_days)} days",
                    category="git"
                ))
                score += 10.0
            elif age_days < 7.0:
                evidence.append(EvidenceItem(
                    rule_name="RECENTLY_EDITED",
                    score_delta=-15.0,
                    reason="Recently modified in the last 7 days",
                    category="git"
                ))
                score -= 15.0

        # Clamp final score between 0.0 and 100.0
        final_score = max(0.0, min(100.0, score))

        if final_score < self.min_score:
            return None

        # Determine confidence
        if final_score >= 80.0:
            confidence = ConfidenceLevel.HIGH
        elif final_score >= 65.0:
            confidence = ConfidenceLevel.MEDIUM
        else:
            confidence = ConfidenceLevel.LOW

        return ZombieCandidate(
            symbol=qname,
            file=file_path,
            score=round(final_score, 1),
            confidence=confidence,
            evidence=evidence,
            reasons=reasons,
            line_number=func.line_number,
            is_public=not is_private,
            is_method=is_method
        )
