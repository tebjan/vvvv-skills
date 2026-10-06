"""Small explicit CLI for agents and release validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .document import VlDocument, serialize_diagnostics
from .catalog import JsonNodeCatalog
from .operations import capabilities
from .session import PatchSession


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vlpatch", description="Inspect and safely manipulate vvvv gamma .vl files")
    sub = parser.add_subparsers(dest="command", required=True)
    discover = sub.add_parser("capabilities")
    discover.add_argument("operations", nargs="*")
    edit = sub.add_parser("edit", help="Apply the same semantic JSON batch as vl_edit")
    edit.add_argument("path", type=Path)
    edit.add_argument("--operations", type=Path, required=True)
    edit.add_argument("--catalog", type=Path)
    edit.add_argument("--output", type=Path)
    for name in ("view", "preview", "check", "canvases"):
        command = sub.add_parser(name)
        command.add_argument("path", type=Path)
        command.add_argument("--canvas")
        if name == "view":
            command.add_argument("--level", default="summary")
        if name == "preview":
            command.add_argument("--output", type=Path, required=True)
    for name in ("inspect", "validate", "find-orphans"):
        command = sub.add_parser(name)
        command.add_argument("path", type=Path)
        command.add_argument("--json", action="store_true")
    clone = sub.add_parser("clone-subgraph")
    clone.add_argument("path", type=Path)
    clone.add_argument("--ids", nargs="+", required=True)
    clone.add_argument("--output", type=Path, required=True)
    clone.add_argument("--dx", type=float, default=0)
    clone.add_argument("--dy", type=float, default=0)
    apply = sub.add_parser("apply")
    apply.add_argument("path", type=Path)
    apply.add_argument("--output", type=Path)
    apply.add_argument("--rename", nargs=2, metavar=("ID", "NAME"))
    apply.add_argument("--set-pad-value", nargs=2, metavar=("ID", "VALUE"))
    apply.add_argument("--move", nargs=3, metavar=("ID", "X", "Y"))
    apply.add_argument("--remove-incomplete-links", action="store_true")
    apply.add_argument("--connect", nargs=2, metavar=("SOURCE_ID", "TARGET_ID"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "capabilities":
        print(json.dumps(capabilities(args.operations or None), indent=2))
        return 0
    if args.command == "edit":
        catalog = JsonNodeCatalog.load(args.catalog) if args.catalog else None
        session = PatchSession.load(args.path, catalog=catalog)
        operations = json.loads(args.operations.read_text(encoding="utf-8"))
        if not isinstance(operations, list):
            raise ValueError("operations file must contain a JSON array")
        result = session.edit_batch(operations)
        result["saved"] = str(session.save(args.output))
        print(json.dumps(result, indent=2))
        return 0
    if args.command in {"view", "preview", "check", "canvases"}:
        # File-only CLI and MCP reuse the exact same scoped inspection adapter.
        from .server import PatchServerCore
        core = PatchServerCore()
        try:
            handle = core.open(args.path)["handle"]
            if args.command == "canvases":
                result = core.canvases(handle)
            elif args.command == "preview":
                result = core.preview(handle, path=args.output, canvas=args.canvas)
            elif args.command == "view":
                result = core.view(handle, level=args.level, canvas=args.canvas)
            else:
                result = core.check(handle, canvas=args.canvas)
            print(json.dumps(result, indent=2))
            return 0 if args.command != "check" or result["structural"]["ok"] else 1
        finally:
            core.close()
    document = VlDocument.load(args.path)
    graph = document.graph()
    if args.command == "inspect":
        payload = {
            "path": str(args.path),
            "document_id": document.root.get("Id"),
            "nodes": len(graph.nodes),
            "operational_nodes": len(graph.operational_nodes()),
            "pins": len(graph.pins),
            "pads": len(graph.pads),
            "links": len(graph.links),
            "dependencies": [item.get("Location") for item in document.root if item.tag in {"NugetDependency", "DocumentDependency", "PlatformDependency", "ProjectDependency"}],
            "orphans": [{"id": node.get("Id"), "name": graph.node_name(node)} for node in graph.orphan_operational_nodes()],
        }
        print(json.dumps(payload, indent=2) if args.json else "\n".join(f"{key}: {value}" for key, value in payload.items()))
        return 0
    if args.command == "validate":
        report = graph.validate()
        if args.json:
            print(json.dumps({"ok": report.ok, "diagnostics": serialize_diagnostics(report)}, indent=2))
        else:
            for diagnostic in report.diagnostics:
                print(f"{diagnostic.severity}: {diagnostic.code}: {diagnostic.message}")
            print("valid" if report.ok else "invalid")
        return 0 if report.ok else 1
    if args.command == "find-orphans":
        orphans = graph.orphan_operational_nodes()
        payload = [{"id": node.get("Id"), "name": graph.node_name(node), "bounds": node.get("Bounds")} for node in orphans]
        print(json.dumps(payload, indent=2) if args.json else "\n".join(f"{item['id']} {item['name']} {item['bounds']}" for item in payload))
        return 0
    if args.command == "clone-subgraph":
        graph.clone_subgraph(args.ids, dx=args.dx, dy=args.dy)
        document.write_atomic(args.output)
        return 0
    if args.command == "apply":
        if args.remove_incomplete_links:
            graph.remove_incomplete_links()
        if args.connect:
            graph.ensure_link(args.connect[0], args.connect[1])
        if args.rename:
            graph.rename(args.rename[0], args.rename[1])
        if args.set_pad_value:
            graph.set_pad_value(args.set_pad_value[0], args.set_pad_value[1])
        if args.move:
            graph.move(args.move[0], float(args.move[1]), float(args.move[2]))
        document.write_atomic(args.output or args.path)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
