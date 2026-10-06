import unittest

from vl_patch_manipulator.catalog import InMemoryNodeCatalog, NodeSpec, PinSpec
from vl_patch_manipulator.session import PatchSession


class ProcessOrphanTests(unittest.TestCase):
    def session(self):
        return PatchSession.new(catalog=InMemoryNodeCatalog(
            NodeSpec(name, inputs=(PinSpec("Input", "Float32"),),
                     outputs=(PinSpec("Output", "Float32", "OutputPin"),))
            for name in ("Relay", "RenderWindow")))

    def process(self, session, name="Family"):
        return session.add_process(name, inputs=(PinSpec("Value", "Float32"),),
                                   outputs=(PinSpec("Output", "Float32", "OutputPin"),))

    def connect_body(self, session, process):
        relay = session.add_node("Relay", patch=process.body)
        session.connect(process.inputs["Value"], f"{relay}.Input")
        session.connect(f"{relay}.Output", process.outputs["Output"])
        return relay

    def test_connected_definition_body_and_root_call_are_not_orphans(self):
        session = self.session()
        process = self.process(session)
        self.connect_body(session, process)
        window = session.add_node("RenderWindow")
        session.connect(f"{process.call}.Output", f"{window}.Input")
        self.assertEqual(session.find_orphans(), [])
        self.assertFalse(any(item.code == "orphan-operational-node" for item in session.validate().diagnostics))

    def test_disconnected_body_branch_and_root_branch_are_still_orphans(self):
        session = self.session()
        process = self.process(session)
        self.connect_body(session, process)
        window = session.add_node("RenderWindow")
        session.connect(f"{process.call}.Output", f"{window}.Input")
        body_a = session.add_node("Relay", patch=process.body)
        body_b = session.add_node("Relay", patch=process.body)
        session.connect(f"{body_a}.Output", f"{body_b}.Input")
        root_a = session.add_node("Relay")
        root_b = session.add_node("Relay")
        session.connect(f"{root_a}.Output", f"{root_b}.Input")
        self.assertEqual({item["alias"] for item in session.find_orphans()}, {body_a, body_b, root_a, root_b})

    def test_connected_unused_definition_does_not_hide_orphan_root_call(self):
        session = self.session()
        process = self.process(session)
        self.connect_body(session, process)
        window = session.add_node("RenderWindow")
        pad = session.add_pad(value="1")
        session.connect(pad, f"{window}.Input")
        self.assertEqual({item["alias"] for item in session.find_orphans()}, {process.call})

    def test_missing_output_connection_is_not_promoted_to_a_terminal_sink(self):
        session = self.session()
        process = self.process(session)
        relay = session.add_node("Relay", patch=process.body)
        session.connect(process.inputs["Value"], f"{relay}.Input")
        window = session.add_node("RenderWindow")
        session.connect(f"{process.call}.Output", f"{window}.Input")
        self.assertEqual({item["alias"] for item in session.find_orphans()}, {relay})

    def test_disabled_update_does_not_hide_dead_definition_body(self):
        session = self.session()
        process = self.process(session)
        relay = self.connect_body(session, process)
        owner = process.body.getparent()
        update = owner.find("Patch[@Name='Update']")
        for fragment in owner.findall("ProcessDefinition/Fragment"):
            if fragment.get("Patch") == update.get("Id"):
                fragment.set("Enabled", "false")
        window = session.add_node("RenderWindow")
        session.connect(f"{process.call}.Output", f"{window}.Input")
        self.assertEqual({item["alias"] for item in session.find_orphans()}, {relay})

    def test_direct_signature_output_and_value_pad_portal_are_supported(self):
        session = self.session()
        direct = self.process(session, "Direct")
        relay = session.add_node("Relay", patch=direct.body)
        session.remove(direct.outputs["Output"])
        session.connect(f"{relay}.Output", direct.update_outputs["Output"])
        window = session.add_node("RenderWindow")
        session.connect(f"{direct.call}.Output", f"{window}.Input")
        self.assertEqual(session.find_orphans(), [])
        other = self.process(session, "PadPortal")
        body = session.add_node("Relay", patch=other.body)
        pad = session.add_pad(patch=other.body)
        session.remove(other.outputs["Output"])
        session.connect(f"{body}.Output", pad)
        session.connect(pad, other.update_outputs["Output"])
        session.connect(f"{other.call}.Output", f"{direct.call}.Value")
        self.assertEqual(session.find_orphans(), [])


if __name__ == "__main__":
    unittest.main()
