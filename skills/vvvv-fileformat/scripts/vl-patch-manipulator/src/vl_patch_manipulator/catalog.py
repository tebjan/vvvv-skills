"""Node catalog interfaces for safe, exact vvvv patch edits.

The offline catalog format is intentionally compatible with the JSON emitted by
the KopfFarben/digitalwannabe vvvv-mcp analyzer, but this module does not import
or vendor that project's implementation.  A catalog is a source of truth for
new nodes: callers must resolve a node before adding or connecting it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Iterable, Protocol


@dataclass(frozen=True)
class PinSpec:
    name: str
    type_name: str = "Object"
    kind: str = "InputPin"
    default_value: str | None = None
    hidden: bool = False
    optional: bool = False
    state: bool = False
    pin_group: bool = False

    @property
    def is_input(self) -> bool:
        return self.kind in {"InputPin", "StateInputPin", "ApplyPin", "ControlPoint"}

    @property
    def is_output(self) -> bool:
        return self.kind in {"OutputPin", "StateOutputPin"}


@dataclass(frozen=True)
class NodeSpec:
    name: str
    category: str = ""
    full_name: str = ""
    kind: str = "Process"
    dependency: str | None = None
    reference_dependency: str | None = None
    source: str | None = None
    summary: str = ""
    inputs: tuple[PinSpec, ...] = field(default_factory=tuple)
    outputs: tuple[PinSpec, ...] = field(default_factory=tuple)
    reference_kind: str = "NodeFlag"
    fixed: bool = True
    prefix_choices: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def operation_name(self) -> str:
        return self.name

    def pin(self, name: str, *, input_only: bool | None = None) -> PinSpec:
        pins = (*self.inputs, *self.outputs)
        for pin in pins:
            if pin.name == name and (input_only is None or pin.is_input == input_only):
                return pin
        raise KeyError(f"catalog node {self.name!r} has no exact pin {name!r}")


class CatalogError(ValueError):
    """Raised when a requested node or pin is not known exactly."""


class NodeCatalog(Protocol):
    def resolve(self, name: str, *, category: str | None = None) -> NodeSpec | None:
        """Resolve an exact node operation name, optionally narrowed by category."""

    def search(self, query: str, *, category: str | None = None, limit: int = 20) -> list[NodeSpec]:
        """Return candidates; callers must still choose an exact result."""


def _pin_from_json(value: dict, *, kind: str) -> PinSpec:
    return PinSpec(
        name=str(value.get("name", "")),
        type_name=str(value.get("type", "Object")),
        kind=kind,
        default_value=value.get("defaultValue") or None,
        hidden=bool(value.get("isHidden", False)),
        optional=bool(value.get("isOptional", False)),
        state=bool(value.get("isState", False)),
        pin_group=bool(value.get("isPinGroup", False)),
    )


class JsonNodeCatalog:
    """Read-only catalog adapter for ``vvvv_nodes_mcp.json``."""

    def __init__(self, specs: Iterable[NodeSpec]):
        self._specs = tuple(specs)
        self._by_name: dict[str, list[NodeSpec]] = {}
        for spec in self._specs:
            self._by_name.setdefault(spec.name, []).append(spec)

    @classmethod
    def load(cls, path: str | Path) -> "JsonNodeCatalog":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        specs: list[NodeSpec] = []
        for value in data.get("nodes", []):
            kind = str(value.get("type", "Process"))
            specs.append(
                NodeSpec(
                    name=str(value.get("name", "")),
                    category=str(value.get("category", "")),
                    full_name=str(value.get("fullName", "")),
                    kind=kind,
                    source=value.get("source"),
                    summary=str(value.get("summary", "")),
                    inputs=tuple(_pin_from_json(pin, kind="InputPin") for pin in value.get("inputs", [])),
                    outputs=tuple(_pin_from_json(pin, kind="OutputPin") for pin in value.get("outputs", [])),
                    reference_kind="ProcessNode" if kind == "Process" else "NodeFlag",
                    fixed=True,
                )
            )
        return cls(specs)

    def resolve(self, name: str, *, category: str | None = None) -> NodeSpec | None:
        candidates = self._by_name.get(name, [])
        if category is not None:
            candidates = [item for item in candidates if item.category == category]
        if len(candidates) == 1:
            return candidates[0]
        return None

    def search(self, query: str, *, category: str | None = None, limit: int = 20) -> list[NodeSpec]:
        query_lower = query.casefold()
        candidates = [item for item in self._specs if query_lower in item.name.casefold() or query_lower in item.full_name.casefold()]
        if category is not None:
            candidates = [item for item in candidates if item.category == category]
        return sorted(candidates, key=lambda item: (item.name.casefold(), item.category))[:limit]


class CompositeCatalog:
    """First-match catalog used to combine a local patch and offline catalog."""

    def __init__(self, *catalogs: NodeCatalog):
        self.catalogs = tuple(catalogs)

    def resolve(self, name: str, *, category: str | None = None) -> NodeSpec | None:
        for catalog in self.catalogs:
            result = catalog.resolve(name, category=category)
            if result is not None:
                return result
        return None

    def search(self, query: str, *, category: str | None = None, limit: int = 20) -> list[NodeSpec]:
        results: list[NodeSpec] = []
        seen: set[tuple[str, str, str]] = set()
        for catalog in self.catalogs:
            for result in catalog.search(query, category=category, limit=limit):
                key = (result.name, result.category, result.full_name)
                if key not in seen:
                    seen.add(key)
                    results.append(result)
        return results[:limit]


class InMemoryNodeCatalog(JsonNodeCatalog):
    """Small exact catalog for generated patches and tests."""

    def __init__(self, specs: Iterable[NodeSpec] = ()):
        super().__init__(specs)


class DocumentCatalog:
    """Catalog exact node and pin metadata already present in a parsed patch."""

    def __init__(self, specs: Iterable[NodeSpec] = ()):
        self._specs = tuple(specs)
        self._by_key: dict[tuple[str, str], NodeSpec] = {(spec.name, spec.category): spec for spec in self._specs}

    @classmethod
    def from_document(cls, document) -> "DocumentCatalog":
        from .document import VlGraph

        graph = document.graph() if not isinstance(document, VlGraph) else document
        specs: dict[tuple[str, str], NodeSpec] = {}
        for node in graph.nodes:
            if node.get("Name") == "Application":
                continue
            reference = node.find("{property}NodeReference")
            if reference is None:
                continue
            choices = reference.findall("Choice")
            if not choices:
                continue
            name = choices[-1].get("Name", "")
            category = reference.get("LastCategoryFullName", "")
            reference_dependency = reference.get("LastDependency")
            dependency = reference_dependency
            for dependency_element in document.root:
                if not isinstance(dependency_element.tag, str):
                    continue
                location = dependency_element.get("Location", "")
                if reference_dependency and (reference_dependency == location or reference_dependency.startswith(location + ".") or reference_dependency.endswith(location + ".vl")):
                    dependency = location
                    break
            pins = []
            for pin in node.findall("Pin"):
                pins.append(
                    PinSpec(
                        name=pin.get("Name", ""),
                        kind=pin.get("Kind", "InputPin"),
                        default_value=pin.get("DefaultValue"),
                        hidden=pin.get("IsHidden", "false").lower() == "true",
                        state=pin.get("Kind") in {"StateInputPin", "StateOutputPin"},
                    )
                )
            spec = NodeSpec(
                name=name,
                category=category,
                full_name=f"{category}.{name}" if category else name,
                kind=choices[-1].get("Kind", "ProcessNode"),
                dependency=dependency,
                reference_dependency=reference_dependency,
                inputs=tuple(pin for pin in pins if pin.is_input),
                outputs=tuple(pin for pin in pins if pin.is_output),
                reference_kind=choices[-1].get("Kind", "NodeFlag"),
                fixed=choices[-1].get("Fixed", "false").lower() == "true",
                prefix_choices=tuple((choice.get("Kind", ""), choice.get("Name", "")) for choice in choices[:-1]),
            )
            specs.setdefault((name, category), spec)
        return cls(specs.values())

    def resolve(self, name: str, *, category: str | None = None) -> NodeSpec | None:
        if category is not None:
            return self._by_key.get((name, category))
        candidates = [spec for (spec_name, _), spec in self._by_key.items() if spec_name == name]
        return candidates[0] if len(candidates) == 1 else None

    def search(self, query: str, *, category: str | None = None, limit: int = 20) -> list[NodeSpec]:
        query_lower = query.casefold()
        candidates = [spec for spec in self._specs if query_lower in spec.name.casefold() or query_lower in spec.full_name.casefold()]
        if category is not None:
            candidates = [spec for spec in candidates if spec.category == category]
        return sorted(candidates, key=lambda item: (item.name.casefold(), item.category))[:limit]
