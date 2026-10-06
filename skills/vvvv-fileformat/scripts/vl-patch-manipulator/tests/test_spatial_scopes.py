from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lxml import etree

from vl_patch_manipulator.catalog import InMemoryNodeCatalog, NodeSpec, PinSpec
from vl_patch_manipulator.session import PatchSession
from vl_patch_manipulator.spatial import _visible_elements


class SpatialScopeTests(unittest.TestCase):
    def test_distinct_inputs_on_same_node_still_report_crossings(self):
        session = PatchSession.new(catalog=InMemoryNodeCatalog([
            NodeSpec("Join", inputs=(PinSpec("Left", "Float32"),
                                      PinSpec("Right", "Float32")),
                     outputs=(PinSpec("Output", "Float32", "OutputPin"),))]))
        node = session.add_node("Join", x=100, y=250)
        session.set_bounds(node, width=105)
        left = session.add_pad(value="1", x=100, y=100)
        right = session.add_pad(value="2", x=200, y=100)
        session.connect(left, f"{node}.Right")
        session.connect(right, f"{node}.Left")
        self.assertEqual(session.layout_analysis()["crossings"], 1)
        # These remain distinct wires even though they share a consumer.
        session.move(left, x=200, y=100)
        session.move(right, x=100, y=100)
        self.assertEqual(session.layout_analysis()["crossings"], 0)

    def test_shared_output_junction_is_not_a_crossing(self):
        session = PatchSession.new(catalog=InMemoryNodeCatalog([
            NodeSpec("Join", inputs=(PinSpec("Left", "Float32"),
                                      PinSpec("Right", "Float32")))]))
        node = session.add_node("Join", x=100, y=250)
        session.set_bounds(node, width=105)
        source = session.add_pad(value="1", x=150, y=100)
        session.connect(source, f"{node}.Left")
        session.connect(source, f"{node}.Right")
        self.assertEqual(session.layout_analysis()["crossings"], 0)

    def session(self):
        return PatchSession.new(catalog=InMemoryNodeCatalog(
            NodeSpec(name, inputs=(PinSpec("Input", "Float32"),),
                     outputs=(PinSpec("Output", "Float32", "OutputPin"),))
            for name in ("First", "Second", "Nested")))

    def test_independent_processes_at_same_coordinates_do_not_collide_in_scope(self):
        session = self.session()
        processes = [session.add_process(name) for name in ("One", "Two")]
        for process, name in zip(processes, ("First", "Second")):
            pad = session.add_pad(value="1", x=100, y=100, patch=process.body)
            node = session.add_node(name, x=100, y=200, patch=process.body)
            session.connect(pad, f"{node}.Input")
            session.add_annotation("comment", text=name, x=400, y=100, patch=process.body)
        self.assertTrue(session.layout_analysis()["overlaps"])
        for process, wanted, excluded in zip(processes, ("First", "Second"), ("Second", "First")):
            report = session.layout_analysis(canvas=process.body)
            self.assertEqual(report["overlaps"], [])
            self.assertEqual(report["annotation_overlaps"], [])
            self.assertEqual(report["element_count"], 2)
            self.assertEqual(report["link_count"], 1)
            with tempfile.TemporaryDirectory() as folder:
                path = session.render_svg(Path(folder) / "scope.svg", canvas=process.body)
                svg = etree.parse(str(path))
                text = " ".join(svg.getroot().itertext())
                self.assertIn(wanted, text)
                self.assertNotIn(excluded, text)
                self.assertEqual(len(svg.findall("{http://www.w3.org/2000/svg}path")), 1)
                self.assertFalse(path.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_scope_includes_executable_regions_but_not_independent_definitions(self):
        session = self.session()
        process = session.add_process("Owner")
        other = session.add_process("Independent")
        foreign = session.add_node("Second", x=500, y=200, patch=other.body)
        process.body.append(session.graph.element(other.definition_id))
        builder = session.add_matrix_repeat_builder(patch=process.body)
        nested = session.graph.element(builder.repeat_region).find("Patch")
        nested_node = session.add_node("Nested", x=700, y=200, patch=nested)
        session._refresh()
        visible = {element.get("Id") for element, _, _, _ in _visible_elements(session, canvas=process.body)}
        self.assertIn(session.node(nested_node).get("Id"), visible)
        self.assertIn(builder.repeat_region, visible)
        self.assertNotIn(session.node(foreign).get("Id"), visible)
        report = session.layout_analysis(canvas=process.body)
        # An alias substring can occur randomly inside a GUID; inspect exact
        # endpoint descriptions rather than stringifying the entire report.
        foreign_alias = session.alias_for(session.node(foreign).get("Id"))
        descriptions = [value for pair in report["misaligned_links"] for value in pair[:2]]
        self.assertFalse(any(value == foreign_alias or value.startswith(foreign_alias + ".")
                             for value in descriptions))

    def test_scoped_links_require_both_endpoints_and_skip_hidden_references(self):
        session = self.session()
        process = session.add_process("Owner", inputs=(PinSpec("Value", "Float32"),))
        peer = session.add_process("Peer")
        first = session.add_node("First", x=100, y=200, patch=process.body)
        second = session.add_node("Second", x=100, y=200, patch=peer.body)
        session.connect(process.inputs["Value"], f"{first}.Input")
        session.connect(f"{first}.Output", f"{second}.Input")
        session.graph.add_link(process.inputs["Value"], session._endpoint_ref(f"{first}.Input"), IsHidden="true")
        report = session.layout_analysis(canvas=process.body)
        self.assertEqual(report["link_count"], 1)
        with tempfile.TemporaryDirectory() as folder:
            path = session.render_svg(Path(folder) / "scope.svg", canvas=process.body)
            svg = etree.parse(str(path))
            self.assertEqual(len(svg.findall("{http://www.w3.org/2000/svg}path")), 1)

    def test_two_coordinate_input_and_slot_geometry_and_labels(self):
        session = self.session()
        process = session.add_process("Owner", inputs=(PinSpec("Font", "PTFont"),))
        portal = session.add_input_placement(process.inputs["Font"], (100, 100))
        slot = session.add_slot("Material", patch=process.body.getparent(), read_position=(250, 100))
        first = session.add_node("First", x=100, y=200, patch=process.body)
        second = session.add_node("Second", x=250, y=200, patch=process.body)
        session.connect(portal, f"{first}.Input")
        session.connect(slot.read_pad, f"{second}.Input")
        # Constants.cs: PadOffset=(.5,-.5), PadHeight/ProxyPinSize=9;
        # DataHubView.GetLinkAnchorPosition uses center +/- height/2.
        for identifier, x in ((portal, 100), (slot.read_pad, 250)):
            self.assertEqual(session._endpoint_anchor(identifier, as_source=True), (x + .5, 104))
            self.assertEqual(session._endpoint_anchor(identifier, as_source=False), (x + .5, 95))
            self.assertEqual(session._element_rectangle(session.graph.element(identifier)), (x - 4, 95, 9, 9))
        self.assertEqual(session._data_hub_label(session.graph.element(portal)), "Font")
        self.assertEqual(session._data_hub_label(session.graph.element(slot.read_pad)), "Material")
        report = session.layout_analysis(canvas=process.body)
        self.assertEqual(report["link_count"], 2)
        with tempfile.TemporaryDirectory() as folder:
            path = session.render_svg(Path(folder) / "scope.svg", canvas=process.body)
            svg = etree.parse(str(path))
            text = " ".join(svg.getroot().itertext())
            self.assertIn("Font", text)
            self.assertIn("Material", text)
            self.assertEqual(len(svg.findall("{http://www.w3.org/2000/svg}path")), 2)
            circles = svg.findall("{http://www.w3.org/2000/svg}circle[@class='pad']")
            self.assertIn(("250.5", "99.5", "4.5"), [(c.get("cx"), c.get("cy"), c.get("r")) for c in circles])

    def test_scope_rejects_detached_foreign_or_noncanvas_elements(self):
        session = self.session()
        canvas = session.graph._main_canvas()
        foreign = self.session().graph._main_canvas()
        for invalid in (deepcopy(canvas), foreign, canvas.getparent()):
            with self.assertRaises(ValueError):
                session.layout_analysis(canvas=invalid)
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "invalid.svg"
                with self.assertRaises(ValueError):
                    session.render_svg(path, canvas=invalid)
                self.assertFalse(path.exists())

    def test_align_and_move_preserve_two_coordinate_placement_bounds(self):
        session = self.session()
        process = session.add_process("Owner", inputs=(PinSpec("Font", "PTFont"),))
        portal = session.add_input_placement(process.inputs["Font"], (100, 100))
        slot = session.add_slot("Material", patch=process.body.getparent(), read_position=(300, 100))
        first = session.add_node("First", x=200, y=200, patch=process.body)
        for identifier in (portal, slot.read_pad):
            session.align_link(identifier, f"{first}.Input", y=120)
            self.assertEqual(session.graph.element(identifier).get("Bounds"), "202,120")
            self.assertEqual(session._endpoint_anchor(identifier, as_source=True)[0],
                             session._endpoint_anchor(session._endpoint_ref(f"{first}.Input"), as_source=False)[0])
            session.move(identifier, 350, 150)
            self.assertEqual(session.graph.element(identifier).get("Bounds"), "350,150")
            session._set_element_position(session.graph.element(identifier), 380, 160)
            self.assertEqual(session.graph.element(identifier).get("Bounds"), "380,160")
        session.align_link(f"{first}.Output", slot.write_pad, move="target")
        self.assertEqual(session.graph.element(slot.write_pad).get("Bounds"), "202,300")
        self.assertEqual(session._endpoint_anchor(slot.write_pad, as_source=False)[0],
                         session._endpoint_anchor(session._endpoint_ref(f"{first}.Output"), as_source=True)[0])

    def test_malformed_two_coordinate_bounds_do_not_crash_layout(self):
        session = self.session()
        process = session.add_process("Owner", inputs=(PinSpec("Value", "Float32"),))
        portal = session.add_input_placement(process.inputs["Value"])
        slot = session.add_slot("State", patch=process.body.getparent())
        first = session.add_node("First", x=200, y=200, patch=process.body)
        for identifier in (portal, slot.read_pad):
            session.graph.element(identifier).set("Bounds", "invalid,100")
            session.connect(identifier, f"{first}.Input")
            self.assertIsNone(session._element_rectangle(session.graph.element(identifier)))
            self.assertIsNone(session._endpoint_anchor(identifier, as_source=True))
        self.assertEqual(session.layout_analysis(canvas=process.body)["link_count"], 0)

    def test_explicit_placement_position_restores_two_bounds_without_losing_identity(self):
        session = self.session()
        process = session.add_process("Owner", inputs=(PinSpec("Value", "Float32"),))
        portal = session.add_input_placement(process.inputs["Value"])
        slot = session.add_slot("State", patch=process.body.getparent())
        links = [etree.tostring(link) for link in session.graph.links]
        for identifier in (portal, slot.read_pad):
            element = session.graph.element(identifier)
            element.set("Bounds", "100,100,100,19")
            element.set("FutureAttribute", "keep")
            unknown = etree.SubElement(element, "{property}Future")
            unknown.text = "preserve"
            preserved = {key: value for key, value in element.attrib.items() if key != "Bounds"}
            session.set_placement_position(identifier, 200.5, -10.5)
            self.assertEqual(element.get("Bounds"), "201,-11")
            self.assertEqual({key: value for key, value in element.attrib.items() if key != "Bounds"}, preserved)
            self.assertIs(element.find("{property}Future"), unknown)
            self.assertEqual(unknown.text, "preserve")
        self.assertEqual([etree.tostring(link) for link in session.graph.links], links)

    def test_placement_position_rejects_nonplacements_and_invalid_coordinates(self):
        session = self.session()
        process = session.add_process("Owner")
        pad = session.add_pad(value="1")
        slot = session.add_slot("State")
        before = session.document.to_bytes()
        for identifier, x, y in ((pad, 10, 20), (process.definition_id, 10, 20),
                                 (slot.slot_id, 10, 20), (slot.read_pad, "invalid", 20)):
            with self.assertRaises(ValueError):
                session.set_placement_position(identifier, x, y)
            self.assertEqual(session.document.to_bytes(), before)

    def test_crossing_labels_reindex_aliases_once_and_compute_each_label_once(self):
        session = self.session()
        pairs = []
        count = 8
        for index in range(count):
            source = session.add_node("First", alias=f"source{index}", x=index * 150, y=100)
            target = session.add_node("Second", alias=f"target{index}", x=(count - index - 1) * 150, y=500)
            session.connect(f"{source}.Output", f"{target}.Input")
            pairs.append((source, "Output", target, "Input"))
        with patch.object(session, "_reindex_aliases", wraps=session._reindex_aliases) as reindex, \
                patch.object(session, "_link_label", wraps=session._link_label) as labels:
            report = session.layout_analysis()
        self.assertEqual(report["crossings"], count * (count - 1) // 2)
        self.assertEqual(reindex.call_count, 1)
        self.assertEqual(labels.call_count, count)
        self.assertEqual(report["crossing_links"], [(pairs[first], pairs[second])
                         for first in range(count) for second in range(first + 1, count)])
        self.assertEqual(report["misaligned_links"][0][:2], ("source0.Output", "target0.Input"))

    def test_analysis_alias_snapshot_refreshes_after_mutation(self):
        session = self.session()
        first = session.add_node("First", alias="oldSource", x=0, y=100)
        second = session.add_node("Second", alias="oldTarget", x=300, y=500)
        session.connect(f"{first}.Output", f"{second}.Input")
        self.assertEqual(session.layout_analysis()["crossings"], 0)
        new_source = session.add_node("First", alias="newSource", x=300, y=100)
        new_target = session.add_node("Second", alias="newTarget", x=0, y=500)
        session.connect(f"{new_source}.Output", f"{new_target}.Input")
        with patch.object(session, "_reindex_aliases", wraps=session._reindex_aliases) as reindex:
            report = session.layout_analysis()
        self.assertEqual(reindex.call_count, 1)
        self.assertEqual(report["crossing_links"], [(("oldSource", "Output", "oldTarget", "Input"),
                                                   ("newSource", "Output", "newTarget", "Input"))])
        self.assertEqual(session.alias_for(session.node(new_source).get("Id")), "newSource")


if __name__ == "__main__":
    unittest.main()
