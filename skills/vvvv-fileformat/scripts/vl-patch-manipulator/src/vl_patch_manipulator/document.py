"""Loss-preserving XML document and typed graph views for VL patches.

The model intentionally wraps lxml elements instead of rebuilding a reduced object
tree. That keeps unknown VL attributes/elements, comments, child ordering and
namespaces intact while still providing typed graph queries and safe mutations.
"""

from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy
from dataclasses import dataclass
import math
from pathlib import Path
import os
import tempfile
from typing import Iterable, Iterator
from uuid import uuid4

from lxml import etree

from .diagnostics import ValidationReport
from .ids import ID_PATTERN, new_vl_id

PROPERTY_NS = "property"
REFLECTION_NS = "reflection"
NS = {"p": PROPERTY_NS, "r": REFLECTION_NS}
REFERENCE_ATTRIBUTES = {"Ids", "Patch", "SlotId", "ParticipatingElements"}


def _vvvv_empty_tag_spacing(payload: bytes) -> bytes:
    """Keep vvvv's ``<Pin ... />`` spelling without touching attribute values."""

    output = bytearray()
    position = 0
    while position < len(payload):
        if payload[position] != ord("<") or position + 1 >= len(payload) or payload[position + 1] in b"/!?":
            output.append(payload[position])
            position += 1
            continue
        end = position + 1
        quote = 0
        while end < len(payload):
            char = payload[end]
            if quote:
                if char == quote:
                    quote = 0
            elif char in (ord('"'), ord("'")):
                quote = char
            elif char == ord(">"):
                break
            end += 1
        if end < len(payload) and payload[end - 1] == ord("/") and payload[end - 2] != ord(" "):
            output.extend(payload[position:end - 1])
            output.extend(b" />")
        else:
            output.extend(payload[position:end + 1])
        position = end + 1
    return bytes(output)


def _local_name(element: etree._Element) -> str:
    return etree.QName(element).localname


def _parse_bounds(value: str | None) -> list[str] | None:
    if value is None:
        return None
    parts = [part.strip() for part in value.split(",")]
    return parts if len(parts) >= 2 else None


def _format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:g}"


def _round_bounds_value(value: float) -> int:
    """Round-half-away-from-zero to the nearest whole pixel.

    vvvv's own canvas geometry is always integral; Python's built-in
    ``round()`` uses round-half-to-even, which occasionally disagrees with the
    "round half up" a human (and vvvv) expects for a plain pixel coordinate.
    """

    return int(math.floor(value + 0.5)) if value >= 0 else -int(math.floor(-value + 0.5))


def _format_bounds(*values: float | str) -> str:
    """Render a ``Bounds`` attribute the way vvvv itself saves one.

    Comma-separated integers, no space -- ``"48,790,225,19"``, never
    ``"47.5, 790, 225, 19"``. vvvv always rounds canvas geometry to whole
    pixels; a fractional or space-separated coordinate in generated output
    makes every one of those lines show as changed the moment a human opens
    and re-saves the patch in vvvv, even though nothing actually moved.
    """

    return ",".join(str(_round_bounds_value(float(value))) for value in values)


def _element_ids(element: etree._Element) -> Iterator[str]:
    for child in element.iter():
        identifier = child.get("Id")
        if identifier:
            yield identifier


@dataclass(frozen=True)
class Endpoint:
    identifier: str
    element: etree._Element | None
    owner: etree._Element | None
    kind: str | None

    @property
    def is_output(self) -> bool:
        # A region ControlPoint is a typed portal, not a one-way input. The
        # outer graph can feed it and the nested graph can read from it; the
        # reverse direction is used for outputs leaving Cache/ForEach regions.
        return self.kind in {"OutputPin", "StateOutputPin", "ControlPoint"}

    @property
    def is_input(self) -> bool:
        return self.kind in {"InputPin", "StateInputPin", "ApplyPin", "ControlPoint"}


class VlDocument:
    """A parsed VL document with BOM-aware loading and atomic serialization."""

    def __init__(self, tree: etree._ElementTree, *, source_path: Path | None = None, had_bom: bool = False):
        self.tree = tree
        self.root = tree.getroot()
        self.source_path = source_path
        self.had_bom = had_bom

    @classmethod
    def parse(cls, data: bytes, *, source_path: Path | None = None) -> "VlDocument":
        had_bom = data.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff", b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff"))
        parser = etree.XMLParser(remove_blank_text=False, strip_cdata=False, resolve_entities=False, remove_comments=False)
        return cls(etree.ElementTree(etree.fromstring(data, parser=parser)), source_path=source_path, had_bom=had_bom)

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> "VlDocument":
        file_path = Path(path)
        return cls.parse(file_path.read_bytes(), source_path=file_path)

    def graph(self) -> "VlGraph":
        return VlGraph(self)

    def validate(self, *, include_orphan_warnings: bool = True) -> ValidationReport:
        return self.graph().validate(include_orphan_warnings=include_orphan_warnings)

    def to_bytes(self) -> bytes:
        body = etree.tostring(
            self.tree,
            encoding="UTF-8",
            xml_declaration=False,
            pretty_print=True,
        )
        return b'<?xml version="1.0" encoding="utf-8"?>\n' + _vvvv_empty_tag_spacing(body)

    def write_atomic(self, path: str | os.PathLike[str] | None = None, *, validate: bool = True) -> Path:
        destination = Path(path) if path is not None else self.source_path
        if destination is None:
            raise ValueError("a destination path is required for an unsaved document")
        report = self.validate() if validate else ValidationReport()
        if not report.ok:
            messages = "; ".join(f"{item.code}: {item.message}" for item in report.errors)
            raise ValueError(f"refusing to write invalid VL document: {messages}")
        payload = self.to_bytes()
        if payload.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff", b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
            raise ValueError("serializer produced a BOM")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("wb", dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(temporary, destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        self.source_path = destination
        return destination


def load_document(path: str | os.PathLike[str]) -> VlDocument:
    return VlDocument.load(path)


class VlGraph:
    """Typed/indexed view over a :class:`VlDocument`.

    The indexes are rebuilt after structural mutations. This is deliberate: it
    keeps every query deterministic and avoids stale references after cloning or
    deleting a subgraph.
    """

    def __init__(self, document: VlDocument):
        self.document = document
        self.refresh()

    def refresh(self) -> None:
        self.by_id: dict[str, etree._Element] = {}
        self.duplicates: dict[str, list[etree._Element]] = defaultdict(list)
        self.owner_by_id: dict[str, etree._Element] = {}
        for element in self.document.root.iter():
            identifier = element.get("Id")
            if identifier:
                self.duplicates[identifier].append(element)
                self.by_id.setdefault(identifier, element)
                parent = element.getparent()
                if parent is not None:
                    self.owner_by_id[identifier] = parent
        self.nodes = [element for element in self.document.root.iter("Node")]
        self.pins = [element for element in self.document.root.iter("Pin")]
        self.pads = [element for element in self.document.root.iter("Pad")]
        self.links = [element for element in self.document.root.iter("Link")]
        self.endpoint_owner: dict[str, etree._Element] = {}
        self.endpoint_kind: dict[str, str | None] = {}
        for element in self.nodes:
            for pin in element.findall("Pin"):
                identifier = pin.get("Id")
                if identifier:
                    self.endpoint_owner[identifier] = element
                    self.endpoint_kind[identifier] = pin.get("Kind")
        for pad in self.pads:
            identifier = pad.get("Id")
            if identifier:
                self.endpoint_owner[identifier] = pad
                # Pads are bidirectional endpoints in VL XML. A value IOBox may
                # source a node input, display a node output, or route through a
                # SlotId portal; the Link endpoint order supplies the direction.
                self.endpoint_kind[identifier] = None
        for control_point in self.document.root.iter("ControlPoint"):
            identifier = control_point.get("Id")
            if identifier:
                self.endpoint_owner[identifier] = control_point
                self.endpoint_kind[identifier] = "ControlPoint"
        self.outgoing: dict[str, set[str]] = defaultdict(set)
        self.incoming: dict[str, set[str]] = defaultdict(set)
        for link in self.links:
            ids = self.link_endpoints(link)
            if ids is None:
                continue
            source, target = ids
            self.outgoing[source].add(target)
            self.incoming[target].add(source)

    def element(self, identifier: str) -> etree._Element:
        try:
            return self.by_id[identifier]
        except KeyError as exc:
            raise KeyError(f"unknown VL element ID: {identifier}") from exc

    def endpoint(self, identifier: str) -> Endpoint:
        element = self.by_id.get(identifier)
        owner = self.endpoint_owner.get(identifier)
        return Endpoint(identifier, element, owner, self.endpoint_kind.get(identifier))

    @staticmethod
    def _annotation_style(pad: etree._Element) -> str | None:
        settings = pad.find(f"{{{PROPERTY_NS}}}ValueBoxSettings")
        if settings is None:
            return None
        string_type = settings.find(f"{{{PROPERTY_NS}}}stringtype")
        return string_type.text if string_type is not None else None

    def annotations(self) -> list[etree._Element]:
        """Return visible canvas annotations, excluding XML comments.

        Real vvvv help patches encode visible prose and clickable URLs as String
        IOBoxes whose ``ValueBoxSettings/stringtype`` is ``Comment`` or ``Link``.
        Framed sections are ``Overlay`` elements with a label and bounds.
        """

        result = [pad for pad in self.pads if self._annotation_style(pad) in {"Comment", "Link"}]
        result.extend(element for element in self.document.root.iter("Overlay"))
        return result

    def annotation_kind(self, element: etree._Element) -> str:
        if _local_name(element) == "Overlay":
            return "region"
        style = self._annotation_style(element)
        settings = element.find(f"{{{PROPERTY_NS}}}ValueBoxSettings")
        fontsize = settings.find(f"{{{PROPERTY_NS}}}fontsize") if settings is not None else None
        if style == "Comment" and fontsize is not None:
            try:
                if int(fontsize.text or "0") >= 15:
                    return "heading"
            except ValueError:
                pass
        return {"Comment": "comment", "Link": "link"}.get(style or "", style or "pad")

    @staticmethod
    def link_hub_ids(link: etree._Element) -> tuple[str, ...] | None:
        value = link.get("Ids")
        if value is None:
            return None
        values = tuple(item.strip() for item in value.split(","))
        return values if len(values) >= 2 and all(values) else None

    @staticmethod
    def link_endpoints(link: etree._Element) -> tuple[str, str] | None:
        values = VlGraph.link_hub_ids(link)
        return (values[0], values[-1]) if values is not None else None

    def operational_nodes(self) -> list[etree._Element]:
        result: list[etree._Element] = []
        for node in self.nodes:
            if node.get("Name") == "Application":
                continue
            ancestor = node.getparent()
            inside_region = False
            while ancestor is not None:
                if _local_name(ancestor) == "Node":
                    ancestor_reference = ancestor.find(f"{{{PROPERTY_NS}}}NodeReference")
                    if ancestor_reference is not None and any(
                        choice.get("Kind") == "StatefulRegion" for choice in ancestor_reference.findall("Choice")
                    ):
                        inside_region = True
                        break
                ancestor = ancestor.getparent()
            if inside_region:
                continue
            reference = node.find("{property}NodeReference")
            if reference is None:
                continue
            choices = reference.findall("Choice")
            if any(choice.get("Kind", "").endswith("Definition") or choice.get("Kind") == "StatefulRegion" for choice in choices):
                continue
            result.append(node)
        return result

    @staticmethod
    def node_name(node: etree._Element) -> str:
        """Return the visible operation name from a node's NodeReference."""

        if node.get("Name"):
            return node.get("Name") or ""
        reference = node.find("{property}NodeReference")
        if reference is None:
            return ""
        choices = reference.findall("Choice")
        return choices[-1].get("Name", "") if choices else ""

    def node_id_for_endpoint(self, identifier: str) -> str | None:
        owner = self.endpoint_owner.get(identifier)
        current = owner
        while current is not None:
            if _local_name(current) == "Node":
                reference = current.find(f"{{{PROPERTY_NS}}}NodeReference")
                if reference is not None and any(choice.get("Kind") == "StatefulRegion" for choice in reference.findall("Choice")):
                    return current.get("Id")
            current = current.getparent()
        return owner.get("Id") if owner is not None else None

    def connected_node_adjacency(self) -> dict[str, set[str]]:
        adjacency: dict[str, set[str]] = defaultdict(set)
        for link in self.links:
            endpoints = self.link_endpoints(link)
            if endpoints is None:
                continue
            source_node = self.node_id_for_endpoint(endpoints[0])
            target_node = self.node_id_for_endpoint(endpoints[1])
            if source_node and target_node and source_node != target_node:
                adjacency[source_node].add(target_node)
                adjacency[target_node].add(source_node)
        return adjacency

    @staticmethod
    def is_feedback(link: etree._Element) -> bool:
        """The saved compiler feedback marker; this does not synthesize state."""

        return link.get("IsFeedback", "false").lower() == "true"

    def is_region_feedback(self, link: etree._Element) -> bool:
        """Recognize a region's paired border control points, not raw node links."""
        endpoints = self.link_endpoints(link)
        if not self.is_feedback(link) or endpoints is None:
            return False
        source, target = (self.by_id.get(identifier) for identifier in endpoints)
        if source is None or target is None or source.tag != "ControlPoint" or target.tag != "ControlPoint":
            return False
        owner = source.getparent()
        if owner is None or owner.tag != "Node" or target.getparent() is not owner:
            return False
        if {source.get("Alignment"), target.get("Alignment")} != {"Top", "Bottom"}:
            return False
        reference = owner.find(f"{{{PROPERTY_NS}}}NodeReference")
        return reference is not None and any(choice.get("Kind") == "StatefulRegion" for choice in reference.findall("Choice"))

    def directed_node_adjacency(self, *, include_feedback: bool = True) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
        """Return node adjacency, optionally only current-frame dependencies."""

        outgoing: dict[str, set[str]] = defaultdict(set)
        incoming: dict[str, set[str]] = defaultdict(set)
        for link in self.links:
            if not include_feedback and self.is_region_feedback(link):
                continue
            endpoints = self.link_endpoints(link)
            if endpoints is None:
                continue
            source_node = self.node_id_for_endpoint(endpoints[0])
            target_node = self.node_id_for_endpoint(endpoints[1])
            if source_node and target_node and source_node != target_node:
                outgoing[source_node].add(target_node)
                incoming[target_node].add(source_node)
        return outgoing, incoming

    def reachable_from_sinks(self, sink_ids: Iterable[str] | None = None) -> set[str]:
        outgoing, incoming = self.directed_node_adjacency(include_feedback=False)
        operational_ids = {node.get("Id") for node in self.operational_nodes() if node.get("Id")}
        if sink_ids is None:
            # Pads are terminal visual sinks too, but an operational render node
            # may feed a status/output pad. Pick nodes with no outgoing edge to
            # another operational node, preferring the canonical RenderWindow.
            candidates = [node for node in self.operational_nodes() if not (outgoing.get(node.get("Id", ""), set()) & operational_ids)]
            render_sinks = [node.get("Id") for node in candidates if self.node_name(node) == "RenderWindow"]
            sink_ids = render_sinks or [node.get("Id") for node in candidates]
        reachable: set[str] = set()
        queue = deque(identifier for identifier in sink_ids if identifier)
        while queue:
            identifier = queue.popleft()
            if identifier in reachable:
                continue
            reachable.add(identifier)
            queue.extend(item for item in incoming.get(identifier, ()) if item in operational_ids)
        return reachable

    def orphan_operational_nodes(self, *, sink_ids: Iterable[str] | None = None) -> list[etree._Element]:
        operational = self.operational_nodes()
        adjacency = self.connected_node_adjacency()
        # BLIND SPOT - DO NOT REMOVE (2026-10-05)
        # A producer writing a shared Slot can reach a renderer through another
        # accessor Pad, without a physical Link between those Pads. Connect valid
        # accessors through a linear-size Slot hub for orphan reachability ONLY.
        # Slots are state, not ordinary current-frame edges: do not add these hubs
        # to directed_node_adjacency or the graph used for structural/spatial edits.
        for pad in self.pads:
            slot_id = pad.get("SlotId")
            slot = self.by_id.get(slot_id)
            if slot is None or slot.tag != "Slot" or self._definition_scope(slot) is not self._definition_scope(pad):
                continue
            accessor = self.node_id_for_endpoint(pad.get("Id", ""))
            if accessor:
                adjacency[accessor].add(slot_id)
                adjacency[slot_id].add(accessor)
        local_output_sinks: set[str] = set()
        if sink_ids is None:
            # BLIND SPOT - DO NOT REMOVE (2026-10-04)
            # A raw IsFeedback flag was mistaken for a window/camera delay.
            # Only paired region border points are internal feedback metadata;
            # raw flagged node edges remain dependencies and fail validation.
            # Real camera state uses a Slot with separate read/write Pads.
            outgoing, _ = self.directed_node_adjacency(include_feedback=False)
            # BLIND SPOT - DO NOT REMOVE (2026-10-04)
            # A local Process body is a separate executable graph. Its output
            # portals, not the application's RenderWindow, are its sinks. A
            # caller and definition have no physical Link between their XML.
            definitions = []
            for node in self.nodes:
                reference = node.find(f"{{{PROPERTY_NS}}}NodeReference")
                if node.get("Name") != "Application" and reference is not None and any(
                    choice.get("Kind") == "ContainerDefinition" and choice.get("Name") == "Process"
                    for choice in reference.findall("Choice")
                ):
                    definitions.append(node)
            definition_set = set(definitions)
            root_nodes = [node for node in operational if not any(parent in definition_set for parent in node.iterancestors())]
            root_ids = {node.get("Id") for node in root_nodes if node.get("Id")}
            candidates = [node for node in root_nodes if not (outgoing.get(node.get("Id", ""), set()) & root_ids)]
            render_sinks = [node.get("Id") for node in candidates if self.node_name(node) == "RenderWindow"]
            sink_ids = render_sinks or [node.get("Id") for node in candidates]
            for definition in definitions:
                owner = definition.find("Patch")
                if owner is None:
                    continue
                lifecycle = {patch.get("Name"): patch for patch in owner.findall("Patch")}
                enabled = {fragment.get("Patch") for fragment in owner.findall("ProcessDefinition/Fragment")
                           if fragment.get("Enabled") == "true"}
                if not all(name in lifecycle and lifecycle[name].get("Id") in enabled for name in ("Create", "Update")):
                    continue
                outputs = [pin for pin in lifecycle["Update"].findall("Pin") if pin.get("Kind") in {"OutputPin", "StateOutputPin"}]
                if outputs:
                    for pin in outputs:
                        for source in self.incoming.get(pin.get("Id", ""), ()):
                            endpoint_owner = self.node_id_for_endpoint(source)
                            source_element = self.by_id.get(endpoint_owner)
                            if source_element is not None and next(
                                (parent for parent in source_element.iterancestors() if parent in definition_set), None) is definition:
                                local_output_sinks.add(endpoint_owner)
                else:
                    # A no-output Process can itself own a render sink. Keep
                    # terminal-node fallback local instead of borrowing sinks
                    # from another definition or the application.
                    body_nodes = [node for node in operational if next(
                        (parent for parent in node.iterancestors() if parent in definition_set), None) is definition]
                    body_ids = {node.get("Id") for node in body_nodes}
                    terminals = [node for node in body_nodes if not (outgoing.get(node.get("Id", ""), set()) & body_ids)]
                    windows = [node.get("Id") for node in terminals if self.node_name(node) == "RenderWindow"]
                    sink_ids.extend(windows or [node.get("Id") for node in terminals])
            sink_ids.extend(local_output_sinks)
        reachable = self.reachable_from_sinks(sink_ids)

        # Stateful regions legitimately express mutation without a value edge
        # from the Repeat body back to the cached array consumer. For orphan
        # detection, every node in the sink's connected component is live; pin
        # direction validation still rejects genuinely reversed scalar links.
        connected: set[str] = set()
        queue = deque(identifier for identifier in sink_ids if identifier)
        while queue:
            identifier = queue.popleft()
            if identifier in connected:
                continue
            connected.add(identifier)
            queue.extend(adjacency.get(identifier, ()))

        return [
            node
            for node in operational
            if (not adjacency.get(node.get("Id", "")) and node.get("Id") not in local_output_sinks)
            or (node.get("Id") not in reachable and node.get("Id") not in connected)
        ]

    def _definition_scope(self, element: etree._Element) -> etree._Element:
        """Compiler symbol registration recurses regions, but stops at definitions."""
        for ancestor in element.iterancestors("Node"):
            reference = ancestor.find(f"{{{PROPERTY_NS}}}NodeReference")
            if reference is not None and any(
                    choice.get("Kind", "").endswith("Definition") for choice in reference.findall("Choice")):
                return ancestor
        return self.document.root

    def validate(self, *, include_orphan_warnings: bool = True) -> ValidationReport:
        report = ValidationReport()
        if etree.QName(self.document.root).localname != "Document":
            report.add("root-name", "document root must be <Document>")
        if self.document.root.nsmap.get("p") != PROPERTY_NS:
            report.add("property-namespace", "Document must declare xmlns:p=\"property\"")
        if self.document.root.get("Version") != "0.128":
            report.add("version", "Document Version must be 0.128")
        if not any(item.get("Location") == "VL.CoreLib" for item in self.document.root.findall("NugetDependency")):
            report.add("core-dependency", "Document is missing its direct VL.CoreLib dependency")
        for application in (node for node in self.nodes if node.get("Name") == "Application"):
            reference = application.find(f"{{{PROPERTY_NS}}}NodeReference")
            is_process = reference is not None and any(
                choice.get("Kind") == "ContainerDefinition" and choice.get("Name") == "Process"
                for choice in reference.findall("Choice")
            )
            if not is_process:
                continue

            application_patch = application.find("Patch")
            if application_patch is None:
                report.add(
                    "application-patch",
                    "Process Application must contain an inner Patch",
                    element_id=application.get("Id"),
                )
                continue

            group_canvas = next(
                (canvas for canvas in application_patch.findall("Canvas") if canvas.get("CanvasType") == "Group"),
                None,
            )
            if group_canvas is None:
                report.add(
                    "application-canvas",
                    "Process Application patch must contain a Group Canvas",
                    element_id=application_patch.get("Id"),
                )

            lifecycle_patches = {
                patch.get("Name"): patch
                for patch in application_patch.findall("Patch")
                if patch.get("Name") in {"Create", "Update"}
            }
            for lifecycle_name in ("Create", "Update"):
                if lifecycle_name not in lifecycle_patches:
                    report.add(
                        f"application-{lifecycle_name.lower()}",
                        f"Process Application must contain a sibling Patch named {lifecycle_name}",
                        element_id=application_patch.get("Id"),
                    )

            process_definition = application_patch.find("ProcessDefinition")
            if process_definition is None:
                report.add(
                    "application-process-definition",
                    "Process Application must contain a ProcessDefinition",
                    element_id=application_patch.get("Id"),
                )
            elif len(lifecycle_patches) == 2:
                enabled_targets = {
                    fragment.get("Patch")
                    for fragment in process_definition.findall("Fragment")
                    if fragment.get("Enabled") == "true"
                }
                for lifecycle_name, lifecycle_patch in lifecycle_patches.items():
                    lifecycle_id = lifecycle_patch.get("Id")
                    if lifecycle_id not in enabled_targets:
                        report.add(
                            "application-lifecycle-fragment",
                            f"ProcessDefinition must enable the {lifecycle_name} patch",
                            element_id=process_definition.get("Id"),
                        )
        for identifier, elements in self.duplicates.items():
            if len(elements) > 1:
                report.add("duplicate-id", f"ID occurs {len(elements)} times", element_id=identifier)
            if not ID_PATTERN.fullmatch(identifier):
                report.add("invalid-id", "ID is not an exactly 22-character base62 identifier", element_id=identifier)
        for patch in self.document.root.iter("Patch"):
            for dependency in patch:
                if not isinstance(dependency.tag, str):
                    continue
                if _local_name(dependency) not in {"NugetDependency", "DocumentDependency", "PlatformDependency", "ProjectDependency"}:
                    continue
                report.add("nested-dependency", "dependencies must be direct children of Document", element_id=dependency.get("Id"))
            sibling_patch_ids = {
                child.get("Id")
                for child in patch
                if isinstance(child.tag, str) and _local_name(child) == "Patch" and child.get("Id")
            }
            for fragment in patch.findall("ProcessDefinition/Fragment"):
                target = fragment.get("Patch")
                if target and target not in sibling_patch_ids:
                    report.add("dangling-fragment", f"Fragment points to missing sibling Patch {target}", element_id=fragment.get("Id"))
        for control_point in self.document.root.iter("ControlPoint"):
            if control_point.get("DefinitionId") is not None:
                report.add("unsupported-input-selector", "ControlPoint DefinitionId is not a VL input selector; reference the signature Pin through an IsHidden link", element_id=control_point.get("Id"))
        for pad in self.pads:
            slot_id = pad.get("SlotId")
            if not slot_id:
                continue
            slot = self.by_id.get(slot_id)
            if slot is None or slot.tag != "Slot":
                report.add("dangling-slot", "Pad SlotId must reference a Slot", element_id=pad.get("Id"))
            # BLIND SPOT - DO NOT REMOVE (2026-10-04)
            # A region's containing Patch is not its compiler symbol scope.
            # Patches.InitializePads binds SlotId in the definition-wide map,
            # including nested regions and lifecycle fragments. Reject only
            # references crossing a definition boundary, not an inner Patch.
            elif self._definition_scope(slot) is not self._definition_scope(pad):
                report.add("slot-scope", "Slot accessor must stay within the Slot's definition", element_id=pad.get("Id"))
        for link in self.links:
            hubs = self.link_hub_ids(link)
            if hubs is None:
                report.add("link-shape", "Link Ids must contain at least two non-empty IDs", element_id=link.get("Id"))
                continue
            source, target = hubs[0], hubs[-1]
            source_endpoint = self.endpoint(source)
            target_endpoint = self.endpoint(target)
            if any(self.endpoint(hub).element is None for hub in hubs):
                report.add("dangling-link", "Link endpoint does not resolve", element_id=link.get("Id"))
                continue
            signature = source_endpoint.element.getparent()
            if (link.get("IsHidden", "false").lower() == "true"
                    and source_endpoint.element.tag == "Pin"
                    and source_endpoint.element.get("Kind") == "InputPin"
                    and signature is not None and signature.tag == "Patch"
                    and target_endpoint.element.tag == "ControlPoint"):
                owner = signature.getparent()
                # Region and lifecycle nesting share the definition symbol
                # map. Reference links can live on an enclosing master Patch.
                if (owner is not None and owner.find("Canvas[@CanvasType='Group']") is not None
                        and (self._definition_scope(link) is not self._definition_scope(source_endpoint.element)
                             or self._definition_scope(target_endpoint.element) is not self._definition_scope(source_endpoint.element))):
                    report.add("input-placement-scope", "Input reference placement must stay within its signature's definition", element_id=link.get("Id"))
            if source_endpoint.is_input and source_endpoint.kind != "ControlPoint":
                report.add("link-direction", "link source is an input pin; source must be an output/pad", element_id=link.get("Id"))
            if target_endpoint.is_output and target_endpoint.kind != "ControlPoint":
                report.add("link-direction", "link target is an output pin; target must be an input", element_id=link.get("Id"))
            if self.is_feedback(link) and not self.is_region_feedback(link):
                report.add("unsupported-feedback-link", "IsFeedback is region border-pair metadata, not a node-to-node delay; use a Slot with separate read/write pads and ordinary links", element_id=link.get("Id"))
        for annotation in self.annotations():
            if _local_name(annotation) != "Pad":
                continue
            settings = annotation.find(f"{{{PROPERTY_NS}}}ValueBoxSettings")
            size = settings.find(f"{{{PROPERTY_NS}}}fontsize") if settings is not None else None
            string_type = settings.find(f"{{{PROPERTY_NS}}}stringtype") if settings is not None else None
            if size is None or size.get(f"{{{PROPERTY_NS}}}Type") != "Int32":
                report.add(
                    "annotation-font-type",
                    "visible comment fontsize must use the canonical p:Type=\"Int32\" attribute",
                    element_id=annotation.get("Id"),
                )
            if (
                string_type is None
                or string_type.get(f"{{{PROPERTY_NS}}}Assembly") != "VL.Core"
                or string_type.get(f"{{{PROPERTY_NS}}}Type") != "VL.Core.StringType"
            ):
                report.add(
                    "annotation-string-type",
                    "visible comments and links must use canonical p:Assembly/p:Type attributes",
                    element_id=annotation.get("Id"),
                )
        if include_orphan_warnings:
            for node in self.orphan_operational_nodes():
                report.add("orphan-operational", "operational node is disconnected from the render/dataflow component", severity="warning", element_id=node.get("Id"))
        return report

    def _main_patch(self) -> etree._Element:
        patch = self.document.root.find("Patch")
        if patch is None:
            raise ValueError("Document has no top-level Patch")
        return patch

    def _main_canvas(self) -> etree._Element:
        application = next((node for node in self.nodes if node.get("Name") == "Application"), None)
        if application is None:
            raise ValueError("Document has no Application node")
        for canvas in application.iter("Canvas"):
            if canvas.get("CanvasType") == "Group":
                return canvas
        raise ValueError("Application has no Group Canvas")

    def _patch_for_element(self, element: etree._Element) -> etree._Element:
        current = element
        while current is not None and _local_name(current) != "Patch":
            current = current.getparent()
        return current if current is not None else self._main_patch()

    def add_dependency(self, location: str, *, version: str | None = None, kind: str = "NugetDependency", is_forward: bool = False) -> str:
        if kind not in {"NugetDependency", "DocumentDependency", "PlatformDependency", "ProjectDependency"}:
            raise ValueError(f"unsupported dependency element: {kind}")
        existing = next((item for item in self.document.root if _local_name(item) == kind and item.get("Location") == location), None)
        if existing is not None:
            return existing.get("Id") or ""
        element = etree.Element(kind, Id=new_vl_id(), Location=location)
        if version is not None:
            element.set("Version", version)
        if is_forward:
            element.set("IsForward", "true")
        patch = self.document.root.find("Patch")
        index = list(self.document.root).index(patch) if patch is not None else len(self.document.root)
        self.document.root.insert(index, element)
        self.refresh()
        return element.get("Id") or ""

    def add_node(self, node: etree._Element, *, patch: etree._Element | None = None) -> str:
        if _local_name(node) != "Node":
            raise ValueError("add_node expects a Node element")
        clone = deepcopy(node)
        self._ensure_fresh_ids(clone)
        (patch or self._main_canvas()).append(clone)
        self.refresh()
        return clone.get("Id") or ""

    def add_pin(self, node_id: str, name: str, kind: str, *, type_annotation: etree._Element | None = None, **attributes: str) -> str:
        node = self.element(node_id)
        if _local_name(node) != "Node":
            raise ValueError("pins can only be added to Node elements")
        pin = etree.Element("Pin", Id=new_vl_id(), Name=name, Kind=kind, **attributes)
        if type_annotation is not None:
            pin.append(deepcopy(type_annotation))
        node.append(pin)
        self.refresh()
        return pin.get("Id") or ""

    def add_pad(self, *, patch: etree._Element | None = None, value: str | None = None, comment: str | None = None, **attributes: str) -> str:
        pad_attributes = {"Id": new_vl_id(), "Bounds": attributes.pop("Bounds", "100,100,80,20"), "ShowValueBox": attributes.pop("ShowValueBox", "true"), "isIOBox": attributes.pop("isIOBox", "true")}
        pad_attributes.update(attributes)
        if value is not None:
            pad_attributes["Value"] = value
        if comment is not None:
            pad_attributes["Comment"] = comment
        pad = etree.Element("Pad", **pad_attributes)
        (patch or self._main_canvas()).append(pad)
        self.refresh()
        return pad.get("Id") or ""

    def add_annotation(
        self,
        *,
        kind: str,
        text: str = "",
        bounds: str = "100,100,300,60",
        patch: etree._Element | None = None,
        font_size: int | None = None,
        relative_to: Iterable[str] | None = None,
        offset: tuple[float, float] = (20, 20),
        placement: str = "right",
    ) -> str:
        """Create a corpus-proven visible help annotation.

        ``comment``/``heading``/``link`` are String IOBoxes.  ``region`` is the
        actual vvvv ``Overlay`` frame used by help patches.  The caller may pass
        node/pad/overlay IDs to ``relative_to``; placement is computed from their
        bounding box without changing the element's style.
        """

        if kind not in {"comment", "heading", "link", "region"}:
            raise ValueError("annotation kind must be comment, heading, link, or region")
        destination = patch or self._main_canvas()
        if relative_to:
            anchor = self._bounds_union(relative_to)
            if anchor is not None:
                x, y, width, height = anchor
                current = _parse_bounds(bounds) or ["0", "0", "300", "60"]
                annotation_width = float(current[2])
                annotation_height = float(current[3])
                if placement == "right":
                    annotation_x, annotation_y = x + width + offset[0], y + offset[1]
                elif placement == "left":
                    annotation_x, annotation_y = x - annotation_width - offset[0], y + offset[1]
                elif placement == "above":
                    annotation_x, annotation_y = x + offset[0], y - annotation_height - offset[1]
                elif placement == "below":
                    annotation_x, annotation_y = x + offset[0], y + height + offset[1]
                else:
                    raise ValueError("annotation placement must be right, left, above, or below")
                current[0] = _format_number(annotation_x)
                current[1] = _format_number(annotation_y)
                bounds = _format_bounds(*current)
        if kind == "region":
            overlay = etree.Element("Overlay", Id=new_vl_id(), Name=text or "Section", Bounds=bounds)
            destination.insert(0, overlay)
            self.refresh()
            return overlay.get("Id") or ""
        pad = etree.Element("Pad", Id=new_vl_id(), Bounds=bounds, ShowValueBox="true", isIOBox="true", Value=text)
        annotation_type = etree.SubElement(pad, f"{{{PROPERTY_NS}}}TypeAnnotation", LastCategoryFullName="Primitive", LastDependency="VL.CoreLib.vl")
        etree.SubElement(annotation_type, "Choice", Kind="TypeFlag", Name="String")
        settings = etree.SubElement(pad, f"{{{PROPERTY_NS}}}ValueBoxSettings")
        size = font_size if font_size is not None else (15 if kind == "heading" else 9)
        size_element = etree.SubElement(
            settings,
            f"{{{PROPERTY_NS}}}fontsize",
            {f"{{{PROPERTY_NS}}}Type": "Int32"},
        )
        size_element.text = str(size)
        string_type = etree.SubElement(
            settings,
            f"{{{PROPERTY_NS}}}stringtype",
            {
                f"{{{PROPERTY_NS}}}Assembly": "VL.Core",
                f"{{{PROPERTY_NS}}}Type": "VL.Core.StringType",
            },
        )
        string_type.text = "Link" if kind == "link" else "Comment"
        destination.append(pad)
        self.refresh()
        return pad.get("Id") or ""

    def _bounds_union(self, identifiers: Iterable[str]) -> tuple[float, float, float, float] | None:
        rectangles: list[tuple[float, float, float, float]] = []
        for identifier in identifiers:
            element = self.by_id.get(identifier)
            if element is None:
                continue
            parts = _parse_bounds(element.get("Bounds"))
            if parts is None or len(parts) < 4:
                continue
            try:
                rectangles.append(tuple(float(value) for value in parts[:4]))
            except ValueError:
                continue
        if not rectangles:
            return None
        left = min(item[0] for item in rectangles)
        top = min(item[1] for item in rectangles)
        right = max(item[0] + item[2] for item in rectangles)
        bottom = max(item[1] + item[3] for item in rectangles)
        return left, top, right - left, bottom - top

    def add_link(self, source_id: str, target_id: str, *, patch: etree._Element | None = None, **attributes: str) -> str:
        self.refresh()
        source = self.endpoint(source_id)
        target = self.endpoint(target_id)
        if source.element is None or target.element is None:
            raise ValueError("both link endpoints must exist")
        if (source.is_input and source.kind != "ControlPoint") or (target.is_output and target.kind != "ControlPoint"):
            raise ValueError("link must run from an output/pad to an input")
        link = etree.Element("Link", Id=new_vl_id(), Ids=f"{source_id},{target_id}", **attributes)
        destination = patch if patch is not None else self._patch_for_element(source.element)
        if len(destination):
            previous = destination[-1]
            closing_indent = previous.tail
            sibling_indent = destination[-2].tail if len(destination) > 1 else destination.text
            if closing_indent is not None and sibling_indent is not None:
                previous.tail = sibling_indent
                link.tail = closing_indent
        destination.append(link)
        self.refresh()
        return link.get("Id") or ""

    def remove_incomplete_links(self) -> list[str]:
        """Remove unfinished editor drags; never guess their missing endpoint."""

        removed: list[str] = []
        for link in list(self.links):
            if self.link_endpoints(link) is not None:
                continue
            identifier = link.get("Id") or ""
            parent = link.getparent()
            if parent is not None:
                parent.remove(link)
                removed.append(identifier)
        if removed:
            self.refresh()
        return removed

    def ensure_link(self, source_id: str, target_id: str) -> str:
        """Set one exact input connection, preserving an already-correct link."""

        for link in list(self.links):
            endpoints = self.link_endpoints(link)
            if endpoints is None or endpoints[1] != target_id:
                continue
            if endpoints[0] == source_id:
                return link.get("Id") or ""
            self.remove_link(link.get("Id") or "")
        return self.add_link(source_id, target_id)

    def remove_node(self, node_id: str) -> None:
        node = self.element(node_id)
        if _local_name(node) != "Node":
            raise ValueError("remove_node expects a Node ID")
        descendants = set(_element_ids(node))
        self._remove_links_for_endpoints(descendants)
        parent = node.getparent()
        if parent is None:
            raise ValueError("node is detached")
        parent.remove(node)
        self.refresh()

    def remove_pad(self, pad_id: str) -> None:
        pad = self.element(pad_id)
        if _local_name(pad) != "Pad":
            raise ValueError("remove_pad expects a Pad ID")
        self._remove_links_for_endpoints({pad_id})
        parent = pad.getparent()
        if parent is None:
            raise ValueError("pad is detached")
        parent.remove(pad)
        self.refresh()

    def remove_link(self, link_id: str) -> None:
        link = self.element(link_id)
        if _local_name(link) != "Link":
            raise ValueError("remove_link expects a Link ID")
        parent = link.getparent()
        if parent is None:
            raise ValueError("link is detached")
        parent.remove(link)
        self.refresh()

    def _remove_links_for_endpoints(self, endpoint_ids: set[str]) -> None:
        for link in list(self.links):
            endpoints = self.link_endpoints(link)
            if endpoints and endpoint_ids.intersection(endpoints):
                parent = link.getparent()
                if parent is not None:
                    parent.remove(link)

    def rename(self, identifier: str, value: str) -> None:
        element = self.element(identifier)
        if _local_name(element) == "Node":
            element.set("Name", value)
        elif _local_name(element) in {"Pin", "Pad", "Slot", "Canvas", "Patch"}:
            element.set("Name", value)
        else:
            raise ValueError(f"safe rename does not support {_local_name(element)}")
        self.refresh()

    def set_pad_value(self, pad_id: str, value: str) -> None:
        pad = self.element(pad_id)
        if _local_name(pad) != "Pad":
            raise ValueError("set_pad_value expects a Pad ID")
        pad.set("Value", value)

    def move(self, identifier: str, x: float, y: float) -> None:
        element = self.element(identifier)
        bounds = _parse_bounds(element.get("Bounds"))
        if bounds is None:
            raise ValueError("element has no parseable Bounds")
        bounds[0] = _format_number(x)
        bounds[1] = _format_number(y)
        element.set("Bounds", _format_bounds(*bounds))

    def clone_subgraph(self, element_ids: Iterable[str], *, patch: etree._Element | None = None, dx: float = 0, dy: float = 0) -> dict[str, str]:
        """Clone nodes/pads and links whose endpoints are wholly in ``element_ids``.

        The returned dictionary maps every original ID to its fresh ID. Nested IDs
        and known reference attributes are remapped too, so a cloned process
        definition remains internally coherent.
        """

        self.refresh()
        selected = [self.element(identifier) for identifier in element_ids]
        endpoint_ids: set[str] = set()
        for element in selected:
            endpoint_ids.update(_element_ids(element))
        selected_links = [link for link in self.links if (endpoints := self.link_endpoints(link)) is not None and set(endpoints).issubset(endpoint_ids)]
        mapping: dict[str, str] = {}
        clones: list[etree._Element] = []
        for element in [*selected, *selected_links]:
            clone = deepcopy(element)
            self._ensure_fresh_ids(clone, mapping)
            if dx or dy:
                bounds = _parse_bounds(clone.get("Bounds"))
                if bounds is not None:
                    bounds[0] = _format_number(float(bounds[0]) + dx)
                    bounds[1] = _format_number(float(bounds[1]) + dy)
                    clone.set("Bounds", _format_bounds(*bounds))
            clones.append(clone)
        destination = patch or self._main_canvas()
        for clone in clones:
            destination.append(clone)
        self.refresh()
        return mapping

    def _ensure_fresh_ids(self, element: etree._Element, mapping: dict[str, str] | None = None) -> None:
        mapping = mapping if mapping is not None else {}
        for child in element.iter():
            old = child.get("Id")
            if old:
                mapping.setdefault(old, new_vl_id())
                child.set("Id", mapping[old])
        for child in element.iter():
            for attribute in REFERENCE_ATTRIBUTES:
                value = child.get(attribute)
                if not value:
                    continue
                if attribute == "Ids":
                    child.set(attribute, ",".join(mapping.get(item.strip(), item.strip()) for item in value.split(",")))
                elif attribute == "ParticipatingElements":
                    child.set(attribute, ",".join(mapping.get(item.strip(), item.strip()) for item in value.split(",")))
                else:
                    child.set(attribute, mapping.get(value, value))


def serialize_diagnostics(report: ValidationReport) -> list[dict[str, str | None]]:
    return [
        {"code": item.code, "message": item.message, "severity": item.severity, "element_id": item.element_id, "path": item.path}
        for item in report.diagnostics
    ]
