"""Command line: flags into a Config (parser.py), then the console entry point (entrypoint.py)."""
from .entrypoint import main
from .parser import build_parser, parse_config

__all__ = ["build_parser", "main", "parse_config"]
