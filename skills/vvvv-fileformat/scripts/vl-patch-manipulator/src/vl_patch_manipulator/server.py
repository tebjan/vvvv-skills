"""Persistent local MCP server for vvvv patch editing.

The server owns hot :class:`PatchSession` instances. Agents use the compact
tools at the bottom of this module; they never need to generate
Python or exchange raw XML.  The core is transport-independent so tests and
other local clients can use :class:`PatchServerCore` directly.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
from typing import Any, Iterable

from .catalog import JsonNodeCatalog, NodeCatalog
from .document import VlDocument
from .session import PatchSession
from .operations import apply_operation, capabilities, resolve_canvas


@dataclass
class _LivePatch:
    handle: str
    path: Path
    session: PatchSession
    revision: int = 0
    last_disk_hash: str = ""
    last_saved_model: bytes = b""
    changed: list[dict[str, Any]] = field(default_factory=list)
    conflict: str | None = None


class VvvvBridgeProvider:
    """Optional live-vvvv boundary.

    The initial implementation is intentionally file-only.  A future HDE
    adapter can implement ``check`` and ``reload`` without changing tool
    schemas.  Structural diagnostics and live compiler diagnostics remain
    separate in the response.
    """

    def check(self, path: Path) -> dict[str, Any]:
        return {"available": False, "path": str(path), "diagnostics": [], "message": "no live vvvv bridge configured"}


class PatchServerCore:
    """Thread-safe session registry, revision log and debounced file watcher."""

    def __init__(self, *, catalog: NodeCatalog | None = None, bridge: VvvvBridgeProvider | None = None, poll_seconds: float = 0.25):
        self.catalog = catalog
        self.bridge = bridge or VvvvBridgeProvider()
        self._sessions: dict[str, _LivePatch] = {}
        self._counter = 1
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._stop = threading.Event()
        self._poll_seconds = poll_seconds
        self._watcher = threading.Thread(target=self._watch_loop, name="vlpatch-file-watch", daemon=True)
        self._watcher.start()

    def close(self) -> None:
        self._stop.set()
        self._watcher.join(timeout=1.0)

    @staticmethod
    def _file_hash(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _get(self, handle: str) -> _LivePatch:
        try:
            return self._sessions[handle]
        except KeyError as exc:
            raise KeyError(f"unknown patch handle: {handle}") from exc

    def open(self, path: str | Path, *, handle: str | None = None, catalog_path: str | Path | None = None) -> dict[str, Any]:
        file_path = Path(path).resolve()
        with self._lock:
            for live in self._sessions.values():
                if live.path == file_path:
                    return self._open_result(live)
            active_catalog = self.catalog
            if catalog_path:
                active_catalog = JsonNodeCatalog.load(catalog_path)
            document = VlDocument.load(file_path)
            session = PatchSession(document, catalog=active_catalog)
            session_handle = handle or f"patch-{self._counter}"
            self._counter += 1
            live = _LivePatch(session_handle, file_path, session, last_disk_hash=self._file_hash(file_path), last_saved_model=session.document.to_bytes())
            self._sessions[session_handle] = live
            return self._open_result(live)

    def close_session(self, handle: str, *, discard: bool = False) -> dict[str, Any]:
        with self._lock:
            live = self._get(handle)
            if not discard and live.session.document.to_bytes() != live.last_saved_model:
                raise RuntimeError("session has unsaved edits; save first or explicitly discard")
            self._sessions.pop(handle)
            return {"handle": handle, "closed": True, "revision": live.revision}

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            return [self._open_result(live) for live in self._sessions.values()]

    def canvases(self, handle: str) -> list[dict[str, Any]]:
        with self._lock:
            return self._get(handle).session.canvases()

    def _open_result(self, live: _LivePatch) -> dict[str, Any]:
        overview = live.session.describe(level="summary")
        return {
            "handle": live.handle,
            "path": str(live.path),
            "revision": live.revision,
            "nodes": len(overview["nodes"]),
            "links": len(overview["links"]),
            "dependencies": len(overview["dependencies"]),
            "diagnostic_count": len(overview["diagnostics"]),
            "conflict": live.conflict,
        }

    def view(self, handle: str, *, level: str = "summary", focus: Iterable[str] | None = None, region: tuple[float, float, float, float] | None = None, canvas: str | None = None) -> dict[str, Any]:
        with self._lock:
            live = self._get(handle)
            scope = resolve_canvas(live.session, canvas)
            if scope is not None:
                value = live.session.spatial_snapshot(canvas=scope)
                return {**value, "handle": handle, "revision": live.revision,
                        "scope": scope.get("Id"), "conflict": live.conflict}
            if level == "spatial":
                value = live.session.spatial_snapshot()
                value["handle"] = handle
                value["revision"] = live.revision
                value["conflict"] = live.conflict
                return value
            if level == "layout":
                value = live.session.layout_intent(focus)
                value["handle"] = handle
                value["revision"] = live.revision
                value["spatial"] = live.session.layout_analysis()
                value["conflict"] = live.conflict
                return value
            value = live.session.describe(level=level, focus=focus)
            if region is not None:
                x, y, width, height = region
                filtered = []
                for node in value["nodes"]:
                    bounds = node.get("bounds", "").split(",")
                    try:
                        nx, ny = float(bounds[0]), float(bounds[1])
                    except (ValueError, IndexError):
                        continue
                    if x <= nx <= x + width and y <= ny <= y + height:
                        filtered.append(node)
                value["nodes"] = filtered
            value["handle"] = handle
            value["revision"] = live.revision
            value["conflict"] = live.conflict
            return value

    def catalog_search(self, query: str, *, handle: str | None = None, category: str | None = None, exact: bool = False, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            active_catalog = self._get(handle).session.catalog if handle else self.catalog
        if active_catalog is None:
            return []
        specs = []
        if exact:
            spec = active_catalog.resolve(query, category=category)
            if spec is not None:
                specs.append(spec)
        else:
            specs = active_catalog.search(query, category=category, limit=limit)
        return [self._spec_json(spec, detail=exact) for spec in specs]

    @staticmethod
    def _spec_json(spec, *, detail: bool) -> dict[str, Any]:
        result = {"name": spec.name, "full_name": spec.full_name, "category": spec.category, "kind": spec.kind, "dependency": spec.dependency, "summary": spec.summary}
        if detail:
            result["inputs"] = [PatchServerCore._pin_json(pin) for pin in spec.inputs]
            result["outputs"] = [PatchServerCore._pin_json(pin) for pin in spec.outputs]
        else:
            result["inputs"] = [pin.name for pin in spec.inputs]
            result["outputs"] = [pin.name for pin in spec.outputs]
        return result

    @staticmethod
    def _pin_json(pin) -> dict[str, Any]:
        return {"name": pin.name, "type": pin.type_name, "kind": pin.kind, "default": pin.default_value, "hidden": pin.hidden, "optional": pin.optional, "state": pin.state}

    def edit(self, handle: str, operations: list[dict[str, Any]], *, expected_revision: int | None = None) -> dict[str, Any]:
        with self._lock:
            live = self._get(handle)
            self._check_revision(live, expected_revision)
            if live.conflict:
                raise RuntimeError(live.conflict)
            before = live.session.describe(level="summary")
            spatial_before = self._spatial_metrics(live.session)
            results = live.session.edit_batch(operations)
            live.revision += 1
            after = live.session.describe(level="summary")
            spatial_after = self._spatial_metrics(live.session)
            diff = self._compact_diff(before, after)
            self._record(live, "tool", diff)
            return {
                "handle": handle,
                "revision": live.revision,
                "changed": diff,
                **results,
                "spatial": {"before": spatial_before, "after": spatial_after},
                "diagnostics": self._compact_diagnostics(live.session.validate()),
            }

    @staticmethod
    def _apply_operation(session: PatchSession, operation: dict[str, Any]) -> Any:
        return apply_operation(session, operation)

    @staticmethod
    def _compact_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        before_ids = {item["id"] for item in before["nodes"]}
        after_ids = {item["id"] for item in after["nodes"]}
        before_annotations = {item["id"] for item in before.get("annotations", [])}
        after_annotations = {item["id"] for item in after.get("annotations", [])}
        before_links = {(item["ids"][0], item["ids"][1]) for item in before["links"]}
        after_links = {(item["ids"][0], item["ids"][1]) for item in after["links"]}
        before_bounds = {item["id"]: item.get("bounds") for item in before["nodes"]}
        moved_nodes = [
            item["alias"]
            for item in after["nodes"]
            if item["id"] in before_bounds and item.get("bounds") != before_bounds[item["id"]]
        ]
        return {
            "added_nodes": [item["alias"] for item in after["nodes"] if item["id"] not in before_ids],
            "removed_nodes": [item["alias"] for item in before["nodes"] if item["id"] not in after_ids],
            "added_annotations": [item["alias"] for item in after.get("annotations", []) if item["id"] not in before_annotations],
            "removed_annotations": [item["alias"] for item in before.get("annotations", []) if item["id"] not in after_annotations],
            "added_links": [list(item) for item in after_links - before_links],
            "removed_links": [list(item) for item in before_links - after_links],
            "moved_nodes": moved_nodes,
            "node_count": len(after["nodes"]),
            "link_count": len(after["links"]),
        }

    @staticmethod
    def _compact_diagnostics(report) -> list[dict[str, Any]]:
        return [{"severity": item.severity, "code": item.code, "message": item.message, "id": item.element_id} for item in report.diagnostics]

    @staticmethod
    def _spatial_metrics(session: PatchSession) -> dict[str, int]:
        analysis = session.layout_analysis()
        return {
            "overlaps": len(analysis["overlaps"]),
            "annotation_overlaps": len(analysis["annotation_overlaps"]),
            "upward_links": len(analysis["upward_links"]),
            "long_links": len(analysis["long_links"]),
            "crossings": int(analysis["crossings"]),
        }

    @staticmethod
    def _check_revision(live: _LivePatch, expected: int | None) -> None:
        if expected is not None and expected != live.revision:
            raise RuntimeError(f"stale patch revision: expected {expected}, current {live.revision}")

    def check(self, handle: str, *, compile: bool = False, canvas: str | None = None) -> dict[str, Any]:
        with self._lock:
            live = self._get(handle)
            report = live.session.validate()
            result = {
                "handle": handle,
                "revision": live.revision,
                "structural": {"ok": report.ok, "diagnostics": self._compact_diagnostics(report)},
                "spatial": live.session.layout_analysis(canvas=resolve_canvas(live.session, canvas)),
                "orphans": live.session.find_orphans(),
            }
            if compile:
                result["vvvv"] = self.bridge.check(live.path)
            return result

    def preview(self, handle: str, *, path: str | Path | None = None, canvas: str | None = None) -> dict[str, Any]:
        """Render the current canvas to SVG and return exact spatial diagnostics."""

        with self._lock:
            live = self._get(handle)
            if path is None:
                preview_root = Path(tempfile.gettempdir()) / "vlpatch-previews"
                destination = preview_root / f"{handle}-r{live.revision}.svg"
            else:
                destination = Path(path).resolve()
            scope = resolve_canvas(live.session, canvas)
            rendered = live.session.render_svg(destination, canvas=scope)
            return {
                "handle": handle,
                "revision": live.revision,
                "path": str(rendered),
                "spatial": live.session.layout_analysis(canvas=scope),
            }

    def save(self, handle: str, *, expected_revision: int | None = None, path: str | Path | None = None) -> dict[str, Any]:
        with self._lock:
            live = self._get(handle)
            self._check_revision(live, expected_revision)
            if live.conflict:
                raise RuntimeError(live.conflict)
            current_disk = self._file_hash(live.path)
            if current_disk != live.last_disk_hash and path is None:
                live.conflict = "file changed on disk since open/save; reload or resolve before saving"
                raise RuntimeError(live.conflict)
            destination = live.session.save(path)
            live.last_disk_hash = self._file_hash(destination)
            live.last_saved_model = live.session.document.to_bytes()
            live.conflict = None
            live.revision += 1
            self._record(live, "save", {"path": str(destination)})
            return {"handle": handle, "revision": live.revision, "saved": str(destination)}

    def changes(self, handle: str, since_revision: int = 0, wait_ms: int = 0) -> dict[str, Any]:
        deadline = time.monotonic() + max(0, min(wait_ms, 60000)) / 1000.0
        with self._condition:
            live = self._get(handle)
            while live.revision <= since_revision and time.monotonic() < deadline:
                self._condition.wait(timeout=max(0.01, deadline - time.monotonic()))
            events = [item for item in live.changed if item["revision"] > since_revision]
            return {"handle": handle, "revision": live.revision, "events": events, "conflict": live.conflict}

    def _record(self, live: _LivePatch, kind: str, changed: dict[str, Any]) -> None:
        live.changed.append({"revision": live.revision, "kind": kind, "changed": changed})
        del live.changed[:-500]
        self._condition.notify_all()

    def _watch_loop(self) -> None:
        while not self._stop.wait(self._poll_seconds):
            with self._condition:
                for live in tuple(self._sessions.values()):
                    try:
                        current_hash = self._file_hash(live.path)
                    except OSError:
                        continue
                    if current_hash == live.last_disk_hash:
                        continue
                    try:
                        candidate = VlDocument.load(live.path)
                        report = candidate.validate(include_orphan_warnings=False)
                        if not report.ok:
                            continue
                    except Exception:
                        continue
                    if live.session.document.to_bytes() != live.last_saved_model:
                        live.conflict = "external file changed while this session has unsaved edits"
                        live.last_disk_hash = current_hash
                        live.revision += 1
                        self._record(live, "conflict", {"message": live.conflict})
                        continue
                    before = live.session.describe(level="summary")
                    live.session.replace_document(candidate)
                    live.last_disk_hash = current_hash
                    live.last_saved_model = live.session.document.to_bytes()
                    live.conflict = None
                    live.revision += 1
                    after = live.session.describe(level="summary")
                    self._record(live, "external", self._compact_diff(before, after))


def build_mcp_server(core: PatchServerCore):
    """Build a FastMCP server exposing compact patch and spatial tools."""

    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("vlpatch-server", instructions="Persistent, BOM-free vvvv gamma patch editing with exact catalog and revision safety.")

    @mcp.tool(name="vl_capabilities", description="Discover supported semantic edit operations and their exact arguments. Use 'as' and $result.field for same-batch builder IDs; Python, MCP and CLI share this contract.")
    def vl_capabilities(operations: list[str] | None = None) -> dict[str, Any]:
        return capabilities(operations)

    @mcp.tool(name="vl_sessions", description="List currently open patch handles and revisions.")
    def vl_sessions() -> list[dict[str, Any]]:
        return core.list_sessions()

    @mcp.tool(name="vl_canvases", description="Discover Process canvases, owning Patch IDs, signature endpoints and Slots for scoped edits/previews.")
    def vl_canvases(handle: str) -> list[dict[str, Any]]:
        return core.canvases(handle)

    @mcp.tool(name="vl_close", description="Release an editor session without saving or closing vvvv. Unsaved model edits are discarded only when discard=True.")
    def vl_close(handle: str, discard: bool = False) -> dict[str, Any]:
        return core.close_session(handle, discard=discard)

    @mcp.tool(name="vl_open", description="Open or reuse a .vl session and return a handle plus tiny overview.")
    def vl_open(path: str, handle: str | None = None, catalog_path: str | None = None) -> dict[str, Any]:
        return core.open(path, handle=handle, catalog_path=catalog_path)

    @mcp.tool(name="vl_view", description="Return a compact semantic/spatial view; use focus or region to limit tokens.")
    def vl_view(handle: str, level: str = "summary", focus: list[str] | None = None, region: list[float] | None = None, canvas: str | None = None) -> dict[str, Any]:
        parsed_region = tuple(region) if region and len(region) == 4 else None
        return core.view(handle, level=level, focus=focus, region=parsed_region, canvas=canvas)

    @mcp.tool(name="vl_catalog", description="Search or exact-lookup catalog nodes and their pins/dependencies; unknown additions are refused.")
    def vl_catalog(query: str, handle: str | None = None, category: str | None = None, exact: bool = False, limit: int = 20) -> list[dict[str, Any]]:
        return core.catalog_search(query, handle=handle, category=category, exact=exact, limit=limit)

    @mcp.tool(name="vl_edit", description="Apply atomic semantic edits including Process creation, Slots, local input placements, closed-subgraph moves and saved reference rebinding. Call vl_capabilities for arguments; name results with 'as' and reuse $name.field in this batch. Returns IDs/results with revision and diagnostics.")
    def vl_edit(handle: str, operations: list[dict[str, Any]], expected_revision: int | None = None) -> dict[str, Any]:
        return core.edit(handle, operations, expected_revision=expected_revision)

    @mcp.tool(name="vl_check", description="Run structural validation and optionally query a configured live-vvvv bridge.")
    def vl_check(handle: str, compile: bool = False, canvas: str | None = None) -> dict[str, Any]:
        return core.check(handle, compile=compile, canvas=canvas)

    @mcp.tool(name="vl_preview", description="Render a BOM-free SVG canvas preview and return overlap, flow and crossing diagnostics.")
    def vl_preview(handle: str, path: str | None = None, canvas: str | None = None) -> dict[str, Any]:
        return core.preview(handle, path=path, canvas=canvas)

    @mcp.tool(name="vl_changes", description="Wait for compact revisioned tool/external changes without reloading the patch.")
    def vl_changes(handle: str, since_revision: int = 0, wait_ms: int = 0) -> dict[str, Any]:
        return core.changes(handle, since_revision=since_revision, wait_ms=wait_ms)

    @mcp.tool(name="vl_save", description="Write the session's edits to disk, BOM-free and atomic; refuses when the file changed on disk since open or the last save.")
    def vl_save(handle: str, expected_revision: int | None = None, path: str | None = None) -> dict[str, Any]:
        return core.save(handle, expected_revision=expected_revision, path=path)

    return mcp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vlpatch-server")
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    catalog = JsonNodeCatalog.load(args.catalog) if args.catalog else None
    core = PatchServerCore(catalog=catalog)
    try:
        mcp = build_mcp_server(core)
        if args.transport == "streamable-http":
            mcp.settings.host = args.host
            mcp.settings.port = args.port
        mcp.run(transport=args.transport)
    finally:
        core.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
