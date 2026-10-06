"""Regression tests for the generated-help-patch layout/typing rules.

Each rule here was measured against real vvvv-saved patches or the owner's
hand fixes to a generated one -- see the docstrings/comments at each
implementation site (session.py: fit_region, _pad_size_for_value,
_intrinsic_node_width, add_node, add_pad, _check_link_type_mismatches;
document.py: _format_bounds) for the evidence. These tests exist so a future
change to the generator cannot silently regress any of them.
"""

from __future__ import annotations

from lxml import etree

from vl_patch_manipulator.catalog import InMemoryNodeCatalog, NodeSpec, PinSpec
from vl_patch_manipulator.document import _format_bounds
from vl_patch_manipulator.session import PatchSession

from test_framework import FIXTURE


def _pin(name: str, *, type_name: str = "Object", kind: str = "InputPin") -> PinSpec:
    return PinSpec(name=name, type_name=type_name, kind=kind)


def _node_spec(name: str, inputs: tuple[PinSpec, ...], outputs: tuple[PinSpec, ...]) -> NodeSpec:
    return NodeSpec(
        name=name,
        category="Test",
        full_name=f"Test.{name}",
        kind="ProcessNode",
        inputs=inputs,
        outputs=outputs,
        reference_kind="ProcessNode",
        fixed=False,
    )


# ---------------------------------------------------------------------------
# Rule 4: Bounds formatting -- integers, comma-joined, no space.
# ---------------------------------------------------------------------------

def test_format_bounds_rounds_to_integers_with_no_space_like_vvvv_itself() -> None:
    # Real evidence: generator wrote "47.5, 790, 225, 19"; vvvv itself saves
    # "48,790,225,19" for the same box.
    assert _format_bounds(47.5, 790, 225, 19) == "48,790,225,19"
    assert _format_bounds(100, 100.0, 80, 20) == "100,100,80,20"


def test_format_bounds_rounds_half_away_from_zero_for_negative_coordinates() -> None:
    assert _format_bounds(-5.5, -0.4, -0.5) == "-6,0,-1"


def test_add_node_and_add_pad_never_write_a_space_or_fractional_bounds() -> None:
    catalog = InMemoryNodeCatalog([_node_spec("Widget", (_pin("In"),), (_pin("Out", kind="OutputPin"),))])
    session = PatchSession.new(catalog=catalog)

    node = session.add_node("Widget", category="Test", x=47.5, y=100.4)
    node_bounds = session.node(node).get("Bounds")
    assert ", " not in node_bounds
    assert node_bounds.split(",")[0] == "48"

    pad = session.add_pad(value="1", x=10.5, y=10, type_name="Boolean")
    pad_bounds = session.graph.element(session._resolve_entity_id(pad)).get("Bounds")
    assert ", " not in pad_bounds
    assert "." not in pad_bounds


# ---------------------------------------------------------------------------
# Rule 1: section-frame title band.
# ---------------------------------------------------------------------------

def test_fit_region_reserves_a_title_band_above_and_keeps_padding_elsewhere() -> None:
    session = PatchSession.new()
    # Boolean pads are a fixed 35x35 (see rule 2), so the union below is
    # exact and independent of any text-growth estimate.
    pad_a = session.add_pad(value="1", x=100, y=100, type_name="Boolean")
    pad_b = session.add_pad(value="2", x=300, y=300, type_name="Boolean")
    region = session.add_annotation("region", text="Test Region", x=0, y=0, width=10, height=10)

    session.fit_region(region, [pad_a, pad_b], padding=16)

    bounds = session.graph.element(session._resolve_entity_id(region)).get("Bounds")
    x, y, width, height = (float(value) for value in bounds.split(","))

    # Content union: left=100, top=100, right=335, bottom=335 (pad_b at
    # 300+35). Side/bottom keep the 16px padding; top reserves the 50px band.
    assert x == 100 - 16
    assert y == 100 - 50
    assert width == (335 - 100) + 16 * 2
    assert height == (335 - 100) + 50 + 16


def test_fit_region_top_padding_is_overridable_and_never_shrinks_below_padding() -> None:
    session = PatchSession.new()
    pad = session.add_pad(value="1", x=0, y=0, type_name="Boolean")
    region = session.add_annotation("region", text="R", x=0, y=0, width=10, height=10)

    session.fit_region(region, [pad], padding=30, top_padding=10)
    bounds = session.graph.element(session._resolve_entity_id(region)).get("Bounds")
    x, y, _width, _height = (float(value) for value in bounds.split(","))
    # An explicit top_padding smaller than padding is honoured as given --
    # only the *default* enforces the >= padding floor.
    assert y == 0 - 10
    assert x == 0 - 30


# ---------------------------------------------------------------------------
# Rule 2: IOBox (Pad) sizing by type and value text.
# ---------------------------------------------------------------------------

def test_pad_size_for_value_matches_vvvv_saved_native_sizes() -> None:
    size = PatchSession._pad_size_for_value
    assert size("Boolean", "True") == (35.0, 35.0)
    assert size("Vector3", "-5, -0.35, -5") == (35.0, 43.0)
    assert size("Vector3", "") == (35.0, 43.0)
    assert size("Vector4", "1, 1, 1, 1") == (35.0, 57.0)
    assert size("RGBA", "0.2726001, 0.6196479, 0.94000006, 1") == (136.0, 15.0)
    assert size("EnvironmentMapPreset", "ProceduralMidday") == (116.0, 15.0)
    assert size(None, None) == (35.0, 15.0)


def test_pad_size_for_value_grows_scalar_width_for_long_text() -> None:
    size = PatchSession._pad_size_for_value
    # Real vvvv-saved samples: short values stay at the base width; "1000000"
    # (7 chars) needs 61px.
    assert size("Float32", "0.33") == (35.0, 15.0)
    assert size("Integer32", "5") == (35.0, 15.0)
    assert size("Integer32", "1000000") == (61.0, 15.0)


def test_add_pad_writes_native_sizes_not_a_flat_100x20_placeholder() -> None:
    session = PatchSession.new()
    vector = session.add_pad(value="-5, -0.35, -5", x=10, y=10, type_name="Vector3")
    assert session.graph.element(session._resolve_entity_id(vector)).get("Bounds") == "10,10,35,43"

    toggle = session.add_pad(value="True", x=10, y=10, type_name="Boolean")
    assert session.graph.element(session._resolve_entity_id(toggle)).get("Bounds") == "10,10,35,35"

    long_value = session.add_pad(value="1000000", x=0, y=0, type_name="Integer32")
    assert session.graph.element(session._resolve_entity_id(long_value)).get("Bounds") == "0,0,61,15"


# ---------------------------------------------------------------------------
# Rule 3: node width from pin rails, not a flat placeholder.
# ---------------------------------------------------------------------------

# (node name, input pin count, output pin count, owner's hand-fixed width in
# "HowTo Procedural Mesh and SDF.vl", 2026-09). All seven are an EXACT match
# for _intrinsic_node_width once the pin count is the owner's corrected one --
# see the method's docstring for why the generated patch came out narrower.
_NODE_WIDTH_CALIBRATION = (
    ("ProcGridGenAS", 15, 2, 285.0),
    ("ProcGridInputAS", 18, 2, 345.0),
    ("ProcGridCS", 16, 2, 305.0),
    ("ProcGridGenMS", 17, 2, 325.0),
    ("ProcGridInputMS", 21, 2, 405.0),
    ("ComputeMeshGenerator", 5, 11, 205.0),
    ("CpuTemplateInstancer", 9, 1, 165.0),
)


def _bare_node(name: str, input_count: int, output_count: int) -> etree._Element:
    node = etree.Element("Node", Name=name)
    for index in range(input_count):
        etree.SubElement(node, "Pin", Name=f"In{index}", Kind="InputPin")
    for index in range(output_count):
        etree.SubElement(node, "Pin", Name=f"Out{index}", Kind="OutputPin")
    return node


def test_intrinsic_node_width_matches_every_owner_hand_fix_with_zero_error() -> None:
    for name, input_count, output_count, expected_width in _NODE_WIDTH_CALIBRATION:
        node = _bare_node(name, input_count, output_count)
        width = PatchSession._intrinsic_node_width(node)
        assert width == expected_width, (name, width, expected_width)


def test_intrinsic_node_width_ignores_hidden_pins() -> None:
    node = _bare_node("Small", 2, 1)
    baseline = PatchSession._intrinsic_node_width(node)
    for index in range(10):
        etree.SubElement(node, "Pin", Name=f"Hidden{index}", Kind="InputPin", IsHidden="true")
    assert PatchSession._intrinsic_node_width(node) == baseline


def test_add_node_seeds_intrinsic_width_instead_of_a_flat_placeholder() -> None:
    catalog = InMemoryNodeCatalog(
        [
            _node_spec("TinyNode", (_pin("A"),), (_pin("B", kind="OutputPin"),)),
            _node_spec(
                "WideNode",
                tuple(_pin(f"In{index}") for index in range(20)),
                (_pin("Out", kind="OutputPin"),),
            ),
        ]
    )
    session = PatchSession.new(catalog=catalog)
    tiny = session.add_node("TinyNode", category="Test", x=0, y=0)
    wide = session.add_node("WideNode", category="Test", x=0, y=0)

    tiny_width = float(session.node(tiny).get("Bounds").split(",")[2])
    wide_width = float(session.node(wide).get("Bounds").split(",")[2])

    # The old flat "100" was simultaneously too wide for a 2-pin node and too
    # narrow for a 20-pin node.
    assert tiny_width < 100.0
    assert wide_width > 100.0
    assert wide_width == PatchSession._intrinsic_node_width(session.node(wide))


# ---------------------------------------------------------------------------
# Rule 5: vl_check flags links vvvv itself refuses (Int32 <-> UInt32).
# ---------------------------------------------------------------------------

def test_validate_flags_int32_pad_into_uint32_node_pin() -> None:
    catalog = InMemoryNodeCatalog(
        [_node_spec("ShaderNode", (_pin("Count", type_name="Integer32 (Unsigned)"),), (_pin("Out", kind="OutputPin"),))]
    )
    session = PatchSession.new(catalog=catalog)
    session.add_node("ShaderNode", alias="shader", category="Test")
    pad = session.add_pad(value="4", x=0, y=0, type_name="Integer32")
    session.connect(pad, "shader.Count")

    codes = {item.code for item in session.validate(include_orphan_warnings=False).errors}
    assert "link-type-mismatch" in codes


def test_validate_does_not_flag_a_matching_int32_link() -> None:
    catalog = InMemoryNodeCatalog(
        [_node_spec("ShaderNode", (_pin("Count", type_name="Integer32"),), (_pin("Out", kind="OutputPin"),))]
    )
    session = PatchSession.new(catalog=catalog)
    session.add_node("ShaderNode", alias="shader", category="Test")
    pad = session.add_pad(value="4", x=0, y=0, type_name="Integer32")
    session.connect(pad, "shader.Count")

    codes = {item.code for item in session.validate(include_orphan_warnings=False).errors}
    assert "link-type-mismatch" not in codes


def test_resolve_endpoint_type_reads_pad_typeannotation_but_needs_a_catalog_for_node_pins() -> None:
    # A Pad's type is always in the file.
    session = PatchSession.from_bytes(FIXTURE)
    typed_pad = session.add_pad(value="4", x=200, y=200, type_name="Integer32")
    assert session._resolve_endpoint_type(session._resolve_entity_id(typed_pad)) == "Integer32"

    # A Node pin's type is NEVER stored inline in the .vl format -- only a
    # catalog can answer it. FIXTURE's session uses the default
    # DocumentCatalog (auto-derived from the same XML), which has no pin
    # types at all, so this must come back None -- "unknown", not "ok".
    assert session._resolve_endpoint_type("000000000000000000000A") is None


def test_type_mismatch_check_is_silent_when_the_catalog_has_no_pin_types() -> None:
    # Same link shape as the positive case above, but resolved purely from
    # the document's own DocumentCatalog (no explicit rich catalog passed).
    # Silence is required here, not a lucky pass: the diagnostic must never
    # guess a type it cannot actually resolve.
    session = PatchSession.from_bytes(FIXTURE)
    report = session.validate(include_orphan_warnings=False)
    assert "link-type-mismatch" not in {item.code for item in report.errors}
