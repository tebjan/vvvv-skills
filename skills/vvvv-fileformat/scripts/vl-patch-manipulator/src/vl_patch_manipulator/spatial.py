"""Token-efficient spatial feedback and visual previews for vvvv patches."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import TYPE_CHECKING

from lxml import etree

from .document import VlGraph, _parse_bounds

if TYPE_CHECKING:
    from .session import PatchSession


def spatial_snapshot(session: PatchSession, *, columns: int = 96, rows: int = 32, canvas: etree._Element | None = None) -> dict[str, object]:
    """Return a compact whole-canvas map plus exact geometry and diagnostics."""

    scope = session._canvas_scope(canvas)
    elements = _visible_elements(session, canvas=canvas)
    if not elements:
        return {"canvas": None, "map": [], "elements": [], "free_bands": [], "analysis": session.layout_analysis(canvas=canvas)}
    rectangles = [item[3] for item in elements]
    left = min(rect[0] for rect in rectangles)
    top = min(rect[1] for rect in rectangles)
    right = max(rect[0] + rect[2] for rect in rectangles)
    bottom = max(rect[1] + rect[3] for rect in rectangles)
    width = max(1.0, right - left)
    height = max(1.0, bottom - top)
    grid = [[" " for _ in range(columns)] for _ in range(rows)]
    described: list[dict[str, object]] = []
    for index, (element, kind, label, bounds) in enumerate(elements, start=1):
        token = _token(index)
        x, y, element_width, element_height = bounds
        grid_x = min(columns - len(token), max(0, round((x + element_width * 0.5 - left) / width * (columns - 1))))
        grid_y = min(rows - 1, max(0, round((y + element_height * 0.5 - top) / height * (rows - 1))))
        for offset, character in enumerate(token):
            grid[grid_y][grid_x + offset] = character
        entry: dict[str, object] = {
            "token": token,
            "alias": session.alias_for(element.get("Id", "")),
            "kind": kind,
            "label": label,
            "bounds": [round(value, 1) for value in bounds],
        }
        if kind == "node":
            stored_bounds = _bounds(element)
            visible_inputs = [pin for pin in element.findall("Pin") if session._is_visible_input(pin)]
            visible_outputs = [pin for pin in element.findall("Pin") if session._is_visible_output(pin)]
            intrinsic_width = session._intrinsic_node_width(element)
            entry["pins"] = {
                "inputs": [
                    {
                        "name": pin.get("Name", ""),
                        "anchor": _rounded_point(session._endpoint_anchor(pin.get("Id", ""))),
                    }
                    for pin in visible_inputs
                ],
                "outputs": [
                    {
                        "name": pin.get("Name", ""),
                        "anchor": _rounded_point(session._endpoint_anchor(pin.get("Id", ""))),
                    }
                    for pin in visible_outputs
                ],
                "hidden": sum(
                    1
                    for pin in element.findall("Pin")
                    if pin.get("IsHidden", "false").lower() == "true"
                ),
            }
            entry["width"] = {
                "stored": round(stored_bounds[2], 1) if stored_bounds is not None else round(element_width, 1),
                "intrinsic": round(intrinsic_width, 1),
                "effective": round(element_width, 1),
                "expanded_ratio": round(element_width / intrinsic_width, 2) if intrinsic_width else 1.0,
            }
        described.append(entry)
    links: list[dict[str, object]] = []
    for link in session._scope_links(scope):
        endpoints = session.graph.link_endpoints(link)
        if endpoints is None:
            continue
        source_owner = session.graph.endpoint_owner.get(endpoints[0])
        target_owner = session.graph.endpoint_owner.get(endpoints[1])
        if source_owner is None or target_owner is None:
            continue
        links.append(
            {
                "source": session.alias_for(source_owner.get("Id", "")),
                "target": session.alias_for(target_owner.get("Id", "")),
                "source_pin": session.graph.by_id[endpoints[0]].get("Name", ""),
                "target_pin": session.graph.by_id[endpoints[1]].get("Name", ""),
                "from": _rounded_point(session._endpoint_anchor(endpoints[0])),
                "to": _rounded_point(session._endpoint_anchor(endpoints[1])),
                "feedback": session.graph.is_feedback(link),
                "region_feedback": session.graph.is_region_feedback(link),
            }
        )
    free_bands = _free_horizontal_bands(rectangles, top, bottom)
    return {
        "canvas": [round(left, 1), round(top, 1), round(width, 1), round(height, 1)],
        "map": ["".join(row).rstrip() for row in grid],
        "elements": described,
        "links": links,
        "free_bands": free_bands,
        "analysis": session.layout_analysis(canvas=canvas),
    }


def render_svg(session: PatchSession, path: str | Path, *, canvas: etree._Element | None = None) -> Path:
    """Render nodes, comments, regions, pins and links to a BOM-free SVG."""

    destination = Path(path)
    scope = session._canvas_scope(canvas)
    elements = _visible_elements(session, canvas=canvas)
    if not elements:
        raise ValueError("cannot render an empty patch")
    rectangles = [item[3] for item in elements]
    left = min(rect[0] for rect in rectangles) - 30
    top = min(rect[1] for rect in rectangles) - 30
    right = max(rect[0] + rect[2] for rect in rectangles) + 30
    bottom = max(rect[1] + rect[3] for rect in rectangles) + 30
    width = right - left
    height = bottom - top
    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{left:g} {top:g} {width:g} {height:g}" width="{width:g}" height="{height:g}">',
        "<style>text{font-family:Segoe UI,Arial,sans-serif}.label{font-size:10px;fill:#eee}.small{font-size:8px;fill:#bbb}.node{fill:#3b3d42;stroke:#8c9099;stroke-width:1}.pad{fill:#4a4d53;stroke:#9da2ac}.comment{fill:#25272b;stroke:#d0a64b}.region{fill:#202226;fill-opacity:.24;stroke:#59616d;stroke-width:1.5}.link{stroke:#7f8792;stroke-width:1;fill:none}.feedback{stroke:#8fb5c2;stroke-dasharray:4 3}.up{stroke:#ff4b4b;stroke-width:2}.pin{fill:#d0d4db}</style>",
        '<rect x="{0:g}" y="{1:g}" width="{2:g}" height="{3:g}" fill="#17181b"/>'.format(left, top, width, height),
    ]
    for element, kind, label, (x, y, element_width, element_height) in elements:
        if kind != "region":
            continue
        parts.append(f'<rect class="region" x="{x:g}" y="{y:g}" width="{element_width:g}" height="{element_height:g}" rx="4"/>')
        parts.append(f'<text class="small" x="{x + 8:g}" y="{y + 13:g}">{escape(label)}</text>')
    for link in session._scope_links(scope):
        endpoints = session.graph.link_endpoints(link)
        if endpoints is None:
            continue
        source = session._endpoint_anchor(endpoints[0], as_source=True)
        target = session._endpoint_anchor(endpoints[1], as_source=False)
        if source is None or target is None:
            continue
        feedback = session.graph.is_feedback(link)
        css = "link feedback" if feedback else "up" if target[1] <= source[1] else "link"
        title = "<title>Compiler feedback marker (not an automatic delay)</title>" if feedback else ""
        parts.append(f'<path class="{css}" d="M {source[0]:g} {source[1]:g} L {target[0]:g} {target[1]:g}">{title}</path>')
    for element, kind, label, (x, y, element_width, element_height) in elements:
        if kind == "region":
            continue
        if kind in {"slot", "control_point"}:
            stored = _parse_bounds(element.get("Bounds"))
            center_x, center_y = float(stored[0]) + 0.5, float(stored[1]) - 0.5
            if kind == "slot":
                parts.append(f'<circle class="pad" cx="{center_x:g}" cy="{center_y:g}" r="4.5"/>')
            else:
                parts.append(f'<rect class="pad" x="{center_x - 4.5:g}" y="{center_y - 4.5:g}" width="9" height="9"/>')
            if label:
                parts.append(f'<text class="label" x="{center_x + 6.5:g}" y="{center_y + 3:g}">{escape(label)}</text>')
            continue
        css = "node" if kind == "node" else "comment" if kind in {"comment", "heading", "link"} else "pad"
        parts.append(f'<rect class="{css}" x="{x:g}" y="{y:g}" width="{element_width:g}" height="{element_height:g}" rx="2"/>')
        text_y = y + min(element_height - 4, 13)
        parts.append(f'<text class="label" x="{x + 5:g}" y="{text_y:g}">{escape(_ellipsize(label, max(8, int(element_width / 6))))}</text>')
        if kind == "node":
            for pin in element.findall("Pin"):
                anchor = session._endpoint_anchor(pin.get("Id", ""))
                if anchor is not None:
                    parts.append(f'<circle class="pin" cx="{anchor[0]:g}" cy="{anchor[1]:g}" r="1.8"/>')
    analysis = session.layout_analysis(canvas=canvas)
    parts.append(
        f'<text class="small" x="{left + 8:g}" y="{bottom - 8:g}">overlaps {len(analysis["overlaps"])} · upward {len(analysis["upward_links"])} · crossings {analysis["crossings"]}</text>'
    )
    parts.append("</svg>")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(parts) + "\n", encoding="utf-8", newline="\n")
    return destination


def _visible_elements(session: PatchSession, *, canvas: etree._Element | None = None) -> list[tuple[etree._Element, str, str, tuple[float, float, float, float]]]:
    scope = session._canvas_scope(canvas)
    annotations = {element.get("Id"): element for element in session.graph.annotations()}
    elements: list[tuple[etree._Element, str, str, tuple[float, float, float, float]]] = []
    for node in session._scope_nodes(scope):
        bounds = session._element_rectangle(node)
        if bounds is not None:
            elements.append((node, "node", VlGraph.node_name(node), bounds))
    for pad in session.graph.pads:
        if scope is not None and pad not in scope:
            continue
        stored = _parse_bounds(pad.get("Bounds"))
        is_slot = bool(pad.get("SlotId")) and stored is not None and len(stored) == 2
        bounds = session._data_hub_rectangle(pad) if is_slot else _bounds(pad)
        if bounds is None:
            continue
        if is_slot:
            kind = "slot"
            label = session._data_hub_label(pad)
        elif pad.get("Id") in annotations:
            kind = session.graph.annotation_kind(pad)
            label = pad.get("Value", "")
        else:
            kind = "pad"
            label = pad.get("Comment") or pad.get("Value") or "Value"
        elements.append((pad, kind, label, bounds))
    for portal in session.document.root.iter("ControlPoint"):
        if scope is not None and portal not in scope:
            continue
        label = session._data_hub_label(portal)
        if not label and portal.get("Alignment") not in {"Top", "Bottom"}:
            continue
        bounds = session._data_hub_rectangle(portal)
        if bounds is not None:
            elements.append((portal, "control_point", label, bounds))
    for overlay in session.document.root.iter("Overlay"):
        if scope is not None and overlay not in scope:
            continue
        bounds = _bounds(overlay)
        if bounds is not None:
            elements.append((overlay, "region", overlay.get("Name", ""), bounds))
    if scope is not None:
        for node in session.graph.nodes:
            if node not in scope:
                continue
            reference = node.find("{property}NodeReference")
            if reference is None or not any(choice.get("Kind", "").endswith("Region") for choice in reference.findall("Choice")):
                continue
            bounds = _bounds(node)
            if bounds is not None:
                elements.append((node, "region", VlGraph.node_name(node), bounds))
    kind_order = {"region": 0, "heading": 1, "comment": 2, "link": 3, "pad": 4, "node": 5}
    elements.sort(key=lambda item: (item[3][1], item[3][0], kind_order.get(item[1], 9)))
    return elements


def _bounds(element: etree._Element) -> tuple[float, float, float, float] | None:
    values = _parse_bounds(element.get("Bounds"))
    if values is None or len(values) < 4:
        return None
    try:
        return tuple(float(value) for value in values[:4])
    except ValueError:
        return None


def _free_horizontal_bands(
    rectangles: list[tuple[float, float, float, float]],
    top: float,
    bottom: float,
    *,
    minimum: float = 48,
) -> list[list[float]]:
    edges = sorted({top, bottom, *(rect[1] for rect in rectangles), *(rect[1] + rect[3] for rect in rectangles)})
    free: list[list[float]] = []
    for upper, lower in zip(edges, edges[1:]):
        if lower - upper < minimum:
            continue
        if not any(rect[1] < lower and rect[1] + rect[3] > upper for rect in rectangles):
            free.append([round(upper, 1), round(lower, 1), round(lower - upper, 1)])
    return free


def _token(index: int) -> str:
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return alphabet[index // len(alphabet) % len(alphabet)] + alphabet[index % len(alphabet)]


def _ellipsize(value: str, limit: int) -> str:
    flattened = " ".join(value.split())
    return flattened if len(flattened) <= limit else flattened[: max(1, limit - 1)] + "…"


def _rounded_point(value: tuple[float, float] | None) -> list[float] | None:
    return [round(value[0], 1), round(value[1], 1)] if value is not None else None
