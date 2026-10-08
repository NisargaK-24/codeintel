from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn

from codeintel.git.repository import GitRepository
from codeintel.graph.dependency_graph import DependencyGraph
from codeintel.graph.graph_analyzer import GraphAnalyzer
from codeintel.impact.analyzer import ImpactAnalyzer
from codeintel.ml.risk_model import CommitRiskModel
from codeintel.parser.analyzer import CodeAnalyzer
from codeintel.quality.analyzer import QualityAnalyzer
from codeintel.risk.engine import CommitRiskEngine
from codeintel.scanner.scanner import RepositoryScanner
from codeintel.zombie.detector import ZombieDetector


def create_app(repo_path: str) -> FastAPI:
    """Create and configure the CodeIntel FastAPI application for a repository."""
    app = FastAPI(
        title="CodeIntel Intelligence Portal",
        description="Local Code Intelligence, Zombie Code Detection, and Predictive Commit Risk Analysis",
        version="0.1.0"
    )

    root = Path(repo_path).resolve()
    _cache: Dict[str, Any] = {}

    def get_analysis_data() -> Dict[str, Any]:
        """Lazy load and cache repository analysis."""
        if "data" in _cache:
            return _cache["data"]

        scanner = RepositoryScanner()
        scan_res = scanner.scan(root)

        analyzer = CodeAnalyzer()
        code_index = analyzer.analyze_repository(root, scan_res)

        dep_graph = DependencyGraph()
        dep_graph.build_from_index(code_index)
        graph_analyzer = GraphAnalyzer(dep_graph)

        file_mtimes = {f.relative_path: f.modified_at for f in scan_res.files}
        zombie_detector = ZombieDetector()
        zombie_report = zombie_detector.analyze(code_index, graph_analyzer, file_mtimes)

        quality_analyzer = QualityAnalyzer()
        quality_report = quality_analyzer.analyze(code_index, root)

        git_repo = GitRepository(root)
        git_state = git_repo.get_repository_state(limit_history=15) if git_repo.is_git else None

        # Risk Analysis
        risk_summary = None
        if git_state and git_state.commits:
            impact_analyzer = ImpactAnalyzer(code_index, graph_analyzer)
            ml_model = CommitRiskModel()
            if len(git_state.commits) >= 2:
                ml_model.train_on_commits(git_state.commits)
            risk_engine = CommitRiskEngine(ml_model)
            risk_summary = risk_engine.evaluate_repository_commits(
                git_state.commits,
                impact_analyzer=impact_analyzer,
                code_index=code_index,
                quality_report=quality_report
            )

        data = {
            "root": str(root),
            "scan": scan_res,
            "index": code_index,
            "graph": dep_graph,
            "graph_analyzer": graph_analyzer,
            "zombies": zombie_report,
            "quality": quality_report,
            "git": git_state,
            "risk": risk_summary
        }
        _cache["data"] = data
        return data

    @app.get("/", response_class=HTMLResponse)
    def serve_dashboard():
        html_file = Path(__file__).parent / "static" / "index.html"
        if not html_file.exists():
            return HTMLResponse("<h1>CodeIntel Web Portal</h1><p>UI assets not found.</p>", status_code=404)
        return HTMLResponse(html_file.read_text(encoding="utf-8"))

    @app.get("/api/overview")
    def get_overview():
        d = get_analysis_data()
        scan_res = d["scan"]
        index = d["index"]
        quality_rep = d["quality"]
        zombies_rep = d["zombies"]
        risk_sum = d["risk"]

        # Health score calculation (0 to 100)
        total_issues = quality_rep.total_issues
        high_issues = quality_rep.high_severity_count
        zombie_count = zombies_rep.potential_zombies_count
        files_count = max(1, len(index.files))

        penalty = (high_issues * 3.0 + (total_issues - high_issues) * 0.5 + zombie_count * 1.5) / files_count
        health_score = max(10.0, min(100.0, round(100.0 - penalty, 1)))

        return {
            "repository_path": d["root"],
            "total_files": len(scan_res.files),
            "total_lines": scan_res.repository.total_lines,
            "languages": scan_res.repository.languages,
            "parsed_files": len(index.files),
            "health_score": health_score,
            "classes_count": len(index.classes),
            "functions_count": len(index.functions),
            "methods_count": len(index.methods),
            "interfaces_count": len(index.interfaces),
            "imports_count": len(index.imports),
            "resolved_imports": index.resolved_imports_count,
            "unresolved_imports": index.unresolved_imports_count,
            "calls_count": len(index.calls),
            "potential_zombies_count": zombies_rep.potential_zombies_count,
            "quality_issues_count": total_issues,
            "average_complexity": quality_rep.average_complexity,
            "max_complexity": quality_rep.max_complexity,
            "average_risk_score": risk_sum.average_risk_score if risk_sum else None,
            "language_stats": index.language_stats,
            "unsupported_languages": index.unsupported_languages
        }

    @app.get("/api/zombies")
    def get_zombies():
        d = get_analysis_data()
        rep = d["zombies"]
        return rep.model_dump()

    @app.get("/api/quality")
    def get_quality():
        d = get_analysis_data()
        rep = d["quality"]
        return rep.model_dump()

    @app.get("/api/graph")
    def get_graph():
        d = get_analysis_data()
        summary = d["graph"].get_summary()
        analyzer: GraphAnalyzer = d["graph_analyzer"]
        call_nodes = list(analyzer.call_subgraph.nodes)
        sorted_nodes = sorted(call_nodes, key=lambda n: analyzer.get_fan_in(n), reverse=True)[:10]
        top_fan_in = [
            {"symbol": sym, "fan_in": analyzer.get_fan_in(sym), "fan_out": analyzer.get_fan_out(sym)}
            for sym in sorted_nodes
        ]
        return {
            "summary": summary.model_dump(),
            "top_fan_in_nodes": top_fan_in
        }

    @app.get("/api/risk")
    def get_risk():
        d = get_analysis_data()
        if not d["risk"]:
            return {"available": False, "message": "Git repository required for commit risk prediction."}
        return {"available": True, "data": d["risk"].model_dump()}

    @app.get("/api/commits")
    def get_commits():
        d = get_analysis_data()
        if not d["git"]:
            return {"is_git": False, "commits": []}
        return {
            "is_git": True,
            "branch": d["git"].branch,
            "commits": [c.model_dump() for c in d["git"].commits]
        }

    return app


def run_server(repo_path: str, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run local uvicorn server for CodeIntel Web Intelligence Portal."""
    app = create_app(repo_path)
    uvicorn.run(app, host=host, port=port, log_level="info")
