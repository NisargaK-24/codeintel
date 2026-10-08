# CodeIntel

**Intelligent Zombie Code Detection and Predictive Commit Risk Analysis**

CodeIntel is an intelligent static analysis and software repository intelligence platform developed as an MCA final-year project.

> **CRITICAL PROJECT ARCHITECTURE CONSTRAINT**:
> CodeIntel operates **100% locally with ZERO LLMs or external cloud AI APIs**.
> All intelligence is derived strictly from:
> - Abstract Syntax Tree (AST) parsing
> - Dependency and call graph analysis (NetworkX)
> - Multi-factor rule-based heuristics with transparent scoring
> - Local Git history and hunk-level diff inspection
> - Software metrics (McCabe Cyclomatic Complexity, Fan-In/Fan-Out, Nesting Depth)

---

## Architecture Pipeline

```
Repository
   │
   ▼
[ Scanner ] ────────► File Discovery, Git State, Exclusions, SHA-256
   │
   ▼
[ Parser ] ─────────► AST Parsing, Stable Qualified Names, Symbol Table
   │
   ▼
[ Dependency Graph ] ► Multi-relational DiGraph (Calls, Imports, Inheritance)
   │
   ├──► [ Zombie Detector ] ──► Multi-factor suspicion scoring (0-100) & false-positive shields
   │
   ├──► [ Code Quality ] ────► McCabe Complexity, Secrets, Linters, Code Smells
   │
   └──► [ Git Analysis ] ────► Local commit history, diff hunks, churn metrics
              │
              ▼
       [ Change Impact ] ───► Blast radius, direct/indirect dependents, path tracing
```

---

## Installation

Ensure Python 3.10+ is installed.

```bash
# Clone the repository and enter the directory
cd CODEINTEL

# Install in editable mode
python -m pip install -e .
```

---

## CLI Usage

CodeIntel provides a modular Typer CLI interface:

```bash
# General help and version
codeintel --help
codeintel --version

# 1. Repository Scanner
codeintel scan <path>
codeintel scan <path> --json --verbose

# 2. Complete Code Analysis & Integration Overview
codeintel analyze <path>
codeintel analyze <path> --json

# 3. Dependency Graph Inspection
codeintel graph <path>
codeintel graph <path> --symbol "payment.service.PaymentService.calculate_payment"

# 4. Potential Zombie Code Detection
codeintel zombie <path>
codeintel zombie <path> --min-score 60 --json

# 5. Static Code Quality & Coding Standards
codeintel quality <path>
codeintel quality <path> --severity HIGH --json

# 6. Local Git Repository History & Commit Diff
codeintel git <path>
codeintel git <path> --commit <hash>

# 7. Change Impact Analysis
codeintel impact <path> --commit <hash>
```

---

## Features (Part 1 Foundation)

1. **Repository Scanner**
   - Recursive scanning respecting `.gitignore` and exclusion patterns
   - SHA-256 hashing, line counting, language detection, binary detection
   - Git repository detection and active branch identification
   - Zero code execution guarantee

2. **AST Code Parser**
   - Python AST extraction of modules, classes, functions, methods, imports, and calls
   - Hierarchical stable qualified symbol names (e.g. `module.Class.method`)
   - McCabe Cyclomatic Complexity computation
   - Error-tolerant: malformed files never crash analysis

3. **Dependency & Call Graph**
   - Directed multi-relational graph backed by NetworkX
   - Computes fan-in, fan-out, direct callers/callees, transitive ancestors/descendants
   - Cycle detection and call path resolution

4. **Potential Zombie Code Detection**
   - Multi-factor suspicion scoring (0-100)
   - False-positive shields: framework decorators (`@app.route`, `@pytest.fixture`), magic methods, entry points, `__all__` exports, test references
   - Transparent score reasoning and confidence classification (`LOW`, `MEDIUM`, `HIGH`)

5. **Code Quality Analyzer**
   - Unused imports detection
   - Function length and parameter limits
   - McCabe cyclomatic complexity (> 10)
   - Deep nesting detection (> 4 levels)
   - PEP-8 naming conventions
   - Public API docstring coverage
   - Hardcoded secret / API-key / credential pattern detection
   - Excessive class complexity

6. **Local Git Analysis**
   - Pure local Git parsing (supporting Git CLI and pure Python fallback)
   - Commit log, author details, timestamp, file churn (added/deleted lines)
   - Hunk-level line diff mapping

7. **Basic Change Impact Analysis**
   - Maps git diff line ranges to AST symbols
   - Identifies directly affected components (depth 1)
   - Traces indirect transitive blast radius
   - Computes impact radius and dependency paths explaining WHY components are affected
