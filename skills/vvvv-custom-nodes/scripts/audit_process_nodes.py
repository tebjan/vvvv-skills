#!/usr/bin/env python3
"""Find likely ProcessNode fragment/output import hazards with a C# syntax parser.

This is a static candidate audit. It does not load vvvv, Roslyn, or imported node
symbols, and it cannot prove that a reported pattern fails at runtime.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
LOCAL_DEPS = SCRIPT_DIR / ".deps"
if LOCAL_DEPS.is_dir():
    sys.path.insert(0, str(LOCAL_DEPS))

try:
    from tree_sitter import Language, Parser
    import tree_sitter_c_sharp
except ImportError as exc:  # pragma: no cover - exercised by CLI setup check
    raise SystemExit(
        "C# parser dependencies are missing. From this directory run:\n"
        "  python -m pip install --target .deps -r requirements.txt"
    ) from exc


DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".deps",
    "bin",
    "obj",
    "lib",
    "thirdparty",
    "third_party",
    "external",
    "packages",
    "node_modules",
    "vendor",
    "generated",
    "sdsl",
}
GENERATED_SUFFIXES = (".g.cs", ".g.i.cs", ".designer.cs", ".generated.cs")
TYPE_DECLARATIONS = {"class_declaration", "record_declaration", "struct_declaration"}
LIFECYCLE_METHODS = {"Create", "Dispose"}


@dataclass
class AttributeInfo:
    name: str
    line: int
    target: str | None = None
    arguments: dict[str, str | None] = field(default_factory=dict)


@dataclass
class MethodInfo:
    name: str
    line: int
    path: str
    return_type: str
    is_public: bool
    is_static: bool
    returns_this: bool
    has_nonvoid_return: bool
    return_is_state: bool
    return_output_name: str | None
    return_output_unknown: bool
    attributes: list[AttributeInfo]
    output_names: list[str]
    output_names_unknown: list[str]


@dataclass
class ClassPart:
    key: str
    name: str
    path: str
    line: int
    kind: str
    attributes: list[AttributeInfo]
    base_types: list[str]
    methods: list[MethodInfo]
    properties: list["PropertyInfo"]


@dataclass
class PropertyInfo:
    name: str
    line: int
    path: str
    is_public: bool
    is_static: bool
    accessor_names: list[str]
    attributes: list[AttributeInfo]
    output_name: str | None
    output_unknown: bool


def _text(node: Any) -> str:
    return node.text.decode("utf-8", errors="replace") if node is not None else ""


def _walk(node: Any) -> Iterable[Any]:
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.named_children))


def _child(node: Any, kind: str) -> Any | None:
    for item in node.named_children:
        if item.type == kind:
            return item
    return None


def _attribute_name(attr: Any) -> tuple[str, str | None]:
    children = list(attr.named_children)
    target = None
    if children and children[0].type == "attribute_target_specifier":
        raw_target = _text(children.pop(0)).strip()
        target = raw_target[:-1].strip() if raw_target.endswith(":") else raw_target
    name_node = children[0] if children else None
    raw_name = _text(name_node).strip()
    return raw_name.split(".")[-1].removesuffix("Attribute"), target


def _constant_value(node: Any) -> str | None:
    if node is None:
        return None
    raw = _text(node).strip()
    if raw == "true" or raw == "false":
        return raw
    if raw.startswith('"') and raw.endswith('"'):
        # Attribute names in this audit are plain strings; keep escaped values
        # visible instead of interpreting C# string syntax incorrectly.
        return raw[1:-1]
    return f"<expression:{raw}>"


def _attributes(node: Any) -> list[AttributeInfo]:
    found: list[AttributeInfo] = []
    for attr_list in node.named_children:
        if attr_list.type != "attribute_list":
            continue
        target_node = next(
            (child for child in attr_list.named_children if child.type == "attribute_target_specifier"),
            None,
        )
        list_target = _text(target_node).strip() if target_node is not None else None
        if list_target and list_target.endswith(":"):
            list_target = list_target[:-1].strip()
        for attr in attr_list.named_children:
            if attr.type != "attribute":
                continue
            name, target = _attribute_name(attr)
            target = target or list_target
            args: dict[str, str | None] = {}
            arg_list = _child(attr, "attribute_argument_list")
            if arg_list is not None:
                for arg in arg_list.named_children:
                    if arg.type != "attribute_argument":
                        continue
                    named = list(arg.named_children)
                    if len(named) >= 2:
                        args[_text(named[0]).strip()] = _constant_value(named[-1])
            found.append(AttributeInfo(name, attr.start_point.row + 1, target, args))
    return found


def _pin_name(attributes: list[AttributeInfo], fallback: str) -> tuple[str | None, bool]:
    for attr in attributes:
        if attr.name == "Pin" and "Name" in attr.arguments:
            value = attr.arguments["Name"]
            return value, value is None or value.startswith("<expression:")
    if not fallback:
        return None, True
    return fallback[0].upper() + fallback[1:], False


def _is_public(method: Any) -> bool:
    return any(child.type == "modifier" and _text(child) == "public" for child in method.named_children)


def _modifiers(method: Any) -> set[str]:
    return {_text(child) for child in method.named_children if child.type == "modifier"}


def _method_signature_parts(method: Any) -> tuple[str, str, Any | None]:
    named = list(method.named_children)
    params_index = next((i for i, child in enumerate(named) if child.type == "parameter_list"), -1)
    if params_index < 1:
        return "", "", None
    before = [
        child
        for child in named[:params_index]
        if child.type not in {"attribute_list", "modifier"}
    ]
    if len(before) < 2:
        return "", "", named[params_index]
    return _text(before[-2]), _text(before[-1]), named[params_index]


def _unwrap_parentheses(node: Any) -> Any:
    while node is not None and node.type == "parenthesized_expression":
        node = next((child for child in node.children if child.type not in {"(", ")"}), None)
    return node


def _returns_this(method: Any) -> bool:
    body = _child(method, "block")
    if body is not None:
        stack = list(reversed(body.named_children))
        while stack:
            node = stack.pop()
            if node.type in {"lambda_expression", "anonymous_method_expression", "local_function_statement"}:
                continue
            if node.type == "return_statement":
                expression_node = next(
                    (child for child in node.children if child.type not in {"return", ";"}),
                    None,
                )
                expression = _unwrap_parentheses(expression_node)
                if expression is not None and expression.type == "this":
                    return True
                continue
            stack.extend(reversed(node.named_children))
    arrow = _child(method, "arrow_expression_clause")
    if arrow is not None:
        expression = next((child for child in arrow.children if child.type != "=>"), None)
        expression = _unwrap_parentheses(expression)
        return expression is not None and expression.type == "this"
    return False


def _parse_method(method: Any, source_path: str) -> MethodInfo | None:
    return_type, name, params = _method_signature_parts(method)
    if not name or params is None:
        return None
    attrs = _attributes(method)
    outputs: list[str] = []
    unknown: list[str] = []
    for parameter in params.named_children:
        if parameter.type != "parameter":
            continue
        modifiers = {_text(c) for c in parameter.named_children if c.type == "modifier"}
        if not modifiers.intersection({"out", "ref"}):
            continue
        ids = [c for c in parameter.named_children if c.type == "identifier"]
        parameter_name = _text(ids[-1]) if ids else ""
        pin_name, unresolved = _pin_name(_attributes(parameter), parameter_name)
        if unresolved:
            unknown.append(f"{parameter_name or '<unnamed>'} (out/ref)")
        elif pin_name is not None:
            outputs.append(pin_name)

    return_attrs = [attr for attr in attrs if attr.target == "return"]
    return_is_state = any(
        attr.name == "Pin" and attr.arguments.get("IsState") == "true"
        for attr in return_attrs
    )
    return_pin, return_unknown = _pin_name(return_attrs, "")
    return_name_explicit = any(
        attr.name == "Pin" and "Name" in attr.arguments
        for attr in return_attrs
    )
    self_return = _returns_this(method)
    has_nonvoid_return = return_type.strip() != "void"
    if has_nonvoid_return and not return_is_state:
        if return_pin is not None and not return_unknown:
            outputs.append(return_pin)
        elif return_name_explicit and return_unknown:
            unknown.append("method return")

    return MethodInfo(
        name=name,
        line=method.start_point.row + 1,
        path=source_path,
        return_type=return_type,
        is_public=_is_public(method),
        is_static="static" in _modifiers(method),
        returns_this=self_return,
        has_nonvoid_return=has_nonvoid_return,
        return_is_state=return_is_state,
        return_output_name=return_pin if return_pin is not None and not return_unknown else None,
        return_output_unknown=return_name_explicit and return_unknown,
        attributes=attrs,
        output_names=outputs,
        output_names_unknown=unknown,
    )


def _type_name(node: Any) -> str:
    raw = _text(node).strip()
    raw = raw.removeprefix("global::").rstrip("?")
    # The grammar parsed the type; this normalization only removes generic
    # arguments and qualification for source-local name matching.
    raw = raw.split("<", 1)[0].strip()
    return raw.split(".")[-1].strip()


def _decl_name(node: Any) -> str:
    name = node.child_by_field_name("name")
    if name is not None:
        return _text(name)
    for child in node.named_children:
        if child.type == "identifier":
            return _text(child)
    return "<unknown>"


def _base_types(node: Any) -> list[str]:
    base_list = _child(node, "base_list")
    if base_list is None:
        return []
    return [_text(item).strip() for item in base_list.named_children]


def _parse_property(prop: Any, source_path: str) -> PropertyInfo | None:
    attrs = _attributes(prop)
    named = list(prop.named_children)
    body_index = next(
        (i for i, child in enumerate(named) if child.type in {"accessor_list", "arrow_expression_clause"}),
        len(named),
    )
    before = [child for child in named[:body_index] if child.type not in {"attribute_list", "modifier"}]
    if len(before) < 2:
        return None
    name = _text(before[-1])
    modifiers = _modifiers(prop)
    is_static = "static" in modifiers
    accessor_names: list[str] = []
    accessor_list = _child(prop, "accessor_list")
    if accessor_list is not None:
        for accessor in accessor_list.named_children:
            accessor_name = next(
                (child.type for child in accessor.children if child.type in {"get", "set", "init"}),
                None,
            )
            if accessor_name is None:
                continue
            accessor_modifiers = {
                _text(child) for child in accessor.named_children if child.type == "modifier"
            }
            if not accessor_modifiers.intersection({"private", "protected", "internal"}):
                accessor_names.append(accessor_name)
    elif _child(prop, "arrow_expression_clause") is not None:
        accessor_names.append("get")
    public = "public" in modifiers or bool(accessor_names and "public" in modifiers)
    if not public and accessor_names:
        # A public accessor modifier can make an otherwise unmodified property public.
        public = any(
            accessor.type == "accessor_declaration"
            and any(child.type == "modifier" and _text(child) == "public" for child in accessor.named_children)
            for accessor in (accessor_list.named_children if accessor_list is not None else [])
        )
    pin_name, pin_unknown = _pin_name(attrs, name)
    return PropertyInfo(
        name=name,
        line=prop.start_point.row + 1,
        path=source_path,
        is_public=public,
        is_static=is_static,
        accessor_names=accessor_names,
        attributes=attrs,
        output_name=pin_name,
        output_unknown=pin_unknown,
    )


def _process_node_attribute(attributes: list[AttributeInfo]) -> AttributeInfo | None:
    return next((attr for attr in attributes if attr.name == "ProcessNode"), None)


def _process_node_settings(attr: AttributeInfo | None) -> tuple[str, bool | None]:
    if attr is None:
        return "NotProcessNode", None
    selection = attr.arguments.get("FragmentSelection", "Implicit")
    normalized_selection = (
        selection.removeprefix("<expression:").removesuffix(">") if selection is not None else None
    )
    if normalized_selection is None:
        selection_state = "Unknown"
    elif normalized_selection.endswith(".Explicit") or normalized_selection == "Explicit":
        selection_state = "Explicit"
    elif normalized_selection.endswith(".Implicit") or normalized_selection == "Implicit":
        selection_state = "Implicit"
    else:
        selection_state = "Unknown"
    state = attr.arguments.get("HasStateOutput", "false")
    state_value = True if state == "true" else False if state == "false" else None
    return selection_state, state_value


def _explicit_fragment_status(method: MethodInfo) -> tuple[bool, bool]:
    fragments = [attr for attr in method.attributes if attr.name == "Fragment"]
    if not fragments:
        return False, False
    hidden = any(attr.arguments.get("IsHidden") == "true" for attr in fragments)
    return not hidden, hidden


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _scan_roots(inputs: list[Path], include_examples: bool) -> tuple[list[Path], list[str]]:
    roots: list[Path] = []
    errors: list[str] = []
    for raw in inputs:
        path = raw.resolve()
        if not path.exists():
            errors.append(f"Input path does not exist: {path}")
            continue
        roots.append(path)
        if include_examples and path.is_dir() and path.name.lower() == "src":
            examples = path.parent / "examples"
            if examples.is_dir():
                roots.append(examples.resolve())
    unique = list(dict.fromkeys(roots))
    return unique, errors


def _source_files(roots: list[Path], excluded_dirs: set[str]) -> tuple[list[Path], list[str]]:
    files: set[Path] = set()
    errors: list[str] = []
    for root in roots:
        if root.is_file():
            if root.suffix.lower() == ".cs":
                files.add(root)
            else:
                errors.append(f"Input file is not C#: {root}")
            continue
        if not root.is_dir():
            errors.append(f"Input is not a file or directory: {root}")
            continue
        for current, dirs, names in os.walk(root, topdown=True, followlinks=False):
            dirs[:] = sorted(
                name
                for name in dirs
                if name.casefold() not in excluded_dirs and not name.startswith(".")
            )
            for name in names:
                lower = name.casefold()
                if not lower.endswith(".cs") or lower.endswith(GENERATED_SUFFIXES):
                    continue
                files.add((Path(current) / name).resolve())
    return sorted(files), errors


def _class_parts(root_node: Any, source_path: str) -> list[ClassPart]:
    results: list[ClassPart] = []

    def visit(node: Any, namespaces: tuple[str, ...], containers: tuple[str, ...]) -> None:
        if node.type == "compilation_unit":
            file_namespace = next(
                (child for child in node.named_children if child.type == "file_scoped_namespace_declaration"),
                None,
            )
            file_name = file_namespace.child_by_field_name("name") if file_namespace is not None else None
            file_parts = tuple(part for part in _text(file_name).split(".") if part)
            for child in node.named_children:
                if child is not file_namespace:
                    visit(child, namespaces + file_parts, containers)
            return

        if node.type in {"namespace_declaration", "file_scoped_namespace_declaration"}:
            name_node = node.child_by_field_name("name")
            if name_node is None:
                name_node = next((c for c in node.named_children if c.type not in {"declaration_list"}), None)
            names = tuple(part for part in _text(name_node).split(".") if part)
            combined = namespaces + names
            for child in node.named_children:
                if child is not name_node:
                    visit(child, combined, containers)
            return

        if node.type in TYPE_DECLARATIONS:
            name = _decl_name(node)
            identity = namespaces + containers + (name,)
            key = ".".join(identity)
            body = _child(node, "declaration_list")
            methods: list[MethodInfo] = []
            properties: list[PropertyInfo] = []
            nested: list[Any] = []
            if body is not None:
                for member in body.named_children:
                    if member.type == "method_declaration":
                        parsed = _parse_method(member, source_path)
                        if parsed is not None:
                            methods.append(parsed)
                    elif member.type == "property_declaration":
                        parsed_property = _parse_property(member, source_path)
                        if parsed_property is not None:
                            properties.append(parsed_property)
                    elif member.type in TYPE_DECLARATIONS:
                        nested.append(member)
            results.append(
                ClassPart(
                    key=key,
                    name=name,
                    path=source_path,
                    line=node.start_point.row + 1,
                    kind=node.type,
                    attributes=_attributes(node),
                    base_types=_base_types(node),
                    methods=methods,
                    properties=properties,
                )
            )
            for child in nested:
                visit(child, namespaces, containers + (name,))
            return

        for child in node.named_children:
            visit(child, namespaces, containers)

    visit(root_node, (), ())
    return results


def _syntax_findings(root_node: Any, path: str) -> list[dict[str, Any]]:
    errors = [node for node in _walk(root_node) if node.type == "ERROR" or node.is_missing]
    if not errors:
        return []
    return [
        {
            "severity": "error",
            "code": "csharp_parse_error",
            "path": path,
            "line": errors[0].start_point.row + 1,
            "column": errors[0].start_point.column + 1,
            "symbol": None,
            "message": "Tree-sitter could not parse one or more C# constructs in this file; findings for this file may be incomplete.",
            "details": {
                "parse_error_nodes": len(errors),
                "locations": [
                    {
                        "line": node.start_point.row + 1,
                        "column": node.start_point.column + 1,
                        "construct": _text(node)[:120],
                    }
                    for node in errors[:8]
                ],
                "truncated": len(errors) > 8,
            },
        }
    ]


def _factory_findings(root_node: Any, path: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for node in _walk(root_node):
        if node.type == "attribute":
            name, _ = _attribute_name(node)
            if name == "ProcessNodeFactory":
                findings.append(
                    {
                        "severity": "review",
                        "code": "factory_registration_unresolved",
                        "path": path,
                        "line": node.start_point.row + 1,
                        "column": node.start_point.column + 1,
                        "symbol": None,
                        "message": "A ProcessNodeFactory registration needs runtime/importer review; dynamic aliases and produced nodes are not resolved by this audit.",
                        "details": _text(node)[:200],
                    }
                )
        elif node.type in {"object_creation_expression", "implicit_object_creation_expression"}:
            type_node = node.child_by_field_name("type")
            if type_node is None:
                type_node = next((c for c in node.named_children if c.type not in {"argument_list", "initializer_expression"}), None)
            created_type = _text(type_node).split(".")[-1].removesuffix("Attribute")
            if created_type == "ProcessNode":
                findings.append(
                    {
                        "severity": "review",
                        "code": "dynamic_registration_unresolved",
                        "path": path,
                        "line": node.start_point.row + 1,
                        "column": node.start_point.column + 1,
                        "symbol": None,
                        "message": "A ProcessNodeAttribute is constructed in code; the generated registration surface is not statically resolved.",
                        "details": _text(node)[:200],
                    }
                )
    return findings


def _effective_methods(methods: list[MethodInfo], selection: str) -> list[MethodInfo]:
    selected: list[MethodInfo] = []
    for method in methods:
        if not method.is_public or method.is_static:
            continue
        _, hidden = _explicit_fragment_status(method)
        if hidden:
            continue
        if selection == "Explicit":
            includes, _ = _explicit_fragment_status(method)
            if not includes:
                continue
        selected.append(method)
    return selected


def _effective_properties(properties: list[PropertyInfo], selection: str) -> list[PropertyInfo]:
    selected: list[PropertyInfo] = []
    for prop in properties:
        if not prop.is_public or prop.is_static:
            continue
        fragments = [attr for attr in prop.attributes if attr.name == "Fragment"]
        hidden = any(attr.arguments.get("IsHidden") == "true" for attr in fragments)
        if hidden:
            continue
        if selection == "Explicit" and not fragments:
            continue
        selected.append(prop)
    return selected


def _finding(
    severity: str,
    code: str,
    path: str,
    line: int,
    symbol: str,
    message: str,
    details: Any = None,
) -> dict[str, Any]:
    result = {
        "severity": severity,
        "code": code,
        "path": path,
        "line": line,
        "symbol": symbol,
        "message": message,
    }
    if details is not None:
        result["details"] = details
    return result


def audit(
    inputs: list[Path],
    repo_root: Path | None = None,
    include_examples: bool = False,
    extra_excluded_dirs: Iterable[str] = (),
) -> dict[str, Any]:
    roots, root_errors = _scan_roots(inputs, include_examples)
    if repo_root is None:
        root_candidates = [p if p.is_dir() else p.parent for p in roots]
        try:
            repo_root = Path(os.path.commonpath([str(p) for p in root_candidates])).resolve()
        except (ValueError, OSError):
            repo_root = Path.cwd().resolve()
    else:
        repo_root = repo_root.resolve()

    excluded = set(DEFAULT_EXCLUDED_DIRS)
    excluded.update(name.casefold() for name in extra_excluded_dirs)
    files, file_errors = _source_files(roots, excluded)
    findings: list[dict[str, Any]] = []
    parse_error_files = 0
    all_parts: list[ClassPart] = []
    for message in root_errors + file_errors:
        findings.append(
            {
                "severity": "error",
                "code": "input_error",
                "path": None,
                "line": None,
                "symbol": None,
                "message": message,
            }
        )

    parser = Parser(Language(tree_sitter_c_sharp.language()))
    for source_file in files:
        relative = _relative(source_file, repo_root)
        raw = source_file.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]
        tree = parser.parse(raw)
        errors = _syntax_findings(tree.root_node, relative)
        if errors:
            parse_error_files += 1
            findings.extend(errors)
        findings.extend(_factory_findings(tree.root_node, relative))
        all_parts.extend(_class_parts(tree.root_node, relative))

    grouped: dict[str, list[ClassPart]] = {}
    for part in all_parts:
        grouped.setdefault(part.key, []).append(part)
    by_short_name: dict[str, list[str]] = {}
    for key, parts in grouped.items():
        by_short_name.setdefault(parts[0].name, []).append(key)

    node_inventory: list[dict[str, Any]] = []
    for key, parts in sorted(grouped.items()):
        process_attrs = [
            attr
            for part in parts
            for attr in part.attributes
            if attr.name == "ProcessNode"
        ]
        if not process_attrs:
            continue
        symbol = key
        location_part = parts[0]
        process_attr = process_attrs[0]
        selection, has_state_output = _process_node_settings(process_attr)
        methods = [method for part in parts for method in part.methods]
        properties = [prop for part in parts for prop in part.properties]
        public_methods = [method for method in methods if method.is_public]
        public_properties = [prop for prop in properties if prop.is_public]
        selected_methods = _effective_methods(methods, selection)
        selected_properties = _effective_properties(properties, selection)
        bases = sorted({base for part in parts for base in part.base_types})
        immutable_hint = any(
            part.kind in {"record_declaration", "struct_declaration"}
            or any(attr.name in {"Immutable", "ImmutableObject"} for attr in part.attributes)
            for part in parts
        )
        location = {"path": location_part.path, "line": location_part.line}

        node_inventory.append(
            {
                "symbol": symbol,
                "location": location,
                "partial_declarations": [
                    {"path": part.path, "line": part.line} for part in sorted(parts, key=lambda p: (p.path, p.line))
                ],
                "fragment_selection": selection,
                "has_state_output": has_state_output,
                "base_types": bases,
                "immutable_definition_hint": immutable_hint,
                "public_method_count": len(public_methods),
                "public_property_count": len(public_properties),
                "selected_public_methods": [
                    {
                        "name": method.name,
                        "path": method.path,
                        "line": method.line,
                        "return_type": method.return_type,
                        "returns_this": method.returns_this,
                        "return_is_state": method.return_is_state,
                        "output_names": method.output_names,
                        "output_names_unknown": method.output_names_unknown,
                    }
                    for method in selected_methods
                ],
                "selected_public_properties": [
                    {
                        "name": prop.name,
                        "path": prop.path,
                        "line": prop.line,
                        "accessors": prop.accessor_names,
                    }
                    for prop in selected_properties
                ],
            }
        )

        if len(process_attrs) > 1:
            findings.append(
                _finding(
                    "review",
                    "multiple_process_node_attributes",
                    location_part.path,
                    process_attr.line,
                    symbol,
                    "This partial type has more than one ProcessNode attribute; verify the compiler/importer view.",
                    [{"path": p.path, "line": a.line} for p in parts for a in p.attributes if a.name == "ProcessNode"],
                )
            )
        if selection == "Unknown":
            findings.append(
                _finding(
                    "review",
                    "fragment_selection_unresolved",
                    location_part.path,
                    process_attr.line,
                    symbol,
                    "FragmentSelection is computed or uses an unsupported expression; public fragment membership is unresolved.",
                    process_attr.arguments.get("FragmentSelection"),
                )
            )
        if has_state_output is None:
            findings.append(
                _finding(
                    "review",
                    "state_output_unresolved",
                    location_part.path,
                    process_attr.line,
                    symbol,
                    "HasStateOutput is computed or uses an unsupported expression.",
                    process_attr.arguments.get("HasStateOutput"),
                )
            )

        member_outputs: dict[str, list[dict[str, Any]]] = {}
        implicit_self_results: dict[str, list[MethodInfo]] = {}
        for method in selected_methods:
            method_outputs = list(method.output_names)
            if method.has_nonvoid_return and method.return_is_state:
                findings.append(
                    _finding(
                        "review",
                        "state_return_candidate",
                        method.path,
                        method.line,
                        f"{symbol}.{method.name}",
                        "The return pin is marked as state; its pin kind and collision behavior are importer-specific, so the audit excludes it from ordinary Result inference.",
                        {"return_type": method.return_type},
                    )
                )
            elif method.has_nonvoid_return and method.return_output_unknown:
                findings.append(
                    _finding(
                        "review",
                        "return_output_name_unresolved",
                        method.path,
                        method.line,
                        f"{symbol}.{method.name}",
                        "The method return may produce an output, but its name cannot be inferred safely from this syntax alone.",
                        {"return_type": method.return_type},
                    )
                )
            elif method.has_nonvoid_return and method.returns_this and method.return_output_name is None:
                if immutable_hint:
                    findings.append(
                        _finding(
                            "review",
                            "immutable_self_return_output_unresolved",
                            method.path,
                            method.line,
                            f"{symbol}.{method.name}",
                            "This self-return belongs to a record/struct/Immutable-hinted definition; the audit does not infer the ordinary mutable-class Result name.",
                            {"return_type": method.return_type},
                        )
                    )
                else:
                    method_outputs.append("Result")
                    implicit_self_results.setdefault("Result", []).append(method)

            if method.returns_this:
                findings.append(
                    _finding(
                        "review",
                        "self_return_candidate",
                        method.path,
                        method.line,
                        f"{symbol}.{method.name}",
                        "This selected public fragment returns this. Fluent self-returns can be valid; inspect its result/state pin kind and neighboring fragments.",
                        {"return_type": method.return_type, "output_names": method_outputs},
                    )
                )

            if method_outputs:
                duplicates = sorted({name for name in method_outputs if method_outputs.count(name) > 1})
                if duplicates:
                    findings.append(
                        _finding(
                            "error",
                            "duplicate_outputs_within_fragment",
                            method.path,
                            method.line,
                            f"{symbol}.{method.name}",
                            "The fragment declares output pins with the same statically known name.",
                            {"duplicate_names": duplicates, "output_names": method_outputs},
                        )
                    )
                for output_name in method_outputs:
                    member_outputs.setdefault(output_name, []).append(
                        {"kind": "method", "name": method.name, "path": method.path, "line": method.line}
                    )

        for prop in selected_properties:
            if prop.output_unknown:
                findings.append(
                    _finding(
                        "review",
                        "property_output_name_unresolved",
                        prop.path,
                        prop.line,
                        f"{symbol}.{prop.name}",
                        "The property is a selected public fragment, but its output name is dynamic or unresolved.",
                        {"accessors": prop.accessor_names},
                    )
                )
            elif prop.output_name:
                member_outputs.setdefault(prop.output_name, []).append(
                    {"kind": "property", "name": prop.name, "path": prop.path, "line": prop.line}
                )

        implicit = selection == "Implicit"
        public_updates = [m for m in selected_methods if m.name.startswith("Update")]
        canonical_updates = [m for m in public_updates if m.name == "Update"]
        extra_updates = [m for m in public_updates if m.name != "Update"]
        if len(canonical_updates) > 1:
            findings.append(
                _finding(
                    "review" if not implicit else "error",
                    "multiple_public_update_overloads",
                    canonical_updates[1].path,
                    canonical_updates[1].line,
                    symbol,
                    "More than one selected public Update overload exists; verify that the importer and node contract support this shape.",
                    [{"path": m.path, "line": m.line, "return_type": m.return_type} for m in canonical_updates],
                )
            )
        for method in extra_updates:
            findings.append(
                _finding(
                    "review",
                    "additional_public_update_method",
                    method.path,
                    method.line,
                    f"{symbol}.{method.name}",
                    "A selected public Update* helper can become another fragment under implicit selection; make it private/internal or explicitly select fragments unless the extra fragment is intentional.",
                    {"fragment_selection": selection, "return_type": method.return_type, "returns_this": method.returns_this},
                )
            )

        implicit_helpers = [
            method
            for method in selected_methods
            if implicit
            and method.name != "Update"
            and method.name not in LIFECYCLE_METHODS
            and not method.name.startswith("Update")
        ]
        implicit_property_helpers = selected_properties if implicit else []
        if implicit_helpers or implicit_property_helpers:
            helper_entries = [
                {"kind": "method", "name": m.name, "path": m.path, "line": m.line, "return_type": m.return_type}
                for m in implicit_helpers
            ] + [
                {
                    "kind": "property",
                    "name": prop.name,
                    "path": prop.path,
                    "line": prop.line,
                    "accessors": prop.accessor_names,
                }
                for prop in implicit_property_helpers
            ]
            first = helper_entries[0]
            findings.append(
                _finding(
                    "review",
                    "public_helpers_imported_implicitly",
                    first["path"],
                    first["line"],
                    symbol,
                    "Implicit selection can expose these public methods/properties as fragments; confirm each is intentional or restrict its visibility/selection.",
                    helper_entries,
                )
            )

        for output_name, colliding in member_outputs.items():
            unique_members = {(member["kind"], member["name"], member["path"], member["line"]) for member in colliding}
            if len(unique_members) < 2:
                continue
            same_default_self_result = (
                output_name == "Result"
                and implicit
                and not immutable_hint
                and len(implicit_self_results.get("Result", [])) == len(unique_members)
            )
            findings.append(
                _finding(
                    "error" if same_default_self_result else "review",
                    "duplicate_self_result_candidates" if same_default_self_result else "duplicate_output_name_candidates",
                    colliding[1]["path"],
                    colliding[1]["line"],
                    symbol,
                    (
                        "Multiple selected public fragments return this with the same inferred Result name; this is a likely duplicate-output/import-compilation hazard, not a runtime-confirmed failure."
                        if same_default_self_result
                        else "Selected public fragments/properties share a statically known output name; verify the importer's deduplication and each fragment's intended output contract."
                    ),
                    {"output_name": output_name, "members": colliding},
                )
            )

        # Inheritance is resolved only against source declarations in the scan.
        inherited_methods: list[MethodInfo] = []
        unresolved_bases: list[str] = []
        for base in bases:
            simple = _type_name_from_text(base)
            if simple in {"object", "ValueType", "Record"}:
                continue
            candidates = by_short_name.get(simple, [])
            if len(candidates) != 1:
                unresolved_bases.append(base)
                continue
            base_parts = grouped[candidates[0]]
            inherited_methods.extend(m for p in base_parts for m in p.methods if m.is_public)
        if unresolved_bases:
            findings.append(
                _finding(
                    "review",
                    "inheritance_unresolved",
                    location_part.path,
                    location_part.line,
                    symbol,
                    "Base types could not be resolved uniquely within the scanned source roots; inherited public fragment members are unknown.",
                    unresolved_bases,
                )
            )
        if inherited_methods:
            inherited_candidates = [m for m in inherited_methods if m.name.startswith("Update") or m.returns_this]
            if inherited_candidates:
                findings.append(
                    _finding(
                        "review",
                        "inherited_public_fragment_candidates",
                        location_part.path,
                        location_part.line,
                        symbol,
                        "A source-resolved base type declares public Update*/self-return methods; importer inheritance and override behavior need review.",
                        [{"name": m.name, "path": m.path, "line": m.line} for m in inherited_candidates],
                    )
                )

    # Keep identical reports from duplicate roots/factory syntax from duplicating output.
    dedupe: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in findings:
        key = (item.get("severity"), item.get("code"), item.get("path"), item.get("line"), item.get("symbol"))
        dedupe.setdefault(key, item)
    findings = sorted(
        dedupe.values(),
        key=lambda item: (
            item.get("path") or "",
            item.get("line") or 0,
            item.get("severity") or "",
            item.get("code") or "",
        ),
    )
    counts = {
        severity: sum(item["severity"] == severity for item in findings)
        for severity in ("error", "review", "info")
    }
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope": {
            "roots": [_relative(root, repo_root) for root in roots],
            "include_examples": include_examples,
            "excluded_directories": sorted(excluded),
            "source_files": len(files),
            "parse_error_files": parse_error_files,
        },
        "summary": {
            "process_nodes": len(node_inventory),
            "findings": counts,
            "total_findings": len(findings),
        },
        "static_limitations": [
            "Findings are static candidates, not proof of vvvv runtime/importer behavior.",
            "Only ProcessNode and ProcessNodeFactory declarations visible in parsed C# syntax are recognized; aliases, generated registrations, external assemblies and runtime factories may be unresolved.",
            "Inheritance is resolved only when exactly one matching base declaration is present in scanned source roots.",
            "Automatic result-pin naming is inferred only for direct self-returns and explicit Pin names; other return naming is importer-dependent.",
        ],
        "nodes": node_inventory,
        "findings": findings,
    }


def _type_name_from_text(raw: str) -> str:
    value = raw.strip().removeprefix("global::").rstrip("?")
    value = value.split("<", 1)[0].strip()
    return value.split(".")[-1].strip()


def _arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit C# ProcessNode fragment/output candidates with tree-sitter.",
        epilog=(
            "Static audit only: it does not load vvvv or prove runtime importer behavior. "
            "Pass src directories for a package audit; --include-examples adds sibling examples directories."
        ),
    )
    parser.add_argument("paths", nargs="+", type=Path, help="C# file/directory roots to audit")
    parser.add_argument("--repo-root", type=Path, help="root used to make report paths relative")
    parser.add_argument("--include-examples", action="store_true", help="when a path ends in src, also scan its sibling examples directory")
    parser.add_argument("--exclude-dir", action="append", default=[], help="additional directory name to prune (repeatable)")
    parser.add_argument("--json-out", type=Path, help="write the full report as UTF-8 JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _arg_parser().parse_args(argv)
    report = audit(args.paths, args.repo_root, args.include_examples, args.exclude_dir)
    summary = report["summary"]
    print(
        f"C# files: {report['scope']['source_files']} | ProcessNode classes: {summary['process_nodes']} | "
        f"findings: {summary['findings']['error']} error, {summary['findings']['review']} review"
    )
    for item in report["findings"]:
        where = item.get("path") or "<input>"
        if item.get("line") is not None:
            where += f":{item['line']}"
        symbol = f" [{item['symbol']}]" if item.get("symbol") else ""
        print(f"{item['severity'].upper()} {item['code']} {where}{symbol}: {item['message']}")
        if item.get("details") is not None:
            print(f"  {json.dumps(item['details'], ensure_ascii=False)}")
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"JSON report: {_relative(args.json_out, Path.cwd())}")
    return 1 if summary["findings"]["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
