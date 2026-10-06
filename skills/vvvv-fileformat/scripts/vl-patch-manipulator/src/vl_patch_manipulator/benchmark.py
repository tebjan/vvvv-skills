"""Small no-respawn benchmark for the persistent session path."""

from __future__ import annotations

import argparse
from pathlib import Path
import tempfile
import time

from .catalog import InMemoryNodeCatalog, NodeSpec, PinSpec
from .server import PatchServerCore
from .session import PatchSession


def _time(call):
    start = time.perf_counter()
    result = call()
    return (time.perf_counter() - start) * 1000.0, result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m vl_patch_manipulator.benchmark")
    parser.add_argument("path", type=Path, nargs="?", default=None)
    args = parser.parse_args(argv)
    if args.path is not None:
        return _run(args.path)
    # A standalone public fixture; never depend on a private checkout or mutate
    # a user's saved patch to benchmark the edit/notification path.
    with tempfile.TemporaryDirectory(prefix="vlpatch-benchmark-") as folder:
        catalog = InMemoryNodeCatalog((NodeSpec(
            "Relay", inputs=(PinSpec("Input", "Float32"),),
            outputs=(PinSpec("Output", "Float32", "OutputPin"),),
        ),))
        fixture = PatchSession.new(catalog=catalog)
        relay = fixture.add_node("Relay", x=100, y=200)
        pad = fixture.add_pad(value="1", type_name="Float32", x=100, y=120)
        fixture.connect(pad, f"{relay}.Input")
        path = fixture.save(Path(folder) / "Benchmark.vl")
        return _run(path)


def _run(path: Path) -> int:
    open_ms, session = _time(lambda: PatchSession.load(path))
    describe_ms, _ = _time(lambda: session.describe(level="summary"))
    validate_ms, report = _time(lambda: session.validate(include_orphan_warnings=False))
    # Exercise the hot in-memory edit path without writing the user's file.
    first_node = next((node for node in session.graph.operational_nodes() if node.get("Id")), None)
    first_input = next((pin for pin in first_node.findall("Pin") if pin.get("Kind") == "InputPin"), None) if first_node is not None else None
    if first_node is not None and first_input is not None:
        node_alias = session.alias_for(first_node.get("Id", ""))
        input_name = first_input.get("Name", "")
        def add_and_connect() -> None:
            pad = session.add_pad(value="0", x=10, y=10, type_name="Float32")
            session.connect(pad, f"{node_alias}.{input_name}")
        edit_ms, _ = _time(add_and_connect)
        edit_validate_ms, _ = _time(lambda: session.validate(include_orphan_warnings=False))
        session.undo()
        session.undo()
    else:
        edit_ms = edit_validate_ms = 0.0

    # The server's bounded change feed is the same path an MCP client uses.
    server = PatchServerCore(poll_seconds=0.05)
    try:
        opened = server.open(path)
        handle = opened["handle"]
        revision = opened["revision"]
        notify_ms, _ = _time(lambda: (server.edit(handle, [{"op": "add_comment", "text": "benchmark"}], expected_revision=revision), server.changes(handle, since_revision=revision)))
    finally:
        server.close()
    print(f"path={path}")
    print(f"nodes={len(session.graph.nodes)} links={len(session.graph.links)} annotations={len(session.graph.annotations())}")
    print(f"open_ms={open_ms:.3f} describe_ms={describe_ms:.3f} validate_ms={validate_ms:.3f} valid={report.ok}")
    print(f"add_connect_ms={edit_ms:.3f} post_edit_validate_ms={edit_validate_ms:.3f} change_feed_ms={notify_ms:.3f}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
