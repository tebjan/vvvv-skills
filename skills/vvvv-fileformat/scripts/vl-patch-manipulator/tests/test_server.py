from __future__ import annotations

from pathlib import Path
import tempfile
import time

from lxml import etree

from vl_patch_manipulator.document import VlDocument
from vl_patch_manipulator.server import PatchServerCore
from vl_patch_manipulator.session import PatchSession

from test_framework import FIXTURE


def test_visible_annotations_match_vvvv_help_encoding() -> None:
    session = PatchSession.from_bytes(FIXTURE)
    heading = session.add_annotation("heading", text="A heading", x=10, y=20, width=200, height=40)
    comment = session.add_annotation("comment", text="line one\nline two", x=10, y=80, width=300, height=70)
    link = session.add_annotation("link", text="https://example.test/docs", x=10, y=160, width=260, height=20)
    region = session.add_annotation("region", text="Inputs", x=0, y=0, width=400, height=220)
    assert {heading, comment, link, region} == {"p1", "p2", "p3", "r1"}
    pads = session.graph.pads
    styles = {
        pad.get("Value"): pad.find("{property}ValueBoxSettings/{property}stringtype").text
        for pad in pads
        if pad.find("{property}ValueBoxSettings/{property}stringtype") is not None
    }
    assert styles["A heading"] == "Comment"
    assert styles["line one\nline two"] == "Comment"
    assert styles["https://example.test/docs"] == "Link"
    assert any(element.get("Name") == "Inputs" for element in session.graph.annotations() if etree.QName(element).localname == "Overlay")
    assert session.validate(include_orphan_warnings=False).ok
    payload = session.document.to_bytes()
    assert b"\xef\xbb\xbf" not in payload
    assert b"line one" in payload and b"line two" in payload
    assert b'<p:fontsize p:Type="Int32">15</p:fontsize>' in payload
    assert b'<p:stringtype p:Assembly="VL.Core" p:Type="VL.Core.StringType">Comment</p:stringtype>' in payload
    assert b'<p:stringtype p:Assembly="VL.Core" p:Type="VL.Core.StringType">Link</p:stringtype>' in payload
    assert b'<p:fontsize Type="Int32">' not in payload
    assert b'<p:stringtype Assembly="VL.Core"' not in payload


def test_multiple_regions_keep_unique_aliases_when_new_overlays_insert_first() -> None:
    session = PatchSession.from_bytes(FIXTURE)
    first = session.add_annotation("region", text="First", x=0, y=0, width=100, height=100)
    second = session.add_annotation("region", text="Second", x=200, y=0, width=100, height=100)
    third = session.add_annotation("region", text="Third", x=400, y=0, width=100, height=100)

    assert len({first, second, third}) == 3
    assert session.graph.element(session._resolve_entity_id(first)).get("Name") == "First"
    assert session.graph.element(session._resolve_entity_id(second)).get("Name") == "Second"
    assert session.graph.element(session._resolve_entity_id(third)).get("Name") == "Third"


def test_spatial_view_reports_exact_bounds_pins_links_and_preview() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "fixture.vl"
        path.write_bytes(FIXTURE)
        core = PatchServerCore(poll_seconds=0.02)
        try:
            handle = core.open(path)["handle"]
            spatial = core.view(handle, level="spatial")
            assert spatial["canvas"] is not None
            assert spatial["map"]
            assert spatial["elements"]
            assert spatial["links"]
            node = next(item for item in spatial["elements"] if item["kind"] == "node")
            assert node["pins"]["inputs"]
            assert node["width"]["stored"] > 0
            preview = core.preview(handle)
            preview_path = Path(preview["path"])
            assert preview_path.suffix == ".svg"
            assert preview_path.is_file()
            assert not preview_path.read_bytes().startswith(b"\xef\xbb\xbf")
            assert "annotation_overlaps" in core.check(handle)["spatial"]
        finally:
            core.close()


def test_pin_anchors_match_vvvv_pin_bar_stretching() -> None:
    session = PatchSession.from_bytes(FIXTURE)
    node = session.graph.operational_nodes()[0]
    alias = session.alias_for(node.get("Id", ""))
    session.add_pin(alias, "Hidden", "InputPin", hidden=True)
    second = session.add_pin(alias, "Second", "InputPin")
    primary = session.add_pin(alias, "Output", "OutputPin")
    diagnostic = session.add_pin(alias, "Error", "OutputPin")
    first = node.find("Pin").get("Id", "")

    # PinBarView uses 5-pixel pins. One pin starts at the left edge; two or
    # more visible pins stretch across the complete stored node width.
    assert session._endpoint_anchor(first) == (102.5, 200.0)
    assert session._endpoint_anchor(second) == (147.5, 200.0)
    assert session._endpoint_anchor(primary) == (102.5, 219.0)
    assert session._endpoint_anchor(diagnostic) == (147.5, 219.0)


def test_pin_anchors_use_nodeviews_expanded_minimum_pinbar_width() -> None:
    session = PatchSession.from_bytes(FIXTURE)
    node = session.graph.operational_nodes()[0]
    alias = session.alias_for(node.get("Id", ""))
    session.set_bounds(alias, width=10)
    first = node.find("Pin").get("Id", "")
    session.add_pin(alias, "Second", "InputPin")
    session.add_pin(alias, "Third", "InputPin")
    fourth = session.add_pin(alias, "Fourth", "InputPin")

    # Four pins require 5*4 + 15*3 == 65 pixels, even when XML stores 10.
    assert session._endpoint_anchor(first) == (102.5, 200.0)
    assert session._endpoint_anchor(fourth) == (162.5, 200.0)


def test_layout_preserves_every_entity_that_existed_when_the_patch_opened() -> None:
    session = PatchSession.from_bytes(FIXTURE)
    before = session.document.to_bytes()
    intent = session.layout_intent()

    assert intent["mode"] == "incremental"
    assert intent["movable"] == []
    assert intent["protected"] == ["n1"]
    session.layout()
    assert session.document.to_bytes() == before


def test_value_pad_layout_is_opt_in_for_existing_human_geometry() -> None:
    session = PatchSession.from_bytes(FIXTURE)
    pad = session.graph.by_id["0000000000000000000008"]
    before = pad.get("Bounds")

    session.layout_value_pads()
    assert pad.get("Bounds") == before

    session.layout_value_pads(force=True)
    assert session._endpoint_anchor("0000000000000000000008")[0] == session._endpoint_anchor("000000000000000000000A")[0]


def test_translate_group_preserves_relative_geometry_exactly() -> None:
    session = PatchSession.from_bytes(FIXTURE)
    session.translate_group(["n1", "0000000000000000000008"], dx=37, dy=-12)

    assert session.graph.by_id["0000000000000000000009"].get("Bounds") == "137,188,50,19"
    assert session.graph.by_id["0000000000000000000008"].get("Bounds") == "137,88,80,20"


def test_incremental_layout_moves_a_new_clone_but_not_its_human_baseline() -> None:
    session = PatchSession.from_bytes(FIXTURE)
    original_id = "0000000000000000000009"
    original_bounds = session.graph.by_id[original_id].get("Bounds")
    mapping = session.graph.clone_subgraph([original_id], dx=400, dy=0)
    clone_id = mapping[original_id]

    intent = session.layout_intent()
    assert intent["movable"] == [session.alias_for(clone_id)]
    assert intent["protected"] == [session.alias_for(original_id)]
    session.layout(start_x=60, start_y=300)

    assert session.graph.by_id[original_id].get("Bounds") == original_bounds
    assert session.graph.by_id[clone_id].get("Bounds") == "60,300,50,19"


def test_successful_save_promotes_current_geometry_to_the_protected_baseline() -> None:
    with tempfile.TemporaryDirectory() as directory:
        session = PatchSession.from_bytes(FIXTURE)
        original_id = "0000000000000000000009"
        mapping = session.graph.clone_subgraph([original_id], dx=400, dy=0)
        clone_id = mapping[original_id]
        session.save(Path(directory) / "accepted.vl")
        before = session.graph.by_id[clone_id].get("Bounds")

        assert session.layout_intent()["movable"] == []
        session.layout(start_x=60, start_y=300)
        assert session.graph.by_id[clone_id].get("Bounds") == before


def test_server_batch_revision_external_update_undo_redo_and_save() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "fixture.vl"
        path.write_bytes(FIXTURE)
        core = PatchServerCore(poll_seconds=0.02)
        try:
            opened = core.open(path)
            handle = opened["handle"]
            edited = core.edit(handle, [{"op": "add_comment", "text": "server note", "x": 20, "y": 20}], expected_revision=0)
            assert edited["revision"] == 1
            assert set(edited["spatial"]) == {"before", "after"}
            assert core.check(handle)["structural"]["ok"]
            undone = core.edit(handle, [{"op": "undo"}], expected_revision=1)
            assert undone["revision"] == 2
            redone = core.edit(handle, [{"op": "redo"}], expected_revision=2)
            assert redone["revision"] == 3
            saved = core.save(handle, expected_revision=3)
            assert Path(saved["saved"]).read_bytes().startswith(b"<?xml")

            external = path.read_bytes().replace(b"FutureThing custom=\"keep\"", b"FutureThing custom=\"changed\"")
            path.write_bytes(external)
            deadline = time.monotonic() + 2
            changes = core.changes(handle, since_revision=3, wait_ms=1000)
            while not changes["events"] and time.monotonic() < deadline:
                changes = core.changes(handle, since_revision=3, wait_ms=100)
            while not any(event["kind"] == "external" for event in changes["events"]) and time.monotonic() < deadline:
                changes = core.changes(handle, since_revision=3, wait_ms=100)
            assert any(event["kind"] == "external" for event in changes["events"])
            assert core.check(handle)["structural"]["ok"]
        finally:
            core.close()
