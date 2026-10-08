import json
from pathlib import Path
from typing import Optional
import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from codeintel.config.settings import settings
from codeintel.git.repository import GitRepository
from codeintel.graph.dependency_graph import DependencyGraph
from codeintel.graph.graph_analyzer import GraphAnalyzer
from codeintel.impact.analyzer import ImpactAnalyzer
from codeintel.parser.analyzer import CodeAnalyzer
from codeintel.quality.analyzer import QualityAnalyzer
from codeintel.scanner.scanner import RepositoryScanner
from codeintel.zombie.detector import ZombieDetector
from codeintel.ml.risk_model import CommitRiskModel
from codeintel.risk.engine import CommitRiskEngine
from codeintel.web.app import run_server

app = typer.Typer(
    name="codeintel",
    help="CodeIntel — Intelligent Zombie Code Detection and Predictive Commit Risk Analysis (No-LLM Static Code Intelligence)",
    add_completion=False
)
console = Console()


def version_callback(value: bool):
    if value:
        console.print("[bold cyan]CodeIntel[/bold cyan] version [bold green]0.1.0[/bold green]")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show CodeIntel version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
):
    """CodeIntel root command callback."""
    pass


@app.command("scan")
def scan_cmd(
    path: str = typer.Argument(".", help="Path to repository directory to scan"),
    json_output: bool = typer.Option(False, "--json", help="Output results in JSON format"),
    verbose: bool = typer.Option(False, "--verbose", help="Show detailed verbose file list")
):
    """Recursively scan repository files, metadata, languages, hashes, and Git status."""
    target = Path(path).resolve()
    scanner = RepositoryScanner()
    try:
        result = scanner.scan(target)
    except Exception as e:
        console.print(f"[bold red]Scan Error:[/bold red] {e}")
        raise typer.Exit(code=1)

    if json_output:
        typer.echo(result.model_dump_json(indent=2))
        return

    # Render Rich Dashboard
    console.print(Panel(
        f"[bold cyan]Repository:[/bold cyan] {result.repository.root_path}\n"
        f"[bold]Git Repository:[/bold] {'[green]Yes[/green]' if result.repository.is_git else '[yellow]No[/yellow]'} "
        f"([cyan]Branch:[/cyan] {result.repository.branch or 'N/A'})\n"
        f"[bold]Total Files Scanned:[/bold] {result.stats.files_scanned} | "
        f"[bold]Files Skipped:[/bold] {result.stats.files_skipped}\n"
        f"[bold]Total Lines:[/bold] {result.stats.lines_total:,} | "
        f"[bold]Total Size:[/bold] {result.stats.size_total / 1024:.2f} KB | "
        f"[bold]Duration:[/bold] {result.stats.scan_duration_seconds:.4f}s",
        title="[bold green]CodeIntel — Repository Scan Summary[/bold green]",
        border_style="green"
    ))

    # Languages Table
    lang_table = Table(title="Languages Detected", box=box.ROUNDED)
    lang_table.add_column("Language", style="cyan")
    lang_table.add_column("File Count", style="magenta", justify="right")
    lang_table.add_column("Percentage", style="green", justify="right")

    total_f = max(1, result.stats.files_scanned)
    for lang, count in sorted(result.repository.languages.items(), key=lambda x: x[1], reverse=True):
        pct = (count / total_f) * 100.0
        lang_table.add_row(lang, str(count), f"{pct:.1f}%")
    console.print(lang_table)

    if verbose:
        files_table = Table(title="Scanned Files Detail", box=box.SIMPLE)
        files_table.add_column("Relative Path", style="dim")
        files_table.add_column("Language", style="cyan")
        files_table.add_column("Lines", justify="right")
        files_table.add_column("Size", justify="right")
        files_table.add_column("SHA-256 (Prefix)", style="yellow")

        for f in result.files:
            files_table.add_row(
                f.relative_path,
                f.language,
                str(f.line_count),
                f"{f.size_bytes} B",
                f.sha256_hash[:12] if f.sha256_hash else "N/A"
            )
        console.print(files_table)


@app.command("graph")
def graph_cmd(
    path: str = typer.Argument(".", help="Path to repository directory"),
    symbol: Optional[str] = typer.Option(None, "--symbol", "-s", help="Inspect specific symbol metrics and call tree"),
    json_output: bool = typer.Option(False, "--json", help="Output results in JSON format")
):
    """Build and query code dependency and caller-callee graphs."""
    target = Path(path).resolve()
    analyzer = CodeAnalyzer()
    code_index = analyzer.analyze_repository(target)
    dep_graph = DependencyGraph()
    dep_graph.build_from_index(code_index)
    graph_analyzer = GraphAnalyzer(dep_graph)

    if symbol:
        metrics = graph_analyzer.get_symbol_metrics(symbol)
        tree = graph_analyzer.render_ascii_tree(symbol)

        if json_output:
            data = metrics.model_dump()
            data["ascii_tree"] = tree
            typer.echo(json.dumps(data, indent=2))
            return

        console.print(Panel(
            f"[bold cyan]Symbol:[/bold cyan] {metrics.symbol}\n"
            f"[bold]Fan-In (Callers):[/bold] {metrics.fan_in}\n"
            f"[bold]Fan-Out (Callees):[/bold] {metrics.fan_out}\n"
            f"[bold]Transitive Callers (Upstream):[/bold] {metrics.transitive_callers_count}\n"
            f"[bold]Transitive Callees (Downstream):[/bold] {metrics.transitive_callees_count}\n"
            f"[bold]In Dependency Cycle:[/bold] {'[bold red]YES[/bold red]' if metrics.is_in_cycle else '[green]NO[/green]'}",
            title="[bold green]Symbol Dependency Metrics[/bold green]",
            border_style="cyan"
        ))

        if metrics.direct_callers:
            console.print("[bold]Direct Callers:[/bold] " + ", ".join(metrics.direct_callers))
        if metrics.direct_callees:
            console.print("[bold]Direct Callees:[/bold] " + ", ".join(metrics.direct_callees))

        console.print("\n[bold green]Call Hierarchy Tree:[/bold green]")
        console.print(tree)
        return

    summary = dep_graph.get_summary()

    if json_output:
        typer.echo(summary.model_dump_json(indent=2))
        return

    console.print(Panel(
        f"[bold]Total Graph Nodes:[/bold] {summary.total_nodes}\n"
        f"[bold]Total Graph Edges:[/bold] {summary.total_edges}\n"
        f"[bold]Caller -> Callee Edges:[/bold] {summary.call_edges_count}\n"
        f"[bold]Import Edges:[/bold] {summary.import_edges_count}\n"
        f"[bold]Dependency Cycles Detected:[/bold] {summary.cyclic_dependencies_count}",
        title="[bold green]Dependency Graph Overview[/bold green]",
        border_style="green"
    ))

    if summary.cycles:
        cycle_table = Table(title="Detected Dependency Cycles", box=box.ROUNDED)
        cycle_table.add_column("Cycle #", style="dim", width=8)
        cycle_table.add_column("Loop Path", style="red")
        for idx, c in enumerate(summary.cycles, 1):
            cycle_table.add_row(str(idx), " -> ".join(c))
        console.print(cycle_table)


@app.command("zombie")
def zombie_cmd(
    path: str = typer.Argument(".", help="Path to repository directory"),
    min_score: int = typer.Option(50, "--min-score", "-m", help="Minimum suspicion score (0-100)"),
    json_output: bool = typer.Option(False, "--json", help="Output results in JSON format")
):
    """Identify Potential Zombie Code using multi-factor evidence scoring."""
    target = Path(path).resolve()
    scanner = RepositoryScanner()
    scan_result = scanner.scan(target)
    analyzer = CodeAnalyzer()
    code_index = analyzer.analyze_repository(target, scan_result)

    dep_graph = DependencyGraph()
    dep_graph.build_from_index(code_index)
    graph_analyzer = GraphAnalyzer(dep_graph)

    # File mtimes
    file_mtimes = {f.relative_path: f.modified_at for f in scan_result.files}

    detector = ZombieDetector(min_score=min_score)
    report = detector.analyze(code_index, graph_analyzer, file_mtimes)

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
        return

    console.print(Panel(
        f"[bold]Functions Evaluated:[/bold] {report.total_functions_analyzed}\n"
        f"[bold]Potential Zombie Candidates:[/bold] [yellow]{report.potential_zombies_count}[/yellow]\n"
        f"[bold]High-Confidence Candidates:[/bold] [red]{report.high_confidence_count}[/red]\n"
        f"[bold]Minimum Score Threshold:[/bold] {min_score}",
        title="[bold green]Potential Zombie Code Detection Summary[/bold green]",
        border_style="yellow"
    ))

    if not report.candidates:
        console.print("[green]No potential zombie code detected meeting threshold.[/green]")
        return

    zombie_table = Table(title="Potential Zombie Candidates", box=box.ROUNDED)
    zombie_table.add_column("Score", justify="right", style="bold")
    zombie_table.add_column("Confidence", style="bold")
    zombie_table.add_column("Symbol", style="cyan")
    zombie_table.add_column("File", style="dim")
    zombie_table.add_column("Evidence Summary")

    for c in report.candidates:
        conf_color = "red" if c.confidence.value == "HIGH" else ("yellow" if c.confidence.value == "MEDIUM" else "cyan")
        zombie_table.add_row(
            f"[{conf_color}]{c.score:.1f}[/{conf_color}]",
            f"[{conf_color}]{c.confidence.value}[/{conf_color}]",
            c.symbol,
            f"{c.file}:{c.line_number or ''}",
            "; ".join(c.reasons[:2])
        )
    console.print(zombie_table)


@app.command("quality")
def quality_cmd(
    path: str = typer.Argument(".", help="Path to repository directory"),
    severity: Optional[str] = typer.Option(None, "--severity", "-s", help="Filter by severity (LOW, MEDIUM, HIGH)"),
    json_output: bool = typer.Option(False, "--json", help="Output results in JSON format")
):
    """Execute static code-quality rules, complexity checks, and defect detection."""
    target = Path(path).resolve()
    analyzer = CodeAnalyzer()
    code_index = analyzer.analyze_repository(target)
    quality_analyzer = QualityAnalyzer()
    report = quality_analyzer.analyze(code_index, target)

    issues = report.issues
    if severity:
        sev_upper = severity.upper()
        issues = [i for i in issues if i.severity.value == sev_upper]

    if json_output:
        data = report.model_dump()
        if severity:
            data["issues"] = [i.model_dump() for i in issues]
        typer.echo(json.dumps(data, indent=2))
        return

    console.print(Panel(
        f"[bold]Average Cyclomatic Complexity:[/bold] {report.average_complexity} | "
        f"[bold]Max Complexity:[/bold] {report.max_complexity}\n"
        f"[bold]Average Function Length:[/bold] {report.average_function_length} lines\n"
        f"[bold]Total Quality Issues:[/bold] {report.total_issues} "
        f"([red]HIGH: {report.high_severity_count}[/red], "
        f"[yellow]MEDIUM: {report.medium_severity_count}[/yellow], "
        f"[cyan]LOW: {report.low_severity_count}[/cyan])",
        title="[bold green]Static Code Quality & Standards Report[/bold green]",
        border_style="green"
    ))

    if not issues:
        console.print("[green]No code quality issues found matching criteria.[/green]")
        return

    issue_table = Table(title=f"Discovered Issues ({len(issues)})", box=box.ROUNDED)
    issue_table.add_column("Rule", style="dim", width=8)
    issue_table.add_column("Severity", style="bold", width=9)
    issue_table.add_column("File:Line", style="cyan")
    issue_table.add_column("Message")

    for issue in issues:
        sev_color = "red" if issue.severity.value == "HIGH" else ("yellow" if issue.severity.value == "MEDIUM" else "cyan")
        issue_table.add_row(
            issue.rule_id,
            f"[{sev_color}]{issue.severity.value}[/{sev_color}]",
            f"{issue.file}:{issue.line}",
            issue.message
        )
    console.print(issue_table)


@app.command("git")
def git_cmd(
    path: str = typer.Argument(".", help="Path to repository directory"),
    commit: Optional[str] = typer.Option(None, "--commit", "-c", help="Inspect specific commit hash"),
    limit: int = typer.Option(10, "--limit", "-l", help="Number of recent commits to display"),
    json_output: bool = typer.Option(False, "--json", help="Output results in JSON format")
):
    """Inspect local Git repository state, commit history, churn, and diffs without external APIs."""
    target = Path(path).resolve()
    git_repo = GitRepository(target)

    if not git_repo.is_git:
        console.print(f"[bold red]Error:[/bold red] '{target}' is not a local Git repository.")
        raise typer.Exit(code=1)

    if commit:
        commit_data = git_repo.get_commit(commit)
        if not commit_data:
            console.print(f"[bold red]Commit not found:[/bold red] {commit}")
            raise typer.Exit(code=1)

        if json_output:
            typer.echo(commit_data.model_dump_json(indent=2))
            return

        console.print(Panel(
            f"[bold cyan]Commit Hash:[/bold cyan] {commit_data.hash}\n"
            f"[bold]Author:[/bold] {commit_data.author_name} <{commit_data.author_email}>\n"
            f"[bold]Message:[/bold] {commit_data.message}\n"
            f"[bold]Files Changed:[/bold] {commit_data.files_changed} "
            f"(Source: {commit_data.source_files_changed}, Tests: {commit_data.test_files_changed})\n"
            f"[bold]Lines Churn:[/bold] [green]+{commit_data.lines_added}[/green] [red]-{commit_data.lines_deleted}[/red]",
            title="[bold green]Git Commit Details[/bold green]",
            border_style="cyan"
        ))

        changes_table = Table(title="Changed Files", box=box.ROUNDED)
        changes_table.add_column("Type", style="bold", width=10)
        changes_table.add_column("File Path", style="cyan")
        changes_table.add_column("+Lines", style="green", justify="right")
        changes_table.add_column("-Lines", style="red", justify="right")
        changes_table.add_column("Modified Line Ranges", style="dim")

        for fc in commit_data.changes:
            ranges_str = ", ".join(f"{s}-{e}" for s, e in fc.modified_line_ranges) if fc.modified_line_ranges else "All"
            changes_table.add_row(
                fc.change_type.value,
                fc.file_path,
                str(fc.lines_added),
                str(fc.lines_deleted),
                ranges_str
            )
        console.print(changes_table)
        return

    state = git_repo.get_repository_state(limit_history=limit)

    if json_output:
        typer.echo(state.model_dump_json(indent=2))
        return

    console.print(Panel(
        f"[bold]Branch:[/bold] {state.branch or 'N/A'}\n"
        f"[bold]Current HEAD:[/bold] {state.current_commit[:10] if state.current_commit else 'N/A'}\n"
        f"[bold]Working Tree Dirty:[/bold] {'[bold red]YES[/bold red]' if state.is_dirty else '[green]NO (clean)[/green]'}\n"
        f"[bold]Untracked Files:[/bold] {len(state.untracked_files)}\n"
        f"[bold]Recent Commits Available:[/bold] {len(state.commits)}",
        title="[bold green]Local Git Repository Status[/bold green]",
        border_style="green"
    ))

    if state.commits:
        hist_table = Table(title=f"Recent Commits (Showing {len(state.commits)})", box=box.ROUNDED)
        hist_table.add_column("Hash", style="dim", width=10)
        hist_table.add_column("Author", style="magenta")
        hist_table.add_column("Churn", justify="right")
        hist_table.add_column("Message", style="white")

        for c in state.commits:
            churn_str = f"[green]+{c.lines_added}[/green]/[red]-{c.lines_deleted}[/red]"
            hist_table.add_row(
                c.hash[:8],
                c.author_name[:20],
                churn_str,
                c.message.splitlines()[0][:50] if c.message else ""
            )
        console.print(hist_table)


@app.command("impact")
def impact_cmd(
    path: str = typer.Argument(".", help="Path to repository directory"),
    commit: str = typer.Option(..., "--commit", "-c", help="Target commit SHA to evaluate for change impact"),
    json_output: bool = typer.Option(False, "--json", help="Output results in JSON format")
):
    """Calculate blast radius, directly and transitively affected components for a commit."""
    target = Path(path).resolve()
    git_repo = GitRepository(target)
    if not git_repo.is_git:
        console.print(f"[bold red]Error:[/bold red] '{target}' is not a local Git repository.")
        raise typer.Exit(code=1)

    commit_data = git_repo.get_commit(commit)
    if not commit_data:
        console.print(f"[bold red]Commit not found:[/bold red] {commit}")
        raise typer.Exit(code=1)

    # Scan & parse
    analyzer = CodeAnalyzer()
    code_index = analyzer.analyze_repository(target)
    dep_graph = DependencyGraph()
    dep_graph.build_from_index(code_index)
    graph_analyzer = GraphAnalyzer(dep_graph)

    impact_analyzer = ImpactAnalyzer(code_index, graph_analyzer)
    impact = impact_analyzer.analyze_commit(commit_data)

    if json_output:
        typer.echo(impact.model_dump_json(indent=2))
        return

    console.print(Panel(
        f"[bold cyan]Commit:[/bold cyan] {impact.commit_hash}\n"
        f"[bold]Files Changed:[/bold] {impact.files_changed_count}\n"
        f"[bold]Symbols Changed:[/bold] {impact.symbols_changed_count}\n"
        f"[bold]Directly Affected:[/bold] [yellow]{impact.directly_affected_count}[/yellow]\n"
        f"[bold]Indirectly Affected:[/bold] [cyan]{impact.indirectly_affected_count}[/cyan]\n"
        f"[bold red]Total Impact Radius:[/bold red] [bold red]{impact.impact_radius}[/bold red]",
        title="[bold green]Change Impact Analysis[/bold green]",
        border_style="red" if impact.impact_radius > 5 else "green"
    ))

    if impact.changed_symbols:
        console.print("[bold]Directly Modified Symbols:[/bold] " + ", ".join(impact.changed_symbols))

    # Table of affected components
    all_affected = impact.directly_affected + impact.indirectly_affected
    if all_affected:
        aff_table = Table(title="Affected Components & Blast Radius", box=box.ROUNDED)
        aff_table.add_column("Type", style="bold", width=10)
        aff_table.add_column("Component Symbol", style="cyan")
        aff_table.add_column("Depth", justify="right", width=6)
        aff_table.add_column("Fan-In", justify="right", width=7)
        aff_table.add_column("Dependency Path (Why Affected)", style="dim")

        for aff in all_affected:
            path_str = " -> ".join(aff.dependency_path)
            depth_type = "[yellow]DIRECT[/yellow]" if aff.depth == 1 else "[cyan]INDIRECT[/cyan]"
            aff_table.add_row(
                depth_type,
                aff.symbol,
                str(aff.depth),
                str(aff.fan_in),
                path_str
            )
        console.print(aff_table)


@app.command("analyze")
def analyze_cmd(
    path: str = typer.Argument(".", help="Path to repository directory"),
    json_output: bool = typer.Option(False, "--json", help="Output results in JSON format"),
    verbose: bool = typer.Option(False, "--verbose", help="Show verbose breakdown")
):
    """Execute integrated end-to-end static code intelligence pipeline."""
    target = Path(path).resolve()
    if not json_output:
        console.print(f"[bold cyan]Analyzing repository:[/bold cyan] {target}")

    # 1. Scanner
    scanner = RepositoryScanner()
    scan_result = scanner.scan(target)

    # 2. Parser
    analyzer = CodeAnalyzer()
    code_index = analyzer.analyze_repository(target, scan_result)

    # 3. Dependency Graph
    dep_graph = DependencyGraph()
    dep_graph.build_from_index(code_index)
    graph_analyzer = GraphAnalyzer(dep_graph)
    graph_summary = dep_graph.get_summary()

    # 4. Zombie Detection
    file_mtimes = {f.relative_path: f.modified_at for f in scan_result.files}
    detector = ZombieDetector()
    zombie_report = detector.analyze(code_index, graph_analyzer, file_mtimes)

    # 5. Quality
    quality_analyzer = QualityAnalyzer()
    quality_report = quality_analyzer.analyze(code_index, target)

    # 6. Local Git
    git_repo = GitRepository(target)
    git_state = git_repo.get_repository_state(limit_history=5) if git_repo.is_git else None

    # 7. Impact for HEAD commit if git repo
    head_impact = None
    if git_state and git_state.commits:
        impact_analyzer = ImpactAnalyzer(code_index, graph_analyzer)
        head_impact = impact_analyzer.analyze_commit(git_state.commits[0])

    if json_output:
        combined = {
            "repository": scan_result.repository.model_dump(),
            "scan_stats": scan_result.stats.model_dump(),
            "language_coverage": {
                "languages": code_index.language_stats,
                "unsupported_languages": {
                    lang: {
                        "files": count,
                        "status": "Language detected but parser unavailable."
                    }
                    for lang, count in code_index.unsupported_languages.items()
                },
                "resolved_imports": code_index.resolved_imports_count,
                "unresolved_imports": code_index.unresolved_imports_count,
            },
            "code_index_summary": {
                "files_count": len(code_index.files),
                "classes_count": len(code_index.classes),
                "functions_count": len(code_index.functions),
                "methods_count": len(code_index.methods),
                "interfaces_count": len(code_index.interfaces),
                "imports_count": len(code_index.imports),
                "calls_count": len(code_index.calls),
                "resolved_imports_count": code_index.resolved_imports_count,
                "unresolved_imports_count": code_index.unresolved_imports_count,
                "parse_errors_count": len(code_index.parse_errors),
                "parse_errors": [e.model_dump() for e in code_index.parse_errors]
            },
            "graph_summary": graph_summary.model_dump(),
            "zombie_summary": {
                "analyzed": zombie_report.total_functions_analyzed,
                "potential_zombies": zombie_report.potential_zombies_count,
                "high_confidence": zombie_report.high_confidence_count,
                "candidates": [c.model_dump() for c in zombie_report.candidates]
            },
            "quality_summary": quality_report.model_dump(),
            "git_state": git_state.model_dump() if git_state else None,
            "head_impact": head_impact.model_dump() if head_impact else None
        }
        typer.echo(json.dumps(combined, indent=2))
        return

    # Beautiful Rich Master Summary
    console.print(Panel(
        f"[bold cyan]Repository:[/bold cyan] {target.name} ({scan_result.repository.root_path})\n"
        f"[bold]Git Active:[/bold] {'[green]Yes[/green] (' + str(git_state.branch) + ')' if git_state and git_state.is_git else '[yellow]No[/yellow]'}\n"
        f"[bold]Total Files Scanned:[/bold] {scan_result.stats.files_scanned} ({scan_result.stats.lines_total:,} lines)\n"
        f"[bold]Scan Duration:[/bold] {scan_result.stats.scan_duration_seconds:.4f}s",
        title="[bold green]CodeIntel — Complete Analysis Dashboard[/bold green]",
        border_style="green"
    ))

    # Multi-Language Parser Coverage Table
    lang_table = Table(title="Multi-Language Parser Coverage", box=box.ROUNDED)
    lang_table.add_column("Language", style="bold cyan")
    lang_table.add_column("Files", justify="right")
    lang_table.add_column("Parsed", justify="right", style="green")
    lang_table.add_column("Failed", justify="right")
    lang_table.add_column("Functions", justify="right", style="magenta")
    lang_table.add_column("Classes", justify="right", style="magenta")
    lang_table.add_column("Methods", justify="right", style="magenta")
    lang_table.add_column("Interfaces", justify="right", style="magenta")
    lang_table.add_column("Imports", justify="right", style="cyan")
    lang_table.add_column("Calls", justify="right", style="cyan")

    for lang_name, stats in code_index.language_stats.items():
        failed_str = f"[red]{stats['failed']}[/red]" if stats['failed'] > 0 else "[green]0[/green]"
        lang_table.add_row(
            lang_name,
            str(stats["files"]),
            str(stats["parsed"]),
            failed_str,
            str(stats["functions"]),
            str(stats["classes"]),
            str(stats["methods"]),
            str(stats.get("interfaces", 0)),
            str(stats["imports"]),
            str(stats["calls"])
        )
    console.print(lang_table)

    # Unsupported Languages Notice
    if code_index.unsupported_languages:
        unsupported_table = Table(title="Detected Languages (No Parser Available)", box=box.ROUNDED)
        unsupported_table.add_column("Language", style="yellow")
        unsupported_table.add_column("Files Detected", justify="right", style="bold")
        unsupported_table.add_column("Parser Status", style="italic dim")

        for ulang, ucnt in sorted(code_index.unsupported_languages.items(), key=lambda x: -x[1]):
            unsupported_table.add_row(
                ulang,
                str(ucnt),
                "Language detected but parser unavailable."
            )
        console.print(unsupported_table)

    # AST Metrics Table
    ast_table = Table(title="Common Code Index Metrics", box=box.ROUNDED)
    ast_table.add_column("Category", style="cyan")
    ast_table.add_column("Count", style="magenta", justify="right")
    ast_table.add_row("Total Files Parsed", str(len(code_index.files)))
    ast_table.add_row("Classes", str(len(code_index.classes)))
    ast_table.add_row("Functions (Standalone)", str(len(code_index.functions) - len(code_index.methods)))
    ast_table.add_row("Methods", str(len(code_index.methods)))
    if code_index.interfaces:
        ast_table.add_row("Interfaces", str(len(code_index.interfaces)))
    ast_table.add_row(
        "Imports",
        f"{len(code_index.imports)} (Resolved: {code_index.resolved_imports_count}, Unresolved: {code_index.unresolved_imports_count})"
    )
    ast_table.add_row("Call Sites", str(len(code_index.calls)))
    ast_table.add_row("Parse Errors", f"[red]{len(code_index.parse_errors)}[/red]" if code_index.parse_errors else "[green]0[/green]")
    console.print(ast_table)

    # Core Intelligence Summary Panels
    console.print(Panel(
        f"[bold]Dependency Graph Nodes:[/bold] {graph_summary.total_nodes} | "
        f"[bold]Edges:[/bold] {graph_summary.total_edges} | "
        f"[bold]Cycles:[/bold] {'[red]' + str(graph_summary.cyclic_dependencies_count) + '[/red]' if graph_summary.cyclic_dependencies_count else '[green]0[/green]'}\n"
        f"[bold]Potential Zombie Code Candidates:[/bold] "
        f"{'[yellow]' + str(zombie_report.potential_zombies_count) + '[/yellow]' if zombie_report.potential_zombies_count else '[green]0[/green]'} "
        f"(High Confidence: [red]{zombie_report.high_confidence_count}[/red])\n"
        f"[bold]Code Quality Issues:[/bold] {quality_report.total_issues} "
        f"([red]HIGH: {quality_report.high_severity_count}[/red], [yellow]MED: {quality_report.medium_severity_count}[/yellow], [cyan]LOW: {quality_report.low_severity_count}[/cyan])\n"
        f"[bold]McCabe Complexity:[/bold] Avg {quality_report.average_complexity} (Max: {quality_report.max_complexity})",
        title="[bold green]Intelligence Metrics Summary[/bold green]",
        border_style="cyan"
    ))

    if head_impact:
        console.print(Panel(
            f"[bold]HEAD Commit:[/bold] {head_impact.commit_hash[:10]}\n"
            f"[bold]Directly Affected Components:[/bold] {head_impact.directly_affected_count}\n"
            f"[bold]Indirectly Affected Components:[/bold] {head_impact.indirectly_affected_count}\n"
            f"[bold red]Total Blast Radius:[/bold red] [bold red]{head_impact.impact_radius}[/bold red]",
            title="[bold yellow]HEAD Commit Impact[/bold yellow]",
            border_style="yellow"
        ))

    console.print("\n[bold green]Analysis complete with zero LLMs or external AI APIs.[/bold green]")


@app.command("risk")
def risk_cmd(
    path: str = typer.Argument(".", help="Path to repository directory to analyze commit risk"),
    commit_hash: Optional[str] = typer.Option(None, "--commit", "-c", help="Specific commit hash to evaluate (defaults to recent commits)"),
    limit: int = typer.Option(5, "--limit", "-l", help="Number of recent commits to analyze"),
    json_output: bool = typer.Option(False, "--json", help="Output results in JSON format")
):
    """Predictive commit risk analysis combining software metrics and local Random Forest ML."""
    target = Path(path).resolve()
    git_repo = GitRepository(target)
    if not git_repo.is_git:
        console.print(f"[bold red]Error:[/bold red] '{target}' is not a valid Git repository.")
        raise typer.Exit(code=1)

    git_state = git_repo.get_repository_state(limit_history=max(limit, 10))
    if not git_state.commits:
        console.print("[yellow]No commits found in repository history.[/yellow]")
        raise typer.Exit()

    # Build code index & graph for impact calculation
    scanner = RepositoryScanner()
    scan_res = scanner.scan(target)
    analyzer = CodeAnalyzer()
    code_index = analyzer.analyze_repository(target, scan_res)
    dep_graph = DependencyGraph()
    dep_graph.build_from_index(code_index)
    graph_analyzer = GraphAnalyzer(dep_graph)
    impact_analyzer = ImpactAnalyzer(code_index, graph_analyzer)

    quality_analyzer = QualityAnalyzer()
    quality_report = quality_analyzer.analyze(code_index, target)

    # Train local ML model on commit history
    ml_model = CommitRiskModel()
    if len(git_state.commits) >= 2:
        ml_model.train_on_commits(git_state.commits)

    risk_engine = CommitRiskEngine(ml_model)

    commits_to_evaluate = git_state.commits[:limit]
    if commit_hash:
        filtered = [c for c in git_state.commits if c.hash.startswith(commit_hash)]
        if not filtered:
            console.print(f"[bold red]Commit not found:[/bold red] '{commit_hash}'")
            raise typer.Exit(code=1)
        commits_to_evaluate = filtered

    summary = risk_engine.evaluate_repository_commits(
        commits_to_evaluate,
        impact_analyzer=impact_analyzer,
        code_index=code_index,
        quality_report=quality_report
    )

    if json_output:
        typer.echo(summary.model_dump_json(indent=2))
        return

    # Render Rich Dashboard
    console.print(Panel(
        f"[bold]Repository:[/bold] {target}\n"
        f"[bold]Commits Evaluated:[/bold] {summary.total_commits_evaluated}\n"
        f"[bold]Average Commit Risk Score:[/bold] [bold cyan]{summary.average_risk_score} / 100[/bold cyan]\n"
        f"[bold]High / Critical Risk Commits:[/bold] [bold red]{summary.high_risk_commits_count + summary.critical_risk_commits_count}[/bold red]\n"
        f"[bold]ML Model Status:[/bold] [bold green]Active (Local Random Forest - Zero LLMs)[/bold green]",
        title="[bold red]Predictive Commit Risk Summary[/bold red]",
        border_style="red"
    ))

    table = Table(title="Commit Risk & Blast Radius Breakdown", box=box.ROUNDED)
    table.add_column("Commit", style="cyan")
    table.add_column("Author", style="dim")
    table.add_column("Risk Score", justify="right", style="bold")
    table.add_column("Tier", justify="center")
    table.add_column("ML Defect Prob", justify="right")
    table.add_column("Blast Radius", justify="right")
    table.add_column("Key Risk Factors", style="yellow")

    for rep in summary.commits:
        tier_style = "bold red" if rep.risk_tier == "CRITICAL" else "red" if rep.risk_tier == "HIGH" else "yellow" if rep.risk_tier == "MEDIUM" else "green"
        tier_str = f"[{tier_style}]{rep.risk_tier.value}[/{tier_style}]"
        prob_str = f"{rep.ml_defect_probability * 100:.1f}%" if rep.ml_defect_probability is not None else "N/A"
        blast_str = str(rep.blast_radius_metrics.get("blast_radius", 0))

        factors_str = "; ".join(f.name for f in rep.top_risk_factors) if rep.top_risk_factors else "Normal churn"

        table.add_row(
            f"{rep.commit_hash[:8]}\n[dim]{rep.commit_message[:35]}[/dim]",
            rep.author[:16],
            f"{rep.risk_score:.1f}",
            tier_str,
            prob_str,
            blast_str,
            factors_str[:50]
        )

    console.print(table)


@app.command("web")
def web_cmd(
    path: str = typer.Argument(".", help="Path to repository directory to serve in web portal"),
    host: str = typer.Option("127.0.0.1", "--host", help="Server host IP"),
    port: int = typer.Option(8000, "--port", "-p", help="Server port")
):
    """Launch local CodeIntel Web Intelligence Portal in your browser."""
    target = Path(path).resolve()
    console.print(f"[bold cyan]Starting CodeIntel Web Portal for:[/bold cyan] {target}")
    console.print(f"[bold green]Open in browser:[/bold green] [bold underline]http://{host}:{port}[/bold underline]")
    console.print("[dim]Press Ctrl+C to stop server.[/dim]\n")
    run_server(str(target), host=host, port=port)

