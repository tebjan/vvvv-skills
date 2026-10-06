"""Persistent, agent-facing patch editing session.

``PatchSession`` is the primary API.  It keeps one parsed XML tree and indexed
graph alive while an agent describes, queries, edits, validates and finally
saves a patch.  The CLI is deliberately only a thin adapter around this class.
"""

from __future__ import annotations

from collections import defaultdict, deque
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from lxml import etree

from .catalog import CatalogError, CompositeCatalog, DocumentCatalog, NodeCatalog, NodeSpec, PinSpec
from .diagnostics import ValidationReport
from .document import PROPERTY_NS, VlDocument, VlGraph, _format_bounds, _format_number, _parse_bounds
from .ids import new_vl_id


@dataclass(frozen=True)
class PatchNodeView:
    alias: str
    identifier: str
    operation: str
    category: str
    bounds: tuple[float, float, float, float] | None


@dataclass(frozen=True)
class MatrixRepeatBuilder:
    """Endpoints and owning regions of a canonical CPU Matrix builder."""

    count_pad: str
    translation_input: str
    height_input: str
    scaling_input: str
    index_output: str
    result_output: str
    cache_region: str
    repeat_region: str


@dataclass(frozen=True)
class ProcessBuilder:
    """A local Process definition, its canvas portals and one matching call."""

    definition_id: str
    body: etree._Element
    inputs: dict[str, str]
    outputs: dict[str, str]
    update_inputs: dict[str, str]
    update_outputs: dict[str, str]
    call: str
    call_id: str
    call_inputs: dict[str, str]
    call_outputs: dict[str, str]


@dataclass(frozen=True)
class SlotBuilder:
    """Named state field and its distinct plain read/write canvas accessors."""

    slot_id: str
    read_pad: str
    write_pad: str


class PatchSession:
    """A reusable in-memory patch model with transactional mutations.

    Typical usage::

        session = PatchSession.load("scene.vl", catalog=offline_catalog)
        print(session.describe(level="summary"))
        session.add_node("Box", alias="box", category="Stride.Geometry")
        session.connect("box.Output", "group.Input")
        session.layout()
        session.save()

    New nodes are never guessed: ``add_node`` requires an exact catalog match.
    Existing XML is retained as lxml elements, so unknown elements, attributes,
    comments, namespaces and order survive edits unless the caller explicitly
    removes or moves the affected element.
    """

    def __init__(self, document: VlDocument, *, catalog: NodeCatalog | None = None):
        self.document = document
        self.graph = document.graph()
        self.document_catalog = DocumentCatalog.from_document(document)
        self._external_catalog = catalog if not isinstance(catalog, DocumentCatalog) else None
        self.catalog = CompositeCatalog(self._external_catalog, self.document_catalog) if self._external_catalog else self.document_catalog
        self._aliases: dict[str, str] = {}
        self._entity_aliases: dict[str, str] = {}
        self._next_alias = 1
        self._undo: list[bytes] = []
        self._redo: list[bytes] = []
        self._transaction_depth = 0
        self._transaction_snapshot: bytes | None = None
        self._reindex_aliases()
        # Geometry which exists when a document is opened is presumed to be
        # intentional human work. Automatic layout may place later additions,
        # but it must not silently reflow this baseline.
        self._layout_baseline_ids = self._canvas_entity_ids()

    @classmethod
    def load(cls, path: str | Path, *, catalog: NodeCatalog | None = None) -> "PatchSession":
        return cls(VlDocument.load(path), catalog=catalog)

    @classmethod
    def from_bytes(cls, data: bytes, *, catalog: NodeCatalog | None = None) -> "PatchSession":
        return cls(VlDocument.parse(data), catalog=catalog)

    @classmethod
    def new(
        cls,
        *,
        language_version: str = "2025.7.3",
        dependencies: Iterable[tuple[str, str | None]] = (("VL.CoreLib", "2025.7.3"),),
        catalog: NodeCatalog | None = None,
    ) -> "PatchSession":
        """Create the minimal Document/Patch/Application/Group skeleton.

        This is the safe starting point for generated help patches: the root
        contains only normal vvvv node placements, visible pads/overlays and
        links. Runtime setup remains inside nodes.
        """

        root = etree.Element("Document", nsmap={"p": PROPERTY_NS, "r": "reflection"}, Id=new_vl_id(), LanguageVersion=language_version, Version="0.128")
        for location, version in dependencies:
            dependency = etree.SubElement(root, "NugetDependency", Id=new_vl_id(), Location=location)
            if version:
                dependency.set("Version", version)
        patch = etree.SubElement(root, "Patch", Id=new_vl_id())
        etree.SubElement(patch, "Canvas", Id=new_vl_id(), DefaultCategory="Main", BordersChecked="false", CanvasType="FullCategory")
        application = etree.SubElement(patch, "Node", Name="Application", Bounds="100,100", Id=new_vl_id())
        reference = etree.SubElement(application, f"{{{PROPERTY_NS}}}NodeReference")
        etree.SubElement(reference, "Choice", Kind="ContainerDefinition", Name="Process")
        etree.SubElement(reference, "FullNameCategoryReference", ID="Primitive")
        inner_patch = etree.SubElement(application, "Patch", Id=new_vl_id())
        etree.SubElement(inner_patch, "Canvas", Id=new_vl_id(), CanvasType="Group")
        # A Process container is not executable merely because it owns a Group
        # canvas. vvvv enters the application through these lifecycle patches
        # and their ProcessDefinition fragments. Omitting them produces a
        # deceptively plausible patch whose nodes and links stay grey forever.
        create_patch = etree.SubElement(inner_patch, "Patch", Id=new_vl_id(), Name="Create")
        update_patch = etree.SubElement(inner_patch, "Patch", Id=new_vl_id(), Name="Update")
        process_definition = etree.SubElement(inner_patch, "ProcessDefinition", Id=new_vl_id())
        etree.SubElement(
            process_definition,
            "Fragment",
            Id=new_vl_id(),
            Patch=create_patch.get("Id"),
            Enabled="true",
        )
        etree.SubElement(
            process_definition,
            "Fragment",
            Id=new_vl_id(),
            Patch=update_patch.get("Id"),
            Enabled="true",
        )
        return cls(VlDocument(etree.ElementTree(root)), catalog=catalog)

    def _reindex_aliases(self) -> None:
        used_aliases = set(self._aliases.values()) | set(self._entity_aliases.values())
        for node in sorted(self.graph.operational_nodes(), key=self._sort_key):
            identifier = node.get("Id")
            if identifier and identifier not in self._aliases:
                while f"n{self._next_alias}" in used_aliases:
                    self._next_alias += 1
                alias = f"n{self._next_alias}"
                self._aliases[identifier] = alias
                used_aliases.add(alias)
                self._next_alias += 1
        pad_number = 1
        region_number = 1
        for element in self.graph.annotations():
            identifier = element.get("Id")
            if not identifier:
                continue
            if self.graph.annotation_kind(element) == "region":
                if identifier not in self._entity_aliases:
                    while f"r{region_number}" in used_aliases:
                        region_number += 1
                    alias = f"r{region_number}"
                    self._entity_aliases[identifier] = alias
                    used_aliases.add(alias)
                region_number += 1
            else:
                if identifier not in self._entity_aliases:
                    while f"p{pad_number}" in used_aliases:
                        pad_number += 1
                    alias = f"p{pad_number}"
                    self._entity_aliases[identifier] = alias
                    used_aliases.add(alias)
                pad_number += 1

    @staticmethod
    def _sort_key(node: etree._Element) -> tuple[float, float, str, str]:
        bounds = _parse_bounds(node.get("Bounds")) or ["0", "0"]
        try:
            x, y = float(bounds[0]), float(bounds[1])
        except ValueError:
            x, y = 0.0, 0.0
        return (y, x, VlGraph.node_name(node), node.get("Id", ""))

    def _refresh(self) -> None:
        # BLIND SPOT - DO NOT REMOVE (2026-10-05)
        # Undo, rollback and external reload replace self.document. Reindexing
        # a graph still bound to the old tree makes following edits/validation
        # operate on XML which will never be saved.
        self.graph.document = self.document
        self.graph.refresh()
        self.document_catalog = DocumentCatalog.from_document(self.document)
        self.catalog = CompositeCatalog(self._external_catalog, self.document_catalog) if self._external_catalog else self.document_catalog
        self._reindex_aliases()

    def _snapshot(self) -> bytes:
        return self.document.to_bytes()

    def _before_mutation(self) -> None:
        if self._transaction_depth == 0:
            self._undo.append(self._snapshot())
            self._redo.clear()

    @contextmanager
    def transaction(self, *, validate: bool = True) -> Iterator["PatchSession"]:
        """Group mutations into one undo unit and validate before commit.

        Any exception or validation error restores the exact pre-transaction
        tree in memory.  Disk state is untouched until :meth:`save` succeeds.
        """

        outermost = self._transaction_depth == 0
        if outermost:
            history = (list(self._undo), list(self._redo), dict(self._aliases),
                       dict(self._entity_aliases), self._next_alias)
            self._transaction_snapshot = self._snapshot()
            self._undo.append(self._transaction_snapshot)
            self._redo.clear()
        self._transaction_depth += 1
        try:
            yield self
            if self._transaction_depth == 1 and validate:
                report = self.validate(include_orphan_warnings=False)
                if not report.ok:
                    raise ValueError(self._format_report(report))
        except Exception:
            if self._transaction_depth == 1 and self._transaction_snapshot is not None:
                self._restore(self._transaction_snapshot)
                self._undo, self._redo, self._aliases, self._entity_aliases, self._next_alias = history
            raise
        finally:
            self._transaction_depth -= 1
            if self._transaction_depth == 0:
                self._transaction_snapshot = None

    def _restore(self, payload: bytes) -> None:
        restored = VlDocument.parse(payload, source_path=self.document.source_path)
        self.document = restored
        self._refresh()

    def replace_document(self, document: VlDocument) -> None:
        """Replace the model after a validated external (usually human) edit.

        The reloaded geometry becomes the new protected baseline. This makes
        collaboration persistent across any number of editor/agent cycles
        without writing tool-specific metadata into the user's ``.vl`` file.
        """

        self.document = document
        self._refresh()
        self._layout_baseline_ids = self._canvas_entity_ids()

    def _canvas_entity_ids(self) -> set[str]:
        return {
            element.get("Id", "")
            for element in (*self.graph.operational_nodes(), *self.graph.pads)
            if element.get("Id")
        }

    def undo(self) -> bool:
        """Restore the most recent in-memory mutation, without touching disk."""

        if not self._undo:
            return False
        current = self._snapshot()
        self._redo.append(current)
        self._restore(self._undo.pop())
        return True

    def redo(self) -> bool:
        """Re-apply the most recently undone in-memory mutation."""

        if not self._redo:
            return False
        current = self._snapshot()
        self._undo.append(current)
        self._restore(self._redo.pop())
        return True

    @staticmethod
    def _format_report(report: ValidationReport) -> str:
        return "; ".join(f"{item.code}: {item.message}" for item in report.errors) or "patch validation failed"

    def validate(self, *, include_orphan_warnings: bool = True) -> ValidationReport:
        report = self.graph.validate(include_orphan_warnings=include_orphan_warnings)
        self._check_link_type_mismatches(report)
        return report

    # Pairs confirmed refused by the target vvvv compiler in live authoring.
    # Extend this set only with verified type contracts, not guesses --
    # vvvv does allow plenty of other cross-type links via implicit
    # conversion nodes, so guessing here would produce false positives.
    _INCOMPATIBLE_LINK_TYPES: frozenset[frozenset[str]] = frozenset(
        {frozenset({"Integer32", "Integer32 (Unsigned)"})}
    )

    def _resolve_endpoint_type(self, endpoint_id: str) -> str | None:
        """Return an endpoint's vvvv type name, or None if it isn't known.

        A Pad's type is always in the file (``TypeAnnotation``). A Node pin's
        type is NOT stored in the file at all -- vvvv resolves it from the
        node's own reflection at load time -- so it can only be answered here
        when ``self.catalog`` carries real pin types for that node (as the
        hardcoded shader/bridge ``NodeSpec`` additions in a generator script
        do). A plain ``DocumentCatalog`` parsed from XML has no pin types
        (every pin comes back ``"Object"``), so this returns None for those
        and the mismatch check silently skips the link rather than guessing.
        """

        owner = self.graph.endpoint_owner.get(endpoint_id)
        if owner is None:
            return None
        local = etree.QName(owner).localname
        if local == "Pad":
            type_annotation = owner.find(f"{{{PROPERTY_NS}}}TypeAnnotation")
            if type_annotation is None:
                return None
            choice = type_annotation.find("Choice")
            name = choice.get("Name") if choice is not None else None
            return name or None
        if local != "Node":
            return None
        pin_element = self.graph.by_id.get(endpoint_id)
        if pin_element is None:
            return None
        pin_name = pin_element.get("Name", "")
        reference = owner.find(f"{{{PROPERTY_NS}}}NodeReference")
        category = reference.get("LastCategoryFullName", "") if reference is not None else ""
        spec = self.catalog.resolve(VlGraph.node_name(owner), category=category or None)
        if spec is None:
            return None
        try:
            # Disambiguate by direction: an input and an output can share a
            # name (e.g. both called "Output" is rare but not impossible),
            # and NodeSpec.pin() without a direction hint returns whichever
            # comes first.
            pin_spec = spec.pin(pin_name, input_only=self.graph.endpoint(endpoint_id).is_input)
        except KeyError:
            return None
        return pin_spec.type_name if pin_spec.type_name and pin_spec.type_name != "Object" else None

    def _check_link_type_mismatches(self, report: ValidationReport) -> None:
        """Flag links whose resolved source/target types vvvv itself refuses.

        Catalog-dependent: only fires when both endpoint types are resolvable
        (see :meth:`_resolve_endpoint_type`). Silence here means "unknown",
        never "compatible".
        """

        for link in self.graph.links:
            endpoints = self.graph.link_endpoints(link)
            if endpoints is None:
                continue
            source_type = self._resolve_endpoint_type(endpoints[0])
            target_type = self._resolve_endpoint_type(endpoints[1])
            if not source_type or not target_type or source_type == target_type:
                continue
            if frozenset({source_type, target_type}) in self._INCOMPATIBLE_LINK_TYPES:
                report.add(
                    "link-type-mismatch",
                    f"vvvv refuses this link: {source_type} source into {target_type} target",
                    severity="error",
                    element_id=link.get("Id"),
                )

    def edit_batch(self, operations: list[dict]) -> dict:
        """Apply the shared Python/MCP/CLI semantic contract atomically.

        Name a result with ``as`` and reuse ``$name.field`` in later arguments.
        Returned Process bodies/Slot endpoints are JSON-safe IDs, not XML objects.
        """
        from .operations import apply_batch
        return apply_batch(self, operations)

    def canvases(self) -> list[dict]:
        """Discover existing Process scopes and boundary IDs without XML dumps."""
        result = []
        for canvas in self.document.root.iter("Canvas"):
            if canvas.get("CanvasType") != "Group":
                continue
            owner = canvas.getparent()
            definition = owner.getparent() if owner is not None else None
            if owner is None or owner.tag != "Patch":
                continue
            result.append({"id": canvas.get("Id"), "patch": owner.get("Id"),
                           "definition": definition.get("Id") if definition is not None else None,
                           "name": definition.get("Name") if definition is not None else None,
                           "inputs": {pin.get("Name"): pin.get("Id") for pin in owner.findall("./Patch/Pin[@Kind='InputPin']")},
                           "outputs": {pin.get("Name"): pin.get("Id") for pin in owner.findall("./Patch/Pin[@Kind='OutputPin']")},
                           "slots": {slot.get("Name"): slot.get("Id") for slot in owner.findall("Slot")}})
        return result

    def save(self, path: str | Path | None = None) -> Path:
        report = self.validate()
        if not report.ok:
            raise ValueError(self._format_report(report))
        destination = self.document.write_atomic(path, validate=False)
        # A successful save is a collaboration checkpoint. Geometry accepted
        # into the file is now protected from later default layout passes.
        self._layout_baseline_ids = self._canvas_entity_ids()
        return destination

    def node(self, alias_or_id: str) -> etree._Element:
        identifier = self._resolve_node_id(alias_or_id)
        return self.graph.element(identifier)

    def resolve_node(self, alias_or_id: str) -> PatchNodeView:
        node = self.node(alias_or_id)
        bounds = _parse_bounds(node.get("Bounds"))
        parsed_bounds = None
        if bounds is not None and len(bounds) >= 4:
            try:
                parsed_bounds = tuple(float(item) for item in bounds[:4])
            except ValueError:
                parsed_bounds = None
        identifier = node.get("Id", "")
        reference = node.find("{property}NodeReference")
        return PatchNodeView(
            alias=self._aliases.get(identifier, identifier),
            identifier=identifier,
            operation=VlGraph.node_name(node),
            category=reference.get("LastCategoryFullName", "") if reference is not None else "",
            bounds=parsed_bounds,
        )

    def _resolve_node_id(self, alias_or_id: str) -> str:
        if alias_or_id in self.graph.by_id and etree.QName(self.graph.by_id[alias_or_id]).localname == "Node":
            return alias_or_id
        for identifier, alias in self._aliases.items():
            if alias == alias_or_id:
                return identifier
        raise KeyError(f"unknown patch node alias or ID: {alias_or_id}")

    def _resolve_entity_id(self, alias_or_id: str) -> str:
        if alias_or_id in self.graph.by_id:
            return alias_or_id
        for identifier, alias in (*self._aliases.items(), *self._entity_aliases.items()):
            if alias == alias_or_id:
                return identifier
        raise KeyError(f"unknown patch entity alias or ID: {alias_or_id}")

    def alias_for(self, identifier: str) -> str:
        self._reindex_aliases()
        return self._aliases.get(identifier, self._entity_aliases.get(identifier, identifier))

    def query_catalog(self, query: str, *, category: str | None = None, limit: int = 20) -> list[NodeSpec]:
        return self.catalog.search(query, category=category, limit=limit)

    def _exact_spec(self, name: str, category: str | None = None) -> NodeSpec:
        spec = self.catalog.resolve(name, category=category)
        if spec is None:
            qualifier = f" in category {category!r}" if category else ""
            raise CatalogError(f"no exact catalog node for {name!r}{qualifier}; refusing to invent XML")
        return spec

    def add_node(
        self,
        name: str,
        *,
        alias: str | None = None,
        category: str | None = None,
        x: float = 100,
        y: float = 100,
        values: dict[str, str] | None = None,
        patch: etree._Element | None = None,
    ) -> str:
        spec = self._exact_spec(name, category)
        if alias is not None and alias in (*self._aliases.values(), *self._entity_aliases.values()):
            raise ValueError(f"node alias already exists: {alias}")
        self._before_mutation()
        if spec.dependency and not self._dependency_available(spec.dependency):
            self.graph.add_dependency(spec.dependency)
        node = etree.Element("Node", Id=new_vl_id())
        if spec.reference_kind == "NodeFlag":
            reference = etree.SubElement(node, f"{{{PROPERTY_NS}}}NodeReference", LastCategoryFullName=spec.category)
        else:
            reference = etree.SubElement(node, f"{{{PROPERTY_NS}}}NodeReference", LastCategoryFullName=spec.category)
        if spec.dependency or spec.reference_dependency:
            reference.set("LastDependency", spec.reference_dependency or spec.dependency or "")
        for choice_kind, choice_name in spec.prefix_choices:
            etree.SubElement(reference, "Choice", Kind=choice_kind, Name=choice_name, Fixed="true")
        choice = etree.SubElement(reference, "Choice", Kind=spec.reference_kind, Name=spec.name)
        if spec.fixed:
            choice.set("Fixed", "true")
        for pin in (*spec.inputs, *spec.outputs):
            attributes = {"Id": new_vl_id(), "Name": pin.name, "Kind": pin.kind}
            if pin.default_value is not None:
                attributes["DefaultValue"] = pin.default_value
            if pin.hidden:
                attributes["IsHidden"] = "true"
            if pin.optional:
                attributes["IsOptional"] = "true"
            etree.SubElement(node, "Pin", **attributes)
        # Size the node from its own pins immediately, the way vvvv itself
        # would draw it, instead of an arbitrary placeholder width. Real vvvv
        # nodes range from ~35px (few pins, short name) to 400px+ (many pins);
        # a flat "100" is wrong in both directions and was the root cause of
        # generated nodes needing a manual widen pass before every commit.
        width = self._intrinsic_node_width(node)
        node.set("Bounds", _format_bounds(x, y, width, 19))
        destination = patch if patch is not None else self.graph._main_canvas()
        destination.append(node)
        self._refresh()
        identifier = node.get("Id", "")
        self._aliases[identifier] = alias or f"n{self._next_alias}"
        if alias is None:
            self._next_alias += 1
        if values:
            for pin_name, value in values.items():
                self.set_pin_default(identifier, pin_name, value)
        return self._aliases[identifier]

    def add_process(
        self,
        name: str,
        *,
        inputs: Iterable[PinSpec] = (),
        outputs: Iterable[PinSpec] = (),
        x: float = 100,
        y: float = 100,
        definition_position: tuple[float, float] = (200, 100),
        alias: str | None = None,
        type_annotations: dict[str, etree._Element] | None = None,
        document_name: str | None = None,
        patch: etree._Element | None = None,
    ) -> ProcessBuilder:
        """Create the saved Plates-style local Process and its first call.

        ``inputs``/``outputs`` preserve PinSpec declaration order. Their types
        annotate the Update signature, not the call pins. Supply exact
        ``p:TypeAnnotation`` elements for namespaced/generic types; otherwise a
        simple TypeFlag is used, as in normal VL type annotations. Returned
        canvas ControlPoint IDs are connectable in either direction.

        ``document_name`` is the eventual .vl filename when this session has
        not been loaded from disk. A loaded document uses its existing name.
        This is a local definition, so no dependency on itself is added.
        """
        input_specs, output_specs = tuple(inputs), tuple(outputs)
        specs = (*input_specs, *output_specs)
        names = [spec.name for spec in specs]
        if not name or name == "Application":
            raise ValueError("Process needs a non-Application name")
        self._require_process_name(name)
        if len(set(names)) != len(names) or any(not value or value == "Node Context" for value in names):
            raise ValueError("Process boundary names must be unique and non-reserved")
        if any(spec.kind != "InputPin" for spec in input_specs) or any(spec.kind != "OutputPin" for spec in output_specs):
            raise ValueError("Process signature requires InputPin inputs and OutputPin outputs")
        if alias is not None and alias in (*self._aliases.values(), *self._entity_aliases.values()):
            raise ValueError(f"node alias already exists: {alias}")
        full_canvas = self.document.root.find("./Patch/Canvas[@CanvasType='FullCategory']")
        if full_canvas is None:
            raise ValueError("document has no FullCategory definition canvas")
        if any(node.get("Name") == name for node in full_canvas.findall("Node")):
            raise ValueError(f"local definition already exists: {name}")
        annotations = type_annotations or {}
        if set(annotations) - set(names):
            raise ValueError("type annotation has no corresponding boundary")
        for spec in specs:
            annotation = annotations.get(spec.name)
            if annotation is not None and annotation.tag != f"{{{PROPERTY_NS}}}TypeAnnotation":
                raise ValueError("boundary type must be a p:TypeAnnotation element")
            if annotation is None and (not spec.type_name or spec.type_name == "Object"):
                raise ValueError(f"boundary {spec.name!r} needs an explicit type")

        self._before_mutation()
        definition = etree.SubElement(full_canvas, "Node", Id=new_vl_id(), Name=name,
                                      Bounds=_format_bounds(*definition_position, 200, 60))
        reference = etree.SubElement(definition, f"{{{PROPERTY_NS}}}NodeReference")
        etree.SubElement(reference, "Choice", Kind="ContainerDefinition", Name="Process")
        etree.SubElement(reference, "CategoryReference", Kind="Category", Name="Primitive")
        owner = etree.SubElement(definition, "Patch", Id=new_vl_id())
        body = etree.SubElement(owner, "Canvas", Id=new_vl_id(), CanvasType="Group")
        create = etree.SubElement(owner, "Patch", Id=new_vl_id(), Name="Create")
        update = etree.SubElement(owner, "Patch", Id=new_vl_id(), Name="Update")
        lifecycle = etree.SubElement(owner, "ProcessDefinition", Id=new_vl_id())
        # BLIND SPOT - DO NOT REMOVE (2026-10-04)
        # A visible Process canvas is not an execution entry point. Both real
        # lifecycle patches must be enabled; its boundaries belong to Update.
        for target in (create, update):
            etree.SubElement(lifecycle, "Fragment", Id=new_vl_id(), Patch=target.get("Id"), Enabled="true")

        portals: list[dict[str, str]] = [{}, {}]
        signature: list[dict[str, str]] = [{}, {}]
        for direction, group in enumerate((input_specs, output_specs)):
            for index, spec in enumerate(group):
                attrs = {"Id": new_vl_id(), "Name": spec.name, "Kind": spec.kind}
                if spec.default_value is not None:
                    attrs["DefaultValue"] = spec.default_value
                pin = etree.SubElement(update, "Pin", **attrs)
                annotation = annotations.get(spec.name)
                if annotation is None:
                    annotation = etree.Element(f"{{{PROPERTY_NS}}}TypeAnnotation")
                    etree.SubElement(annotation, "Choice", Kind="TypeFlag", Name=spec.type_name)
                annotation = deepcopy(annotation)
                for descendant in annotation.iter():
                    if descendant.get("Id"):
                        descendant.set("Id", new_vl_id())
                pin.append(annotation)
                portal = etree.SubElement(body, "ControlPoint", Id=new_vl_id(),
                                          Bounds=f"{_format_number(100 + index * 120)},{100 if direction == 0 else 800}")
                pin_id, portal_id = pin.get("Id", ""), portal.get("Id", "")
                signature[direction][spec.name] = pin_id
                portals[direction][spec.name] = portal_id
                endpoints = (pin_id, portal_id) if direction == 0 else (portal_id, pin_id)
                etree.SubElement(owner, "Link", Id=new_vl_id(), Ids=",".join(endpoints), IsHidden="true")

        destination = patch if patch is not None else self.graph._main_canvas()
        call = etree.SubElement(destination, "Node", Id=new_vl_id())
        call_reference = etree.SubElement(call, f"{{{PROPERTY_NS}}}NodeReference",
                                          LastCategoryFullName=full_canvas.get("DefaultCategory", "Main"))
        local_name = document_name or (self.document.source_path.name if self.document.source_path else None)
        if local_name:
            call_reference.set("LastDependency", local_name)
        etree.SubElement(call_reference, "Choice", Kind="ProcessNode", Name=name)
        etree.SubElement(call, "Pin", Id=new_vl_id(), Name="Node Context", Kind="InputPin", IsHidden="true")
        call_pins: list[dict[str, str]] = [{}, {}]
        for direction, group in enumerate((input_specs, output_specs)):
            for spec in group:
                attrs = {"Id": new_vl_id(), "Name": spec.name, "Kind": spec.kind}
                if spec.default_value is not None:
                    attrs["DefaultValue"] = spec.default_value
                if spec.hidden:
                    attrs["IsHidden"] = "true"
                if spec.optional:
                    attrs["IsOptional"] = "true"
                pin = etree.SubElement(call, "Pin", **attrs)
                call_pins[direction][spec.name] = pin.get("Id", "")
        call.set("Bounds", _format_bounds(x, y, self._intrinsic_node_width(call), 19))
        self._refresh()
        call_id = call.get("Id", "")
        if alias is not None:
            self._aliases[call_id] = alias
        return ProcessBuilder(definition.get("Id", ""), body, *portals, *signature,
                              self.alias_for(call_id), call_id, *call_pins)

    def add_input_placement(
        self,
        existing_input: str,
        position: tuple[float, float] = (100, 100),
        *,
        patch: etree._Element | None = None,
    ) -> str:
        """Place the same signature input near another consumer.

        Accept a signature Pin ID or an existing input ControlPoint ID. Like
        VL.Model.Patch.AddProxy, create a plain ControlPoint and a hidden link
        from the original signature Pin. No second parameter or Slot is made.
        ``patch`` may be its owning Patch or one of that Patch's canvases.
        """
        source = self.graph.element(self._resolve_entity_id(existing_input))
        existing_portal = source if source.tag == "ControlPoint" else None
        if source.tag == "ControlPoint":
            references = [self.graph.element(hubs[0]) for link in self.graph.links
                          if link.get("IsHidden", "false").lower() == "true"
                          and (hubs := self.graph.link_hub_ids(link))
                          and hubs[-1] == source.get("Id")]
            if len(references) != 1:
                raise ValueError("input placement needs exactly one signature reference")
            source = references[0]
        signature = source.getparent()
        if (source.tag != "Pin" or source.get("Kind") != "InputPin"
                or signature is None or signature.tag != "Patch"):
            raise ValueError("input placement must reference a signature InputPin")
        owner = signature.getparent()
        if owner is None or owner.tag != "Patch":
            raise ValueError("signature input needs an owning Patch")
        if existing_portal is not None and next(existing_portal.iterancestors("Patch"), None) is not owner:
            raise ValueError("existing input placement crosses its owning Patch")
        canvas = self._placement_canvas(owner, patch)
        if len(position) != 2:
            raise ValueError("input placement position needs x and y")
        bounds = _format_bounds(*position)
        self._before_mutation()
        portal = etree.SubElement(canvas, "ControlPoint", Id=new_vl_id(), Bounds=bounds)
        # BLIND SPOT - DO NOT REMOVE (2026-10-04)
        # Repeated inputs share the signature Pin via hidden reference links.
        # Duplicating signature Pins changes the public contract; invented
        # DefinitionId selectors do not resolve these canvas placements.
        etree.SubElement(owner, "Link", Id=new_vl_id(),
                         Ids=f"{source.get('Id')},{portal.get('Id')}", IsHidden="true")
        self._refresh()
        return portal.get("Id", "")

    def _placement_canvas(self, owner: etree._Element, patch: etree._Element | None) -> etree._Element:
        """Resolve an attached canvas without crossing the field/signature scope."""
        if owner.getroottree().getroot() is not self.document.root:
            raise ValueError("placement owner must belong to this document")
        destination = owner if patch is None else patch
        if destination.getroottree().getroot() is not self.document.root:
            raise ValueError("placement destination must belong to this document")
        if destination is owner:
            canvas = owner.find("Canvas[@CanvasType='Group']")
            if canvas is None:
                raise ValueError("placement owner needs a Group Canvas")
            return canvas
        if destination.tag != "Canvas" or next(destination.iterancestors("Patch"), None) is not owner:
            raise ValueError("placement must stay in its owning Patch")
        return destination

    def _dependency_available(self, dependency: str) -> bool:
        for item in self.document.root:
            if not isinstance(item.tag, str):
                continue
            location = item.get("Location", "")
            if location == dependency or location.endswith(dependency) or dependency.endswith(location):
                return True
        return False

    def _resolve_pin_id(self, node_alias_or_id: str, pin_name: str, *, input_only: bool | None = None) -> str:
        node = self.node(node_alias_or_id)
        for pin in node.findall("Pin"):
            if pin.get("Name") == pin_name:
                kind = pin.get("Kind", "")
                is_input = kind in {"InputPin", "StateInputPin", "ApplyPin", "ControlPoint"}
                if input_only is None or input_only == is_input:
                    return pin.get("Id", "")
        operation = VlGraph.node_name(node)
        direction = "input" if input_only else "output" if input_only is False else ""
        raise KeyError(f"node {operation!r} has no exact {direction} pin {pin_name!r}")

    def _endpoint_ref(self, value: str, *, input_only: bool | None = None) -> str:
        if "." not in value:
            try:
                return self._resolve_entity_id(value)
            except KeyError:
                return value
        node_name, pin_name = value.rsplit(".", 1)
        return self._resolve_pin_id(node_name, pin_name, input_only=input_only)

    def connect(self, source: str, target: str) -> str:
        """Connect ``alias.pin`` to ``alias.pin`` after exact endpoint checks."""

        source_id = self._endpoint_ref(source, input_only=False)
        target_id = self._endpoint_ref(target, input_only=True)
        self._before_mutation()
        return self.graph.ensure_link(source_id, target_id)

    def disconnect(self, target: str) -> int:
        target_id = self._endpoint_ref(target, input_only=True)
        self._before_mutation()
        removed = 0
        for link in list(self.graph.links):
            endpoints = self.graph.link_endpoints(link)
            if endpoints and endpoints[1] == target_id:
                self.graph.remove_link(link.get("Id", ""))
                removed += 1
        return removed

    def add_pad(self, *, value: str | None = None, comment: str | None = None,
                x: float = 100, y: float = 100, type_name: str | None = None,
                type_category: str = "Primitive", type_dependency: str = "VL.CoreLib.vl",
                patch: etree._Element | None = None) -> str:
        self._before_mutation()
        width, height = self._pad_size_for_value(type_name, value)
        attributes = {"Bounds": _format_bounds(x, y, width, height)}
        identifier = self.graph.add_pad(value=value, comment=comment, **attributes)
        if patch is not None:
            patch.append(self.graph.element(identifier))
            self._refresh()
        if type_name:
            pad = self.graph.element(identifier)
            annotation = etree.SubElement(
                pad, f"{{{PROPERTY_NS}}}TypeAnnotation",
                LastCategoryFullName=type_category, LastDependency=type_dependency,
            )
            etree.SubElement(annotation, "Choice", Kind="TypeFlag", Name=type_name)
            self._refresh()
        return self.alias_for(identifier)

    def add_slot(
        self,
        name: str,
        *,
        patch: etree._Element | None = None,
        read_position: tuple[float, float] = (100, 100),
        write_position: tuple[float, float] = (100, 300),
        type_annotation: etree._Element | None = None,
        type_name: str | None = None,
    ) -> SlotBuilder:
        """Create the saved PathTrace Scene state-field/accessor pattern.

        Connect a producer to ``write_pad`` and ``read_pad`` to its consumer
        with ordinary links. VL reads/writes the real Slot; ``IsFeedback`` on
        a direct link does not allocate state or generate a delayed assignment.
        Types may be inferred, as in the saved patch, or supplied explicitly.
        """
        owner = patch if patch is not None else self.graph._main_canvas().getparent()
        if owner is None or owner.tag != "Patch" or owner.getroottree().getroot() is not self.document.root:
            raise ValueError("slot owner must be an attached Patch in this document")
        canvas = owner.find("Canvas[@CanvasType='Group']")
        if canvas is None:
            raise ValueError("slot owner needs a Group Canvas")
        if not name or any(slot.get("Name") == name for slot in owner.findall("Slot")):
            raise ValueError("slot name must be nonempty and unique in its Patch")
        if type_annotation is not None and type_annotation.tag != f"{{{PROPERTY_NS}}}TypeAnnotation":
            raise ValueError("slot type must be a p:TypeAnnotation element")
        if type_annotation is not None and type_name is not None:
            raise ValueError("supply type_annotation or type_name, not both")
        read_bounds = ",".join(_format_number(value) for value in read_position)
        write_bounds = ",".join(_format_number(value) for value in write_position)
        if len(read_position) != 2 or len(write_position) != 2:
            raise ValueError("slot accessor positions need x and y")
        self._before_mutation()
        slot = etree.SubElement(owner, "Slot", Id=new_vl_id(), Name=name)
        if type_annotation is not None:
            annotation = deepcopy(type_annotation)
            for element in annotation.iter():
                if element.get("Id"):
                    element.set("Id", new_vl_id())
            slot.append(annotation)
        elif type_name is not None:
            annotation = etree.SubElement(slot, f"{{{PROPERTY_NS}}}TypeAnnotation")
            etree.SubElement(annotation, "Choice", Kind="TypeFlag", Name=type_name)
        slot_id = slot.get("Id", "")
        # BLIND SPOT - DO NOT REMOVE (2026-10-04)
        # A link flag is not a state field. The compiler skips IsFeedback link
        # assignments; real stored values require a Slot and separate accessor
        # Pads. Preserve their shared SlotId, not a direct producer/consumer edge.
        read_pad = etree.SubElement(canvas, "Pad", Id=new_vl_id(), SlotId=slot_id, Bounds=read_bounds)
        write_pad = etree.SubElement(canvas, "Pad", Id=new_vl_id(), SlotId=slot_id, Bounds=write_bounds)
        self._refresh()
        return SlotBuilder(slot_id, read_pad.get("Id", ""), write_pad.get("Id", ""))

    def add_slot_read(
        self,
        existing_slot: str | SlotBuilder,
        position: tuple[float, float] = (100, 100),
        *,
        patch: etree._Element | None = None,
    ) -> str:
        """Add a plain read accessor sharing an existing Slot's identity.

        Connect this Pad only as a source to read the field. XML contains no
        read/write flag: incoming links make a Pad a writer. A Slot read uses
        an earlier write in compiler order, otherwise its stored value (null
        initially for uninitialized reference types). Canvas positions do not
        enforce that order, and this API does not guarantee a frame delay.
        """
        identifier = existing_slot.slot_id if isinstance(existing_slot, SlotBuilder) else self._resolve_entity_id(existing_slot)
        slot = self.graph.element(identifier)
        owner = slot.getparent()
        if slot.tag != "Slot" or owner is None or owner.tag != "Patch":
            raise ValueError("slot read must reference an existing Slot in a Patch")
        canvas = self._placement_canvas(owner, patch)
        if len(position) != 2:
            raise ValueError("slot read position needs x and y")
        bounds = _format_bounds(*position)
        self._before_mutation()
        pad = etree.SubElement(canvas, "Pad", Id=new_vl_id(), SlotId=identifier, Bounds=bounds)
        self._refresh()
        return pad.get("Id", "")

    def add_annotation(
        self,
        kind: str,
        *,
        text: str = "",
        x: float = 100,
        y: float = 100,
        width: float = 300,
        height: float = 60,
        font_size: int | None = None,
        relative_to: Iterable[str] | None = None,
        offset: tuple[float, float] = (20, 20),
        placement: str = "right",
        patch: etree._Element | None = None,
    ) -> str:
        self._before_mutation()
        relative_ids = [self._resolve_entity_id(value) for value in relative_to] if relative_to else None
        identifier = self.graph.add_annotation(
            kind=kind,
            text=text,
            bounds=_format_bounds(x, y, width, height),
            font_size=font_size,
            relative_to=relative_ids,
            offset=offset,
            placement=placement,
        )
        if patch is not None:
            element = self.graph.element(identifier)
            if kind == "region":
                patch.insert(0, element)
            else:
                patch.append(element)
        self._refresh()
        self._reindex_aliases()
        return self.alias_for(identifier)

    def add_dependency(self, location: str, *, version: str | None = None) -> str:
        self._before_mutation()
        return self.graph.add_dependency(location, version=version)

    def add_pin(self, node_alias_or_id: str, name: str, kind: str = "InputPin", *, default_value: str | None = None, hidden: bool = False) -> str:
        """Add a dynamic/pin-group pin (for example Group Input 5)."""

        self._before_mutation()
        attributes = {}
        if default_value is not None:
            attributes["DefaultValue"] = default_value
        if hidden:
            attributes["IsHidden"] = "true"
        return self.graph.add_pin(self._resolve_node_id(node_alias_or_id), name, kind, **attributes)

    def add_matrix_repeat_builder(
        self,
        *,
        x: float = 100,
        y: float = 300,
        count: int = 1,
        count_comment: str = "Transform Count",
        patch: etree._Element | None = None,
    ) -> MatrixRepeatBuilder:
        """Create vvvv's canonical Cache/Repeat MutableArray Matrix loop.

        The translation ControlPoint carries a Vector2 position spread into the
        Repeat; XyZ selects its current item and adds a scalar Y value before
        TransformSRT. Scaling is a scalar TransformSRT input, not a spread
        relay. One count IOBox drives both MutableArray allocation and Repeat
        iteration, so the array dimension cannot diverge from the loop.
        The stable ``ReadOnlyMemory<Matrix>`` result is suitable for a CPU
        instancer without rebuilding immutable spreads every frame.
        """

        if count < 0:
            raise ValueError("count must be non-negative")

        self._before_mutation()
        canvas = patch if patch is not None else self.graph._main_canvas()
        outer_patch = canvas.getparent()
        if outer_patch is None or etree.QName(outer_patch).localname != "Patch":
            raise ValueError("Application Group canvas has no owning Patch")

        def bounds(px: float, py: float, width: float, height: float) -> str:
            return _format_bounds(px, py, width, height)

        def pin(parent: etree._Element, name: str, kind: str, **attributes: str) -> str:
            element = etree.SubElement(parent, "Pin", Id=new_vl_id(), Name=name, Kind=kind, **attributes)
            return element.get("Id", "")

        def operation_node(
            parent: etree._Element,
            *,
            px: float,
            py: float,
            width: float,
            height: float = 19,
            category: str,
            name: str,
            dependency: str = "VL.CoreLib.vl",
        ) -> etree._Element:
            node = etree.SubElement(parent, "Node", Id=new_vl_id(), Bounds=bounds(px, py, width, height))
            reference = etree.SubElement(
                node,
                f"{{{PROPERTY_NS}}}NodeReference",
                LastCategoryFullName=category,
                LastDependency=dependency,
            )
            etree.SubElement(reference, "Choice", Kind="NodeFlag", Name="Node", Fixed="true")
            etree.SubElement(reference, "Choice", Kind="OperationCallFlag", Name=name)
            return node

        # Count IOBox: one source of truth for allocation and iteration.
        count_pad = etree.SubElement(
            canvas,
            "Pad",
            Id=new_vl_id(),
            Comment=count_comment,
            Bounds=bounds(x + 54, y - 70, 45, 15),
            ShowValueBox="true",
            isIOBox="true",
            Value=str(count),
        )
        count_type = etree.SubElement(
            count_pad,
            f"{{{PROPERTY_NS}}}TypeAnnotation",
            LastCategoryFullName="Primitive",
            LastDependency="VL.CoreLib.vl",
        )
        etree.SubElement(count_type, "Choice", Kind="TypeFlag", Name="Integer32")

        # Cache owns the MutableArray and reallocates it only when count changes.
        cache = etree.SubElement(canvas, "Node", Id=new_vl_id(), Bounds=bounds(x, y, 110, 92))
        cache_reference = etree.SubElement(
            cache,
            f"{{{PROPERTY_NS}}}NodeReference",
            LastCategoryFullName="Primitive",
            LastDependency="Builtin",
        )
        etree.SubElement(cache_reference, "Choice", Kind="StatefulRegion", Name="Region (Stateful)", Fixed="true")
        etree.SubElement(cache_reference, "Choice", Kind="ProcessStatefulRegion", Name="Cache")
        pin(cache, "Force", "InputPin")
        pin(cache, "Dispose Cached Outputs", "InputPin")
        pin(cache, "Has Changed", "OutputPin")
        cache_patch = etree.SubElement(cache, "Patch", Id=new_vl_id(), ManuallySortedPins="true")
        etree.SubElement(cache_patch, "Patch", Id=new_vl_id(), Name="Create", ManuallySortedPins="true")
        etree.SubElement(cache_patch, "Patch", Id=new_vl_id(), Name="Then", ManuallySortedPins="true")
        create = operation_node(
            cache_patch,
            px=x + 13,
            py=y + 25,
            width=84,
            height=26,
            category="Collections.Mutable.MutableArray",
            name="Create",
        )
        pin(create, "Node Context", "InputPin", IsHidden="true")
        create_length = pin(create, "Length", "InputPin")
        create_result = pin(create, "Result", "StateOutputPin")
        cache_top = etree.SubElement(cache, "ControlPoint", Id=new_vl_id(), Bounds=_format_bounds(x + 20, y + 6), Alignment="Top")
        cache_bottom = etree.SubElement(cache, "ControlPoint", Id=new_vl_id(), Bounds=_format_bounds(x + 20, y + 82), Alignment="Bottom")

        # Repeat writes one Matrix into the cached array for every index.
        repeat_x = x + 155
        repeat = etree.SubElement(canvas, "Node", Id=new_vl_id(), Bounds=bounds(repeat_x, y, 270, 250))
        repeat_reference = etree.SubElement(
            repeat,
            f"{{{PROPERTY_NS}}}NodeReference",
            LastCategoryFullName="Primitive",
            LastDependency="Builtin",
        )
        etree.SubElement(repeat_reference, "Choice", Kind="StatefulRegion", Name="Region (Stateful)", Fixed="true")
        etree.SubElement(repeat_reference, "Choice", Kind="ApplicationStatefulRegion", Name="Repeat")
        repeat_count = pin(repeat, "Iteration Count", "InputPin")
        pin(repeat, "Break", "OutputPin")
        repeat_patch = etree.SubElement(repeat, "Patch", Id=new_vl_id(), ManuallySortedPins="true")
        etree.SubElement(repeat_patch, "Patch", Id=new_vl_id(), Name="Create", ManuallySortedPins="true")
        update_patch = etree.SubElement(repeat_patch, "Patch", Id=new_vl_id(), Name="Update", ManuallySortedPins="true")
        update_index = pin(update_patch, "Index", "InputPin")
        etree.SubElement(repeat_patch, "Patch", Id=new_vl_id(), Name="Dispose", ManuallySortedPins="true")

        translation_cp = etree.SubElement(
            repeat,
            "ControlPoint",
            Id=new_vl_id(),
            Bounds=_format_bounds(repeat_x + 50, y + 6),
            Alignment="Top",
        )
        index_cp = etree.SubElement(
            repeat_patch,
            "ControlPoint",
            Id=new_vl_id(),
            Bounds=_format_bounds(repeat_x + 24, y + 122),
        )

        transform = operation_node(
            repeat_patch,
            px=repeat_x + 82,
            py=y + 82,
            width=90,
            category="3D.Transform",
            name="TransformSRT",
        )
        pin(transform, "Input", "InputPin")
        transform_scaling = pin(transform, "Scaling", "InputPin")
        pin(transform, "Rotation", "InputPin")
        transform_translation = pin(transform, "Translation", "InputPin")
        transform_output = pin(transform, "Output", "OutputPin")

        # vvvv's saved Cache/Repeat pattern feeds a Vector2 spread through the
        # top portal and selects an item inside Repeat. Linking that spread
        # directly to TransformSRT.Translation looks structurally valid in XML
        # but leaves the graph with an incompatible type/iteration dimension.
        xyz = operation_node(
            repeat_patch,
            px=repeat_x + 35,
            py=y + 36,
            width=45,
            category="2D.Vector2",
            name="XyZ",
        )
        xyz_input = pin(xyz, "Input", "StateInputPin")
        xyz_y = pin(xyz, "Y", "InputPin")
        xyz_output = pin(xyz, "Output", "StateOutputPin")

        set_item = operation_node(
            repeat_patch,
            px=repeat_x + 82,
            py=y + 178,
            width=84,
            height=26,
            category="Collections.Mutable.MutableArray",
            name="SetItem",
        )
        set_input = pin(set_item, "Input", "StateInputPin")
        set_index = pin(set_item, "Index", "InputPin")
        set_value = pin(set_item, "Value", "InputPin")
        pin(set_item, "Output", "StateOutputPin")

        memory = operation_node(
            canvas,
            px=x + 5,
            py=y + 285,
            width=125,
            category="System.MemoryUtils",
            name="AsReadOnlyMemory",
        )
        memory_reference = memory.find(f"{{{PROPERTY_NS}}}NodeReference")
        if memory_reference is not None:
            memory_reference.set("OverloadStrategy", "AllPinsThatAreNotCommon")
            etree.SubElement(memory_reference, "CategoryReference", Kind="ClassType", Name="MemoryUtils", NeedsToBeDirectParent="true")
            for kind, name, category, type_name in (
                ("InputPin", "Input", "Collections.Mutable", "MutableArray"),
                ("OutputPin", "Result", "System", "ReadOnlyMemory"),
            ):
                pin_reference = etree.SubElement(memory_reference, "PinReference", Kind=kind, Name=name)
                data_type = etree.SubElement(
                    pin_reference,
                    f"{{{PROPERTY_NS}}}DataTypeReference",
                    {f"{{{PROPERTY_NS}}}Type": "TypeReference"},
                    LastCategoryFullName=category,
                    LastDependency="VL.CoreLib.vl",
                )
                etree.SubElement(data_type, "Choice", Kind="TypeFlag", Name=type_name)
                etree.SubElement(etree.SubElement(data_type, f"{{{PROPERTY_NS}}}TypeArguments"), "TypeParameterReference")
        memory_input = pin(memory, "Input", "InputPin")
        memory_result = pin(memory, "Result", "OutputPin")

        # Region-crossing links live in the owning Application Patch, exactly
        # like vvvv's own serializer; ControlPoints relay across the boundary.
        self._refresh()
        self.graph.add_link(count_pad.get("Id", ""), cache_top.get("Id", ""), patch=outer_patch)
        self.graph.add_link(cache_top.get("Id", ""), create_length, patch=outer_patch)
        self.graph.add_link(create_result, cache_bottom.get("Id", ""), patch=outer_patch)
        self.graph.add_link(cache_bottom.get("Id", ""), set_input, patch=outer_patch)
        self.graph.add_link(cache_bottom.get("Id", ""), memory_input, patch=outer_patch)
        self.graph.add_link(count_pad.get("Id", ""), repeat_count, patch=outer_patch)
        self.graph.add_link(update_index, index_cp.get("Id", ""), patch=outer_patch, IsHidden="true")
        self.graph.add_link(index_cp.get("Id", ""), set_index, patch=outer_patch)
        self.graph.add_link(translation_cp.get("Id", ""), xyz_input, patch=outer_patch)
        self.graph.add_link(xyz_output, transform_translation, patch=outer_patch)
        self.graph.add_link(transform_output, set_value, patch=outer_patch)
        self._refresh()

        return MatrixRepeatBuilder(
            count_pad=count_pad.get("Id", ""),
            translation_input=translation_cp.get("Id", ""),
            height_input=xyz_y,
            scaling_input=transform_scaling,
            index_output=index_cp.get("Id", ""),
            result_output=memory_result,
            cache_region=cache.get("Id", ""),
            repeat_region=repeat.get("Id", ""),
        )

    def remove_slot(self, existing_slot: str | SlotBuilder, *, accessor_ids: Iterable[str] = ()) -> dict:
        """Remove a Slot only after explicitly naming every remaining accessor.

        Defaults to removing an unused field. For a dedicated state channel,
        supply its exact accessor IDs; all those Pads and incident links are
        removed together. A missing, extra, foreign, or non-Pad accessor rejects
        the request before mutation, protecting shared Slots from partial removal.
        """
        identifier = existing_slot.slot_id if isinstance(existing_slot, SlotBuilder) else self._resolve_entity_id(existing_slot)
        slot = self.graph.element(identifier)
        owner = slot.getparent()
        if slot.tag != "Slot" or owner is None or owner.tag != "Patch":
            raise ValueError("remove_slot requires an existing Slot in a Patch")
        supplied = [self._resolve_entity_id(value) for value in accessor_ids]
        if len(supplied) != len(set(supplied)):
            raise ValueError("Slot accessor IDs must be unique")
        accessors = [element for element in self.document.root.iter()
                     if element.get("SlotId") == identifier]
        actual = {element.get("Id") for element in accessors}
        if any(element.tag != "Pad" or self.graph._definition_scope(element) is not self.graph._definition_scope(slot)
               for element in accessors):
            raise ValueError("Slot has invalid or foreign accessors")
        if set(supplied) != actual:
            raise ValueError("explicit accessor_ids must name every remaining Slot accessor exactly")
        removed_links = [link.get("Id") for link in self.graph.links
                         if actual.intersection(self.graph.link_hub_ids(link) or ())]
        self._before_mutation()
        def preserve_closing_whitespace(element):
            # The last child owns the whitespace before its parent's closing
            # tag. Carry it to the surviving sibling when deleting that child.
            if element.getnext() is None:
                previous = element.getprevious()
                if previous is not None:
                    previous.tail = element.tail
                else:
                    element.getparent().text = element.tail
        for link_id in removed_links:
            preserve_closing_whitespace(self.graph.element(link_id))
            self.graph.remove_link(link_id)
        for element in accessors:
            preserve_closing_whitespace(element)
            self.graph.remove_pad(element.get("Id"))
            self._entity_aliases.pop(element.get("Id"), None)
        preserve_closing_whitespace(slot)
        owner.remove(slot)
        self._entity_aliases.pop(identifier, None)
        self._refresh()
        return {"slot": identifier, "accessors": supplied, "links": removed_links}

    def remove(self, alias_or_id: str) -> None:
        identifier = self._resolve_entity_id(alias_or_id)
        self._before_mutation()
        element = self.graph.element(identifier)
        if etree.QName(element).localname == "Node":
            self.graph.remove_node(identifier)
            self._aliases.pop(identifier, None)
        elif etree.QName(element).localname == "Pad":
            self.graph.remove_pad(identifier)
            self._entity_aliases.pop(identifier, None)
        elif etree.QName(element).localname == "Overlay":
            parent = element.getparent()
            if parent is None:
                raise ValueError("annotation is detached")
            parent.remove(element)
            self._entity_aliases.pop(identifier, None)
            self._refresh()
        elif etree.QName(element).localname == "ControlPoint":
            for link in list(self.graph.links):
                if identifier in (self.graph.link_hub_ids(link) or ()):
                    self.graph.remove_link(link.get("Id", ""))
            parent = element.getparent()
            if parent is None:
                raise ValueError("ControlPoint is detached")
            parent.remove(element)
            self._entity_aliases.pop(identifier, None)
            self._refresh()
        else:
            raise ValueError("remove supports nodes, pads, regions, and ControlPoints")

    @staticmethod
    def _require_process_name(name: str) -> None:
        if not name or not name[0].isupper() or not name.isalnum():
            raise ValueError("custom Process name must be PascalCase without spaces or punctuation")

    def rename_local_process(self, alias_or_id: str, name: str, *, document_name: str | None = None) -> dict:
        """Rename a local Process definition and its local call selectors together.

        Preserves IDs, pins, links, values and geometry. Imported library calls
        with the same spelling are not renamed. Does not rename CLR metadata.
        """
        self._require_process_name(name)
        definition = self.node(alias_or_id)
        reference = definition.find(f"{{{PROPERTY_NS}}}NodeReference")
        choice = reference.find("Choice[@Kind='ContainerDefinition']") if reference is not None else None
        if choice is None or choice.get("Name") != "Process" or definition.get("Name") == "Application":
            raise ValueError("rename_local_process requires a non-Application Process definition")
        old = definition.get("Name")
        siblings = definition.getparent()
        if any(n is not definition and n.get("Name") == name for n in siblings.findall("Node")):
            raise ValueError(f"local definition already exists: {name}")
        category = siblings.get("DefaultCategory", "Main")
        filename = document_name or (self.document.source_path.name if self.document.source_path else "")
        calls = []
        for node in self.graph.nodes:
            ref = node.find(f"{{{PROPERTY_NS}}}NodeReference")
            if ref is None or ref.get("LastCategoryFullName", category) != category:
                continue
            if ref.get("LastDependency", "") not in {"", filename}:
                continue
            for call in ref.findall("Choice"):
                if call.get("Kind") not in {"ProcessNode", "ProcessAppFlag"}:
                    continue
                if call.get("Name") == old:
                    calls.append((node, call))
        self._before_mutation()
        definition.set("Name", name)
        for node, call in calls:
            call.set("Name", name)
            if node.get("Name") == old:
                node.set("Name", name)
        self._refresh()
        return {"definition": definition.get("Id"), "old_name": old, "name": name,
                "calls": [node.get("Id") for node, _ in calls]}

    def order_group_inputs_by_x(self, alias_or_id: str, *, independent_peers: bool = False) -> dict:
        """Rewire a peer renderer Group in source-X order, with stable ties.

        Explicit opt-in is required: sequential renderer Groups use input order
        as execution order, so this is unsafe for producer/consumer stages. Preserve pin
        order/IDs, link IDs, intermediate hubs, widths and all source membership.
        """
        if not independent_peers:
            raise ValueError("confirm independent_peers before changing Group execution order")
        node = self.node(alias_or_id)
        if self.graph.node_name(node) != "Group":
            raise ValueError("expected a renderer Group")
        ref = node.find(f"{{{PROPERTY_NS}}}NodeReference")
        if ref is None or ref.get("LastCategoryFullName") != "Stride.DX12Bridge.Rendering":
            raise ValueError("expected the verified DX12 renderer Group")
        pins = [p for p in node.findall("Pin") if p.get("Kind") == "InputPin"
                and (p.get("Name") == "Input" or (p.get("Name", "").startswith("Input")
                     and p.get("Name", "").removeprefix("Input").strip().isdigit()))]
        incoming = {p.get("Id"): [] for p in pins}
        for link in self.graph.links:
            hubs = [value.strip() for value in link.get("Ids", "").split(",")]
            if len(hubs) >= 2 and hubs[-1] in incoming and link.get("IsHidden", "false").lower() != "true":
                incoming[hubs[-1]].append((link, hubs))
        if any(len(items) > 1 for items in incoming.values()):
            raise ValueError("Group pin has multiple incoming links")
        connected = [p for p in pins if incoming[p.get("Id")]]
        rows = [incoming[p.get("Id")][0] for p in connected]
        ordered = sorted(enumerate(rows), key=lambda item: (
            self._endpoint_anchor(item[1][1][0], as_source=True)[0], item[0]))
        updates = [(link, hubs[:-1] + [pin.get("Id")])
                   for pin, (_, (link, hubs)) in zip(connected, ordered)]
        changed = sum(link.get("Ids") != ",".join(hubs) for link, hubs in updates)
        if changed:
            self._before_mutation()
            for link, hubs in updates:
                link.set("Ids", ",".join(hubs))
            self._refresh()
        return {"group": node.get("Id"), "changed_links": changed,
                "sources": [hubs[0] for _, hubs in updates]}

    def set_node_reference(
        self, alias_or_id: str, reference: etree._Element, *,
        pin_renames: dict[str, str] | None = None,
    ) -> None:
        """Bind a node to a verified saved reference without replacing its graph.

        Use a reference from an actual library/working patch, including category
        and overload selectors. LastCategoryFullName alone is only an editor
        hint. Node/pin IDs, links, defaults and user canvas geometry survive.
        Renames are explicit because real operation outputs may differ.
        """
        node = self.node(alias_or_id)
        if reference.tag != f"{{{PROPERTY_NS}}}NodeReference" or reference.find("Choice") is None:
            raise ValueError("expected a verified NodeReference with operation choices")
        renames = pin_renames or {}
        pins = node.findall("Pin")
        names = {p.get("Name") for p in pins}
        if set(renames) - names:
            raise ValueError("pin rename refers to a missing pin")
        final_names = [renames.get(p.get("Name"), p.get("Name")) for p in pins]
        if len(final_names) != len(set(final_names)):
            raise ValueError("pin rename would create duplicate names")
        old = node.find(f"{{{PROPERTY_NS}}}NodeReference")
        if old is None:
            raise ValueError("node has no operation reference")
        self._before_mutation()
        node.replace(old, deepcopy(reference))
        for pin in pins:
            if pin.get("Name") in renames:
                pin.set("Name", renames[pin.get("Name")])
        self._refresh()

    def set_pin_default(self, alias_or_id: str, pin_name: str, value: str) -> None:
        pin_id = self._resolve_pin_id(alias_or_id, pin_name, input_only=True)
        self._before_mutation()
        pin = self.graph.element(pin_id)
        pin.set("DefaultValue", value)

    def set_pad_value(self, alias_or_id: str, value: str) -> None:
        """Set an existing IO box value without replacing its ID or links."""

        identifier = self._resolve_entity_id(alias_or_id)
        self._before_mutation()
        self.graph.set_pad_value(identifier, value)

    def move(self, alias_or_id: str, x: float, y: float) -> None:
        self._before_mutation()
        self.graph.move(self._resolve_entity_id(alias_or_id), x, y)

    def set_placement_position(self, alias_or_id: str, x: float, y: float) -> None:
        """Set canonical position-only Bounds on a ControlPoint or Slot Pad.

        This explicit repair also removes accidentally invented dimensions.
        It cannot resize ordinary IOBoxes or nodes, and preserves every other
        attribute, child property, shared signature/Slot identity and link.
        """
        element = self.graph.element(self._resolve_entity_id(alias_or_id))
        if element.tag == "Pad":
            slot = self.graph.by_id.get(element.get("SlotId"))
            if slot is None or slot.tag != "Slot":
                raise ValueError("placement Pad must reference an existing Slot")
        elif element.tag != "ControlPoint":
            raise ValueError("placement position requires a ControlPoint or Slot Pad")
        bounds = _format_bounds(float(x), float(y))
        self._before_mutation()
        element.set("Bounds", bounds)

    def set_bounds(
        self,
        alias_or_id: str,
        *,
        x: float | None = None,
        y: float | None = None,
        width: float | None = None,
        height: float | None = None,
    ) -> None:
        """Set canvas geometry without discarding unspecified dimensions."""

        identifier = self._resolve_entity_id(alias_or_id)
        element = self.graph.element(identifier)
        bounds = _parse_bounds(element.get("Bounds")) or ["0", "0", "100", "19"]
        position_only = len(bounds) == 2 and element.tag in {"Pad", "ControlPoint"} and width is None and height is None
        if not position_only:
            while len(bounds) < 4:
                bounds.append("19" if len(bounds) == 3 else "100")
        self._before_mutation()
        for index, value in enumerate((x, y, width, height)):
            if value is not None:
                bounds[index] = _format_number(float(value))
        element.set("Bounds", _format_bounds(*bounds))

    # vvvv draws an Overlay's Name label inside its own top edge. A region
    # fitted with a uniform padding on all four sides leaves the label sitting
    # directly on top of the first row of nodes/IOBoxes inside it. Measured
    # from the owner's hand fixes to three generated regions in "HowTo
    # Procedural Mesh and SDF.vl" (2026-09): the top edge moved up 40-46px
    # beyond the side/bottom padding (46px and 56px of total top clearance
    # against a 16px side/bottom padding), while the bottom edge never moved.
    _REGION_TITLE_BAND = 50.0

    def fit_region(
        self,
        region: str,
        targets: Iterable[str],
        *,
        padding: float = 24,
        top_padding: float | None = None,
    ) -> None:
        """Fit an Overlay around related nodes/pads and keep it behind them.

        ``padding`` applies to the left, right and bottom edges. The top edge
        additionally reserves a title band (``top_padding``, defaulting to
        :attr:`_REGION_TITLE_BAND`) so the region's Name label does not
        overlap the first node or IOBox inside it.
        """

        region_id = self._resolve_entity_id(region)
        element = self.graph.element(region_id)
        if etree.QName(element).localname != "Overlay":
            raise ValueError("fit_region expects an Overlay annotation")
        target_ids = [self._resolve_entity_id(target) for target in targets]
        bounds = self.graph._bounds_union(target_ids)
        if bounds is None:
            raise ValueError("fit_region needs at least one bounded target")
        x, y, width, height = bounds
        if top_padding is None:
            top_padding = max(padding, self._REGION_TITLE_BAND)
        self.set_bounds(
            region_id,
            x=x - padding,
            y=y - top_padding,
            width=width + padding * 2,
            height=height + top_padding + padding,
        )
        parent = element.getparent()
        if parent is not None and parent.index(element) != 0:
            self._before_mutation()
            parent.remove(element)
            parent.insert(0, element)

    def align_link(
        self,
        source: str,
        target: str,
        *,
        move: str = "source",
        y: float | None = None,
    ) -> None:
        """Align one endpoint owner so an output falls vertically into an input.

        ``source`` and ``target`` use the same ``alias.pin`` syntax as
        :meth:`connect`. This is the pin-aware primitive for hand-authored help
        layouts; node centres are insufficient when a wide Group has many
        collection inputs.
        """

        source_id = self._endpoint_ref(source, input_only=False)
        target_id = self._endpoint_ref(target, input_only=True)
        source_owner = self.graph.endpoint_owner.get(source_id)
        target_owner = self.graph.endpoint_owner.get(target_id)
        if source_owner is None or target_owner is None:
            raise KeyError("link endpoint has no canvas owner")
        source_anchor = self._endpoint_anchor(source_id, as_source=True)
        target_anchor = self._endpoint_anchor(target_id, as_source=False)
        owner = source_owner if move == "source" else target_owner if move == "target" else None
        rectangle = self._element_rectangle(owner) if owner is not None else None
        if source_anchor is None or target_anchor is None or rectangle is None or owner is None:
            raise ValueError("align_link requires bounded source and target elements")
        # Connector body bounds are centered around the stored position.
        # Move the model coordinates, not the rectangle's offset top-left.
        stored_bounds = _parse_bounds(owner.get("Bounds"))
        x, current_y = float(stored_bounds[0]), float(stored_bounds[1])
        delta = target_anchor[0] - source_anchor[0]
        aligned_x = x + delta if move == "source" else x - delta
        self.set_bounds(owner.get("Id", ""), x=aligned_x, y=y if y is not None else current_y)

    def layout_value_pads(
        self,
        *,
        vertical_gap: float = 38,
        targets: Iterable[str] | None = None,
        force: bool = False,
    ) -> None:
        """Place only new (or explicitly selected) connected value IOBoxes.

        Existing IOBox positions are human-authored geometry and remain fixed.
        ``force=True`` is the explicit destructive/full-layout escape hatch.
        """

        self._before_mutation()
        if force:
            pad_ids = None
        elif targets is not None:
            pad_ids = {self._resolve_entity_id(target) for target in targets}
        else:
            pad_ids = {
                pad.get("Id", "")
                for pad in self._connected_value_pads()
                if pad.get("Id", "") not in self._layout_baseline_ids
            }
        self._place_connected_value_pads(vertical_gap=vertical_gap, pad_ids=pad_ids)

    def normalize_node_sizes(self) -> None:
        """Expand nodes to fit their title and visible top/bottom pin rails."""

        self._before_mutation()
        for node in self.graph.operational_nodes():
            bounds = _parse_bounds(node.get("Bounds")) or ["0", "0", "100", "19"]
            while len(bounds) < 4:
                bounds.append("19" if len(bounds) == 3 else "100")
            bounds[2] = _format_number(self._element_size(node)[0])
            node.set("Bounds", _format_bounds(*bounds))

    def align(self, aliases: Iterable[str], *, axis: str = "y", value: float | None = None) -> None:
        identifiers = [self._resolve_entity_id(alias) for alias in aliases]
        if not identifiers:
            return
        self._before_mutation()
        positions: list[float] = []
        for identifier in identifiers:
            bounds = _parse_bounds(self.graph.element(identifier).get("Bounds"))
            if bounds is None:
                continue
            positions.append(float(bounds[1 if axis == "y" else 0]))
        target = value if value is not None else (sum(positions) / len(positions) if positions else 0)
        for identifier in identifiers:
            bounds = _parse_bounds(self.graph.element(identifier).get("Bounds"))
            if bounds is None:
                continue
            if axis == "y":
                bounds[1] = _format_number(target)
            elif axis == "x":
                bounds[0] = _format_number(target)
            else:
                raise ValueError("axis must be 'x' or 'y'")
            self.graph.element(identifier).set("Bounds", _format_bounds(*bounds))

    def distribute(self, aliases: Iterable[str], *, axis: str = "x", gap: float = 20) -> None:
        identifiers = [self._resolve_entity_id(alias) for alias in aliases]
        if len(identifiers) < 2:
            return
        self._before_mutation()
        indexed = []
        for identifier in identifiers:
            element = self.graph.element(identifier)
            bounds = _parse_bounds(element.get("Bounds"))
            if bounds is not None:
                indexed.append((float(bounds[0 if axis == "x" else 1]), identifier, bounds))
        indexed.sort()
        cursor = indexed[0][0]
        for _, _, bounds in indexed:
            if axis == "x":
                bounds[0] = _format_number(cursor)
                cursor += float(bounds[2]) + gap
            elif axis == "y":
                bounds[1] = _format_number(cursor)
                cursor += float(bounds[3]) + gap
            else:
                raise ValueError("axis must be 'x' or 'y'")
        for _, identifier, bounds in indexed:
            self.graph.element(identifier).set("Bounds", _format_bounds(*bounds))

    def translate_group(self, targets: Iterable[str], *, dx: float = 0, dy: float = 0) -> None:
        """Move a hand-arranged group rigidly, preserving all relative geometry."""

        identifiers = [self._resolve_entity_id(target) for target in targets]
        if not identifiers or (dx == 0 and dy == 0):
            return
        self._before_mutation()
        for identifier in identifiers:
            element = self.graph.element(identifier)
            rectangle = self._element_rectangle(element)
            if rectangle is None:
                continue
            self._set_element_position(element, rectangle[0] + dx, rectangle[1] + dy)

    def move_subgraph(
        self,
        element_ids: Iterable[str],
        destination_canvas: etree._Element,
        *,
        dx: float = 0,
        dy: float = 0,
    ) -> None:
        """Reparent an exact closed canvas selection without replacing IDs.

        Disconnect crossing links explicitly first, then rewire through the
        new Process portals. Internal links move to the destination's owning
        Patch; region-internal XML and all relative geometry remain intact.
        """
        if destination_canvas.tag != "Canvas" or destination_canvas.getparent() is None:
            raise ValueError("destination must be an attached Canvas")
        if destination_canvas.getroottree().getroot() is not self.document.root:
            raise ValueError("destination belongs to another document")
        elements = [self.graph.element(self._resolve_entity_id(value)) for value in element_ids]
        elements = list(dict.fromkeys(elements))
        if not elements:
            return
        source = elements[0].getparent()
        if source is None or source.tag != "Canvas":
            raise ValueError("selection must contain direct canvas elements")
        selected: set[str] = set()
        for element in elements:
            if element.getparent() is not source or element.tag not in {"Node", "Pad", "ControlPoint", "Overlay"}:
                raise ValueError("selection must contain direct elements of one canvas")
            if destination_canvas is element or destination_canvas in element.iterdescendants():
                raise ValueError("cannot move a region into itself")
            selected.update(item.get("Id") for item in element.iter() if item.get("Id"))
        internal_links = []
        for link in self.graph.links:
            hubs = self.graph.link_hub_ids(link) or ()
            included = [hub in selected for hub in hubs]
            if any(included) and not all(included):
                raise ValueError("selection has crossing links; disconnect them before moving")
            if included and all(included) and not any(parent in elements for parent in link.iterancestors()):
                internal_links.append(link)
        destination_patch = destination_canvas.getparent()
        if destination_patch.tag != "Patch":
            raise ValueError("destination Canvas must have an owning Patch")
        self._before_mutation()
        for element in elements:
            bounds = _parse_bounds(element.get("Bounds"))
            if bounds is not None and len(bounds) >= 2:
                bounds[0] = _format_number(float(bounds[0]) + dx)
                bounds[1] = _format_number(float(bounds[1]) + dy)
                element.set("Bounds", ",".join(bounds))
            destination_canvas.append(element)
        for link in internal_links:
            destination_patch.append(link)
        self._refresh()

    def layout_intent(
        self,
        targets: Iterable[str] | None = None,
        *,
        force: bool = False,
    ) -> dict[str, object]:
        """Describe what an automatic layout would move before it moves it."""

        all_nodes = {
            node.get("Id", "")
            for node in self.graph.operational_nodes()
            if node.get("Id")
        }
        if force:
            movable = set(all_nodes)
        elif targets is not None:
            movable = {self._resolve_node_id(target) for target in targets}
        else:
            movable = all_nodes - self._layout_baseline_ids
        protected = all_nodes - movable
        adjacency = self.graph.connected_node_adjacency()
        remaining = set(movable)
        components: list[list[str]] = []
        while remaining:
            seed = min(remaining, key=self._node_position_key)
            stack = [seed]
            component: set[str] = set()
            while stack:
                identifier = stack.pop()
                if identifier not in remaining:
                    continue
                remaining.remove(identifier)
                component.add(identifier)
                stack.extend(adjacency.get(identifier, set()) & remaining)
            components.append([self.alias_for(item) for item in sorted(component, key=self._node_position_key)])
        return {
            "mode": "full" if force else "incremental",
            "movable": [self.alias_for(item) for item in sorted(movable, key=self._node_position_key)],
            "protected": [self.alias_for(item) for item in sorted(protected, key=self._node_position_key)],
            "components": components,
            "baseline_is_preserved": not force,
        }

    def layout(
        self,
        *,
        targets: Iterable[str] | None = None,
        force: bool = False,
        start_x: float = 60,
        start_y: float = 180,
        column_gap: float = 54,
        row_gap: float = 64,
        sweeps: int = 8,
    ) -> None:
        """Lay out new/selected nodes as dense, top-to-bottom vvvv dataflow.

        Nodes use longest-path ranks and barycentric crossing reduction. Value
        pads are placed above their exact target pins. Variable-input
        aggregators are widened so fan-in links remain individually readable.

        By default, geometry present when this session opened is immutable.
        This preserves human layout across repeated editor/agent cycles. Pass
        exact ``targets`` to reflow a deliberate neighborhood, or ``force`` to
        request a whole-patch layout explicitly.
        """

        outgoing, incoming = self.graph.directed_node_adjacency(include_feedback=False)
        nodes = [node for node in self.graph.operational_nodes() if node.get("Id")]
        all_node_by_id = {node.get("Id", ""): node for node in nodes}
        intent = self.layout_intent(targets, force=force)
        movable_aliases = set(intent["movable"])
        node_by_id = {
            identifier: node
            for identifier, node in all_node_by_id.items()
            if self.alias_for(identifier) in movable_aliases
        }
        node_ids = set(node_by_id)
        if not node_ids:
            return
        self._before_mutation()

        indegree = {identifier: len(incoming.get(identifier, set()) & node_ids) for identifier in node_ids}
        ready = deque(sorted((identifier for identifier, degree in indegree.items() if degree == 0), key=self._node_position_key))
        topo: list[str] = []
        while ready:
            identifier = ready.popleft()
            topo.append(identifier)
            for child in sorted(outgoing.get(identifier, set()) & node_ids, key=self._node_position_key):
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
        topo.extend(sorted(node_ids - set(topo), key=self._node_position_key))

        depths: dict[str, int] = {}
        for identifier in topo:
            parents = incoming.get(identifier, set()) & node_ids
            depths[identifier] = max((depths.get(parent, 0) + 1 for parent in parents), default=0)

        rows: dict[int, list[str]] = defaultdict(list)
        original_x: dict[str, float] = {}
        for identifier, node in node_by_id.items():
            bounds = _parse_bounds(node.get("Bounds")) or ["0", "0", "100", "19"]
            original_x[identifier] = float(bounds[0])
            rows[depths[identifier]].append(identifier)
        for row in rows.values():
            row.sort(key=lambda identifier: (original_x[identifier], self._node_position_key(identifier)))

        def neighbor_position(identifier: str, neighbors: set[str], positions: dict[str, float]) -> float:
            values = [positions[item] for item in neighbors if item in positions]
            return sum(values) / len(values) if values else positions.get(identifier, original_x[identifier])

        max_depth = max(rows, default=0)
        for _ in range(max(0, sweeps)):
            positions = {identifier: float(index) for row in rows.values() for index, identifier in enumerate(row)}
            for depth in range(1, max_depth + 1):
                rows[depth].sort(
                    key=lambda identifier: (
                        neighbor_position(identifier, incoming.get(identifier, set()) & node_ids, positions),
                        original_x[identifier],
                    )
                )
                positions.update({identifier: float(index) for index, identifier in enumerate(rows[depth])})
            for depth in range(max_depth - 1, -1, -1):
                rows[depth].sort(
                    key=lambda identifier: (
                        neighbor_position(identifier, outgoing.get(identifier, set()) & node_ids, positions),
                        original_x[identifier],
                    )
                )
                positions.update({identifier: float(index) for index, identifier in enumerate(rows[depth])})

        for node in node_by_id.values():
            bounds = _parse_bounds(node.get("Bounds")) or ["0", "0", "100", "19"]
            bounds[2] = _format_number(self._element_size(node)[0])
            node.set("Bounds", _format_bounds(*bounds))

        row_widths = {
            depth: sum(self._element_size(node_by_id[item])[0] for item in row) + column_gap * max(0, len(row) - 1)
            for depth, row in rows.items()
        }
        canvas_width = max(row_widths.values(), default=0)

        # Anchor the new island near its already-arranged neighbours while
        # leaving every existing node untouched. Endpoint anchors, not node
        # centres, are the meaningful geometry in vvvv.
        boundary_x: list[float] = []
        incoming_boundary_y: list[float] = []
        outgoing_boundary_y: list[float] = []
        for link in self.graph.links:
            endpoints = self.graph.link_endpoints(link)
            if endpoints is None:
                continue
            source_owner = self.graph.endpoint_owner.get(endpoints[0])
            target_owner = self.graph.endpoint_owner.get(endpoints[1])
            if source_owner is None or target_owner is None:
                continue
            source_id = source_owner.get("Id", "")
            target_id = target_owner.get("Id", "")
            if source_id in node_ids and target_id not in node_ids:
                anchor = self._endpoint_anchor(endpoints[1])
                if anchor is not None:
                    boundary_x.append(anchor[0])
                    outgoing_boundary_y.append(anchor[1])
            elif source_id not in node_ids and target_id in node_ids:
                anchor = self._endpoint_anchor(endpoints[0])
                if anchor is not None:
                    boundary_x.append(anchor[0])
                    incoming_boundary_y.append(anchor[1])

        total_height = sum(
            max(self._element_size(node_by_id[item])[1] for item in rows.get(depth, [])) + row_gap
            for depth in range(max_depth + 1)
            if rows.get(depth)
        ) - row_gap
        if boundary_x:
            start_x = sum(boundary_x) / len(boundary_x) - canvas_width * 0.5
        if incoming_boundary_y:
            start_y = max(incoming_boundary_y) + row_gap
        elif outgoing_boundary_y:
            start_y = min(outgoing_boundary_y) - row_gap - total_height

        y = start_y
        for depth in range(max_depth + 1):
            row = rows.get(depth, [])
            if not row:
                continue
            cursor = start_x + (canvas_width - row_widths[depth]) * 0.5
            row_height = max(self._element_size(node_by_id[item])[1] for item in row)
            for identifier in row:
                node = node_by_id[identifier]
                width, _ = self._element_size(node)
                self._set_element_position(node, cursor, y)
                cursor += width + column_gap
            y += row_height + row_gap

        new_pad_ids = {
            pad.get("Id", "")
            for pad in self._connected_value_pads()
            if force or pad.get("Id", "") not in self._layout_baseline_ids
        }
        self._place_connected_value_pads(
            vertical_gap=max(36.0, row_gap * 0.58),
            pad_ids=new_pad_ids,
        )

    def _canvas_scope(self, canvas: etree._Element | None) -> set[etree._Element] | None:
        """Select a canvas and executable regions without entering definitions."""
        if canvas is None:
            return None
        if canvas.tag != "Canvas" or canvas.getroottree().getroot() is not self.document.root:
            raise ValueError("canvas must be an attached Canvas in this document")
        selected: set[etree._Element] = set()
        pending = [canvas]
        while pending:
            element = pending.pop()
            if element.tag == "Node":
                reference = element.find(f"{{{PROPERTY_NS}}}NodeReference")
                if reference is not None and any(
                        choice.get("Kind", "").endswith("Definition") for choice in reference.findall("Choice")):
                    continue
            selected.add(element)
            pending.extend(element)
        return selected

    def _scope_nodes(self, scope: set[etree._Element] | None) -> list[etree._Element]:
        if scope is None:
            return self.graph.operational_nodes()
        nodes = []
        for node in self.graph.nodes:
            if node not in scope:
                continue
            reference = node.find(f"{{{PROPERTY_NS}}}NodeReference")
            if reference is not None and not any(
                    choice.get("Kind", "").endswith(("Definition", "Region")) for choice in reference.findall("Choice")):
                nodes.append(node)
        return nodes

    def _scope_links(self, scope: set[etree._Element] | None) -> list[etree._Element]:
        if scope is None:
            return self.graph.links
        return [link for link in self.graph.links
                if link.get("IsHidden", "false").lower() != "true"
                and (endpoints := self.graph.link_endpoints(link)) is not None
                and all(self.graph.by_id.get(identifier) in scope for identifier in endpoints)]

    def _data_hub_label(self, element: etree._Element) -> str:
        if element.tag == "Pad" and element.get("SlotId"):
            slot = self.graph.by_id.get(element.get("SlotId"))
            return slot.get("Name", "") if slot is not None else ""
        if element.tag == "ControlPoint":
            identifier = element.get("Id")
            for link in self.graph.links:
                endpoints = self.graph.link_endpoints(link)
                if link.get("IsHidden", "false").lower() != "true" or endpoints is None or identifier not in endpoints:
                    continue
                other = self.graph.by_id.get(endpoints[1] if endpoints[0] == identifier else endpoints[0])
                if other is not None and other.get("Name"):
                    return other.get("Name", "")
        return element.get("Name") or element.get("Comment") or ""

    def _data_hub_rectangle(self, element: etree._Element) -> tuple[float, float, float, float] | None:
        """Exact connector body plus an approximate font-sized label envelope."""
        rectangle = self._element_rectangle(element)
        if rectangle is None:
            return None
        label = self._data_hub_label(element)
        x, y, width, height = rectangle
        if label:
            # ControlPointView places its label at body-right + LabelOffset=2.
            # Text width/height are estimates; connector positions are exact.
            width += 2 + len(label) * 5.2
            y -= 2
            height += 4
        return x, y, width, height

    def layout_analysis(self, *, long_link: float = 520, canvas: etree._Element | None = None) -> dict[str, object]:
        """Measure visual errors, optionally for one canvas and its regions."""

        scope = self._canvas_scope(canvas)
        # One read-only snapshot per analysis. alias_for refreshes the entire
        # graph, so calling it for every crossing multiplies graph scans by
        # the number of crossing pairs. Never retain this across mutations.
        self._reindex_aliases()
        aliases = {**self._entity_aliases, **self._aliases}
        elements = [*self._scope_nodes(scope), *(pad for pad in self._connected_value_pads() if scope is None or pad in scope)]
        if scope is not None:
            elements.extend(element for element in self.document.root.iter("ControlPoint") if element in scope)
        rectangles: dict[str, tuple[float, float, float, float]] = {}
        for element in elements:
            identifier = element.get("Id")
            bounds = _parse_bounds(element.get("Bounds"))
            rectangle = self._data_hub_rectangle(element) if element.tag in {"Pad", "ControlPoint"} and bounds is not None and len(bounds) == 2 else self._element_rectangle(element)
            if identifier and rectangle is not None:
                rectangles[identifier] = rectangle

        overlaps: list[tuple[str, str]] = []
        identifiers = list(rectangles)
        for index, left_id in enumerate(identifiers):
            for right_id in identifiers[index + 1 :]:
                if self._rectangles_overlap(rectangles[left_id], rectangles[right_id]):
                    overlaps.append((aliases.get(left_id, left_id), aliases.get(right_id, right_id)))

        annotation_overlaps: list[tuple[str, str]] = []
        for annotation in self.graph.annotations():
            if scope is not None and annotation not in scope:
                continue
            if etree.QName(annotation).localname == "Overlay":
                continue
            annotation_id = annotation.get("Id", "")
            annotation_rectangle = self._element_rectangle(annotation)
            if annotation_rectangle is None:
                continue
            for element_id, rectangle in rectangles.items():
                if self._rectangles_overlap(annotation_rectangle, rectangle):
                    annotation_overlaps.append((aliases.get(annotation_id, annotation_id), aliases.get(element_id, element_id)))

        segments: list[tuple[str, str, str, str, tuple[float, float], tuple[float, float]]] = []
        segment_labels: list[tuple[str, str, str, str]] = []
        upward: list[tuple[str, str]] = []
        feedback_links: list[tuple[str, str, str, str]] = []
        region_feedback_count = 0
        long_links: list[tuple[str, str, float]] = []
        pin_offsets: list[tuple[str, str, float]] = []
        for link in self._scope_links(scope):
            endpoints = self.graph.link_endpoints(link)
            if endpoints is None:
                continue
            source, target = endpoints
            source_anchor = self._endpoint_anchor(source, as_source=True)
            target_anchor = self._endpoint_anchor(target, as_source=False)
            source_owner = self.graph.endpoint_owner.get(source)
            target_owner = self.graph.endpoint_owner.get(target)
            if source_anchor is None or target_anchor is None or source_owner is None or target_owner is None:
                continue
            source_id = source_owner.get("Id", source)
            target_id = target_owner.get("Id", target)
            segment = (source_id, target_id, source, target, source_anchor, target_anchor)
            label = self._link_label(segment, aliases=aliases)
            if self.graph.is_feedback(link):
                feedback_links.append(label)
            if self.graph.is_region_feedback(link):
                region_feedback_count += 1
                continue
            if target_anchor[1] <= source_anchor[1]:
                upward.append((aliases.get(source_id, source_id), aliases.get(target_id, target_id)))
            distance = ((target_anchor[0] - source_anchor[0]) ** 2 + (target_anchor[1] - source_anchor[1]) ** 2) ** 0.5
            if distance > long_link:
                long_links.append((aliases.get(source_id, source_id), aliases.get(target_id, target_id), round(distance, 1)))
            pin_offsets.append(
                (
                    self._endpoint_description(source, aliases=aliases),
                    self._endpoint_description(target, aliases=aliases),
                    round(target_anchor[0] - source_anchor[0], 1),
                )
            )
            segments.append(segment)
            segment_labels.append(label)

        crossing_links: list[tuple[tuple[str, str, str, str], tuple[str, str, str, str]]] = []
        for index, first in enumerate(segments):
            for second_index in range(index + 1, len(segments)):
                second = segments[second_index]
                # BLIND SPOT - DO NOT REMOVE (2026-10-05)
                # Distinct pins on one node can have crossing wires. Excluding
                # a shared owner hides crossed multi-input staircases; ignore
                # only a genuine shared endpoint/junction.
                if first[2] in second[2:4] or first[3] in second[2:4]:
                    continue
                if self._segments_cross(first[4], first[5], second[4], second[5]):
                    crossing_links.append((segment_labels[index], segment_labels[second_index]))
        return {
            "ok": not overlaps and not annotation_overlaps and not upward,
            "overlaps": overlaps,
            "annotation_overlaps": annotation_overlaps,
            "upward_links": upward,
            "feedback_links": feedback_links,
            "long_links": long_links,
            "crossings": len(crossing_links),
            "crossing_links": crossing_links,
            "vertical_links": sum(1 for _, _, offset in pin_offsets if abs(offset) <= 1.0),
            "misaligned_links": [item for item in pin_offsets if abs(item[2]) > 1.0],
            "element_count": len(rectangles),
            "link_count": len(segments) + region_feedback_count,
        }

    def _link_label(
        self,
        segment: tuple[str, str, str, str, tuple[float, float], tuple[float, float]],
        *,
        aliases: dict[str, str] | None = None,
    ) -> tuple[str, str, str, str]:
        source_owner, target_owner, source_endpoint, target_endpoint, _, _ = segment
        return (
            self.alias_for(source_owner) if aliases is None else aliases.get(source_owner, source_owner),
            self.graph.by_id[source_endpoint].get("Name", ""),
            self.alias_for(target_owner) if aliases is None else aliases.get(target_owner, target_owner),
            self.graph.by_id[target_endpoint].get("Name", ""),
        )

    def spatial_snapshot(self, *, columns: int = 96, rows: int = 32, canvas: etree._Element | None = None) -> dict[str, object]:
        """Return the whole-canvas map used by agent layout feedback."""

        from .spatial import spatial_snapshot

        return spatial_snapshot(self, columns=columns, rows=rows, canvas=canvas)

    def render_svg(self, path: str | Path, *, canvas: etree._Element | None = None) -> Path:
        """Write a geometry preview, optionally for one canvas and its regions."""

        from .spatial import render_svg

        return render_svg(self, path, canvas=canvas)

    def _node_position_key(self, identifier: str) -> tuple[float, str]:
        node = self.graph.by_id[identifier]
        bounds = _parse_bounds(node.get("Bounds")) or ["0", "0"]
        return float(bounds[0]), VlGraph.node_name(node)

    @staticmethod
    def _is_visible_input(pin: etree._Element) -> bool:
        return pin.get("Kind") in {"InputPin", "StateInputPin", "ApplyPin", "ControlPoint"} and pin.get("IsHidden", "false").lower() != "true"

    @staticmethod
    def _is_visible_output(pin: etree._Element) -> bool:
        return pin.get("Kind") in {"OutputPin", "StateOutputPin"} and pin.get("IsHidden", "false").lower() != "true"

    @classmethod
    def _element_size(cls, element: etree._Element) -> tuple[float, float]:
        bounds = _parse_bounds(element.get("Bounds")) or ["0", "0", "100", "19"]
        stored_width = float(bounds[2]) if len(bounds) > 2 else 100.0
        height = float(bounds[3]) if len(bounds) > 3 else 19.0
        if etree.QName(element).localname != "Node":
            return stored_width, height
        return max(stored_width, cls._intrinsic_node_width(element)), height

    @classmethod
    def _intrinsic_node_width(cls, element: etree._Element) -> float:
        """Estimate vvvv's compact width from title and visible pin rails.

        Human help patches routinely keep nodes denser than ordinary UI text
        metrics. Hidden pins consume no rail space. A stored wider Bounds value
        remains authoritative and represents an intentional manual stretch.

        Pin rail width is 5*P + 15*(P-1), with P the larger visible rail.
        A missing reflected pin can underestimate width even when the geometry
        formula is correct. Check the real pin list before changing constants.
        Title width is a font-metric approximation, not an editor measurement.
        """

        title_width = 12.0 + len(VlGraph.node_name(element)) * 5.2
        visible_inputs = sum(1 for pin in element.findall("Pin") if cls._is_visible_input(pin))
        visible_outputs = sum(1 for pin in element.findall("Pin") if cls._is_visible_output(pin))
        pin_count = max(visible_inputs, visible_outputs)
        # vvvv PinBarView: NodePinSize.Width == 5 and MinPinGap == 15.
        pin_width = 5.0 * pin_count + 15.0 * max(0, pin_count - 1)
        return max(25.0, title_width, pin_width)

    # IOBox (Pad) sizes vvvv itself saves, measured from vvvv-saved patches --
    # never from this generator's own output: "HowTo PathTrace Scene.vl",
    # "HowTo Render with DLSS Upscaling.vl", "HowTo Install Shader File
    # Icons.vl" (2026-09). Vector/Color/Boolean boxes are a FIXED size
    # regardless of the current value's text -- vvvv never grows them, so
    # sizing one to fit e.g. "-5, -0.35, -5" invents a size vvvv does not use.
    # Enum-like pads size to the WIDEST choice in their enum type, not to the
    # current value's text (EnvironmentMapPreset's current value is longer
    # than DLSSPreset's yet renders narrower), so they cannot be derived from
    # a text-length formula either -- they are looked up per type. Only the
    # enum types this generator actually emits are listed; an unlisted type
    # falls back to the scalar/text-growth estimate below.
    _FIXED_PAD_SIZES: dict[str, tuple[float, float]] = {
        "Boolean": (35.0, 35.0),
        "Vector2": (35.0, 28.0),
        "Vector3": (35.0, 43.0),
        "Vector4": (35.0, 57.0),
        "RGBA": (136.0, 15.0),
        "Color": (136.0, 15.0),
        "EnvironmentMapPreset": (116.0, 15.0),
        "ToneMapOperator": (71.0, 15.0),
        "MultisampleCount": (54.0, 15.0),
        "NormalDirection": (49.0, 15.0),
        "DLSSMode": (109.0, 15.0),
        "DLSSGMode": (52.0, 15.0),
        "DLSSPreset": (166.0, 15.0),
        "ReflexMode": (152.0, 15.0),
        "PixelFormat": (174.0, 15.0),
    }
    # Scalar numeric/string default. vvvv-saved Float32/Integer32 IOBoxes hold
    # this size up to about 4 characters ("0.33", "1.22", ...); text-growth
    # constants below are calibrated on real samples that DO grow: "100" (3
    # chars) -> 41px and "1000000" (7 chars) -> 61px.
    _DEFAULT_PAD_SIZE = (35.0, 15.0)
    _PAD_TEXT_GROWTH_THRESHOLD = 4
    _PAD_CHAR_GROWTH = 26.0 / 3.0  # px per character beyond the threshold

    @classmethod
    def _pad_size_for_value(cls, type_name: str | None, value: str | None) -> tuple[float, float]:
        """Estimate the IOBox size vvvv itself would save for this type/value.

        Used by :meth:`add_pad` so a generated IOBox starts at vvvv's own
        native size instead of a flat placeholder. See ``_FIXED_PAD_SIZES``
        and ``_DEFAULT_PAD_SIZE`` for where the constants come from.
        """

        if type_name:
            fixed = cls._FIXED_PAD_SIZES.get(type_name)
            if fixed is not None:
                return fixed
        base_width, base_height = cls._DEFAULT_PAD_SIZE
        text = value or ""
        extra_chars = len(text) - cls._PAD_TEXT_GROWTH_THRESHOLD
        if extra_chars <= 0:
            return base_width, base_height
        return base_width + extra_chars * cls._PAD_CHAR_GROWTH, base_height

    @staticmethod
    def _set_element_position(element: etree._Element, x: float, y: float) -> None:
        bounds = _parse_bounds(element.get("Bounds")) or ["0", "0", "100", "19"]
        if len(bounds) != 2 or element.tag not in {"Pad", "ControlPoint"}:
            while len(bounds) < 4:
                bounds.append("19" if len(bounds) == 3 else "100")
        bounds[0] = _format_number(x)
        bounds[1] = _format_number(y)
        element.set("Bounds", _format_bounds(*bounds))

    def _connected_value_pads(self) -> list[etree._Element]:
        annotations = {element.get("Id") for element in self.graph.annotations()}
        return [
            pad
            for pad in self.graph.pads
            if pad.get("Id") not in annotations and self.graph.outgoing.get(pad.get("Id", ""))
        ]

    def _place_connected_value_pads(
        self,
        *,
        vertical_gap: float,
        pad_ids: set[str] | None = None,
    ) -> None:
        node_rectangles = [
            rectangle
            for node in self.graph.operational_nodes()
            if (rectangle := self._element_rectangle(node)) is not None
        ]
        connected_pads = self._connected_value_pads()
        pads = [pad for pad in connected_pads if pad_ids is None or pad.get("Id", "") in pad_ids]
        active_ids = {pad.get("Id", "") for pad in pads}
        # Existing IOBoxes are obstacles, never collateral layout targets.
        placed = [
            rectangle
            for pad in connected_pads
            if pad.get("Id", "") not in active_ids
            if (rectangle := self._element_rectangle(pad)) is not None
        ]
        pads.sort(
            key=lambda pad: min(
                (anchor[1] for target in self.graph.outgoing.get(pad.get("Id", ""), set()) if (anchor := self._endpoint_anchor(target)) is not None),
                default=0,
            )
        )
        for pad in pads:
            targets = sorted(self.graph.outgoing.get(pad.get("Id", ""), set()))
            anchors = [self._endpoint_anchor(target) for target in targets]
            anchors = [anchor for anchor in anchors if anchor is not None]
            if not anchors:
                continue
            pad_width, pad_height = self._element_size(pad)
            # Pad Bounds.X is the connector position, not the left edge of a
            # centred value editor. PadView's connector anchor is X + 0.5.
            # Align that connector directly above the destination pin. When
            # wide editors collide, staircase them vertically; shifting them
            # sideways would reintroduce diagonal links.
            preferred_x = sum(anchor[0] for anchor in anchors) / len(anchors) - 0.5
            top = min(anchor[1] for anchor in anchors)
            preferred_y = top - vertical_gap - pad_height
            candidates: list[tuple[float, float]] = []
            for level in range(16):
                candidate_y = preferred_y - level * (pad_height + 8)
                candidates.append((preferred_x, candidate_y))
            selected = candidates[-1]
            for candidate in candidates:
                rectangle = (candidate[0], candidate[1], pad_width, pad_height)
                if not any(self._rectangles_overlap(rectangle, other) for other in (*node_rectangles, *placed)):
                    selected = candidate
                    break
            self._set_element_position(pad, selected[0], selected[1])
            placed.append((selected[0], selected[1], pad_width, pad_height))

    def _endpoint_anchor(self, endpoint_id: str, *, as_source: bool | None = None) -> tuple[float, float] | None:
        owner = self.graph.endpoint_owner.get(endpoint_id)
        if owner is None:
            return None
        if owner.tag in {"Pad", "ControlPoint"}:
            bounds = _parse_bounds(owner.get("Bounds"))
            if bounds is None or len(bounds) < 2:
                return None
            try:
                x, y = float(bounds[0]), float(bounds[1])
            except ValueError:
                return None
            # PadView/ControlPointView use PadOffset=(.5,-.5).
            # DataHubView.GetLinkAnchorPosition adds/subtracts half the 9px
            # body height. Explicit role handles bidirectional through hubs.
            is_source = bool(self.graph.outgoing.get(endpoint_id)) if as_source is None else as_source
            return x + 0.5, y + (4.0 if is_source else -5.0)
        rectangle = self._element_rectangle(owner)
        if rectangle is None:
            return None
        x, y, width, height = rectangle
        endpoint = self.graph.by_id.get(endpoint_id)
        if endpoint is None:
            return None
        # NodeView expands a stored node bound to ComputeNodeWidth when its
        # label or either visible pin bar needs more room. PinBarView then
        # stretches its pins over that effective width, not the stale stored
        # width from XML.
        width = max(width, self._intrinsic_node_width(owner))
        inputs = [pin for pin in owner.findall("Pin") if self._is_visible_input(pin)]
        outputs = [pin for pin in owner.findall("Pin") if self._is_visible_output(pin)]
        input_pin = self._is_visible_input(endpoint)
        pins = inputs if input_pin else outputs
        if endpoint not in pins or not pins:
            return x + 2.5, y + (0 if input_pin else height)
        index = pins.index(endpoint)
        # Exact PinBarView layout: one pin is left-aligned; two or more stretch
        # from the left edge to the right edge across the complete node width.
        if len(pins) == 1:
            pin_x = 0.0
        else:
            distance = (width - 5.0) / (len(pins) - 1)
            pin_x = round(index * distance)
        anchor_x = x + pin_x + 2.5
        return anchor_x, y + (0 if input_pin else height)

    @classmethod
    def _element_rectangle(cls, element: etree._Element) -> tuple[float, float, float, float] | None:
        bounds = _parse_bounds(element.get("Bounds"))
        if bounds is None:
            return None
        if len(bounds) == 2 and element.tag in {"Pad", "ControlPoint"}:
            try:
                x, y = (float(value) for value in bounds)
            except ValueError:
                return None
            return x - 4, y - 5, 9, 9
        if len(bounds) < 4:
            return None
        try:
            x, y, width, height = (float(value) for value in bounds[:4])
        except ValueError:
            return None
        if etree.QName(element).localname == "Node":
            width = max(width, cls._intrinsic_node_width(element))
        return x, y, width, height

    @staticmethod
    def _rectangles_overlap(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> bool:
        lx, ly, lw, lh = left
        rx, ry, rw, rh = right
        return lx < rx + rw and rx < lx + lw and ly < ry + rh and ry < ly + lh

    @staticmethod
    def _segments_cross(
        a: tuple[float, float],
        b: tuple[float, float],
        c: tuple[float, float],
        d: tuple[float, float],
    ) -> bool:
        def orientation(p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]) -> float:
            return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

        ab_c = orientation(a, b, c)
        ab_d = orientation(a, b, d)
        cd_a = orientation(c, d, a)
        cd_b = orientation(c, d, b)
        return ab_c * ab_d < 0 and cd_a * cd_b < 0

    def find_orphans(self) -> list[dict[str, str | None]]:
        return [{"alias": self.alias_for(node.get("Id", "")), "id": node.get("Id"), "operation": VlGraph.node_name(node)} for node in self.graph.orphan_operational_nodes()]

    def describe(self, *, level: str = "summary", focus: Iterable[str] | None = None) -> dict:
        """Return a compact exact description suitable for an agent prompt."""

        self._reindex_aliases()
        focus_ids = None
        if focus is not None:
            focus_ids = {self._resolve_node_id(item) for item in focus}
            neighbors = self.graph.connected_node_adjacency()
            expanded = set(focus_ids)
            for identifier in tuple(focus_ids):
                expanded.update(neighbors.get(identifier, set()))
            focus_ids = expanded
        nodes = []
        for node in sorted(self.graph.operational_nodes(), key=self._sort_key):
            identifier = node.get("Id", "")
            if focus_ids is not None and identifier not in focus_ids:
                continue
            reference = node.find("{property}NodeReference")
            pins = []
            for pin in node.findall("Pin"):
                if level == "summary" and pin.get("IsHidden", "false").lower() == "true":
                    continue
                pins.append({
                    "name": pin.get("Name", ""),
                    "dir": "in" if pin.get("Kind", "").endswith("InputPin") or pin.get("Kind") in {"ApplyPin", "ControlPoint"} else "out",
                    "kind": pin.get("Kind", ""),
                    "default": pin.get("DefaultValue"),
                    "hidden": pin.get("IsHidden", "false").lower() == "true",
                })
            nodes.append({
                "alias": self.alias_for(identifier),
                "id": identifier,
                "operation": VlGraph.node_name(node),
                "category": reference.get("LastCategoryFullName", "") if reference is not None else "",
                "bounds": node.get("Bounds"),
                "pins": pins,
            })
        links = []
        for link in self.graph.links:
            endpoints = self.graph.link_endpoints(link)
            if endpoints is None:
                continue
            source_owner = self.graph.node_id_for_endpoint(endpoints[0])
            target_owner = self.graph.node_id_for_endpoint(endpoints[1])
            if focus_ids is not None and source_owner not in focus_ids and target_owner not in focus_ids:
                continue
            links.append({
                "source": self._endpoint_description(endpoints[0]),
                "target": self._endpoint_description(endpoints[1]),
                "ids": endpoints,
            })
        pads = []
        for pad in self.graph.pads:
            pads.append({"id": pad.get("Id"), "comment": pad.get("Comment"), "value": pad.get("Value"), "bounds": pad.get("Bounds")})
        annotations = []
        for element in self.graph.annotations():
            annotations.append({
                "alias": self.alias_for(element.get("Id", "")),
                "id": element.get("Id"),
                "kind": self.graph.annotation_kind(element),
                "text": element.get("Value") if etree.QName(element).localname == "Pad" else element.get("Name"),
                "bounds": element.get("Bounds"),
                "style": self._annotation_font_size(element),
            })
        dependencies = [
            {"id": item.get("Id"), "location": item.get("Location"), "version": item.get("Version")}
            for item in self.document.root
            if isinstance(item.tag, str) and item.tag.endswith("Dependency")
        ]
        report = self.validate(include_orphan_warnings=True)
        return {
            "patch": self.document.source_path.stem if self.document.source_path else None,
            "document_id": self.document.root.get("Id"),
            "dependencies": dependencies,
            "nodes": nodes,
            "links": links,
            "pads": pads,
            "annotations": annotations,
            "orphans": self.find_orphans(),
            "diagnostics": [{"severity": item.severity, "code": item.code, "message": item.message, "id": item.element_id} for item in report.diagnostics],
        }

    @staticmethod
    def _annotation_font_size(element: etree._Element) -> str | None:
        if etree.QName(element).localname != "Pad":
            return None
        settings = element.find("{property}ValueBoxSettings")
        size = settings.find("{property}fontsize") if settings is not None else None
        return size.text if size is not None else None

    def _endpoint_description(self, identifier: str, *, aliases: dict[str, str] | None = None) -> str:
        owner = self.graph.endpoint_owner.get(identifier)
        if owner is None:
            return identifier
        if VlGraph.node_name(owner) or owner.get("Name"):
            owner_id = owner.get("Id", "")
            alias = self.alias_for(owner_id) if aliases is None else aliases.get(owner_id, owner_id)
            return f"{alias}.{self.graph.element(identifier).get('Name', identifier)}"
        return owner.get("Comment") or owner.get("Value") or identifier
