from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Set
from pydantic import BaseModel, Field

from codeintel.models.code import CodeIndex
from codeintel.models.repository import ScannedFile


class FileParseResult(BaseModel):
    """Result of parsing a single source file."""
    file_path: str = Field(description="Path to the parsed file")
    relative_path: str = Field(description="Relative path within repository")
    code_index: CodeIndex = Field(default_factory=CodeIndex)
    success: bool = Field(default=True)
    error_message: Optional[str] = Field(default=None)
    language: str = Field(default="Unknown", description="Language parsed")


class BaseParser(ABC):
    """Abstract interface for static code parsers across multiple languages."""

    name: str = "BaseParser"
    supported_languages: Set[str] = set()

    def can_parse(self, language: str) -> bool:
        """Check if this parser handles the given language name."""
        return language.lower() in {lang.lower() for lang in self.supported_languages}

    @abstractmethod
    def parse_source(self, code: str, file_path: str, relative_path: str, language: Optional[str] = None) -> FileParseResult:
        """Parse source code string into structured symbol and call index."""
        pass

    def parse_file(self, file_path: Path, repo_root: Path, language: Optional[str] = None) -> FileParseResult:
        """Safely read and parse a source file without execution."""
        rel_path = file_path.relative_to(repo_root).as_posix()
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                code = f.read()
            return self.parse_source(code, str(file_path), rel_path, language=language)
        except Exception as e:
            return FileParseResult(
                file_path=str(file_path),
                relative_path=rel_path,
                success=False,
                error_message=f"Failed to read file: {str(e)}",
                language=language or "Unknown"
            )

    def parse_repository(self, files: List[ScannedFile], repo_root: Path) -> CodeIndex:
        """Batch parse all files handled by this parser into a unified CodeIndex."""
        combined_index = CodeIndex()
        for sf in files:
            if self.can_parse(sf.language):
                f_path = Path(sf.path)
                res = self.parse_file(f_path, repo_root, language=sf.language)
                idx = res.code_index

                combined_index.files.extend(idx.files)
                combined_index.symbols.update(idx.symbols)
                combined_index.functions.update(idx.functions)
                combined_index.classes.update(idx.classes)
                combined_index.methods.update(idx.methods)
                combined_index.interfaces.update(idx.interfaces)
                combined_index.exports.extend(idx.exports)
                combined_index.imports.extend(idx.imports)
                combined_index.calls.extend(idx.calls)
                combined_index.references.extend(idx.references)
                combined_index.parse_errors.extend(idx.parse_errors)

        return combined_index
