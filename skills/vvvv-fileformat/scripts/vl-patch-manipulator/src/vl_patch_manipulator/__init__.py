"""Structural, BOM-free tooling for vvvv gamma ``.vl`` documents."""

from .document import VlDocument, VlGraph, ValidationReport, load_document
from .ids import new_vl_id
from .catalog import CatalogError, CompositeCatalog, DocumentCatalog, InMemoryNodeCatalog, JsonNodeCatalog, NodeSpec, PinSpec
from .session import PatchSession
from .server import PatchServerCore

__all__ = [
    "VlDocument",
    "VlGraph",
    "ValidationReport",
    "load_document",
    "new_vl_id",
    "CatalogError",
    "CompositeCatalog",
    "DocumentCatalog",
    "JsonNodeCatalog",
    "InMemoryNodeCatalog",
    "NodeSpec",
    "PinSpec",
    "PatchSession",
    "PatchServerCore",
]
