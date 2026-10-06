from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from lxml import etree

from vl_patch_manipulator.catalog import InMemoryNodeCatalog, NodeSpec, PinSpec
from vl_patch_manipulator.document import PROPERTY_NS
from vl_patch_manipulator.ids import ID_PATTERN
from vl_patch_manipulator.session import PatchSession


class ProcessTests(unittest.TestCase):
    def session(self) -> PatchSession:
        return PatchSession.new(catalog=InMemoryNodeCatalog((
            NodeSpec("Relay", inputs=(PinSpec("Input", "Float32"),),
                     outputs=(PinSpec("Output", "Float32", "OutputPin"),)),
        )))

    def process(self, session: PatchSession, **kwargs):
        return session.add_process("Family", inputs=(PinSpec("Value", "Float32"),),
                                   outputs=(PinSpec("Output", "Float32", "OutputPin"),),
                                   document_name="Test.vl", **kwargs)

    def test_process_matches_saved_plates_lifecycle_and_call(self):
        session = self.session()
        process = self.process(session, alias="family")
        owner = process.body.getparent()
        self.assertEqual([item.get("Name") for item in owner.findall("Patch")], ["Create", "Update"])
        self.assertEqual({item.get("Patch") for item in owner.findall("ProcessDefinition/Fragment")
                          if item.get("Enabled") == "true"}, {item.get("Id") for item in owner.findall("Patch")})
        definition = session.graph.element(process.definition_id)
        self.assertEqual(definition.getparent().get("CanvasType"), "FullCategory")
        self.assertEqual(definition.find("{property}NodeReference/CategoryReference").attrib,
                         {"Kind": "Category", "Name": "Primitive"})
        call = session.node(process.call)
        reference = call.find("{property}NodeReference")
        self.assertEqual(reference.get("LastDependency"), "Test.vl")
        self.assertEqual(reference.find("Choice").attrib, {"Kind": "ProcessNode", "Name": "Family"})
        self.assertEqual([(pin.get("Name"), pin.get("Kind")) for pin in call.findall("Pin")],
                         [("Node Context", "InputPin"), ("Value", "InputPin"), ("Output", "OutputPin")])
        self.assertEqual(call.find("Pin").get("IsHidden"), "true")
        # The signature boundary uses hidden reference links, not fabricated
        # PadPinKind attributes or an implicit initialization convention.
        self.assertEqual(len(owner.findall("Link[@IsHidden='true']")), 2)
        self.assertTrue(session.validate(include_orphan_warnings=False).ok)

    def test_boundaries_dataflow_ids_and_round_trip(self):
        session = self.session()
        process = self.process(session)
        relay = session.add_node("Relay", patch=process.body)
        session.connect(process.inputs["Value"], f"{relay}.Input")
        session.connect(f"{relay}.Output", process.outputs["Output"])
        owner = process.body.getparent()
        hidden = {link.get("Ids") for link in owner.findall("Link[@IsHidden='true']")}
        self.assertEqual(hidden, {
            f"{process.update_inputs['Value']},{process.inputs['Value']}",
            f"{process.outputs['Output']},{process.update_outputs['Output']}",
        })
        self.assertIs(session.node(relay).getparent(), process.body)
        ids = [element.get("Id") for element in session.document.root.iter() if element.get("Id")]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(ID_PATTERN.fullmatch(value) for value in ids))
        with tempfile.TemporaryDirectory() as folder:
            path = session.save(Path(folder) / "Test.vl")
            data = path.read_bytes()
            self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
            reopened = PatchSession.load(path)
            self.assertTrue(reopened.validate(include_orphan_warnings=False).ok)
            self.assertEqual(reopened.document.to_bytes(), data)
            self.assertEqual(reopened.document_catalog.resolve("Family", category="Main").inputs[1].name, "Value")

    def test_typed_signature_preserves_order_and_exact_generic_annotation(self):
        session = self.session()
        annotation = etree.Element(f"{{{PROPERTY_NS}}}TypeAnnotation", LastCategoryFullName="System", LastDependency="VL.CoreLib.vl")
        etree.SubElement(annotation, "Choice", Kind="TypeFlag", Name="ReadOnlyMemory")
        arguments = etree.SubElement(annotation, f"{{{PROPERTY_NS}}}TypeArguments")
        matrix = etree.SubElement(arguments, "TypeReference", LastCategoryFullName="3D", LastDependency="VL.CoreLib.vl")
        etree.SubElement(matrix, "Choice", Kind="TypeFlag", Name="Matrix")
        process = session.add_process("Guide", inputs=(PinSpec("Lines", "ReadOnlyMemory"), PinSpec("Font", "PTFont")),
                                      outputs=(PinSpec("Output", "IDX12RendererBase", "OutputPin"),),
                                      type_annotations={"Lines": annotation})
        signature = process.body.getparent().find("Patch[@Name='Update']")
        self.assertEqual([pin.get("Name") for pin in signature.findall("Pin")], ["Lines", "Font", "Output"])
        copied = signature.find("Pin/{property}TypeAnnotation")
        self.assertEqual([(element.tag, dict(element.attrib), element.text) for element in copied.iter()],
                         [(element.tag, dict(element.attrib), element.text) for element in annotation.iter()])
        self.assertIsNot(copied, annotation)
        self.assertIsNone(annotation.getparent())
        self.assertEqual(signature.findall("Pin")[1].find("{property}TypeAnnotation/Choice").get("Name"), "PTFont")

    def test_invalid_contracts_do_not_mutate(self):
        session = self.session()
        before = session.document.to_bytes()
        for kwargs in ({"inputs": (PinSpec("X"),)},
                       {"outputs": (PinSpec("X", "Float32"),)},
                       {"inputs": (PinSpec("X", "Float32"), PinSpec("X", "Float32"))},
                       {"type_annotations": {"Missing": etree.Element("Wrong")}}):
            with self.assertRaises(ValueError):
                session.add_process("Invalid", **kwargs)
            self.assertEqual(session.document.to_bytes(), before)
        self.process(session)
        before = session.document.to_bytes()
        with self.assertRaises(ValueError):
            self.process(session)
        self.assertEqual(session.document.to_bytes(), before)

    def test_empty_canvas_scopes(self):
        session = self.session()
        process = session.add_process("Empty")
        relay = session.add_node("Relay", patch=process.body)
        self.assertIs(session.node(relay).getparent(), process.body)
        pad = session.add_pad(value="1", type_name="Float32", patch=process.body)
        comment = session.add_annotation("comment", text="Local help", patch=process.body)
        self.assertIs(session.graph.element(session._resolve_entity_id(pad)).getparent(), process.body)
        self.assertIs(session.graph.element(session._resolve_entity_id(comment)).getparent(), process.body)
        builder = session.add_matrix_repeat_builder(patch=process.body)
        self.assertIs(session.graph.element(builder.cache_region).getparent(), process.body)
        self.assertTrue(session.validate(include_orphan_warnings=False).ok)

    def test_remove_control_point_cleans_all_incident_links(self):
        session = self.session()
        process = self.process(session)
        relay = session.add_node("Relay", patch=process.body)
        session.connect(process.inputs["Value"], f"{relay}.Input")
        untouched = session.connect(f"{relay}.Output", process.outputs["Output"])
        session.remove(process.inputs["Value"])
        self.assertNotIn(process.inputs["Value"], session.graph.by_id)
        self.assertIn(untouched, session.graph.by_id)
        self.assertTrue(all(process.inputs["Value"] not in (session.graph.link_hub_ids(link) or ()) for link in session.graph.links))
        self.assertTrue(session.validate(include_orphan_warnings=False).ok)

    def test_move_closed_subgraph_retains_ids_and_geometry(self):
        session = self.session()
        pad = session.add_pad(value="1", x=10, y=20)
        relay = session.add_node("Relay", x=10, y=60)
        link = session.connect(pad, f"{relay}.Input")
        process = self.process(session)
        pad_id = session._resolve_entity_id(pad)
        relay_id = session.node(relay).get("Id")
        width = session.node(relay).get("Bounds").split(",")[2:]
        session.move_subgraph((pad, relay), process.body, dx=100, dy=200)
        self.assertIs(session.node(relay).getparent(), process.body)
        self.assertIs(session.graph.element(pad_id).getparent(), process.body)
        self.assertIs(session.graph.element(link).getparent(), process.body.getparent())
        self.assertEqual(session.node(relay).get("Id"), relay_id)
        self.assertEqual(session.node(relay).get("Bounds").split(","), ["110", "260", *width])
        self.assertTrue(session.validate(include_orphan_warnings=False).ok)

    def test_move_crossing_link_rejected_without_mutation(self):
        session = self.session()
        pad = session.add_pad(value="1")
        relay = session.add_node("Relay")
        session.connect(pad, f"{relay}.Input")
        process = self.process(session)
        before = session.document.to_bytes()
        with self.assertRaisesRegex(ValueError, "crossing links"):
            session.move_subgraph((relay,), process.body)
        self.assertEqual(session.document.to_bytes(), before)


if __name__ == "__main__":
    unittest.main()
