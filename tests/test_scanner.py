from pathlib import Path
import pytest

from codeintel.scanner.exclusions import ExclusionManager
from codeintel.scanner.gitignore import GitIgnoreMatcher
from codeintel.scanner.scanner import RepositoryScanner, detect_language, compute_sha256

FIXTURE_REPO_PATH = Path(__file__).parent / "fixtures" / "sample_repo"


class TestScanner:
    """Test suite for repository discovery, exclusions, gitignore, and metadata extraction."""

    def test_scanner_discovery(self):
        scanner = RepositoryScanner()
        result = scanner.scan(FIXTURE_REPO_PATH)

        assert result.repository.is_git is True
        assert result.stats.files_scanned >= 10
        assert result.stats.lines_total > 200
        assert result.stats.size_total > 1000

        # Check that expected files are discovered
        rel_paths = {f.relative_path.replace("\\", "/") for f in result.files}
        assert "payment/service.py" in rel_paths
        assert "payment/calculator.py" in rel_paths
        assert "orders/processor.py" in rel_paths
        assert "utils/helpers.py" in rel_paths

    def test_scanner_metadata(self):
        scanner = RepositoryScanner()
        result = scanner.scan(FIXTURE_REPO_PATH)

        service_file = next(f for f in result.files if f.relative_path.replace("\\", "/") == "payment/service.py")
        assert service_file.language == "Python"
        assert service_file.line_count > 30
        assert service_file.size_bytes > 500
        assert len(service_file.sha256_hash) == 64
        assert service_file.is_binary is False

    def test_scanner_exclusions(self, tmp_path):
        # Create a repo with excluded directory (.git, __pycache__, .venv)
        pycache_dir = tmp_path / "__pycache__"
        pycache_dir.mkdir()
        (pycache_dir / "cache.pyc").write_bytes(b"\x00\x01\x02")

        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()
        (venv_dir / "lib.py").write_text("x = 1")

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("print('hello')")

        scanner = RepositoryScanner()
        result = scanner.scan(tmp_path)

        scanned_rel = [f.relative_path.replace("\\", "/") for f in result.files]
        assert "src/main.py" in scanned_rel
        assert not any("__pycache__" in p for p in scanned_rel)
        assert not any(".venv" in p for p in scanned_rel)

    def test_scanner_gitignore(self, tmp_path):
        (tmp_path / ".gitignore").write_text("*.log\nsecret_dir/\n")
        (tmp_path / "normal.py").write_text("a = 1")
        (tmp_path / "test.log").write_text("log data")

        secret_dir = tmp_path / "secret_dir"
        secret_dir.mkdir()
        (secret_dir / "secret.py").write_text("token = 123")

        scanner = RepositoryScanner(respect_gitignore=True)
        result = scanner.scan(tmp_path)

        scanned_rel = [f.relative_path.replace("\\", "/") for f in result.files]
        assert "normal.py" in scanned_rel
        assert "test.log" not in scanned_rel
        assert not any("secret_dir" in p for p in scanned_rel)

    def test_scanner_invalid_paths(self):
        scanner = RepositoryScanner()
        with pytest.raises(FileNotFoundError):
            scanner.scan(Path("c:/non_existent_directory_xyz_12345"))

    def test_binary_detection(self, tmp_path):
        bin_file = tmp_path / "sample.bin"
        bin_file.write_bytes(b"some text with a \x00 null byte")

        exclusions = ExclusionManager()
        assert exclusions.is_binary_file(bin_file) is True

    def test_language_detection(self):
        assert detect_language(Path("test.py")) == "Python"
        assert detect_language(Path("index.js")) == "JavaScript"
        assert detect_language(Path("app.ts")) == "TypeScript"
        assert detect_language(Path("Dockerfile")) == "Dockerfile"
        assert detect_language(Path("unknown.xyz123")) == "Unknown"
