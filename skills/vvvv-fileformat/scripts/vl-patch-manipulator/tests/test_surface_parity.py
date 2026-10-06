from __future__ import annotations

import ast
import asyncio
import inspect
import json
from pathlib import Path

import anyio
from mcp import ClientSession
import pytest

from vl_patch_manipulator.cli import main
from vl_patch_manipulator.document import VlDocument
from vl_patch_manipulator.operations import METHODS, capabilities
from vl_patch_manipulator.server import PatchServerCore, build_mcp_server
from vl_patch_manipulator.session import PatchSession

from test_framework import FIXTURE


def batch() -> list[dict]:
    return [
        {"op": "add_process", "name": "LocalDemo", "alias": "demo", "as": "helper",
         "inputs": [{"name": "Value", "type_name": "Float32"}],
         "outputs": [{"name": "Output", "type_name": "Float32"}]},
        {"op": "add_input_placement", "existing_input": "$helper.inputs.Value",
         "position": [260, 180], "patch": "$helper.body", "as": "local"},
        {"op": "add_slot", "name": "Shared", "type_name": "Float32",
         "patch": "$helper.body", "as": "slot"},
        {"op": "add_slot_read", "existing_slot": "$slot.slot_id",
         "position": [260, 350], "patch": "$helper.body", "as": "read"},
        {"op": "connect", "source": "$local", "target": "$slot.write_pad"},
        {"op": "connect", "source": "$read", "target": "$helper.outputs.Output"},
        {"op": "set_placement_position", "target": "$local", "x": 261, "y": 181},
        {"op": "add_pad", "value": "1", "type": "Float32", "as": "constant"},
        {"op": "move_subgraph", "ids": ["$constant"], "canvas": "$helper.body", "dx": 10, "dy": 20},
        {"op": "add_comment", "text": "Local controls", "patch": "$helper.body", "as": "note"},
        {"op": "add_region", "text": "Demo", "patch": "$helper.body", "as": "region"},
        {"op": "fit_region", "region": "$region", "targets": ["$constant"], "top_padding": 50},
        {"op": "add_slot", "name": "Obsolete", "patch": "$helper.body", "as": "obsolete"},
        {"op": "connect", "source": "$local", "target": "$obsolete.write_pad"},
        {"op": "remove_slot", "existing_slot": "$obsolete.slot_id",
         "accessor_ids": ["$obsolete.read_pad", "$obsolete.write_pad"], "as": "removed_slot"},
    ]


def assert_semantics(session: PatchSession, result: dict) -> None:
    named = result["named"]
    helper = named["helper"]
    body = session.graph.element(helper["body"])
    local = session.graph.element(named["local"])
    assert local.getparent() is body
    assert local.get("Bounds") == "261,181"
    assert len(session.graph.element(helper["update_inputs"]["Value"]).getparent().findall("Pin[@Kind='InputPin']")) == 1
    slot = named["slot"]["slot_id"]
    assert session.graph.element(named["read"]).get("SlotId") == slot
    assert session.graph.element(named["slot"]["write_pad"]).get("SlotId") == slot
    assert named["removed_slot"]["slot"] not in session.graph.by_id
    assert all(identifier not in session.graph.by_id for identifier in named["removed_slot"]["accessors"])
    assert len(named["removed_slot"]["links"]) == 1
    assert session.graph.element(session._resolve_entity_id(named["constant"])).getparent() is body
    assert session.node("0000000000000000000009").get("Bounds") == "100,200,50,19"
    assert b'FutureThing custom="keep"' in session.document.to_bytes()
    assert not session.document.to_bytes().startswith(b"\xef\xbb\xbf")
    assert session.validate(include_orphan_warnings=False).ok
    assert any(item["id"] == helper["body"] for item in session.canvases())
    json.dumps(result)


def test_every_public_mutation_is_exposed_and_arguments_follow_python() -> None:
    tree = ast.parse(inspect.getsource(PatchSession))
    mutations = {node.name for node in tree.body[0].body if isinstance(node, ast.FunctionDef)
                 and not node.name.startswith("_") and any(
                     isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                     and call.func.attr == "_before_mutation" for call in ast.walk(node))}
    assert mutations <= set(METHODS.values()), mutations - set(METHODS.values())
    for name, contract in capabilities()["operations"].items():
        if METHODS[name].startswith("@"):
            continue
        args = set(inspect.signature(getattr(PatchSession, METHODS[name])).parameters) - {"self"}
        assert set(contract["arguments"]) == args
        assert set(contract["aliases"].values()) <= args


def test_python_and_core_share_builders_scope_results_and_roundtrip(tmp_path: Path) -> None:
    session = PatchSession.from_bytes(FIXTURE)
    result = session.edit_batch(batch())
    assert_semantics(session, result)
    path = tmp_path / "fixture.vl"
    path.write_bytes(FIXTURE)
    core = PatchServerCore()
    try:
        handle = core.open(path)["handle"]
        edited = core.edit(handle, batch(), expected_revision=0)
        current = core._get(handle).session
        assert_semantics(current, edited)
        scope = edited["named"]["helper"]["body"]
        spatial = core.view(handle, level="spatial", canvas=scope)
        assert spatial["map"] and spatial["elements"]
        assert not any(item["label"] == "Sink" for item in spatial["elements"])
        preview = core.preview(handle, canvas=scope, path=tmp_path / "helper.svg")
        assert "Sink" not in Path(preview["path"]).read_text(encoding="utf-8")
        assert preview["spatial"] == core.check(handle, canvas=scope)["spatial"]
        core.save(handle, expected_revision=1)
        assert_semantics(PatchSession.load(path), edited)
    finally:
        core.close()


def test_failed_batch_restores_tree_indexes_history_and_revision(tmp_path: Path) -> None:
    path = tmp_path / "fixture.vl"
    path.write_bytes(FIXTURE)
    core = PatchServerCore()
    try:
        handle = core.open(path)["handle"]
        session = core._get(handle).session
        original = session.document.to_bytes()
        with pytest.raises(ValueError, match="unknown batch result"):
            core.edit(handle, batch() + [{"op": "move", "target": "$missing", "x": 1, "y": 2}])
        assert session.document.to_bytes() == original
        assert session.graph.document is session.document
        assert len(session.canvases()) == 1
        assert not session._undo
        assert core._get(handle).revision == 0
        assert path.read_bytes() == FIXTURE
        edited = core.edit(handle, batch(), expected_revision=0)
        after = session.document.to_bytes()
        core.edit(handle, [{"op": "undo"}], expected_revision=1)
        assert session.document.to_bytes() == original
        assert len(session.canvases()) == 1
        core.edit(handle, [{"op": "redo"}], expected_revision=2)
        assert session.document.to_bytes() == after
        assert_semantics(session, edited)
        with pytest.raises(RuntimeError, match="stale"):
            core.edit(handle, [{"op": "add_comment", "text": "stale"}], expected_revision=0)
        with pytest.raises(RuntimeError, match="unsaved"):
            core.close_session(handle)
    finally:
        core.close()


def test_cli_uses_same_edit_and_discovery_contract(tmp_path: Path, capsys) -> None:
    path = tmp_path / "fixture.vl"
    ops = tmp_path / "operations.json"
    path.write_bytes(FIXTURE)
    ops.write_text(json.dumps(batch()), encoding="utf-8")
    assert main(["edit", str(path), "--operations", str(ops)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert_semantics(PatchSession.load(path), result)
    assert main(["capabilities", "add_process", "add_slot"]) == 0
    assert json.loads(capsys.readouterr().out) == capabilities(["add_process", "add_slot"])
    assert main(["check", str(path), "--canvas", result["named"]["helper"]["body"]]) == 0
    assert json.loads(capsys.readouterr().out)["structural"]["ok"]


def test_verified_rebinding_and_typed_loop_scope(tmp_path: Path) -> None:
    session = PatchSession.from_bytes(FIXTURE)
    donor = tmp_path / "donor.vl"
    donor.write_bytes(FIXTURE)
    result = session.edit_batch([
        {"op": "set_node_reference", "target": "n1", "reference": {"path": str(donor), "id": "0000000000000000000009"}},
        {"op": "add_process", "name": "Matrices", "as": "helper"},
        {"op": "add_matrix_repeat_builder", "count": 3, "patch": "$helper.body", "as": "loop"},
    ])
    repeat = session.graph.element(result["named"]["loop"]["repeat_region"])
    assert repeat.getparent().get("Id") == result["named"]["helper"]["body"]
    assert session.validate(include_orphan_warnings=False).ok


def test_mcp_wire_discovery_edits_scope_and_saved_reload(tmp_path: Path) -> None:
    async def scenario():
        path = tmp_path / "wire.vl"
        path.write_bytes(FIXTURE)
        core = PatchServerCore()
        mcp = build_mcp_server(core)
        client_write, server_read = anyio.create_memory_object_stream(10)
        server_write, client_read = anyio.create_memory_object_stream(10)
        try:
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(mcp._mcp_server.run, server_read, server_write,
                                 mcp._mcp_server.create_initialization_options())
                async with ClientSession(client_read, client_write) as client:
                    await client.initialize()
                    tools = {tool.name: tool for tool in (await client.list_tools()).tools}
                    assert {"vl_capabilities", "vl_canvases", "vl_edit", "vl_preview"} <= tools.keys()
                    assert "canvas" in tools["vl_preview"].inputSchema["properties"]
                    opened = await client.call_tool("vl_open", {"path": str(path)})
                    handle = opened.structuredContent["handle"]
                    contract = await client.call_tool("vl_capabilities", {"operations": ["add_slot", "add_input_placement"]})
                    assert contract.structuredContent == capabilities(["add_slot", "add_input_placement"])
                    edited = await client.call_tool("vl_edit", {"handle": handle, "operations": batch(), "expected_revision": 0})
                    assert not edited.isError
                    result = edited.structuredContent
                    assert_semantics(core._get(handle).session, result)
                    scope = result["named"]["helper"]["body"]
                    view = await client.call_tool("vl_view", {"handle": handle, "canvas": scope})
                    assert view.structuredContent["map"]
                    saved = await client.call_tool("vl_save", {"handle": handle, "expected_revision": 1})
                    assert not saved.isError
                    assert_semantics(PatchSession.load(path), result)
                tasks.cancel_scope.cancel()
        finally:
            core.close()
    asyncio.run(scenario())


def test_unknown_arguments_and_literal_dollars_do_not_change_contract() -> None:
    session = PatchSession.from_bytes(FIXTURE)
    original = session.document.to_bytes()
    with pytest.raises(TypeError):
        session.edit_batch([{"op": "add_slot", "name": "Bad", "invented": True}])
    assert session.document.to_bytes() == original
    result = session.edit_batch([{"op": "add_comment", "text": "$$literal", "as": "note"}])
    pad = session.graph.element(session._resolve_entity_id(result["named"]["note"]))
    assert pad.get("Value") == "$literal"


def test_local_helper_catalog_refreshes_and_invalid_names_rollback() -> None:
    session = PatchSession.from_bytes(FIXTURE)
    result = session.edit_batch([
        {"op": "add_process", "name": "Reusable", "as": "helper"},
        {"op": "add_node", "name": "Reusable", "as": "second"},
    ])
    assert session.graph.element(result["named"]["second"]).tag == "Node"
    before = session.document.to_bytes()
    with pytest.raises(ValueError, match="unique identifiers"):
        session.edit_batch([{"op": "add_comment", "text": "Bad", "as": []}])
    with pytest.raises(ValueError, match="exactly"):
        session.edit_batch([{"op": "rename", "target": "n1", "name": "Bad", "extra": True}])
    assert session.document.to_bytes() == before
