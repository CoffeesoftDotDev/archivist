"""Filesystem helpers and removal strategies: no business rules, no imports from the rest of the app."""
from .fs import find_files, format_size, is_hidden, is_link, is_readonly, iter_tree, make_writable
from .removers import DryRunRemover, PermanentRemover, Remover, TrashRemover, make_remover

__all__ = [
    "DryRunRemover",
    "PermanentRemover",
    "Remover",
    "TrashRemover",
    "find_files",
    "format_size",
    "is_hidden",
    "is_link",
    "is_readonly",
    "iter_tree",
    "make_remover",
    "make_writable",
]
