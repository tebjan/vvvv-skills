"""One discoverable semantic edit contract for Python, MCP and CLI clients.

The adapter resolves JSON references only; PatchSession remains the XML authority.
New public mutation methods must be registered here and pass the parity test.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
import inspect
from pathlib import Path
import re
from typing import Any

from lxml import etree

from .catalog import PinSpec
from .document import VlDocument
from .session import PatchSession


# External spellings retain the original MCP contract. Python parameter names
# remain accepted too; discovery describes both rather than silently dropping args.
METHODS = {
    name: name for name in (
        "add_node", "add_pad", "add_annotation", "add_dependency", "add_pin",
        "add_process", "add_slot", "add_slot_read", "remove_slot", "add_input_placement",
        "add_matrix_repeat_builder", "connect", "disconnect", "remove", "move",
        "set_bounds", "set_placement_position", "set_node_reference",
        "rename_local_process", "order_group_inputs_by_x",
        "set_pin_default", "set_pad_value", "fit_region", "align_link",
        "layout_value_pads", "normalize_node_sizes", "align", "distribute",
        "translate_group", "move_subgraph", "layout", "undo", "redo",
    )
}
METHODS.update({
    "set_value": "set_pin_default",
    "add_comment": "add_annotation", "add_heading": "add_annotation",
    "add_region": "add_annotation", "add_link_annotation": "add_annotation",
    "clone_subgraph": "@clone_subgraph", "rename": "@rename",
    "remove_incomplete_links": "@remove_incomplete_links",
})
RENAMES = {
    "add_pad": {"type": "type_name"},
    "add_pin": {"node": "node_alias_or_id", "default": "default_value"},
    "set_value": {"target": "alias_or_id", "pin": "pin_name"},
    "set_pin_default": {"target": "alias_or_id", "pin": "pin_name"},
    **{name: {"target": "alias_or_id"} for name in (
        "remove", "move", "set_bounds", "set_placement_position",
        "set_node_reference", "set_pad_value",
    )},
    "align": {"targets": "aliases"}, "distribute": {"targets": "aliases"},
    "move_subgraph": {"ids": "element_ids", "canvas": "destination_canvas"},
}
ANNOTATIONS = {"add_comment": "comment", "add_heading": "heading",
               "add_region": "region", "add_link_annotation": "link"}


def json_result(value: Any) -> Any:
    """Return reusable IDs, not lxml objects or lossy dataclass reprs."""
    if isinstance(value, etree._Element):
        return value.get("Id")
    if is_dataclass(value):
        return {field.name: json_result(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        return {key: json_result(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_result(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _stable_result(session: PatchSession, value: Any) -> Any:
    value = json_result(value)
    aliases = {alias: identifier for identifier, alias in
               (*session._aliases.items(), *session._entity_aliases.items())}

    def convert(item: Any) -> Any:
        if isinstance(item, str):
            return aliases.get(item, item)
        if isinstance(item, dict):
            return {key: convert(child) for key, child in item.items()}
        if isinstance(item, list):
            return [convert(child) for child in item]
        return item
    return convert(value)


def capabilities(names: list[str] | None = None) -> dict[str, Any]:
    selected = sorted(METHODS) if names is None else names
    operations = {}
    for name in selected:
        if name not in METHODS:
            raise ValueError(f"unknown operation: {name}")
        method = METHODS[name]
        if method.startswith("@"):
            params = {"clone_subgraph": ["ids", "patch=None", "dx=0", "dy=0"],
                      "rename": ["target", "name"], "remove_incomplete_links": []}[name]
            operations[name] = {"arguments": params}
            continue
        function = getattr(PatchSession, method)
        signature = inspect.signature(function)
        operations[name] = {
            "method": method,
            "arguments": {key: {"type": str(param.annotation),
                                 "required": param.default is inspect.Parameter.empty,
                                 **({"default": json_result(param.default)}
                                    if param.default is not inspect.Parameter.empty else {})}
                          for key, param in signature.parameters.items() if key != "self"},
            "aliases": RENAMES.get(name, {}),
            "help": inspect.getdoc(function) or "",
        }
        if name in ANNOTATIONS:
            operations[name]["arguments"]["kind"] = {"fixed": ANNOTATIONS[name]}
    return {
        "version": 1, "operations": operations,
        "batch": "Each edit may set 'as'. Later arguments use '$name.field' references. Results are JSON IDs.",
        "scope": "patch/canvas accept attached Canvas, owning Patch or Process definition IDs; scopes must be in this session.",
        "pins": "Process inputs/outputs are PinSpec objects: name,type_name,kind,default_value,hidden,optional,state,pin_group. Direction defaults to its list.",
        "references": "type_annotation(s)/reference use donor element IDs, or {path,id}; copy verified saved properties, never guess overload XML.",
    }


def resolve_canvas(session: PatchSession, identifier: str | None) -> etree._Element | None:
    if identifier is None:
        return None
    element = session.graph.element(session._resolve_entity_id(identifier))
    if element.tag == "Node":
        element = element.find("Patch")
    if element is not None and element.tag == "Patch":
        element = element.find("Canvas[@CanvasType='Group']")
    if element is None or element.tag != "Canvas":
        raise ValueError("scope must identify an attached Canvas, owning Patch or Process definition")
    return element


def _resolve_results(value: Any, results: dict[str, Any]) -> Any:
    if isinstance(value, str) and value.startswith("$$"):
        return value[1:]
    if isinstance(value, str) and value.startswith("$"):
        parts = value[1:].split(".")
        try:
            result = results[parts[0]]
            for part in parts[1:]:
                result = result[part]
            return result
        except (KeyError, TypeError) as exc:
            raise ValueError(f"unknown batch result reference {value!r}") from exc
    if isinstance(value, dict):
        return {key: _resolve_results(item, results) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_results(item, results) for item in value]
    return value


def _property(session: PatchSession, value: Any, name: str,
              donors: dict[str, VlDocument]) -> etree._Element:
    graph = session.graph
    identifier = value
    if isinstance(value, dict):
        path = str(Path(value["path"]).resolve())
        if path not in donors:
            donors[path] = VlDocument.load(path)
        graph = donors[path].graph()
        identifier = value["id"]
    else:
        identifier = session._resolve_entity_id(value)
    element = graph.element(identifier)
    property_element = element.find(f"{{property}}{name}")
    if property_element is None:
        raise ValueError(f"donor has no {name}")
    return property_element


def apply_operation(session: PatchSession, operation: dict[str, Any], *,
                    donors: dict[str, VlDocument] | None = None) -> Any:
    kind = operation["op"]
    if kind not in METHODS:
        raise ValueError(f"unsupported edit operation {kind!r}")
    kwargs = {RENAMES.get(kind, {}).get(key, key): value
              for key, value in operation.items() if key not in {"op", "as"}}
    donors = donors if donors is not None else {}
    if kind == "clone_subgraph":
        ids = [session._resolve_entity_id(item) for item in kwargs.pop("ids")]
        if kwargs.get("patch") is not None:
            kwargs["patch"] = resolve_canvas(session, kwargs["patch"])
        inspect.signature(session.graph.clone_subgraph).bind(ids, **kwargs)
        session._before_mutation()
        result = session.graph.clone_subgraph(ids, **kwargs)
        session._refresh()
        return result
    if kind == "rename":
        if set(kwargs) != {"target", "name"}:
            raise ValueError("rename requires exactly target and name")
        target = session.graph.element(session._resolve_entity_id(kwargs["target"]))
        reference = target.find("{property}NodeReference")
        if reference is not None and reference.find("Choice[@Kind='ContainerDefinition'][@Name='Process']") is not None:
            return session.rename_local_process(kwargs["target"], kwargs["name"])
        session._before_mutation()
        result = session.graph.rename(session._resolve_entity_id(kwargs["target"]), kwargs["name"])
        session._refresh()
        return result
    if kind == "remove_incomplete_links":
        if kwargs:
            raise ValueError("remove_incomplete_links takes no arguments")
        session._before_mutation()
        return session.graph.remove_incomplete_links()
    if kind in ANNOTATIONS:
        kwargs["kind"] = ANNOTATIONS[kind]
        if "name" in kwargs:
            kwargs.setdefault("text", kwargs.pop("name"))
    if METHODS[kind] == "add_annotation":
        if isinstance(kwargs.get("relative_to"), str):
            kwargs["relative_to"] = [kwargs["relative_to"]]
        if "offset_x" in kwargs or "offset_y" in kwargs:
            kwargs["offset"] = (kwargs.pop("offset_x", 20), kwargs.pop("offset_y", 20))
    if "patch" in kwargs and kwargs["patch"] is not None:
        canvas = resolve_canvas(session, kwargs["patch"])
        kwargs["patch"] = canvas.getparent() if kind == "add_slot" else canvas
    if "destination_canvas" in kwargs:
        kwargs["destination_canvas"] = resolve_canvas(session, kwargs["destination_canvas"])
    if kind == "add_process":
        for key, direction in (("inputs", "InputPin"), ("outputs", "OutputPin")):
            if key in kwargs:
                kwargs[key] = [PinSpec(**{"kind": direction, **item}) for item in kwargs[key]]
        if "type_annotations" in kwargs:
            kwargs["type_annotations"] = {key: _property(session, value, "TypeAnnotation", donors)
                                          for key, value in kwargs["type_annotations"].items()}
    if kwargs.get("type_annotation") is not None:
        kwargs["type_annotation"] = _property(session, kwargs["type_annotation"], "TypeAnnotation", donors)
    if kind == "set_node_reference":
        kwargs["reference"] = _property(session, kwargs["reference"], "NodeReference", donors)
    function = getattr(session, METHODS[kind])
    # Binding rejects missing/unknown arguments rather than silently ignoring them.
    inspect.signature(function).bind(**kwargs)
    return _stable_result(session, function(**kwargs))


def apply_batch(session: PatchSession, operations: list[dict[str, Any]]) -> dict[str, Any]:
    results: list[Any] = []
    named: dict[str, Any] = {}
    donors: dict[str, VlDocument] = {}
    # Reject duplicate result names before any mutation, and reserve undo/redo for
    # standalone edits: mixing history restoration with new edits is ambiguous.
    names = [item["as"] for item in operations if "as" in item]
    if any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in names) or len(set(names)) != len(names):
        raise ValueError("batch result names must be unique identifiers")
    if any(item.get("op") in {"undo", "redo"} for item in operations) and len(operations) != 1:
        raise ValueError("undo/redo must be standalone batches")
    if len(operations) == 1 and operations[0].get("op") in {"undo", "redo"}:
        # Starting a new undo unit before undo would restore that same unit,
        # not the user's previous edit. History operations are standalone.
        result = apply_operation(session, operations[0])
        return {"results": [result], "named": {names[0]: result} if names else {}}
    with session.transaction(validate=True):
        for operation in operations:
            resolved = _resolve_results({key: value for key, value in operation.items() if key != "as"}, named)
            result = apply_operation(session, resolved, donors=donors)
            results.append(json_result(result))
            if "as" in operation:
                named[operation["as"]] = results[-1]
    return {"results": results, "named": named}
