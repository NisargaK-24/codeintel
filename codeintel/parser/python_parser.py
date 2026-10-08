import ast
from pathlib import Path
from typing import Any, List, Optional, Set

from codeintel.models.code import (
    CallInfo, ClassInfo, CodeIndex, FunctionInfo, ImportInfo,
    MethodInfo, ParseErrorInfo, ReferenceInfo, Symbol, SymbolKind
)
from codeintel.parser.base import BaseParser, FileParseResult


def file_path_to_module_name(relative_path: str) -> str:
    """Convert relative file path to Python dot-separated module path."""
    p = Path(relative_path.replace("\\", "/"))
    parts = list(p.parts)
    if not parts:
        return ""
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) if parts else p.stem


def calculate_cyclomatic_complexity(node: ast.AST) -> int:
    """
    Calculate McCabe Cyclomatic Complexity for an AST function/method node.
    Complexity starts at 1, incrementing for each decision point.
    """
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.ExceptHandler, ast.With, ast.AsyncWith, ast.Assert, ast.IfExp)):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += max(0, len(child.values) - 1)
        elif isinstance(child, ast.comprehension):
            complexity += 1
            if child.ifs:
                complexity += len(child.ifs)
        elif hasattr(ast, "Match") and isinstance(child, ast.Match):
            complexity += max(0, len(child.cases) - 1)
    return complexity


def get_decorator_name(decorator_node: ast.AST) -> str:
    """Format decorator AST node into readable string representation."""
    if isinstance(decorator_node, ast.Name):
        return decorator_node.id
    elif isinstance(decorator_node, ast.Attribute):
        base = get_decorator_name(decorator_node.value)
        return f"{base}.{decorator_node.attr}" if base else decorator_node.attr
    elif isinstance(decorator_node, ast.Call):
        func_name = get_decorator_name(decorator_node.func)
        return func_name
    return ast.unparse(decorator_node) if hasattr(ast, "unparse") else "decorator"


def get_callee_expression_str(node: ast.AST) -> str:
    """Format callee expression from ast.Call node."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        value_str = get_callee_expression_str(node.value)
        return f"{value_str}.{node.attr}" if value_str else node.attr
    elif hasattr(ast, "unparse"):
        try:
            return ast.unparse(node)
        except Exception:
            return "expression"
    return "unknown"


def extract_parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> List[str]:
    """Extract argument names from function definition."""
    params: List[str] = []
    args = node.args
    # Positional only
    for a in getattr(args, "posonlyargs", []):
        params.append(a.arg)
    # Regular args
    for a in args.args:
        params.append(a.arg)
    # Vararg (*args)
    if args.vararg:
        params.append(f"*{args.vararg.arg}")
    # Keyword only
    for a in args.kwonlyargs:
        params.append(a.arg)
    # Kwarg (**kwargs)
    if args.kwarg:
        params.append(f"**{args.kwarg.arg}")
    return params


class PythonAstParser(BaseParser):
    """Parses Python source files using standard library AST safely without code execution."""

    name: str = "Python"
    supported_languages: Set[str] = {"Python"}

    def parse_source(self, code: str, file_path: str, relative_path: str, language: Optional[str] = None) -> FileParseResult:
        module_name = file_path_to_module_name(relative_path)
        index = CodeIndex(files=[relative_path])

        try:
            tree = ast.parse(code, filename=file_path)
        except SyntaxError as e:
            err = ParseErrorInfo(
                file_path=relative_path,
                error_message=f"SyntaxError: {e.msg} at line {e.lineno}",
                line_number=e.lineno,
                language="Python"
            )
            index.parse_errors.append(err)
            return FileParseResult(
                file_path=file_path,
                relative_path=relative_path,
                code_index=index,
                success=False,
                error_message=err.error_message,
                language="Python"
            )
        except Exception as e:
            err = ParseErrorInfo(
                file_path=relative_path,
                error_message=f"ParseError: {str(e)}",
                line_number=None,
                language="Python"
            )
            index.parse_errors.append(err)
            return FileParseResult(
                file_path=file_path,
                relative_path=relative_path,
                code_index=index,
                success=False,
                error_message=err.error_message,
                language="Python"
            )

        # Module level symbol
        mod_docstring = ast.get_docstring(tree)
        module_symbol = Symbol(
            name=module_name.split(".")[-1] if module_name else "module",
            qualified_name=module_name,
            kind=SymbolKind.MODULE,
            file_path=relative_path,
            line_number=1,
            end_line_number=len(code.splitlines()) or 1,
            parent_qualified_name=None,
            docstring=mod_docstring
        )
        index.symbols[module_name] = module_symbol

        # Traverse AST and extract symbols
        self._extract_nodes(tree, module_name, relative_path, index)

        return FileParseResult(
            file_path=file_path,
            relative_path=relative_path,
            code_index=index,
            success=True
        )

    def _extract_nodes(
        self,
        tree: ast.AST,
        module_name: str,
        relative_path: str,
        index: CodeIndex
    ) -> None:
        """Walk AST to collect imports, classes, functions, methods, calls, and references."""
        # First collect imports and top-level definitions
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imp = ImportInfo(
                        module=alias.name,
                        imported_name=alias.name,
                        alias=alias.asname,
                        is_from=False,
                        line_number=node.lineno,
                        file_path=relative_path
                    )
                    index.imports.append(imp)
            elif isinstance(node, ast.ImportFrom):
                mod_str = node.module or ""
                if node.level > 0:
                    # relative import level
                    prefix = "." * node.level
                    mod_str = f"{prefix}{mod_str}" if mod_str else prefix
                for alias in node.names:
                    imp = ImportInfo(
                        module=mod_str,
                        imported_name=alias.name,
                        alias=alias.asname,
                        is_from=True,
                        line_number=node.lineno,
                        file_path=relative_path
                    )
                    index.imports.append(imp)

        # Collect classes, functions, methods, calls, references recursively
        self._visit_scope(tree, parent_qname=module_name, current_class=None, relative_path=relative_path, index=index)

    def _visit_scope(
        self,
        scope_node: ast.AST,
        parent_qname: str,
        current_class: Optional[ClassInfo],
        relative_path: str,
        index: CodeIndex
    ) -> None:
        body = getattr(scope_node, "body", [])
        for node in body:
            if isinstance(node, ast.ClassDef):
                self._handle_class_def(node, parent_qname, relative_path, index)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._handle_function_def(node, parent_qname, current_class, relative_path, index)
            elif hasattr(node, "body"):
                self._visit_scope(node, parent_qname, current_class, relative_path, index)

    def _handle_class_def(
        self,
        node: ast.ClassDef,
        parent_qname: str,
        relative_path: str,
        index: CodeIndex
    ) -> None:
        class_name = node.name
        qname = f"{parent_qname}.{class_name}" if parent_qname else class_name
        docstring = ast.get_docstring(node)
        decorators = [get_decorator_name(d) for d in node.decorator_list]
        base_classes = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                base_classes.append(base.id)
            elif isinstance(base, ast.Attribute):
                base_classes.append(f"{get_callee_expression_str(base.value)}.{base.attr}")
            elif hasattr(ast, "unparse"):
                base_classes.append(ast.unparse(base))

        end_lineno = getattr(node, "end_lineno", node.lineno)
        class_info = ClassInfo(
            name=class_name,
            qualified_name=qname,
            kind=SymbolKind.CLASS,
            file_path=relative_path,
            line_number=node.lineno,
            end_line_number=end_lineno,
            parent_qualified_name=parent_qname,
            docstring=docstring,
            base_classes=base_classes,
            decorators=decorators,
            method_names=[],
            length_lines=max(1, end_lineno - node.lineno + 1)
        )
        index.classes[qname] = class_info
        index.symbols[qname] = class_info

        # Visit class body to collect methods and nested symbols
        self._visit_scope(node, parent_qname=qname, current_class=class_info, relative_path=relative_path, index=index)

    def _handle_function_def(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        parent_qname: str,
        current_class: Optional[ClassInfo],
        relative_path: str,
        index: CodeIndex
    ) -> None:
        func_name = node.name
        is_method = current_class is not None

        # Build qualified name
        if is_method:
            qname = f"{parent_qname}.{func_name}"
        else:
            # If parent is already a function, mark as nested <locals>
            if parent_qname and (parent_qname in index.functions or "<locals>" in parent_qname):
                qname = f"{parent_qname}.<locals>.{func_name}"
            else:
                qname = f"{parent_qname}.{func_name}" if parent_qname else func_name

        docstring = ast.get_docstring(node)
        decorators = [get_decorator_name(d) for d in node.decorator_list]
        parameters = extract_parameters(node)
        complexity = calculate_cyclomatic_complexity(node)
        end_lineno = getattr(node, "end_lineno", node.lineno)
        length_lines = max(1, end_lineno - node.lineno + 1)

        # Return annotation
        return_annotation = None
        if node.returns:
            if hasattr(ast, "unparse"):
                return_annotation = ast.unparse(node.returns)
            elif isinstance(node.returns, ast.Name):
                return_annotation = node.returns.id

        # Collect internal calls and references inside this function
        called_functions: List[str] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                callee_str = get_callee_expression_str(child.func)
                called_functions.append(callee_str)
                call_info = CallInfo(
                    caller_qualified_name=qname,
                    callee_name=callee_str,
                    resolved_callee=None,
                    line_number=child.lineno,
                    file_path=relative_path,
                    arguments_count=len(child.args) + len(child.keywords)
                )
                index.calls.append(call_info)
            elif isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                ref_info = ReferenceInfo(
                    symbol_name=child.id,
                    context_symbol=qname,
                    line_number=child.lineno,
                    file_path=relative_path
                )
                index.references.append(ref_info)

        if is_method:
            is_static = any(d == "staticmethod" for d in decorators)
            is_cls = any(d == "classmethod" for d in decorators)
            is_prop = any(d == "property" or d.endswith(".setter") for d in decorators)

            method_info = MethodInfo(
                name=func_name,
                qualified_name=qname,
                kind=SymbolKind.METHOD,
                file_path=relative_path,
                line_number=node.lineno,
                end_line_number=end_lineno,
                parent_qualified_name=parent_qname,
                docstring=docstring,
                parameters=parameters,
                return_annotation=return_annotation,
                decorators=decorators,
                is_method=True,
                is_async=isinstance(node, ast.AsyncFunctionDef),
                cyclomatic_complexity=complexity,
                length_lines=length_lines,
                called_functions=called_functions,
                class_name=current_class.name,
                is_static=is_static,
                is_classmethod=is_cls,
                is_property=is_prop
            )
            index.methods[qname] = method_info
            index.functions[qname] = method_info
            index.symbols[qname] = method_info
            current_class.method_names.append(func_name)
        else:
            func_info = FunctionInfo(
                name=func_name,
                qualified_name=qname,
                kind=SymbolKind.FUNCTION,
                file_path=relative_path,
                line_number=node.lineno,
                end_line_number=end_lineno,
                parent_qualified_name=parent_qname,
                docstring=docstring,
                parameters=parameters,
                return_annotation=return_annotation,
                decorators=decorators,
                is_method=False,
                is_async=isinstance(node, ast.AsyncFunctionDef),
                cyclomatic_complexity=complexity,
                length_lines=length_lines,
                called_functions=called_functions
            )
            index.functions[qname] = func_info
            index.symbols[qname] = func_info

        # Visit nested functions/classes inside this function body
        self._visit_scope(node, parent_qname=qname, current_class=None, relative_path=relative_path, index=index)


# Canonical alias
PythonParser = PythonAstParser
