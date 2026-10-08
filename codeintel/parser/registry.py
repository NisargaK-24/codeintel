from typing import Dict, List, Optional
from codeintel.parser.base import BaseParser
from codeintel.parser.python_parser import PythonParser
from codeintel.parser.typescript_parser import TypeScriptParser
from codeintel.parser.javascript_parser import JavaScriptParser


class ParserRegistry:
    """Registry coordinating language-specific parsers."""

    def __init__(self):
        self._parsers: Dict[str, BaseParser] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register primary language parsers: Python, TypeScript, JavaScript."""
        py_parser = PythonParser()
        ts_parser = TypeScriptParser()
        js_parser = JavaScriptParser()

        self.register(py_parser)
        self.register(ts_parser)
        self.register(js_parser)

    def register(self, parser: BaseParser) -> None:
        """Register a parser instance for all its supported languages."""
        for lang in parser.supported_languages:
            self._parsers[lang.lower()] = parser

    def get_parser_for_language(self, language: str) -> Optional[BaseParser]:
        """Find the registered parser for a given language name."""
        return self._parsers.get(language.lower())

    def is_language_supported(self, language: str) -> bool:
        """Check if a language has an active registered parser."""
        return language.lower() in self._parsers

    def get_supported_languages(self) -> List[str]:
        """List canonical names of all supported languages."""
        seen = set()
        result = []
        for p in self._parsers.values():
            if p.name not in seen:
                seen.add(p.name)
                result.append(p.name)
        return result


# Global default registry instance
default_parser_registry = ParserRegistry()
