"""V2 platform runtime: explicit migrations and managed pipelines."""

from .migrations import MigrationError, MigrationRunner

__all__ = ["MigrationError", "MigrationRunner"]
