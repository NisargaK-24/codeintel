import tempfile
from pathlib import Path
import pytest

from codeintel.models.code import SymbolKind
from codeintel.parser.analyzer import CodeAnalyzer
from codeintel.parser.javascript_parser import JavaScriptParser
from codeintel.parser.registry import ParserRegistry
from codeintel.parser.resolver import resolve_ts_relative_import
from codeintel.parser.typescript_parser import TypeScriptParser
from codeintel.graph.dependency_graph import DependencyGraph
from codeintel.graph.graph_analyzer import GraphAnalyzer
from codeintel.zombie.detector import ZombieDetector
from codeintel.quality.analyzer import QualityAnalyzer


@pytest.fixture
def ts_fixture_dir(tmp_path: Path) -> Path:
    """Create a deterministic TypeScript fixture project with relative imports, exports, and classes."""
    # 1. utils/math.ts
    utils_dir = tmp_path / "src" / "utils"
    utils_dir.mkdir(parents=True, exist_ok=True)
    math_ts = utils_dir / "math.ts"
    math_ts.write_text(
        """// Math utility module
export function add(a: number, b: number): number {
    return a + b;
}

export const multiply = (x: number, y: number): number => {
    return x * y;
};

export const secretKey = "ghp_123456789012345678901234567890123456";
""",
        encoding="utf-8"
    )

    # 2. models/user.ts
    models_dir = tmp_path / "src" / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    user_ts = models_dir / "user.ts"
    user_ts.write_text(
        """// User domain models
export interface Identifiable {
    id: string;
}

export class User implements Identifiable {
    id: string;
    name: string;

    constructor(id: string, name: string) {
        this.id = id;
        this.name = name;
    }

    public getDisplayName(): string {
        return this.name;
    }
}

export class AdminUser extends User {
    role: string = "admin";

    public getRole(): string {
        return this.role;
    }
}
""",
        encoding="utf-8"
    )

    # 3. services/userService.ts
    services_dir = tmp_path / "src" / "services"
    services_dir.mkdir(parents=True, exist_ok=True)
    service_ts = services_dir / "userService.ts"
    service_ts.write_text(
        """import { User, AdminUser } from "../models/user";
import { add, multiply } from "../utils/math";
import { externalLib } from "external-package";

export function createAdmin(name: string): AdminUser {
    const admin = new AdminUser("1", name);
    const score = add(10, 20);
    return admin;
}

export const calculateTotal = (a: number, b: number) => {
    return multiply(a, b);
};

function unusedPrivateHelper() {
    return "private";
}
""",
        encoding="utf-8"
    )

    return tmp_path


@pytest.fixture
def js_fixture_dir(tmp_path: Path) -> Path:
    """Create a deterministic JavaScript fixture project."""
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    # 1. helper.js
    helper_js = src_dir / "helper.js"
    helper_js.write_text(
        """export function formatString(str) {
    return str.trim().toUpperCase();
}

export const parseNumber = (val) => {
    return parseInt(val, 10);
};
""",
        encoding="utf-8"
    )

    # 2. app.js
    app_js = src_dir / "app.js"
    app_js.write_text(
        """import { formatString, parseNumber } from "./helper";

export class Component {
    render() {
        return "<div/>";
    }
}

export class ExtendedComponent extends Component {
    render() {
        formatString("hello");
        parseNumber("42");
        return "<span>hello</span>";
    }
}

function localUnusedJsFunc() {
    return 100;
}
""",
        encoding="utf-8"
    )

    return tmp_path


class TestMultiLanguageParsing:

    def test_typescript_parser_symbol_extraction(self, ts_fixture_dir: Path):
        parser = TypeScriptParser()
        math_file = ts_fixture_dir / "src" / "utils" / "math.ts"
        result = parser.parse_file(math_file, ts_fixture_dir)

        assert result.success is True
        idx = result.code_index

        # Check functions and arrow functions
        func_names = [f.name for f in idx.functions.values()]
        assert "add" in func_names
        assert "multiply" in func_names

        # Check arrow function flag
        multiply_func = next(f for f in idx.functions.values() if f.name == "multiply")
        assert multiply_func.is_arrow is True

        # Check exported flag
        add_func = next(f for f in idx.functions.values() if f.name == "add")
        assert add_func.is_exported is True

    def test_typescript_classes_and_interfaces(self, ts_fixture_dir: Path):
        parser = TypeScriptParser()
        user_file = ts_fixture_dir / "src" / "models" / "user.ts"
        result = parser.parse_file(user_file, ts_fixture_dir)

        assert result.success is True
        idx = result.code_index

        # Interface
        assert any(i.name == "Identifiable" for i in idx.interfaces.values())

        # Classes
        class_names = [c.name for c in idx.classes.values()]
        assert "User" in class_names
        assert "AdminUser" in class_names

        admin_class = next(c for c in idx.classes.values() if c.name == "AdminUser")
        assert "User" in admin_class.base_classes

        # Methods
        method_names = [m.name for m in idx.methods.values()]
        assert "getDisplayName" in method_names
        assert "getRole" in method_names

    def test_typescript_imports_exports_calls(self, ts_fixture_dir: Path):
        parser = TypeScriptParser()
        service_file = ts_fixture_dir / "src" / "services" / "userService.ts"
        result = parser.parse_file(service_file, ts_fixture_dir)

        assert result.success is True
        idx = result.code_index

        # Imports
        imported_symbols = [imp.imported_name for imp in idx.imports]
        assert "User" in imported_symbols
        assert "AdminUser" in imported_symbols
        assert "add" in imported_symbols
        assert "multiply" in imported_symbols

        # Calls
        callee_names = [c.callee_name for c in idx.calls]
        assert "AdminUser" in callee_names or "add" in callee_names

    def test_javascript_parser_extraction(self, js_fixture_dir: Path):
        parser = JavaScriptParser()
        app_file = js_fixture_dir / "src" / "app.js"
        result = parser.parse_file(app_file, js_fixture_dir)

        assert result.success is True
        idx = result.code_index

        class_names = [c.name for c in idx.classes.values()]
        assert "Component" in class_names
        assert "ExtendedComponent" in class_names

        ext_comp = next(c for c in idx.classes.values() if c.name == "ExtendedComponent")
        assert "Component" in ext_comp.base_classes

        # Calls
        callee_names = [c.callee_name for c in idx.calls]
        assert "formatString" in callee_names
        assert "parseNumber" in callee_names

    def test_relative_import_resolution(self, ts_fixture_dir: Path):
        known_files = {
            "src/utils/math.ts",
            "src/models/user.ts",
            "src/services/userService.ts",
        }

        # 1. Relative import that exists
        resolved, path = resolve_ts_relative_import(
            import_module="../models/user",
            current_file_path="src/services/userService.ts",
            repo_root=ts_fixture_dir,
            known_files=known_files
        )
        assert resolved is True
        assert path == "src/models/user.ts"

        # 2. External module package that is NOT local
        resolved_ext, path_ext = resolve_ts_relative_import(
            import_module="external-package",
            current_file_path="src/services/userService.ts",
            repo_root=ts_fixture_dir,
            known_files=known_files
        )
        assert resolved_ext is False
        assert path_ext is None

    def test_parser_registry_selection(self):
        registry = ParserRegistry()
        py_parser = registry.get_parser_for_language("Python")
        ts_parser = registry.get_parser_for_language("TypeScript")
        js_parser = registry.get_parser_for_language("JavaScript")
        sql_parser = registry.get_parser_for_language("SQL")

        assert py_parser is not None
        assert py_parser.name == "Python"
        assert ts_parser is not None
        assert ts_parser.name == "TypeScript"
        assert js_parser is not None
        assert js_parser.name == "JavaScript"
        assert sql_parser is None

    def test_code_analyzer_end_to_end_typescript(self, ts_fixture_dir: Path):
        analyzer = CodeAnalyzer()
        code_index = analyzer.analyze_repository(ts_fixture_dir)

        assert len(code_index.files) == 3
        assert "TypeScript" in code_index.language_stats
        ts_stats = code_index.language_stats["TypeScript"]
        assert ts_stats["files"] == 3
        assert ts_stats["parsed"] == 3
        assert ts_stats["failed"] == 0
        assert ts_stats["functions"] >= 4
        assert ts_stats["classes"] >= 2

        # Check import resolution counts
        assert code_index.resolved_imports_count >= 4
        assert code_index.unresolved_imports_count >= 1  # external-package

    def test_dependency_graph_with_typescript(self, ts_fixture_dir: Path):
        analyzer = CodeAnalyzer()
        code_index = analyzer.analyze_repository(ts_fixture_dir)

        graph = DependencyGraph()
        graph.build_from_index(code_index)
        summary = graph.get_summary()

        assert summary.total_nodes > 0
        assert summary.total_edges > 0

    def test_zombie_detection_shields_ts_exports(self, ts_fixture_dir: Path):
        analyzer = CodeAnalyzer()
        code_index = analyzer.analyze_repository(ts_fixture_dir)

        graph = DependencyGraph()
        graph.build_from_index(code_index)
        graph_analyzer = GraphAnalyzer(graph)

        detector = ZombieDetector(min_score=40)
        report = detector.analyze(code_index, graph_analyzer, {})

        candidate_names = [c.symbol.split(".")[-1] for c in report.candidates]
        # Private uncalled helper should have higher suspicion than exported functions
        assert "unusedPrivateHelper" in candidate_names
        # Exported functions should be shielded and not high confidence zombies
        assert not any(c.symbol.endswith(".add") and c.confidence.value == "HIGH" for c in report.candidates)

    def test_quality_analysis_typescript_rules(self, ts_fixture_dir: Path):
        analyzer = CodeAnalyzer()
        code_index = analyzer.analyze_repository(ts_fixture_dir)

        quality_analyzer = QualityAnalyzer()
        report = quality_analyzer.analyze(code_index, ts_fixture_dir)

        # The math.ts has a secretKey: "ghp_123456789012345678901234567890123456"
        secret_issues = [i for i in report.issues if i.rule_id == "CQ008"]
        assert len(secret_issues) >= 1
        assert secret_issues[0].language in ("TypeScript", "JavaScript")
