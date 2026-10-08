from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import tree_sitter_typescript as tst
from tree_sitter import Language, Node, Parser

from codeintel.models.code import (
    CallInfo, ClassInfo, CodeIndex, ExportInfo, FunctionInfo,
    ImportInfo, InterfaceInfo, MethodInfo, ParseErrorInfo,
    ReferenceInfo, Symbol, SymbolKind
)
from codeintel.parser.base import BaseParser, FileParseResult
from codeintel.parser.tree_sitter_base import (
    build_line_offsets, calculate_ts_cyclomatic_complexity,
    extract_leading_docstring, extract_ts_parameters,
    get_line_number_from_offset, get_node_text
)


def get_node_start_line(node: Node, line_offsets: List[int]) -> int:
    return get_line_number_from_offset(line_offsets, node.start_byte)


def get_node_end_line(node: Node, line_offsets: List[int]) -> int:
    end_byte = max(node.start_byte, node.end_byte - 1)
    return get_line_number_from_offset(line_offsets, end_byte)



def ts_file_path_to_module_name(relative_path: str) -> str:
    """Convert relative TS/TSX file path to dot-separated module path."""
    p = Path(relative_path.replace("\\", "/"))
    parts = list(p.parts)
    if not parts:
        return ""
    last = parts[-1]
    for ext in [".d.ts", ".tsx", ".ts"]:
        if last.endswith(ext):
            last = last[:-len(ext)]
            break
    parts[-1] = last
    if parts[-1] == "index":
        parts.pop()
    return ".".join(parts) if parts else p.stem


class TypeScriptParser(BaseParser):
    """Parses TypeScript and TSX files using Tree-sitter without code execution."""

    name: str = "TypeScript"
    supported_languages: Set[str] = {"TypeScript"}

    def __init__(self):
        self._ts_lang = Language(tst.language_typescript())
        self._tsx_lang = Language(tst.language_tsx())
        self._ts_parser = Parser(self._ts_lang)
        self._tsx_parser = Parser(self._tsx_lang)

    def _get_parser_for_path(self, file_path: str) -> Parser:
        if file_path.endswith(".tsx"):
            return self._tsx_parser
        return self._ts_parser

    def parse_source(self, code: str, file_path: str, relative_path: str, language: Optional[str] = None) -> FileParseResult:
        module_name = ts_file_path_to_module_name(relative_path)
        index = CodeIndex(files=[relative_path])
        code_bytes = code.encode("utf-8")
        line_offsets = build_line_offsets(code_bytes)

        parser = self._get_parser_for_path(relative_path)
        try:
            tree = parser.parse(code_bytes)
        except Exception as e:
            err = ParseErrorInfo(
                file_path=relative_path,
                error_message=f"TreeSitterParseError: {str(e)}",
                line_number=None,
                language="TypeScript"
            )
            index.parse_errors.append(err)
            return FileParseResult(
                file_path=file_path,
                relative_path=relative_path,
                code_index=index,
                success=False,
                error_message=err.error_message,
                language="TypeScript"
            )

        root = tree.root_node
        if root.has_error:
            # Note: tree-sitter produces partial AST even with errors, but log syntax error
            for child in root.children:
                if child.type == "ERROR":
                    index.parse_errors.append(ParseErrorInfo(
                        file_path=relative_path,
                        error_message="TypeScript syntax error in AST",
                        line_number=get_node_start_line(child, line_offsets),
                        language="TypeScript"
                    ))
                    break

        # Module-level symbol
        module_symbol = Symbol(
            name=module_name.split(".")[-1] if module_name else "module",
            qualified_name=module_name,
            kind=SymbolKind.MODULE,
            file_path=relative_path,
            line_number=1,
            end_line_number=max(1, len(code.splitlines())),
            parent_qualified_name=None,
            docstring=None,
            language="TypeScript"
        )
        index.symbols[module_name] = module_symbol

        # Walk AST iteratively
        self._traverse_node(root, module_name, relative_path, code_bytes, line_offsets, index, is_parent_exported=False)

        return FileParseResult(
            file_path=file_path,
            relative_path=relative_path,
            code_index=index,
            success=True,
            language="TypeScript"
        )

    def _traverse_node(
        self,
        initial_node: Node,
        initial_qname: str,
        relative_path: str,
        code_bytes: bytes,
        line_offsets: List[int],
        index: CodeIndex,
        is_parent_exported: bool = False
    ) -> None:
        """Iteratively process AST nodes to extract declarations, imports, exports, and calls safely without recursion."""
        stack: List[Tuple[Node, str, bool]] = [(initial_node, initial_qname, is_parent_exported)]

        while stack:
            curr, parent_qname, exported_flag = stack.pop()
            node_type = curr.type

            # 1. Imports
            if node_type == "import_statement":
                self._handle_import(curr, relative_path, code_bytes, line_offsets, index)

            # 2. Exports
            elif node_type == "export_statement":
                self._handle_export(curr, parent_qname, relative_path, code_bytes, line_offsets, index, stack=stack)

            # 3. Function Declaration
            elif node_type == "function_declaration":
                self._handle_function(curr, parent_qname, relative_path, code_bytes, line_offsets, index, is_exported=exported_flag, stack=stack)

            # 4. Lexical / Variable Declaration (const foo = () => {})
            elif node_type in ("lexical_declaration", "variable_declaration"):
                self._handle_variable_declaration(curr, parent_qname, relative_path, code_bytes, line_offsets, index, is_exported=exported_flag, stack=stack)

            # 5. Class Declaration
            elif node_type == "class_declaration":
                self._handle_class(curr, parent_qname, relative_path, code_bytes, line_offsets, index, is_exported=exported_flag, stack=stack)

            # 6. Interface Declaration
            elif node_type == "interface_declaration":
                self._handle_interface(curr, parent_qname, relative_path, code_bytes, line_offsets, index, is_exported=exported_flag)

            # 7. Function Call
            elif node_type == "call_expression":
                self._handle_call(curr, parent_qname, relative_path, code_bytes, line_offsets, index)
                for child in reversed(curr.children):
                    if child.is_named:
                        stack.append((child, parent_qname, False))

            # 8. Identifier Reference
            elif node_type == "identifier":
                sym_name = get_node_text(curr, code_bytes)
                index.references.append(ReferenceInfo(
                    symbol_name=sym_name,
                    context_symbol=parent_qname,
                    line_number=get_node_start_line(curr, line_offsets),
                    file_path=relative_path,
                    language="TypeScript"
                ))

            # 9. Other blocks and container nodes
            elif node_type not in (
                "function_declaration", "class_declaration", "interface_declaration",
                "export_statement", "method_definition", "import_statement"
            ):
                for child in reversed(curr.children):
                    if child.is_named:
                        stack.append((child, parent_qname, exported_flag))

    def _handle_import(self, node: Node, relative_path: str, code_bytes: bytes, line_offsets: List[int], index: CodeIndex) -> None:
        source_node = node.child_by_field_name("source")
        if not source_node:
            for c in node.children:
                if c.type == "string":
                    source_node = c
                    break

        module_str = get_node_text(source_node, code_bytes).strip("'\"") if source_node else ""
        line_no = get_node_start_line(node, line_offsets)

        clause_node = None
        for c in node.children:
            if c.type == "import_clause":
                clause_node = c
                break

        if not clause_node:
            # Side-effect import: import "./setup";
            index.imports.append(ImportInfo(
                module=module_str,
                imported_name=module_str,
                alias=None,
                is_from=False,
                line_number=line_no,
                file_path=relative_path,
                language="TypeScript"
            ))
            return

        for child in clause_node.children:
            if child.type == "identifier":
                # Default import: import React from 'react'
                name = get_node_text(child, code_bytes)
                index.imports.append(ImportInfo(
                    module=module_str,
                    imported_name=name,
                    alias=None,
                    is_from=True,
                    is_default=True,
                    line_number=line_no,
                    file_path=relative_path,
                    language="TypeScript"
                ))
            elif child.type == "namespace_import":
                # Namespace import: import * as React from 'react'
                ident = None
                for sub in child.children:
                    if sub.type == "identifier":
                        ident = get_node_text(sub, code_bytes)
                index.imports.append(ImportInfo(
                    module=module_str,
                    imported_name=ident or "*",
                    alias=ident,
                    is_from=True,
                    is_namespace=True,
                    line_number=line_no,
                    file_path=relative_path,
                    language="TypeScript"
                ))
            elif child.type == "named_imports":
                # Named imports: import { a, b as c } from './mod'
                for spec in child.children:
                    if spec.type == "import_specifier":
                        name_node = spec.child_by_field_name("name")
                        alias_node = spec.child_by_field_name("alias")
                        if name_node:
                            orig_name = get_node_text(name_node, code_bytes)
                            alias_name = get_node_text(alias_node, code_bytes) if alias_node else None
                            index.imports.append(ImportInfo(
                                module=module_str,
                                imported_name=orig_name,
                                alias=alias_name,
                                is_from=True,
                                line_number=line_no,
                                file_path=relative_path,
                                language="TypeScript"
                            ))

    def _handle_export(
        self,
        node: Node,
        parent_qname: str,
        relative_path: str,
        code_bytes: bytes,
        line_offsets: List[int],
        index: CodeIndex,
        stack: Optional[List[Tuple[Node, str, bool]]] = None
    ) -> None:
        line_no = get_node_start_line(node, line_offsets)
        is_default = any(c.type == "default" for c in node.children)

        for child in node.children:
            if child.type == "export_clause":
                for spec in child.children:
                    if spec.type == "export_specifier":
                        name_node = spec.child_by_field_name("name")
                        alias_node = spec.child_by_field_name("alias")
                        if name_node:
                            orig = get_node_text(name_node, code_bytes)
                            alias = get_node_text(alias_node, code_bytes) if alias_node else None
                            index.exports.append(ExportInfo(
                                name=orig,
                                exported_as=alias,
                                is_default=is_default,
                                file_path=relative_path,
                                line_number=line_no
                            ))
            elif child.is_named and child.type not in ("export", "default"):
                if stack is not None:
                    stack.append((child, parent_qname, True))
                else:
                    self._traverse_node(child, parent_qname, relative_path, code_bytes, line_offsets, index, is_parent_exported=True)

    def _handle_function(
        self,
        node: Node,
        parent_qname: str,
        relative_path: str,
        code_bytes: bytes,
        line_offsets: List[int],
        index: CodeIndex,
        is_exported: bool,
        stack: Optional[List[Tuple[Node, str, bool]]] = None
    ) -> None:
        name_node = node.child_by_field_name("name")
        func_name = get_node_text(name_node, code_bytes) if name_node else "anonymous"
        qname = f"{parent_qname}.{func_name}" if parent_qname else func_name

        params = extract_ts_parameters(node.child_by_field_name("parameters"), code_bytes)
        return_node = node.child_by_field_name("return_type")
        return_annot = get_node_text(return_node, code_bytes) if return_node else None
        docstring = extract_leading_docstring(node, code_bytes)
        complexity = calculate_ts_cyclomatic_complexity(node, code_bytes)

        start_line = get_node_start_line(node, line_offsets)
        end_line = get_node_end_line(node, line_offsets)
        length_lines = max(1, end_line - start_line + 1)
        is_async = any(c.type == "async" for c in node.children)

        func_info = FunctionInfo(
            name=func_name,
            qualified_name=qname,
            kind=SymbolKind.FUNCTION,
            file_path=relative_path,
            line_number=start_line,
            end_line_number=end_line,
            parent_qualified_name=parent_qname,
            docstring=docstring,
            language="TypeScript",
            is_exported=is_exported,
            parameters=params,
            return_annotation=return_annot,
            is_method=False,
            is_async=is_async,
            is_arrow=False,
            cyclomatic_complexity=complexity,
            length_lines=length_lines
        )
        index.functions[qname] = func_info
        index.symbols[qname] = func_info

        if is_exported:
            index.exports.append(ExportInfo(
                name=func_name,
                exported_as=None,
                is_default=False,
                file_path=relative_path,
                line_number=start_line
            ))

        body = node.child_by_field_name("body")
        if body:
            if stack is not None:
                stack.append((body, qname, False))
            else:
                self._traverse_node(body, qname, relative_path, code_bytes, line_offsets, index, is_parent_exported=False)

    def _handle_variable_declaration(
        self,
        node: Node,
        parent_qname: str,
        relative_path: str,
        code_bytes: bytes,
        line_offsets: List[int],
        index: CodeIndex,
        is_exported: bool,
        stack: Optional[List[Tuple[Node, str, bool]]] = None
    ) -> None:
        for declarator in node.children:
            if declarator.type == "variable_declarator":
                name_node = declarator.child_by_field_name("name")
                value_node = declarator.child_by_field_name("value")

                if name_node and value_node and value_node.type in ("arrow_function", "function_expression"):
                    func_name = get_node_text(name_node, code_bytes)
                    qname = f"{parent_qname}.{func_name}" if parent_qname else func_name

                    params = extract_ts_parameters(value_node.child_by_field_name("parameters"), code_bytes)
                    return_node = value_node.child_by_field_name("return_type")
                    return_annot = get_node_text(return_node, code_bytes) if return_node else None
                    docstring = extract_leading_docstring(node, code_bytes)
                    complexity = calculate_ts_cyclomatic_complexity(value_node, code_bytes)

                    start_line = get_node_start_line(declarator, line_offsets)
                    end_line = get_node_end_line(declarator, line_offsets)
                    length_lines = max(1, end_line - start_line + 1)
                    is_async = any(c.type == "async" for c in value_node.children)

                    func_info = FunctionInfo(
                        name=func_name,
                        qualified_name=qname,
                        kind=SymbolKind.FUNCTION,
                        file_path=relative_path,
                        line_number=start_line,
                        end_line_number=end_line,
                        parent_qualified_name=parent_qname,
                        docstring=docstring,
                        language="TypeScript",
                        is_exported=is_exported,
                        parameters=params,
                        return_annotation=return_annot,
                        is_method=False,
                        is_async=is_async,
                        is_arrow=(value_node.type == "arrow_function"),
                        cyclomatic_complexity=complexity,
                        length_lines=length_lines
                    )
                    index.functions[qname] = func_info
                    index.symbols[qname] = func_info

                    if is_exported:
                        index.exports.append(ExportInfo(
                            name=func_name,
                            exported_as=None,
                            is_default=False,
                            file_path=relative_path,
                            line_number=start_line
                        ))

                    body = value_node.child_by_field_name("body")
                    if body:
                        if stack is not None:
                            stack.append((body, qname, False))
                        else:
                            self._traverse_node(body, qname, relative_path, code_bytes, line_offsets, index, is_parent_exported=False)
                elif stack is not None:
                    stack.append((declarator, parent_qname, False))

    def _handle_class(
        self,
        node: Node,
        parent_qname: str,
        relative_path: str,
        code_bytes: bytes,
        line_offsets: List[int],
        index: CodeIndex,
        is_exported: bool,
        stack: Optional[List[Tuple[Node, str, bool]]] = None
    ) -> None:
        name_node = node.child_by_field_name("name")
        class_name = get_node_text(name_node, code_bytes) if name_node else "AnonymousClass"
        qname = f"{parent_qname}.{class_name}" if parent_qname else class_name

        docstring = extract_leading_docstring(node, code_bytes)
        start_line = get_node_start_line(node, line_offsets)
        end_line = get_node_end_line(node, line_offsets)

        base_classes: List[str] = []
        implemented_interfaces: List[str] = []
        for child in node.children:
            if child.type == "class_heritage":
                for h_clause in child.children:
                    if h_clause.type == "extends_clause":
                        for sub in h_clause.children:
                            if sub.is_named and sub.type not in ("extends",):
                                base_classes.append(get_node_text(sub, code_bytes))
                    elif h_clause.type == "implements_clause":
                        for sub in h_clause.children:
                            if sub.is_named and sub.type not in ("implements",):
                                implemented_interfaces.append(get_node_text(sub, code_bytes))
                    elif h_clause.is_named and h_clause.type not in ("extends", "implements"):
                        base_classes.append(get_node_text(h_clause, code_bytes))

        decorators: List[str] = []
        for child in node.children:
            if child.type == "decorator":
                decorators.append(get_node_text(child, code_bytes).lstrip("@"))

        class_info = ClassInfo(
            name=class_name,
            qualified_name=qname,
            kind=SymbolKind.CLASS,
            file_path=relative_path,
            line_number=start_line,
            end_line_number=end_line,
            parent_qualified_name=parent_qname,
            docstring=docstring,
            language="TypeScript",
            is_exported=is_exported,
            base_classes=base_classes,
            implemented_interfaces=implemented_interfaces,
            decorators=decorators,
            method_names=[],
            length_lines=max(1, end_line - start_line + 1)
        )
        index.classes[qname] = class_info
        index.symbols[qname] = class_info

        if is_exported:
            index.exports.append(ExportInfo(
                name=class_name,
                exported_as=None,
                is_default=False,
                file_path=relative_path,
                line_number=start_line
            ))

        body = node.child_by_field_name("body")
        if body:
            for m_node in body.children:
                if m_node.type == "method_definition":
                    self._handle_method(m_node, qname, class_name, relative_path, code_bytes, line_offsets, index, class_info, stack=stack)

    def _handle_method(
        self,
        node: Node,
        class_qname: str,
        class_name: str,
        relative_path: str,
        code_bytes: bytes,
        line_offsets: List[int],
        index: CodeIndex,
        class_info: ClassInfo,
        stack: Optional[List[Tuple[Node, str, bool]]] = None
    ) -> None:
        name_node = node.child_by_field_name("name")
        method_name = get_node_text(name_node, code_bytes) if name_node else "anonymousMethod"
        qname = f"{class_qname}.{method_name}"

        params = extract_ts_parameters(node.child_by_field_name("parameters"), code_bytes)
        return_node = node.child_by_field_name("return_type")
        return_annot = get_node_text(return_node, code_bytes) if return_node else None
        docstring = extract_leading_docstring(node, code_bytes)
        complexity = calculate_ts_cyclomatic_complexity(node, code_bytes)

        start_line = get_node_start_line(node, line_offsets)
        end_line = get_node_end_line(node, line_offsets)

        is_static = any(c.type == "static" for c in node.children)
        is_prop = any(c.type in ("get", "set") for c in node.children)
        is_async = any(c.type == "async" for c in node.children)

        method_info = MethodInfo(
            name=method_name,
            qualified_name=qname,
            kind=SymbolKind.METHOD,
            file_path=relative_path,
            line_number=start_line,
            end_line_number=end_line,
            parent_qualified_name=class_qname,
            docstring=docstring,
            language="TypeScript",
            parameters=params,
            return_annotation=return_annot,
            is_method=True,
            class_name=class_name,
            is_static=is_static,
            is_classmethod=False,
            is_property=is_prop,
            is_async=is_async,
            cyclomatic_complexity=complexity,
            length_lines=max(1, end_line - start_line + 1)
        )
        index.methods[qname] = method_info
        index.functions[qname] = method_info
        index.symbols[qname] = method_info
        class_info.method_names.append(method_name)

        body = node.child_by_field_name("body")
        if body:
            if stack is not None:
                stack.append((body, qname, False))
            else:
                self._traverse_node(body, qname, relative_path, code_bytes, line_offsets, index, is_parent_exported=False)

    def _handle_interface(
        self,
        node: Node,
        parent_qname: str,
        relative_path: str,
        code_bytes: bytes,
        line_offsets: List[int],
        index: CodeIndex,
        is_exported: bool
    ) -> None:
        name_node = node.child_by_field_name("name")
        interface_name = get_node_text(name_node, code_bytes) if name_node else "AnonymousInterface"
        qname = f"{parent_qname}.{interface_name}" if parent_qname else interface_name

        docstring = extract_leading_docstring(node, code_bytes)
        start_line = get_node_start_line(node, line_offsets)
        end_line = get_node_end_line(node, line_offsets)

        extends_list: List[str] = []
        for child in node.children:
            if child.type == "extends_type_clause":
                for sub in child.children:
                    if sub.is_named and sub.type not in ("extends",):
                        extends_list.append(get_node_text(sub, code_bytes))

        props: List[str] = []
        methods: List[str] = []
        body = node.child_by_field_name("body")
        if body:
            for item in body.children:
                if item.type == "property_signature":
                    pname = item.child_by_field_name("name")
                    if pname:
                        props.append(get_node_text(pname, code_bytes))
                elif item.type == "method_signature":
                    mname = item.child_by_field_name("name")
                    if mname:
                        methods.append(get_node_text(mname, code_bytes))

        interface_info = InterfaceInfo(
            name=interface_name,
            qualified_name=qname,
            kind=SymbolKind.INTERFACE,
            file_path=relative_path,
            line_number=start_line,
            end_line_number=end_line,
            parent_qualified_name=parent_qname,
            docstring=docstring,
            language="TypeScript",
            is_exported=is_exported,
            extended_interfaces=extends_list,
            properties=props,
            method_names=methods
        )
        index.interfaces[qname] = interface_info
        index.symbols[qname] = interface_info

        if is_exported:
            index.exports.append(ExportInfo(
                name=interface_name,
                exported_as=None,
                is_default=False,
                file_path=relative_path,
                line_number=start_line
            ))

    def _handle_call(
        self,
        node: Node,
        parent_qname: str,
        relative_path: str,
        code_bytes: bytes,
        line_offsets: List[int],
        index: CodeIndex
    ) -> None:
        fn_node = node.child_by_field_name("function")
        if not fn_node:
            return
        callee_expr = get_node_text(fn_node, code_bytes)
        args_node = node.child_by_field_name("arguments")
        arg_count = len([c for c in args_node.children if c.is_named]) if args_node else 0

        index.calls.append(CallInfo(
            caller_qualified_name=parent_qname,
            callee_name=callee_expr,
            resolved_callee=None,
            line_number=get_node_start_line(node, line_offsets),
            file_path=relative_path,
            arguments_count=arg_count,
            language="TypeScript"
        ))

