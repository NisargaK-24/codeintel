from pathlib import Path
from typing import Dict, List, Optional, Set

from codeintel.models.code import CallInfo, CodeIndex
from codeintel.models.repository import ScanResult
from codeintel.parser.base import BaseParser
from codeintel.parser.registry import ParserRegistry, default_parser_registry
from codeintel.parser.resolver import resolve_ts_relative_import
from codeintel.scanner.scanner import RepositoryScanner


class CodeAnalyzer:
    """Orchestrates multi-language parsing across repository files, resolves symbol calls, and builds CodeIndex."""

    def __init__(self, parser: Optional[BaseParser] = None, registry: Optional[ParserRegistry] = None):
        self.registry = registry or ParserRegistry()
        if parser is not None:
            self.registry.register(parser)

    def analyze_repository(self, target_path: str | Path, scan_result: Optional[ScanResult] = None) -> CodeIndex:
        """Scan and parse all supported files across languages in the repository to produce a unified CodeIndex."""
        root = Path(target_path).resolve()
        if scan_result is None:
            scanner = RepositoryScanner()
            scan_result = scanner.scan(root)

        master_index = CodeIndex()
        known_files: Set[str] = {f.relative_path.replace("\\", "/") for f in scan_result.files}

        # Track per-language files
        for scanned_file in scan_result.files:
            lang = scanned_file.language
            parser = self.registry.get_parser_for_language(lang)

            if not parser:
                # Track detected languages without active parsers
                if not scanned_file.is_binary:
                    master_index.unsupported_languages[lang] = master_index.unsupported_languages.get(lang, 0) + 1
                continue

            # Initialize stats
            stats = master_index.language_stats.setdefault(parser.name, {
                "files": 0, "parsed": 0, "failed": 0,
                "functions": 0, "classes": 0, "methods": 0, "interfaces": 0,
                "imports": 0, "calls": 0
            })
            stats["files"] += 1

            full_path = Path(scanned_file.path)
            parse_result = parser.parse_file(full_path, root, language=lang)
            file_idx = parse_result.code_index

            if parse_result.success and not file_idx.parse_errors:
                stats["parsed"] += 1
            else:
                stats["failed"] += 1

            # Count symbols added by this file
            stats["functions"] += len(file_idx.functions) - len(file_idx.methods)
            stats["classes"] += len(file_idx.classes)
            stats["methods"] += len(file_idx.methods)
            stats["interfaces"] += len(file_idx.interfaces)
            stats["imports"] += len(file_idx.imports)
            stats["calls"] += len(file_idx.calls)

            # Merge into master index
            master_index.files.extend(file_idx.files)
            master_index.symbols.update(file_idx.symbols)
            master_index.functions.update(file_idx.functions)
            master_index.classes.update(file_idx.classes)
            master_index.methods.update(file_idx.methods)
            master_index.interfaces.update(file_idx.interfaces)
            master_index.exports.extend(file_idx.exports)
            master_index.imports.extend(file_idx.imports)
            master_index.calls.extend(file_idx.calls)
            master_index.references.extend(file_idx.references)
            master_index.parse_errors.extend(file_idx.parse_errors)

        # 1. Resolve relative and module imports
        self._resolve_imports(master_index, root, known_files)

        # 2. Resolve call targets across modules and languages
        self._resolve_calls(master_index)

        return master_index

    def _resolve_imports(self, index: CodeIndex, root: Path, known_files: Set[str]) -> None:
        """Resolve import targets for TypeScript/JavaScript and Python imports."""
        resolved_count = 0
        unresolved_count = 0

        for imp in index.imports:
            if imp.language in ("TypeScript", "JavaScript"):
                is_resolved, resolved_path = resolve_ts_relative_import(
                    import_module=imp.module,
                    current_file_path=imp.file_path,
                    repo_root=root,
                    known_files=known_files
                )
                imp.is_resolved = is_resolved
                imp.resolved_path = resolved_path
                if is_resolved:
                    resolved_count += 1
                else:
                    unresolved_count += 1
            elif imp.language == "Python":
                # Check if imported module exists among indexed files or python symbols
                mod_file_cand = imp.module.replace(".", "/") + ".py"
                mod_init_cand = imp.module.replace(".", "/") + "/__init__.py"
                if mod_file_cand in known_files or mod_init_cand in known_files:
                    imp.is_resolved = True
                    imp.resolved_path = mod_file_cand if mod_file_cand in known_files else mod_init_cand
                    resolved_count += 1
                else:
                    # Might be standard library (sys, math, os) or external package
                    imp.is_resolved = False
                    unresolved_count += 1

        index.resolved_imports_count = resolved_count
        index.unresolved_imports_count = unresolved_count

    def _resolve_calls(self, index: CodeIndex) -> None:
        """Resolve callee names to canonical qualified symbol names using imports and scope."""
        # Build quick lookup: (file_path, imported_alias_or_name) -> target_qualified_name
        import_map: Dict[tuple[str, str], str] = {}
        for imp in index.imports:
            alias_key = imp.alias or imp.imported_name
            target = f"{imp.module}.{imp.imported_name}" if imp.is_from else imp.module
            import_map[(imp.file_path, alias_key)] = target

        for call in index.calls:
            caller_sym = index.symbols.get(call.caller_qualified_name)
            file_path = call.file_path
            callee_expr = call.callee_name

            resolved: Optional[str] = None

            # 1. Simple call (e.g. "calculate_tax" or "formatCurrency")
            if "." not in callee_expr:
                # Check same file / module symbols
                for qname, sym in index.symbols.items():
                    if sym.file_path == file_path and sym.name == callee_expr:
                        resolved = qname
                        break

                # Check imports in this file
                if not resolved and (file_path, callee_expr) in import_map:
                    resolved = import_map[(file_path, callee_expr)]

            # 2. Member / attribute call (e.g. "self.pay", "this.service.pay", "calc.calculate_tax")
            else:
                parts = callee_expr.split(".")
                obj_name, attr_name = parts[0], parts[-1]

                if obj_name in ("self", "cls", "this"):
                    if caller_sym and caller_sym.parent_qualified_name:
                        class_qname = caller_sym.parent_qualified_name
                        candidate = f"{class_qname}.{attr_name}"
                        if candidate in index.methods:
                            resolved = candidate
                elif (file_path, obj_name) in import_map:
                    base_target = import_map[(file_path, obj_name)]
                    resolved = f"{base_target}.{attr_name}"

            call.resolved_callee = resolved
