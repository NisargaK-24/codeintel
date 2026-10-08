from pathlib import Path
from typing import Optional, Set, Tuple

TS_JS_EXTENSIONS = [
    ".ts", ".tsx", ".d.ts", ".js", ".jsx", ".mjs", ".cjs",
    "/index.ts", "/index.tsx", "/index.d.ts", "/index.js", "/index.jsx"
]


def resolve_ts_relative_import(
    import_module: str,
    current_file_path: str,
    repo_root: Path,
    known_files: Set[str]
) -> Tuple[bool, Optional[str]]:
    """
    Resolve TypeScript / JavaScript import path (e.g. './utils', '../services/payment')
    to an existing file relative path within the repository.
    Returns (is_resolved, resolved_path).
    """
    cleaned_mod = import_module.strip("'\"")

    # Only attempt resolution for relative or path alias imports
    is_relative = cleaned_mod.startswith(".")
    is_alias = cleaned_mod.startswith("@/") or cleaned_mod.startswith("~/")

    if not is_relative and not is_alias:
        # Third party package or bare module specifier (e.g. 'react', 'lodash')
        return False, None

    norm_current = current_file_path.replace("\\", "/")
    current_dir = Path(norm_current).parent

    candidates = []

    if is_relative:
        base = (current_dir / cleaned_mod).as_posix()
        # Direct file with extension
        candidates.append(base)
        for ext in TS_JS_EXTENSIONS:
            candidates.append(f"{base}{ext}")
    elif is_alias:
        # Alias @/ or ~/ mapping to root or src/
        sub_path = cleaned_mod[2:]
        for prefix in ["", "src/"]:
            base = f"{prefix}{sub_path}"
            candidates.append(base)
            for ext in TS_JS_EXTENSIONS:
                candidates.append(f"{base}{ext}")

    import os

    # Check candidates against known files in repository
    norm_known = {
        os.path.normpath(f.replace("\\", "/")).replace("\\", "/").lstrip("./"): f.replace("\\", "/")
        for f in known_files
    }

    for cand in candidates:
        norm_cand = os.path.normpath(cand).replace("\\", "/").lstrip("./")
        if norm_cand in norm_known:
            return True, norm_known[norm_cand]

        # Check actual filesystem
        target_file = (repo_root / norm_cand).resolve()
        if target_file.is_file():
            try:
                rel = target_file.relative_to(repo_root.resolve()).as_posix()
                return True, rel
            except ValueError:
                pass

    return False, None
