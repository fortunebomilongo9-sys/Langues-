"""Moteur de recherche : normalisation, analyse de requête, scoring, orchestration."""

from . import compose, dedupe, normalize, pipeline, query_parser, scoring  # noqa: F401

__all__ = ["compose", "dedupe", "normalize", "pipeline", "query_parser", "scoring"]
