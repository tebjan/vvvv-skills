from pathlib import Path
import tempfile
import unittest

from lxml import etree

from vl_patch_manipulator.catalog import InMemoryNodeCatalog, NodeSpec, PinSpec
from vl_patch_manipulator.session import PatchSession
from vl_patch_manipulator.ids import new_vl_id


class FeedbackTests(unittest.TestCase):
    def session(self):
        return PatchSession.new(catalog=InMemoryNodeCatalog(
            NodeSpec(name, inputs=(PinSpec("Input", "Float32"),),
                     outputs=(PinSpec("Output", "Float32", "OutputPin"),))
            for name in ("Source", "OrbitCamera", "RenderWindow", "Relay")))

    def feedback(self, session, source, target):
        return session.graph.add_link(session._endpoint_ref(source, input_only=False),
                                      session._endpoint_ref(target, input_only=True), IsFeedback="true")

    def test_flag_only_camera_window_delay_is_rejected(self):
        session = self.session()
        source = session.add_node("Source", x=10, y=10)
        camera = session.add_node("OrbitCamera", x=10, y=100)
        window = session.add_node("RenderWindow", x=10, y=200)
        session.connect(f"{source}.Output", f"{camera}.Input")
        session.connect(f"{camera}.Output", f"{window}.Input")
        self.feedback(session, f"{window}.Output", f"{camera}.Input")
        source_id = session.node(source).get("Id")
        camera_id = session.node(camera).get("Id")
        window_id = session.node(window).get("Id")
        outgoing, _ = session.graph.directed_node_adjacency()
        self.assertEqual(outgoing[window_id], {camera_id})
        outgoing, _ = session.graph.directed_node_adjacency(include_feedback=False)
        self.assertEqual(outgoing[window_id], {camera_id})
        self.assertNotEqual(session.graph.reachable_from_sinks(), {source_id, camera_id, window_id})
        self.assertFalse(session.validate().ok)
        self.assertIn("unsupported-feedback-link", {item.code for item in session.validate().errors})
        analysis = session.layout_analysis()
        self.assertEqual(len(analysis["upward_links"]), 1)
        self.assertEqual(len(analysis["feedback_links"]), 1)
        self.assertEqual(analysis["link_count"], 3)

    def test_backward_ordinary_link_remains_a_layout_error(self):
        session = self.session()
        lower = session.add_node("Relay", x=10, y=200)
        upper = session.add_node("Relay", x=10, y=10)
        link_id = session.connect(f"{lower}.Output", f"{upper}.Input")
        self.assertEqual(len(session.layout_analysis()["upward_links"]), 1)
        session.graph.element(link_id).set("IsFeedback", "false")
        self.assertEqual(len(session.layout_analysis()["upward_links"]), 1)
        session.graph.element(link_id).set("IsFeedback", "true")
        analysis = session.layout_analysis()
        self.assertEqual(len(analysis["upward_links"]), 1)
        self.assertFalse(analysis["ok"])
        self.assertFalse(session.validate().ok)

    def test_raw_feedback_flag_does_not_hide_crossings_and_offsets(self):
        session = self.session()
        lower_left = session.add_node("Relay", x=0, y=200)
        upper_right = session.add_node("Relay", x=200, y=0)
        upper_left = session.add_node("Relay", x=0, y=0)
        lower_right = session.add_node("Relay", x=200, y=200)
        feedback = self.feedback(session, f"{lower_left}.Output", f"{upper_right}.Input")
        session.connect(f"{upper_left}.Output", f"{lower_right}.Input")
        analysis = session.layout_analysis()
        self.assertEqual(analysis["crossings"], 1)
        self.assertEqual(len(analysis["misaligned_links"]), 2)
        self.assertEqual(analysis["link_count"], 2)
        session.graph.element(feedback).set("IsFeedback", "false")
        analysis = session.layout_analysis()
        self.assertEqual(analysis["crossings"], 1)
        self.assertEqual(len(analysis["upward_links"]), 1)

    def test_snapshot_and_svg_identify_feedback_without_red_error_style(self):
        session = self.session()
        camera = session.add_node("OrbitCamera", x=0, y=0)
        window = session.add_node("RenderWindow", x=0, y=200)
        session.connect(f"{camera}.Output", f"{window}.Input")
        self.feedback(session, f"{window}.Output", f"{camera}.Input")
        links = session.spatial_snapshot()["links"]
        self.assertEqual([link["feedback"] for link in links], [False, True])
        with tempfile.TemporaryDirectory() as folder:
            path = session.render_svg(Path(folder) / "feedback.svg")
            svg = etree.parse(str(path))
            paths = svg.findall("{http://www.w3.org/2000/svg}path")
            self.assertEqual([item.get("class") for item in paths], ["link", "link feedback"])
            self.assertIn("not an automatic delay", paths[1].find("{http://www.w3.org/2000/svg}title").text)
            self.assertFalse(path.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_paired_region_border_feedback_is_recognized(self):
        session = self.session()
        region = etree.SubElement(session.graph._main_canvas(), "Node", Id=new_vl_id(), Bounds="100,100,200,200")
        reference = etree.SubElement(region, "{property}NodeReference")
        etree.SubElement(reference, "Choice", Kind="StatefulRegion", Name="Region (Stateful)", Fixed="true")
        etree.SubElement(reference, "CategoryReference", Kind="Category", Name="Primitive")
        etree.SubElement(reference, "Choice", Kind="ApplicationStatefulRegion", Name="ForEach")
        top = etree.SubElement(region, "ControlPoint", Id=new_vl_id(), Bounds="120,100", Alignment="Top")
        bottom = etree.SubElement(region, "ControlPoint", Id=new_vl_id(), Bounds="120,300", Alignment="Bottom")
        session._refresh()
        link_id = session.graph.add_link(bottom.get("Id"), top.get("Id"), IsFeedback="true")
        self.assertTrue(session.graph.is_region_feedback(session.graph.element(link_id)))
        self.assertTrue(session.validate(include_orphan_warnings=False).ok)
        analysis = session.layout_analysis()
        self.assertEqual(analysis["upward_links"], [])
        # The saved border-pair structure establishes feedback classification.
        top.set("Alignment", "None")
        self.assertFalse(session.validate(include_orphan_warnings=False).ok)


if __name__ == "__main__":
    unittest.main()
