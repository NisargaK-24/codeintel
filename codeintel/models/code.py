from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


class SymbolKind(str, Enum):
    """Category of code symbol."""
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    INTERFACE = "interface"


class Symbol(BaseModel):
    """Represents any named code entity extracted from AST or Tree-sitter."""
    name: str = Field(description="Unqualified identifier name")
    qualified_name: str = Field(description="Hierarchical canonical identifier (e.g. module.Class.method)")
    kind: SymbolKind = Field(description="Symbol category")
    file_path: str = Field(description="File containing the symbol")
    line_number: int = Field(description="Starting line in source file (1-indexed)")
    end_line_number: int = Field(description="Ending line in source file (1-indexed)")
    parent_qualified_name: Optional[str] = Field(default=None, description="Enclosing scope symbol")
    docstring: Optional[str] = Field(default=None, description="Attached docstring if present")
    language: str = Field(default="Python", description="Source programming language")
    is_exported: bool = Field(default=False, description="Whether symbol is exported from module")

    # Compatibility aliases
    @property
    def file(self) -> str:
        return self.file_path

    @property
    def start_line(self) -> int:
        return self.line_number

    @property
    def end_line(self) -> int:
        return self.end_line_number

    @property
    def symbol_type(self) -> str:
        return self.kind.value


class FunctionInfo(Symbol):
    """Detailed metadata for a top-level, nested, or arrow function."""
    kind: SymbolKind = Field(default=SymbolKind.FUNCTION)
    parameters: List[str] = Field(default_factory=list, description="Parameter names")
    return_annotation: Optional[str] = Field(default=None, description="Type annotation for return value")
    decorators: List[str] = Field(default_factory=list, description="Names of applied decorators")
    is_method: bool = Field(default=False, description="Whether this function belongs to a class")
    is_async: bool = Field(default=False, description="Whether this is an async function")
    is_arrow: bool = Field(default=False, description="Whether this is an arrow function (JS/TS)")
    cyclomatic_complexity: int = Field(default=1, description="McCabe cyclomatic complexity score")
    length_lines: int = Field(default=1, description="Total source lines spanning this function")
    called_functions: List[str] = Field(default_factory=list, description="Names of functions called within body")


class MethodInfo(FunctionInfo):
    """Detailed metadata for a class method."""
    kind: SymbolKind = Field(default=SymbolKind.METHOD)
    is_method: bool = Field(default=True)
    class_name: str = Field(default="", description="Name of the enclosing class")
    is_static: bool = Field(default=False, description="Whether method is decorated with @staticmethod or static keyword")
    is_classmethod: bool = Field(default=False, description="Whether method is decorated with @classmethod")
    is_property: bool = Field(default=False, description="Whether method is a property/getter")


class ClassInfo(Symbol):
    """Detailed metadata for a class definition."""
    kind: SymbolKind = Field(default=SymbolKind.CLASS)
    base_classes: List[str] = Field(default_factory=list, description="Direct base class names")
    implemented_interfaces: List[str] = Field(default_factory=list, description="Implemented interface names (TS)")
    decorators: List[str] = Field(default_factory=list, description="Decorators applied to class")
    method_names: List[str] = Field(default_factory=list, description="Names of methods defined on class")
    length_lines: int = Field(default=1, description="Total source lines spanning this class")


class InterfaceInfo(Symbol):
    """Detailed metadata for a TypeScript interface definition."""
    kind: SymbolKind = Field(default=SymbolKind.INTERFACE)
    extended_interfaces: List[str] = Field(default_factory=list, description="Extended interface names")
    properties: List[str] = Field(default_factory=list, description="Property names defined in interface")
    method_names: List[str] = Field(default_factory=list, description="Method signatures defined in interface")


class ExportInfo(BaseModel):
    """Module export record (ES6 / CommonJS / Python __all__)."""
    name: str = Field(description="Exported symbol name or *")
    exported_as: Optional[str] = Field(default=None, description="Export alias if exported as another name")
    is_default: bool = Field(default=False, description="Whether this is the default export")
    file_path: str = Field(description="File containing export")
    line_number: int = Field(description="Line number of export")


class ImportInfo(BaseModel):
    """Import statement parsed from source file."""
    module: str = Field(description="Module being imported (e.g. './utils' or 'os.path')")
    imported_name: str = Field(description="Specific symbol imported or module name")
    alias: Optional[str] = Field(default=None, description="Alias if imported with 'as'")
    is_from: bool = Field(default=False, description="Whether this was a 'from x import y' statement")
    is_default: bool = Field(default=False, description="Whether default import (JS/TS)")
    is_namespace: bool = Field(default=False, description="Whether import * as namespace (JS/TS)")
    line_number: int = Field(description="Line number of import")
    file_path: str = Field(description="File containing this import")
    language: str = Field(default="Python", description="Source code language")
    is_resolved: bool = Field(default=False, description="Whether import target was successfully resolved")
    resolved_path: Optional[str] = Field(default=None, description="Resolved relative file path if matched")


class CallInfo(BaseModel):
    """Function or method call expression."""
    caller_qualified_name: str = Field(description="Symbol making the call")
    callee_name: str = Field(description="Expression being invoked (e.g. 'calculate_tax' or 'self.pay')")
    resolved_callee: Optional[str] = Field(default=None, description="Resolved qualified name if matched")
    line_number: int = Field(description="Line number where call occurs")
    file_path: str = Field(description="File where call occurs")
    arguments_count: int = Field(default=0, description="Number of arguments supplied to call")
    language: str = Field(default="Python", description="Source language")


class ReferenceInfo(BaseModel):
    """Symbol identifier reference."""
    symbol_name: str = Field(description="Name referenced in code")
    context_symbol: str = Field(description="Symbol within which reference occurs")
    line_number: int = Field(description="Line number of reference")
    file_path: str = Field(description="File where reference occurs")
    language: str = Field(default="Python", description="Source language")


class ParseErrorInfo(BaseModel):
    """Diagnostic record for files with syntax or parsing errors."""
    file_path: str = Field(description="File that failed to parse")
    error_message: str = Field(description="Error details")
    line_number: Optional[int] = Field(default=None, description="Line number of failure")
    language: str = Field(default="Unknown", description="Language of file")


class CodeIndex(BaseModel):
    """Aggregated index of all parsed symbols, imports, and calls in a repository across languages."""
    files: List[str] = Field(default_factory=list, description="List of parsed file paths")
    symbols: Dict[str, Symbol] = Field(default_factory=dict, description="Qualified name -> Symbol mapping")
    functions: Dict[str, FunctionInfo] = Field(default_factory=dict, description="Qualified name -> FunctionInfo")
    classes: Dict[str, ClassInfo] = Field(default_factory=dict, description="Qualified name -> ClassInfo")
    methods: Dict[str, MethodInfo] = Field(default_factory=dict, description="Qualified name -> MethodInfo")
    interfaces: Dict[str, InterfaceInfo] = Field(default_factory=dict, description="Qualified name -> InterfaceInfo")
    exports: List[ExportInfo] = Field(default_factory=list, description="All parsed export statements")
    imports: List[ImportInfo] = Field(default_factory=list, description="All parsed import statements")
    calls: List[CallInfo] = Field(default_factory=list, description="All parsed function call sites")
    references: List[ReferenceInfo] = Field(default_factory=list, description="All symbol identifier references")
    parse_errors: List[ParseErrorInfo] = Field(default_factory=list, description="Files with parse errors")
    resolved_imports_count: int = Field(default=0, description="Count of successfully resolved imports")
    unresolved_imports_count: int = Field(default=0, description="Count of unresolved imports")
    language_stats: Dict[str, Dict[str, int]] = Field(
        default_factory=dict,
        description="Per-language summary statistics (files, parsed, failed, functions, classes, methods, imports, calls)"
    )
    unsupported_languages: Dict[str, int] = Field(
        default_factory=dict,
        description="Languages detected in scan for which no parser is registered"
    )
