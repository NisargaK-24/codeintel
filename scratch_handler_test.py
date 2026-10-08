from codeintel.parser.typescript_parser import TypeScriptParser
from codeintel.models.code import CodeIndex

code = open('C:/carcblog-main/src/components/islands/AISettingsForm.tsx', encoding='utf-8').read()
p = TypeScriptParser()

handlers = ["import", "interface", "export", "function", "variable", "class", "call", "reference"]

for h_limit in range(1, len(handlers) + 1):
    active = handlers[:h_limit]
    print(f"Testing with active handlers: {active}", flush=True)
    idx = CodeIndex()

    def make_traverse(act):
        def traverse(self, initial_node, initial_qname, relative_path, code_bytes, index, is_parent_exported=False):
            stack = [(initial_node, initial_qname, is_parent_exported)]
            while stack:
                curr, parent_qname, exported_flag = stack.pop()
                ntype = curr.type
                if "import" in act and ntype == "import_statement":
                    self._handle_import(curr, relative_path, code_bytes, index)
                elif "export" in act and ntype == "export_statement":
                    self._handle_export(curr, parent_qname, relative_path, code_bytes, index, stack=stack)
                elif "function" in act and ntype == "function_declaration":
                    self._handle_function(curr, parent_qname, relative_path, code_bytes, index, is_exported=exported_flag, stack=stack)
                elif "variable" in act and ntype in ("lexical_declaration", "variable_declaration"):
                    self._handle_variable_declaration(curr, parent_qname, relative_path, code_bytes, index, is_exported=exported_flag, stack=stack)
                elif "class" in act and ntype == "class_declaration":
                    self._handle_class(curr, parent_qname, relative_path, code_bytes, index, is_exported=exported_flag, stack=stack)
                elif "interface" in act and ntype == "interface_declaration":
                    self._handle_interface(curr, parent_qname, relative_path, code_bytes, index, is_exported=exported_flag)
                elif "call" in act and ntype == "call_expression":
                    self._handle_call(curr, parent_qname, relative_path, code_bytes, index)
                    for c in reversed(curr.children):
                        if c.is_named:
                            stack.append((c, parent_qname, False))
                elif "reference" in act and ntype == "identifier":
                    from codeintel.models.code import ReferenceInfo
                    from codeintel.parser.tree_sitter_base import get_node_text
                    sym = get_node_text(curr, code_bytes)
                    index.references.append(ReferenceInfo(
                        symbol_name=sym,
                        context_symbol=parent_qname,
                        line_number=curr.start_point.row + 1,
                        file_path=relative_path,
                        language="TypeScript"
                    ))
                else:
                    for c in reversed(curr.children):
                        if c.is_named:
                            stack.append((c, parent_qname, exported_flag))
        return traverse

    TypeScriptParser._traverse_node = make_traverse(active)
    p.parse_source(code, 'AISettingsForm.tsx', 'AISettingsForm.tsx')
    print(f"Passed handlers: {active}", flush=True)

print("ALL HANDLERS PASSED!")
