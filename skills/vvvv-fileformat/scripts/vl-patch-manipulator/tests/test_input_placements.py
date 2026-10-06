from copy import deepcopy
import unittest

from lxml import etree

from vl_patch_manipulator.catalog import PinSpec
from vl_patch_manipulator.ids import ID_PATTERN
from vl_patch_manipulator.session import PatchSession


class InputPlacementTests(unittest.TestCase):
    def session(self):
        session = PatchSession.new()
        process = session.add_process("Guide", inputs=(PinSpec("Font", "PTFont"),),
                                      outputs=(PinSpec("Output", "Float32", "OutputPin"),))
        return session, process

    def test_repeated_input_uses_one_signature_and_saved_proxy_schema(self):
        session, process = self.session()
        signature = process.body.getparent().find("Patch[@Name='Update']")
        before_signature = etree.tostring(signature)
        first = session.add_input_placement(process.inputs["Font"], (220, 180), patch=process.body)
        second = session.add_input_placement(process.update_inputs["Font"], (480, 190))
        third = session.add_input_placement(first, (740, 200), patch=process.body.getparent())
        self.assertEqual(etree.tostring(signature), before_signature)
        # VL.Model.Patch.AddProxy (Nodes.cs:1017) writes plain ControlPoints
        # with hidden links to one existing signature Pin. Saved donor:
        # VVVV.VL.DynamicBuffersAndTextures.vl, Input Mu9Mbn4i2Q5PJWpiwi8KmK
        # has eight such ControlPoint placements, no DefinitionId selector.
        for identifier, bounds in ((first, "220,180"), (second, "480,190"), (third, "740,200")):
            element = session.graph.element(identifier)
            self.assertEqual(element.attrib, {"Id": identifier, "Bounds": bounds})
            self.assertIs(element.getparent(), process.body)
            links = [link for link in session.graph.links
                     if link.get("Ids") == f"{process.update_inputs['Font']},{identifier}"]
            self.assertEqual(len(links), 1)
            self.assertEqual(links[0].get("IsHidden"), "true")
            self.assertIs(links[0].getparent(), process.body.getparent())
        ids = [element.get("Id") for element in session.document.root.iter() if element.get("Id")]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(ID_PATTERN.fullmatch(identifier) for identifier in ids))
        self.assertTrue(session.validate(include_orphan_warnings=False).ok)

    def test_invalid_input_or_scope_does_not_mutate(self):
        session, process = self.session()
        other = session.add_process("Other")
        slot = session.add_slot("State")
        before = session.document.to_bytes()
        for source, kwargs in (
            (process.inputs["Font"], {"patch": other.body}),
            (process.inputs["Font"], {"patch": deepcopy(process.body)}),
            (process.inputs["Font"], {"position": (1, 2, 3)}),
            (process.outputs["Output"], {}),
            (process.call_inputs["Font"], {}),
            (slot.read_pad, {}),
        ):
            with self.assertRaises(ValueError):
                session.add_input_placement(source, **kwargs)
            self.assertEqual(session.document.to_bytes(), before)

    def test_unknown_xml_and_signature_preserved_through_serializer(self):
        session, process = self.session()
        owner = process.body.getparent()
        owner.set("FutureAttribute", "keep")
        unknown = etree.SubElement(owner, "{property}Future", {"{property}Type": "String"})
        unknown.text = "unmodified"
        comment = etree.Comment("human annotation")
        owner.append(comment)
        baseline = [(element, etree.tostring(element)) for element in owner]
        portal = session.add_input_placement(process.inputs["Font"], (250.5, -10.5))
        self.assertEqual(session.graph.element(portal).get("Bounds"), "251,-11")
        # Only the canvas receives its new child; all other baseline children
        # including unknown namespaced properties retain their content/order.
        for element, payload in baseline:
            if element is not process.body:
                self.assertEqual(etree.tostring(element), payload)
        payload = session.document.to_bytes()
        reopened = PatchSession.from_bytes(payload)
        self.assertEqual(reopened.document.to_bytes(), payload)
        self.assertTrue(reopened.validate(include_orphan_warnings=False).ok)
        self.assertEqual(reopened.graph.element(owner.get("Id")).get("FutureAttribute"), "keep")

    def test_validator_rejects_cross_scope_hidden_reference(self):
        session, process = self.session()
        other = session.add_process("Other")
        portal = session.add_input_placement(process.inputs["Font"])
        other.body.append(session.graph.element(portal))
        session.graph.refresh()
        report = session.graph.validate(include_orphan_warnings=False)
        self.assertIn("input-placement-scope", [item.code for item in report.errors])
        before = session.document.to_bytes()
        with self.assertRaises(ValueError):
            session.add_input_placement(portal)
        self.assertEqual(session.document.to_bytes(), before)

    def test_validator_rejects_invented_definition_id_selector(self):
        session, process = self.session()
        portal = session.add_input_placement(process.inputs["Font"])
        element = session.graph.element(portal)
        element.set("DefinitionId", process.update_inputs["Font"])
        report = session.validate(include_orphan_warnings=False)
        self.assertIn("unsupported-input-selector", [item.code for item in report.errors])

    def test_validator_accepts_input_proxy_inside_nested_region(self):
        session, process = self.session()
        portal = session.add_input_placement(process.inputs["Font"])
        builder = session.add_matrix_repeat_builder(patch=process.body)
        nested = session.graph.element(builder.repeat_region).find("Patch")
        nested.append(session.graph.element(portal))
        session.graph.refresh()
        self.assertTrue(session.graph.validate(include_orphan_warnings=False).ok)
        reopened = PatchSession.from_bytes(session.document.to_bytes())
        self.assertTrue(reopened.validate(include_orphan_warnings=False).ok)


if __name__ == "__main__":
    unittest.main()
