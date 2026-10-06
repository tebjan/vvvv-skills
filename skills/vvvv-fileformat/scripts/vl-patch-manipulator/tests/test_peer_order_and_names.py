from copy import deepcopy

import pytest

from vl_patch_manipulator.catalog import InMemoryNodeCatalog, NodeSpec, PinSpec
from vl_patch_manipulator.session import PatchSession
from vl_patch_manipulator.ids import new_vl_id


def test_custom_names_and_local_selectors_are_updated_together():
    session = PatchSession.new()
    for name in ("Two Words", "lowercase", "Punctuation!", ""):
        before = session.document.to_bytes()
        with pytest.raises(ValueError):
            session.add_process(name)
        assert session.document.to_bytes() == before
    helper = session.add_process("Original", document_name="Test.vl")
    before = {e.get("Id"): e.get("Bounds") for e in session.document.root.iter()}
    external = deepcopy(session.node(helper.call))
    for element in external.iter():
        if element.get("Id"):
            element.set("Id", new_vl_id())
    external.find("{property}NodeReference").set("LastDependency", "Other.vl")
    # Query safety for a same-spelling imported call; this element is not saved.
    session.node(helper.call).getparent().append(external)
    session._refresh()
    result = session.rename_local_process(helper.definition_id, "Renamed", document_name="Test.vl")
    assert result["calls"] == [helper.call_id]
    assert session.node(helper.call).find("{property}NodeReference/Choice").get("Name") == "Renamed"
    assert external.find("{property}NodeReference/Choice").get("Name") == "Original"
    assert all(session.graph.element(identifier).get("Bounds") == value for identifier, value in before.items() if identifier)


def test_saved_process_app_selector_renames_and_collision_is_atomic(tmp_path):
    session = PatchSession.new()
    helper = session.add_process("Original", document_name="Test.vl")
    session.node(helper.call).find("{property}NodeReference/Choice").set("Kind", "ProcessAppFlag")
    session.add_process("Occupied")
    path = session.save(tmp_path / "Test.vl")
    session = PatchSession.load(path)
    before = session.document.to_bytes()
    with pytest.raises(ValueError, match="already exists"):
        session.rename_local_process(helper.definition_id, "Occupied")
    assert session.document.to_bytes() == before
    assert session.rename_local_process(helper.definition_id, "Renamed")["calls"] == [helper.call_id]
    assert session.graph.element(helper.call_id).find("{property}NodeReference/Choice").get("Name") == "Renamed"


def peer_session():
    catalog = InMemoryNodeCatalog((
        NodeSpec("Source", outputs=(PinSpec("Output", "Float32", "OutputPin"),)),
        NodeSpec("Group", category="Stride.DX12Bridge.Rendering",
                 inputs=tuple(PinSpec(name, "Float32") for name in ("Input", "Input2", "Input3")),
                 outputs=(PinSpec("Output", "Float32", "OutputPin"),)),
    ))
    session = PatchSession.new(catalog=catalog)
    group = session.add_node("Group", category="Stride.DX12Bridge.Rendering", x=0, y=300)
    sources = [session.add_node("Source", x=x, y=100) for x in (300, 100, 200)]
    links = [session.connect(f"{source}.Output", f"{group}.{pin}")
             for source, pin in zip(sources, ("Input", "Input2", "Input3"))]
    return session, group, sources, links


def test_peer_collection_order_is_opt_in_stable_and_geometry_preserving():
    session, group, sources, links = peer_session()
    before = session.document.to_bytes()
    with pytest.raises(ValueError, match="independent_peers"):
        session.order_group_inputs_by_x(group)
    assert session.document.to_bytes() == before
    geometry = {e.get("Id"): e.get("Bounds") for e in session.document.root.iter()}
    endpoints = {identifier: session.graph.link_hub_ids(session.graph.element(identifier)) for identifier in links}
    result = session.order_group_inputs_by_x(group, independent_peers=True)
    assert result["changed_links"] == 3
    assert result["sources"] == [endpoints[links[i]][0] for i in (1, 2, 0)]
    assert {e.get("Id"): e.get("Bounds") for e in session.document.root.iter()} == geometry
    assert {session.graph.link_hub_ids(session.graph.element(identifier))[0] for identifier in links} == {
        value[0] for value in endpoints.values()}
    assert session.validate(include_orphan_warnings=False).ok
    ordered = session.document.to_bytes()
    assert session.order_group_inputs_by_x(group, independent_peers=True)["changed_links"] == 0
    assert session.document.to_bytes() == ordered


def test_shared_edit_surface_accepts_both_operations():
    session, group, _, _ = peer_session()
    helper = session.add_process("Original")
    result = session.edit_batch([
        {"op": "rename_local_process", "alias_or_id": helper.definition_id, "name": "Renamed"},
        {"op": "order_group_inputs_by_x", "alias_or_id": group, "independent_peers": True},
    ])
    assert result
    assert session.node(helper.definition_id).get("Name") == "Renamed"
