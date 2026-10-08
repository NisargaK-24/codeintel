from pathlib import Path
from codeintel.models.code import SymbolKind
from codeintel.parser.python_parser import PythonAstParser, calculate_cyclomatic_complexity
from codeintel.parser.analyzer import CodeAnalyzer

FIXTURE_REPO_PATH = Path(__file__).parent / "fixtures" / "sample_repo"


class TestParser:
    """Test suite for Python AST parsing, symbol extraction, calls, and malformed files."""

    def test_parse_functions_and_classes(self):
        parser = PythonAstParser()
        service_path = FIXTURE_REPO_PATH / "payment" / "service.py"
        res = parser.parse_file(service_path, FIXTURE_REPO_PATH)

        assert res.success is True
        idx = res.code_index

        # Check PaymentService class
        assert "payment.service.PaymentService" in idx.classes
        cls = idx.classes["payment.service.PaymentService"]
        assert cls.name == "PaymentService"
        assert cls.docstring is not None
        assert "calculate_payment" in cls.method_names
        assert "process_refund" in cls.method_names

        # Check calculate_tax function
        assert "payment.service.calculate_tax" in idx.functions
        tax_func = idx.functions["payment.service.calculate_tax"]
        assert tax_func.name == "calculate_tax"
        assert "amount" in tax_func.parameters
        assert "rate" in tax_func.parameters
        assert tax_func.line_number > 0
        assert tax_func.end_line_number >= tax_func.line_number

    def test_parse_methods_and_properties(self):
        parser = PythonAstParser()
        service_path = FIXTURE_REPO_PATH / "payment" / "service.py"
        res = parser.parse_file(service_path, FIXTURE_REPO_PATH)
        idx = res.code_index

        status_method = idx.methods["payment.service.PaymentService.status"]
        assert status_method.is_property is True
        assert status_method.class_name == "PaymentService"
        assert "property" in status_method.decorators

    def test_parse_imports(self):
        parser = PythonAstParser()
        proc_path = FIXTURE_REPO_PATH / "orders" / "processor.py"
        res = parser.parse_file(proc_path, FIXTURE_REPO_PATH)
        idx = res.code_index

        imported_names = {imp.imported_name for imp in idx.imports}
        assert "PaymentService" in imported_names
        assert "apply_discount" in imported_names

    def test_parse_calls_and_resolution(self):
        analyzer = CodeAnalyzer()
        idx = analyzer.analyze_repository(FIXTURE_REPO_PATH)

        # Check that calls in OrderProcessor.process_order are resolved
        proc_calls = [c for c in idx.calls if c.caller_qualified_name == "orders.processor.OrderProcessor.process_order"]
        assert len(proc_calls) >= 2

        # Check resolved callee for apply_discount
        discount_call = next(c for c in proc_calls if "apply_discount" in c.callee_name)
        assert discount_call.resolved_callee == "payment.calculator.apply_discount"

    def test_decorators_and_inheritance(self):
        code = """
class BaseHandler:
    pass

@custom_decorator
class CustomHandler(BaseHandler):
    @classmethod
    def create(cls):
        pass
"""
        parser = PythonAstParser()
        res = parser.parse_source(code, "handler.py", "handler.py")
        assert res.success is True
        idx = res.code_index

        assert "handler.CustomHandler" in idx.classes
        cls = idx.classes["handler.CustomHandler"]
        assert "BaseHandler" in cls.base_classes
        assert "custom_decorator" in cls.decorators

        method = idx.methods["handler.CustomHandler.create"]
        assert method.is_classmethod is True

    def test_malformed_python_graceful_handling(self):
        bad_code = "def syntax_broken_function(:\n    return 1 +"
        parser = PythonAstParser()
        res = parser.parse_source(bad_code, "broken.py", "broken.py")

        assert res.success is False
        assert len(res.code_index.parse_errors) == 1
        err = res.code_index.parse_errors[0]
        assert "SyntaxError" in err.error_message
        assert err.line_number is not None

    def test_cyclomatic_complexity_calculation(self):
        code = """
def complex_fn(x, y):
    if x > 0:
        if y > 0:
            return 1
        elif y < 0:
            return -1
    for i in range(10):
        while x < 5:
            x += 1
    return 0
"""
        parser = PythonAstParser()
        res = parser.parse_source(code, "test.py", "test.py")
        func = res.code_index.functions["test.complex_fn"]
        # Base=1 + if + if + elif + for + while = 6
        assert func.cyclomatic_complexity >= 5
