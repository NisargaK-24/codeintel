from typing import Set
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for CodeIntel static code intelligence."""

    model_config = SettingsConfigDict(
        env_prefix="CODEINTEL_",
        env_file=".env",
        extra="ignore"
    )

    # Scanner Settings
    max_file_size_bytes: int = Field(
        default=5 * 1024 * 1024,
        description="Maximum file size in bytes to read and scan (default 5MB)"
    )
    excluded_dirs: Set[str] = Field(
        default_factory=lambda: {
            ".git", "__pycache__", ".venv", "venv", "env", "node_modules",
            ".tox", ".nox", ".idea", ".vscode", "build", "dist",
            ".pytest_cache", ".mypy_cache", ".coverage", "htmlcov",
            "eggs", ".eggs", "*.egg-info"
        },
        description="Directory names to skip during recursive scan"
    )
    binary_extensions: Set[str] = Field(
        default_factory=lambda: {
            ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib", ".exe", ".bin",
            ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
            ".pdf", ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z",
            ".whl", ".jar", ".war", ".ear", ".db", ".sqlite", ".sqlite3"
        },
        description="File extensions considered binary"
    )

    # Quality Thresholds
    max_function_length: int = Field(default=50, description="Max recommended lines in a function")
    max_function_params: int = Field(default=5, description="Max recommended parameters for a function")
    max_cyclomatic_complexity: int = Field(default=10, description="McCabe cyclomatic complexity threshold")
    max_nesting_depth: int = Field(default=4, description="Max recommended block nesting depth")
    max_class_methods: int = Field(default=15, description="Max recommended methods in a class")
    max_class_length: int = Field(default=300, description="Max recommended lines in a class")

    # Zombie Detection Settings
    zombie_min_score: int = Field(default=50, description="Score threshold (0-100) to classify as potential zombie")
    zombie_age_days_suspicious: int = Field(default=90, description="Days without modification to increase suspicion")

    # Runtime Flags
    verbose: bool = Field(default=False, description="Enable verbose diagnostic logs")
    output_json: bool = Field(default=False, description="Output results in JSON format")


settings = Settings()
