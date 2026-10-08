import bisect
from typing import List, Optional, Set, Tuple
from tree_sitter import Node


def build_line_offsets(code_bytes: bytes) -> List[int]:
    """Precompute 0-indexed byte offsets for line starts to map byte positions to 1-indexed line numbers."""
    offsets = [0]
    for idx, b in enumerate(code_bytes):
        if b == 10:  # ord('\n')
            offsets.append(idx + 1)
    return offsets


def get_line_number_from_offset(line_offsets: List[int], byte_offset: int) -> int:
    """O(log N) lookup of 1-indexed line number for a given byte offset."""
    return bisect.bisect_right(line_offsets, byte_offset)


def get_node_text(node: Optional[Node], code_bytes: bytes = b"") -> str:
    """Extract utf-8 decoded text corresponding to a Tree-sitter AST node."""
    if node is None:
        return ""
    if code_bytes:
        try:
            sb = node.start_byte
            eb = node.end_byte
            if 0 <= sb <= eb <= len(code_bytes):
                return code_bytes[sb:eb].decode("utf-8", errors="replace").strip()
        except Exception:
            pass
    try:
        if hasattr(node, "text") and node.text is not None:
            return node.text.decode("utf-8", errors="replace").strip()
    except Exception:
        pass
    return ""


def calculate_ts_cyclomatic_complexity(node: Node, code_bytes: bytes = b"") -> int:
    """
    Calculate McCabe cyclomatic complexity for a Tree-sitter function or method node.
    Starts at 1, incrementing for each decision/branch point. Iterative traversal.
    """
    complexity = 1
    branch_types = {
        "if_statement", "while_statement", "for_statement", "for_in_statement",
        "catch_clause", "ternary_expression"
    }

    stack = [node]
    while stack:
        curr = stack.pop()
        if curr.type in branch_types:
            complexity += 1
        elif curr.type == "switch_case":
            if curr.children and curr.children[0].type != "default":
                complexity += 1
        elif curr.type == "binary_expression":
            for child in curr.children:
                if not child.is_named and child.type in {"&&", "||", "??"}:
                    complexity += 1
                    break

        for child in curr.children:
            stack.append(child)

    return complexity


def calculate_ts_nesting_depth(node: Node, current_depth: int = 0) -> int:
    """Find maximum block nesting depth inside a Tree-sitter node using iterative traversal."""
    nesting_types = {
        "if_statement", "while_statement", "for_statement", "for_in_statement",
        "try_statement", "catch_clause", "switch_statement"
    }
    max_d = current_depth
    stack = [(node, current_depth)]
    while stack:
        curr, depth = stack.pop()
        new_depth = depth + 1 if curr.type in nesting_types else depth
        if new_depth > max_d:
            max_d = new_depth
        for child in curr.children:
            stack.append((child, new_depth))

    return max_d


def extract_ts_parameters(params_node: Optional[Node], code_bytes: bytes) -> List[str]:
    """Extract formal parameter names from parameters/formal_parameters node."""
    if not params_node:
        return []
    params: List[str] = []
    for child in params_node.children:
        if not child.is_named:
            continue
        if child.type == "required_parameter" or child.type == "optional_parameter":
            p_name_node = child.child_by_field_name("name") or child.child_by_field_name("pattern")
            if p_name_node:
                params.append(get_node_text(p_name_node, code_bytes))
            else:
                params.append(get_node_text(child, code_bytes).split(":")[0].strip())
        elif child.type == "identifier":
            params.append(get_node_text(child, code_bytes))
        elif child.type == "rest_pattern":
            params.append(get_node_text(child, code_bytes))
        elif child.type == "assignment_pattern":
            left = child.child_by_field_name("left")
            if left:
                params.append(get_node_text(left, code_bytes))
    return params


def extract_leading_docstring(node: Node, code_bytes: bytes) -> Optional[str]:
    """Extract leading JSDoc / multiline comment preceding a declaration."""
    prev = node.prev_sibling
    if prev and prev.type == "comment":
        comment_text = get_node_text(prev, code_bytes)
        if comment_text.startswith("/**") or comment_text.startswith("/*"):
            # Clean up JSDoc comment
            lines = []
            for line in comment_text.splitlines():
                stripped = line.strip().lstrip("/*").rstrip("*/").strip().lstrip("*").strip()
                if stripped:
                    lines.append(stripped)
            return " ".join(lines) if lines else comment_text
    return None
