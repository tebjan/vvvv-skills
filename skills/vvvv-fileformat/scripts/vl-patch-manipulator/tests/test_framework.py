from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from uuid import UUID

from lxml import etree

from vl_patch_manipulator.catalog import JsonNodeCatalog
from vl_patch_manipulator.document import VlDocument
from vl_patch_manipulator.ids import ID_LENGTH, ID_PATTERN, guid_to_vl_id, new_vl_id
from vl_patch_manipulator.session import PatchSession


FIXTURE = b'''<?xml version="1.0" encoding="utf-8"?>
<Document xmlns:p="property" Id="0000000000000000000001" LanguageVersion="2025.7.3" Version="0.128">
  <NugetDependency Id="0000000000000000000002" Location="VL.CoreLib" Version="2025.7.3" />
  <!-- Unknown content must survive round-trip. -->
  <Patch Id="0000000000000000000003">
    <Canvas Id="0000000000000000000004" DefaultCategory="Main" CanvasType="FullCategory" />
    <Node Name="Application" Bounds="100,100" Id="0000000000000000000005">
      <p:NodeReference><Choice Kind="ContainerDefinition" Name="Process" /></p:NodeReference>
      <Patch Id="0000000000000000000006">
        <Canvas Id="0000000000000000000007" CanvasType="Group">
          <Pad Id="0000000000000000000008" Bounds="100,100,80,20" isIOBox="true" Value="1" />
          <Node Name="Sink" Bounds="100,200,50,19" Id="0000000000000000000009">
            <p:NodeReference><Choice Kind="NodeFlag" Name="Node" Fixed="true" /></p:NodeReference>
            <Pin Id="000000000000000000000A" Name="Input" Kind="InputPin" />
          </Node>
          <Link Id="000000000000000000000B" Ids="0000000000000000000008,000000000000000000000A" />
          <FutureThing custom="keep" />
        </Canvas>
        <Patch Id="000000000000000000000C" Name="Create" />
        <Patch Id="000000000000000000000D" Name="Update" />
        <ProcessDefinition Id="000000000000000000000E">
          <Fragment Id="000000000000000000000F" Patch="000000000000000000000C" Enabled="true" />
          <Fragment Id="000000000000000000000G" Patch="000000000000000000000D" Enabled="true" />
        </ProcessDefinition>
      </Patch>
    </Node>
  </Patch>
</Document>
'''


class FrameworkTests(unittest.TestCase):
    def test_verified_reference_rebind_preserves_identity_geometry_and_links(self) -> None:
        session = PatchSession(VlDocument.parse(FIXTURE))
        node_id = '0000000000000000000009'
        pin_id = '000000000000000000000A'
        original_bounds = session.node(node_id).get('Bounds')
        original_link = etree.tostring(session.graph.element('000000000000000000000B'))
        reference = etree.fromstring(b'<p:NodeReference xmlns:p="property" LastCategoryFullName="System"><Choice Kind="NodeFlag" Name="Node" Fixed="true"/><Choice Kind="OperationCallFlag" Name="AsReadOnlyMemory"/></p:NodeReference>')
        session.set_node_reference(node_id, reference, pin_renames={'Input': 'Value'})
        reference.set('LastCategoryFullName', 'Changed donor')
        self.assertEqual(session.node(node_id).get('Bounds'), original_bounds)
        self.assertEqual(session.graph.element(pin_id).get('Name'), 'Value')
        self.assertEqual(etree.tostring(session.graph.element('000000000000000000000B')), original_link)
        self.assertEqual(session.node(node_id).find('{property}NodeReference').get('LastCategoryFullName'), 'System')
        self.assertIn('FutureThing', session.document.to_bytes().decode('utf-8'))

    def test_verified_reference_rebind_rejects_missing_pin_before_mutation(self) -> None:
        session = PatchSession(VlDocument.parse(FIXTURE))
        before = session.document.to_bytes()
        reference = etree.fromstring(b'<p:NodeReference xmlns:p="property"><Choice Kind="OperationCallFlag" Name="Concat"/></p:NodeReference>')
        with self.assertRaises(ValueError):
            session.set_node_reference('0000000000000000000009', reference, pin_renames={'Missing': 'Value'})
        self.assertEqual(session.document.to_bytes(), before)

    def test_id_shape(self) -> None:
        identifier = new_vl_id()
        self.assertEqual(len(identifier), ID_LENGTH)
        self.assertIsNotNone(ID_PATTERN.fullmatch(identifier))

    def test_id_encoding_matches_vl_guid_encoders(self) -> None:
        # VL uses A as digit zero, unlike the conventional 0..9,A..Z,a..z
        # alphabet. Its two 64-bit halves are encoded independently.
        self.assertEqual(guid_to_vl_id(UUID(int=0)), "A" * 22)
        self.assertEqual(guid_to_vl_id(UUID(int=1)), "A" * 21 + "B")
        # Guid.ToByteArray() reverses the first three UUID fields. This vector
        # would fail if the UUID's RFC-order bytes or one 128-bit integer were used.
        mixed = UUID("00000000-0000-0100-0000-000000000000")
        self.assertEqual(guid_to_vl_id(mixed), "A" * 10 + "B" + "A" * 11)

    def test_validate_query_and_round_trip(self) -> None:
        document = VlDocument.parse(FIXTURE)
        graph = document.graph()
        report = graph.validate()
        self.assertTrue(report.ok, report.diagnostics)
        self.assertEqual(len(graph.orphan_operational_nodes()), 0)
        self.assertEqual(graph.incoming["000000000000000000000A"], {"0000000000000000000008"})
        self.assertIn("FutureThing", document.to_bytes().decode("utf-8"))

    def test_incomplete_link_cleanup_and_exact_connection(self) -> None:
        document = VlDocument.parse(FIXTURE)
        graph = document.graph()
        patch = document.root.find("./Patch/Node/Patch")
        self.assertIsNotNone(patch)
        etree.SubElement(patch, "Link", Id=guid_to_vl_id(UUID(int=30)), Ids="0000000000000000000008")
        etree.SubElement(patch, "Link", Id=guid_to_vl_id(UUID(int=31)))
        graph.refresh()
        self.assertEqual(sum(item.code == "link-shape" for item in graph.validate().errors), 2)
        self.assertEqual(len(graph.remove_incomplete_links()), 2)
        source = "0000000000000000000008"
        target = "000000000000000000000A"
        original = graph.ensure_link(source, target)
        self.assertEqual(original, "000000000000000000000B")
        self.assertEqual(graph.ensure_link(source, target), original)
        self.assertTrue(graph.validate().ok)

    def test_link_with_intermediate_data_hub_is_not_an_incomplete_drag(self) -> None:
        # VL's Link.SourceId and SinkId are the first and last Ids; DataHubs
        # may contain intermediate routing points. Two shipped help patches
        # contain three-ID links saved by vvvv.
        document = VlDocument.parse(FIXTURE)
        graph = document.graph()
        canvas = document.root.find("./Patch/Node/Patch/Canvas")
        self.assertIsNotNone(canvas)
        middle = guid_to_vl_id(UUID(int=32))
        etree.SubElement(canvas, "Pad", Id=middle, Bounds="100,150,80,20", isIOBox="true", Value="1")
        link = document.root.find("./Patch/Node/Patch/Canvas/Link")
        self.assertIsNotNone(link)
        link.set("Ids", f"0000000000000000000008,{middle},000000000000000000000A")
        graph.refresh()
        self.assertEqual(graph.link_hub_ids(link), ("0000000000000000000008", middle, "000000000000000000000A"))
        self.assertEqual(graph.link_endpoints(link), ("0000000000000000000008", "000000000000000000000A"))
        self.assertEqual(graph.remove_incomplete_links(), [])
        self.assertTrue(graph.validate().ok, graph.validate().diagnostics)

    def test_clone_remaps_ids_and_references(self) -> None:
        document = VlDocument.parse(FIXTURE)
        graph = document.graph()
        original_node = "0000000000000000000009"
        mapping = graph.clone_subgraph([original_node], dx=100, dy=50)
        self.assertIn(original_node, mapping)
        self.assertNotEqual(original_node, mapping[original_node])
        self.assertEqual(len(graph.by_id), 18)

    def test_new_process_application_contains_executable_lifecycle(self) -> None:
        session = PatchSession.new()
        application = session.document.root.find("./Patch/Node[@Name='Application']")
        self.assertIsNotNone(application)
        application_patch = application.find("Patch")
        self.assertIsNotNone(application_patch)
        lifecycle = {patch.get("Name"): patch.get("Id") for patch in application_patch.findall("Patch")}
        self.assertEqual(set(lifecycle), {"Create", "Update"})
        enabled = {
            fragment.get("Patch")
            for fragment in application_patch.findall("ProcessDefinition/Fragment")
            if fragment.get("Enabled") == "true"
        }
        self.assertEqual(enabled, set(lifecycle.values()))
        self.assertTrue(session.validate(include_orphan_warnings=False).ok)

    def test_process_application_without_lifecycle_is_rejected(self) -> None:
        session = PatchSession.new()
        application_patch = session.document.root.find("./Patch/Node[@Name='Application']/Patch")
        for child in list(application_patch):
            if child.tag == "ProcessDefinition" or (child.tag == "Patch" and child.get("Name") in {"Create", "Update"}):
                application_patch.remove(child)
        session.graph.refresh()
        codes = {item.code for item in session.validate(include_orphan_warnings=False).errors}
        self.assertEqual(
            codes & {"application-create", "application-update", "application-process-definition"},
            {"application-create", "application-update", "application-process-definition"},
        )

    def test_matrix_repeat_builder_has_canonical_regions_and_dimensions(self) -> None:
        session = PatchSession.new()
        builder = session.add_matrix_repeat_builder(x=200, y=300, count=100)

        cache = session.graph.element(builder.cache_region)
        repeat = session.graph.element(builder.repeat_region)
        self.assertEqual(cache.find("{property}NodeReference/Choice[@Kind='ProcessStatefulRegion']").get("Name"), "Cache")
        self.assertEqual(repeat.find("{property}NodeReference/Choice[@Kind='ApplicationStatefulRegion']").get("Name"), "Repeat")
        self.assertEqual(
            {patch.get("Name") for patch in repeat.findall("Patch/Patch")},
            {"Create", "Update", "Dispose"},
        )

        count_targets = session.graph.outgoing[builder.count_pad]
        self.assertEqual(len(count_targets), 2)
        self.assertIn(
            next(pin.get("Id") for pin in repeat.findall("Pin") if pin.get("Name") == "Iteration Count"),
            count_targets,
        )
        result_owner = session.graph.endpoint_owner[builder.result_output]
        memory_input = next(pin.get("Id") for pin in result_owner.findall("Pin") if pin.get("Name") == "Input")
        self.assertTrue(session.graph.incoming[memory_input])
        memory_reference = result_owner.find("{property}NodeReference")
        self.assertIsNotNone(memory_reference.find("CategoryReference[@Name='MemoryUtils']"))
        self.assertEqual(
            [pin.get("Name") for pin in memory_reference.findall("PinReference")],
            ["Input", "Result"],
        )
        self.assertTrue(session.validate(include_orphan_warnings=False).ok)
        self.assertFalse(session.document.to_bytes().startswith(b"\xef\xbb\xbf"))

    def test_region_control_points_are_bidirectional_link_relays(self) -> None:
        session = PatchSession.new()
        builder = session.add_matrix_repeat_builder(count=3)
        translation = session.graph.endpoint(builder.translation_input)
        self.assertEqual(translation.kind, "ControlPoint")
        self.assertTrue(translation.is_input)
        self.assertTrue(translation.is_output)
        self.assertEqual(session.graph.endpoint(builder.height_input).kind, "InputPin")
        xyz = session.graph.endpoint_owner[builder.height_input]
        self.assertEqual(
            xyz.find("{property}NodeReference/Choice[@Kind='OperationCallFlag']").get("Name"),
            "XyZ",
        )
        xyz_input = next(pin.get("Id") for pin in xyz.findall("Pin") if pin.get("Name") == "Input")
        xyz_output = next(pin.get("Id") for pin in xyz.findall("Pin") if pin.get("Name") == "Output")
        self.assertIn(builder.translation_input, session.graph.incoming[xyz_input])
        self.assertEqual(
            session.graph.endpoint_owner[builder.scaling_input].find(
                "{property}NodeReference/Choice[@Kind='OperationCallFlag']"
            ).get("Name"),
            "TransformSRT",
        )
        self.assertTrue(session.graph.outgoing[xyz_output])
        codes = {item.code for item in session.validate(include_orphan_warnings=False).errors}
        self.assertNotIn("link-direction", codes)

    def test_atomic_write_is_bom_free(self) -> None:
        document = VlDocument.parse(FIXTURE)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "copy.vl"
            document.write_atomic(path)
            payload = path.read_bytes()
            self.assertFalse(payload.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")))
            etree.fromstring(payload)

    def test_catalog_preserves_process_and_operation_node_kinds(self) -> None:
        payload = {
            "nodes": [
                {"name": "Stateful", "category": "Test", "type": "Process", "inputs": [], "outputs": []},
                {"name": "Pure", "category": "Test", "type": "Operation", "inputs": [], "outputs": []},
            ]
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "catalog.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            catalog = JsonNodeCatalog.load(path)

        process = catalog.resolve("Stateful", category="Test")
        operation = catalog.resolve("Pure", category="Test")
        self.assertIsNotNone(process)
        self.assertIsNotNone(operation)
        self.assertEqual(process.reference_kind, "ProcessNode")
        self.assertEqual(operation.reference_kind, "NodeFlag")

        session = PatchSession.new(catalog=catalog)
        session.add_node("Stateful", category="Test")
        session.add_node("Pure", category="Test")
        choices = {
            choice.get("Name"): choice.get("Kind")
            for choice in session.document.root.findall(".//{property}NodeReference/Choice")
        }
        self.assertEqual(choices["Stateful"], "ProcessNode")
        self.assertEqual(choices["Pure"], "NodeFlag")


if __name__ == "__main__":
    unittest.main()
