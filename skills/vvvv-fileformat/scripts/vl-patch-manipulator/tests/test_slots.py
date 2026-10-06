import unittest

from lxml import etree

from vl_patch_manipulator.catalog import InMemoryNodeCatalog, NodeSpec, PinSpec
from vl_patch_manipulator.session import PatchSession
from vl_patch_manipulator.ids import new_vl_id


class SlotTests(unittest.TestCase):
    def session(self):
        return PatchSession.new(catalog=InMemoryNodeCatalog(
            NodeSpec(name, inputs=(PinSpec("Input"),), outputs=(PinSpec("Output", kind="OutputPin"),))
            for name in ("OrbitCamera", "RenderWindow")))

    def test_real_slot_matches_saved_accessor_pattern_and_round_trips(self):
        session = self.session()
        slot = session.add_slot("Input Source", read_position=(960, 1788), write_position=(996, 2038))
        field = session.graph.element(slot.slot_id)
        self.assertEqual(field.tag, "Slot")
        owner = session.graph._main_canvas().getparent()
        self.assertIs(field.getparent(), owner)
        for identifier, bounds in ((slot.read_pad, "960,1788"), (slot.write_pad, "996,2038")):
            pad = session.graph.element(identifier)
            self.assertEqual(pad.attrib, {"Id": identifier, "SlotId": slot.slot_id, "Bounds": bounds})
            self.assertIs(pad.getparent(), session.graph._main_canvas())
        # Frozen vvvv-saved donor: automatic window association removed this
        # feedback field from the live help patch, but Slot serialization stays valid.
        document = etree.fromstring(b'<Patch><Slot Id="FeKzN7lGsVHMgaJb6iqamN" Name="Input Source" />'
                                    b'<Canvas><Pad Id="R8WC40VTe8TQJ7LWUyA1cV" SlotId="FeKzN7lGsVHMgaJb6iqamN" Bounds="996,2038" />'
                                    b'<Pad Id="CCHxsNehs5SNf5MYlVLFAI" SlotId="FeKzN7lGsVHMgaJb6iqamN" Bounds="960,1788" /></Canvas></Patch>')
        original_slot = document.find("Slot")
        original_pads = document.findall(f".//Pad[@SlotId='{original_slot.get('Id')}']")
        self.assertEqual(len(original_pads), 2)
        self.assertTrue(all(set(pad.attrib) == {"Id", "SlotId", "Bounds"} for pad in original_pads))
        reopened = PatchSession.from_bytes(session.document.to_bytes())
        self.assertEqual(reopened.graph.element(slot.read_pad).get("SlotId"), slot.slot_id)
        self.assertEqual(reopened.graph.element(slot.write_pad).get("SlotId"), slot.slot_id)
        self.assertTrue(reopened.validate().ok)

    def test_camera_window_use_real_slot_with_ordinary_links(self):
        session = self.session()
        camera = session.add_node("OrbitCamera", y=100)
        window = session.add_node("RenderWindow", y=300)
        slot = session.add_slot("Input Source")
        session.connect(f"{camera}.Output", f"{window}.Input")
        session.connect(f"{window}.Output", slot.write_pad)
        session.connect(slot.read_pad, f"{camera}.Input")
        outgoing, _ = session.graph.directed_node_adjacency()
        camera_id, window_id = session.node(camera).get("Id"), session.node(window).get("Id")
        self.assertNotIn(camera_id, outgoing.get(window_id, set()))
        self.assertEqual(outgoing[camera_id], {window_id})
        self.assertEqual(session.find_orphans(), [])
        self.assertTrue(all(link.get("IsFeedback") is None for link in session.graph.links))
        self.assertTrue(session.validate().ok)

    def test_shared_slot_writers_reach_window_through_multiple_reads(self):
        session = self.session()
        producer = session.add_node("OrbitCamera")
        first = session.add_node("OrbitCamera")
        second = session.add_node("OrbitCamera")
        window = session.add_node("RenderWindow")
        slot = session.add_slot("Shared Resource")
        extra_read = session.add_slot_read(slot)
        session.connect(f"{producer}.Output", slot.write_pad)
        session.connect(slot.read_pad, f"{first}.Input")
        session.connect(extra_read, f"{second}.Input")
        session.connect(f"{first}.Output", f"{second}.Input")
        session.connect(f"{second}.Output", f"{window}.Input")
        directed_before = session.graph.directed_node_adjacency(include_feedback=False)
        connected_before = session.graph.connected_node_adjacency()
        self.assertEqual(session.find_orphans(), [])
        self.assertFalse(any(item.code == "orphan-operational-node" for item in session.validate().diagnostics))
        self.assertEqual(session.graph.directed_node_adjacency(include_feedback=False), directed_before)
        self.assertEqual(session.graph.connected_node_adjacency(), connected_before)
        producer_id, first_id = session.node(producer).get("Id"), session.node(first).get("Id")
        self.assertNotIn(first_id, directed_before[0].get(producer_id, set()))

    def test_unused_slot_reads_do_not_hide_disconnected_writer(self):
        session = self.session()
        producer = session.add_node("OrbitCamera")
        window = session.add_node("RenderWindow")
        slot = session.add_slot("Unused Resource")
        session.add_slot_read(slot)
        session.connect(f"{producer}.Output", slot.write_pad)
        pad = session.add_pad(value="1")
        session.connect(pad, f"{window}.Input")
        self.assertEqual({item["alias"] for item in session.find_orphans()}, {producer})

    def test_local_process_slot_writer_reaches_its_output_boundary(self):
        session = self.session()
        process = session.add_process("SharedResource", outputs=(PinSpec("Output", "Float32", "OutputPin"),))
        producer = session.add_node("OrbitCamera", patch=process.body)
        consumer = session.add_node("OrbitCamera", patch=process.body)
        slot = session.add_slot("Resource", patch=process.body.getparent())
        session.connect(f"{producer}.Output", slot.write_pad)
        session.connect(slot.read_pad, f"{consumer}.Input")
        session.connect(f"{consumer}.Output", process.outputs["Output"])
        window = session.add_node("RenderWindow")
        session.connect(f"{process.call}.Output", f"{window}.Input")
        self.assertEqual(session.find_orphans(), [])

    def test_foreign_definition_slot_read_does_not_connect_writer(self):
        session = self.session()
        process = session.add_process("Other", outputs=(PinSpec("Output", "Float32", "OutputPin"),))
        producer = session.add_node("OrbitCamera")
        consumer = session.add_node("OrbitCamera", patch=process.body)
        slot = session.add_slot("Resource")
        process.body.append(session.graph.element(slot.read_pad))
        session.graph.refresh()
        session.connect(f"{producer}.Output", slot.write_pad)
        session.connect(slot.read_pad, f"{consumer}.Input")
        session.connect(f"{consumer}.Output", process.outputs["Output"])
        window = session.add_node("RenderWindow")
        session.connect(f"{process.call}.Output", f"{window}.Input")
        self.assertEqual({item["alias"] for item in session.find_orphans()}, {producer})
        self.assertIn("slot-scope", {item.code for item in session.validate().errors})

    def test_scoped_typed_slot_and_invalid_request_do_not_mutate(self):
        session = self.session()
        process = session.add_process("Helper")
        owner = process.body.getparent()
        slot = session.add_slot("State", patch=owner, type_name="Float32")
        self.assertIs(session.graph.element(slot.slot_id).getparent(), owner)
        self.assertIs(session.graph.element(slot.read_pad).getparent(), process.body)
        self.assertEqual(session.graph.element(slot.slot_id).find("{property}TypeAnnotation/Choice").get("Name"), "Float32")
        before = session.document.to_bytes()
        with self.assertRaises(ValueError):
            session.add_slot("State", patch=owner)
        with self.assertRaises(ValueError):
            session.add_slot("Bad", patch=process.body)
        self.assertEqual(session.document.to_bytes(), before)

    def test_repeated_slot_reads_share_field_and_do_not_clone_type_or_value(self):
        session = self.session()
        slot = session.add_slot("Font", type_name="PTFont")
        field = session.graph.element(slot.slot_id)
        etree.SubElement(field, "{property}Value", {"{reflection}IsNull": "true"})
        before_field = etree.tostring(field)
        pads = [session.add_slot_read(slot, (100 + index * 100, 200)) for index in range(3)]
        pads.append(session.add_slot_read(slot.slot_id, (450, 220)))
        self.assertEqual(len(set(pads)), 4)
        self.assertEqual(etree.tostring(field), before_field)
        self.assertEqual(len(field.getparent().findall("Slot")), 1)
        for identifier in pads:
            pad = session.graph.element(identifier)
            self.assertEqual(set(pad.attrib), {"Id", "SlotId", "Bounds"})
            self.assertEqual(pad.get("SlotId"), slot.slot_id)
            self.assertEqual(len(pad), 0)
        payload = session.document.to_bytes()
        reopened = PatchSession.from_bytes(payload)
        self.assertEqual(reopened.document.to_bytes(), payload)
        self.assertTrue(reopened.validate().ok)

    def test_slot_read_rejects_foreign_field_and_scope_without_mutation(self):
        session = self.session()
        process = session.add_process("Other")
        slot = session.add_slot("Font")
        before = session.document.to_bytes()
        for source, kwargs in ((slot.slot_id, {"patch": process.body}),
                               (slot.slot_id, {"position": (1, 2, 3)}),
                               (slot.read_pad, {}),
                               (process.definition_id, {})):
            with self.assertRaises(ValueError):
                session.add_slot_read(source, **kwargs)
            self.assertEqual(session.document.to_bytes(), before)

    def test_remove_slot_requires_exact_accessors_and_preserves_shared_state(self):
        session = self.session()
        slot = session.add_slot("Input Source")
        extra = session.add_slot_read(slot)
        before = session.document.to_bytes()
        for accessors in ((), (slot.read_pad, slot.write_pad),
                          (slot.read_pad, slot.write_pad, extra, extra)):
            with self.assertRaises(ValueError):
                session.remove_slot(slot, accessor_ids=accessors)
            self.assertEqual(session.document.to_bytes(), before)
        camera = session.add_node("OrbitCamera")
        window = session.add_node("RenderWindow")
        session.connect(f"{camera}.Output", f"{window}.Input")
        session.connect(f"{window}.Output", slot.write_pad)
        session.connect(slot.read_pad, f"{camera}.Input")
        session.connect(extra, f"{camera}.Input")
        before = session.document.to_bytes()
        kept_link = session.graph.links[0].get("Id")
        result = session.remove_slot(slot, accessor_ids=(slot.read_pad, slot.write_pad, extra))
        self.assertEqual(len(result["links"]), 2)
        self.assertIn(kept_link, session.graph.by_id)
        self.assertNotIn(slot.slot_id, session.graph.by_id)
        self.assertTrue(session.validate().ok)
        self.assertTrue(session.undo())
        self.assertEqual(session.document.to_bytes(), before)
        self.assertTrue(session.redo())
        reopened = PatchSession.from_bytes(session.document.to_bytes())
        self.assertNotIn(slot.slot_id, reopened.graph.by_id)
        self.assertTrue(reopened.validate().ok)

    def test_remove_empty_slot_and_reject_foreign_accessors_without_mutation(self):
        session = self.session()
        slot = session.add_slot("Unused")
        session.remove(slot.read_pad)
        session.remove(slot.write_pad)
        session.remove_slot(slot)
        self.assertNotIn(slot.slot_id, session.graph.by_id)
        foreign = session.add_slot("Foreign")
        process = session.add_process("Other")
        process.body.append(session.graph.element(foreign.read_pad))
        session.graph.refresh()
        before = session.document.to_bytes()
        with self.assertRaisesRegex(ValueError, "foreign"):
            session.remove_slot(foreign, accessor_ids=(foreign.read_pad, foreign.write_pad))
        self.assertEqual(session.document.to_bytes(), before)

    def test_validator_rejects_missing_slot_and_cross_scope_accessor(self):
        session = self.session()
        process = session.add_process("Other")
        slot = session.add_slot("Font")
        read = session.add_slot_read(slot)
        process.body.append(session.graph.element(read))
        session.graph.element(slot.read_pad).set("SlotId", new_vl_id())
        session.graph.refresh()
        errors = [item.code for item in session.graph.validate().errors]
        self.assertIn("slot-scope", errors)
        self.assertIn("dangling-slot", errors)

    def test_validator_accepts_outer_slot_inside_nested_region_and_lifecycle(self):
        session = self.session()
        process = session.add_process("Owner")
        owner = process.body.getparent()
        slot = session.add_slot("State", patch=owner)
        builder = session.add_matrix_repeat_builder(patch=process.body)
        nested = session.graph.element(builder.repeat_region).find("Patch")
        nested_read = session.add_slot_read(slot)
        nested.append(session.graph.element(nested_read))
        update_read = session.add_slot_read(slot)
        owner.find("Patch[@Name='Update']").append(session.graph.element(update_read))
        session.graph.refresh()
        self.assertTrue(session.graph.validate(include_orphan_warnings=False).ok)
        reopened = PatchSession.from_bytes(session.document.to_bytes())
        self.assertTrue(reopened.validate(include_orphan_warnings=False).ok)


if __name__ == "__main__":
    unittest.main()
