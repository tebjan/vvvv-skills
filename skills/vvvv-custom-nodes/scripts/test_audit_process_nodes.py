import json
import tempfile
import unittest
from pathlib import Path

from audit_process_nodes import audit


class ProcessNodeAuditTests(unittest.TestCase):
    def run_audit(self, sources: dict[str, str]) -> dict:
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            root = Path(temp)
            for relative, content in sources.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            return audit([root], repo_root=root)

    @staticmethod
    def codes(report: dict, symbol: str | None = None) -> set[str]:
        return {
            finding["code"]
            for finding in report["findings"]
            if symbol is None or finding.get("symbol", "").startswith(symbol)
        }

    def test_implicit_self_return_updates_report_duplicate_result_candidate(self) -> None:
        report = self.run_audit(
            {
                "Dispatcher.cs": """
                [ProcessNode]
                public class Dispatcher
                {
                    public Dispatcher Update(int count) => this;
                    public Dispatcher UpdateWithElements(int count) => this;
                }
                """
            }
        )
        self.assertIn("duplicate_self_result_candidates", self.codes(report, "Dispatcher"))
        self.assertIn("additional_public_update_method", self.codes(report, "Dispatcher.UpdateWithElements"))
        self.assertEqual(2, sum(f["code"] == "self_return_candidate" for f in report["findings"]))
        details = next(f["details"] for f in report["findings"] if f["code"] == "duplicate_self_result_candidates")
        self.assertEqual([5, 6], [entry["line"] for entry in details["members"]])

    def test_void_update_with_state_output_and_direct_out_name(self) -> None:
        report = self.run_audit(
            {
                "Stateful.cs": """
                [ProcessNode(HasStateOutput = true)]
                public class Stateful
                {
                    public void Update(out int output) { output = 1; }
                }
                """
            }
        )
        node = report["nodes"][0]
        self.assertTrue(node["has_state_output"])
        self.assertEqual(["Update"], [method["name"] for method in node["selected_public_methods"]])
        self.assertEqual(["Output"], node["selected_public_methods"][0]["output_names"])
        self.assertNotIn("duplicate_outputs_within_fragment", self.codes(report, "Stateful"))
        self.assertNotIn("self_return_candidate", self.codes(report, "Stateful"))

    def test_explicit_selection_excludes_unmarked_public_helper(self) -> None:
        report = self.run_audit(
            {
                "Explicit.cs": """
                [ProcessNode(FragmentSelection = FragmentSelection.Explicit)]
                public class ExplicitNode
                {
                    [Fragment]
                    public void Update() { }
                    public ExplicitNode UpdateWithElements() => this;
                    public void Helper() { }
                }
                """
            }
        )
        node = report["nodes"][0]
        self.assertEqual("Explicit", node["fragment_selection"])
        self.assertEqual(["Update"], [item["name"] for item in node["selected_public_methods"]])
        self.assertNotIn("additional_public_update_method", self.codes(report, "ExplicitNode"))
        self.assertNotIn("public_helpers_imported_implicitly", self.codes(report, "ExplicitNode"))

    def test_comments_and_strings_are_not_syntax_matches(self) -> None:
        report = self.run_audit(
            {
                "NoNode.cs": """
                // [ProcessNode] public class CommentOnly { public void Update() {} }
                public class Plain
                {
                    public string Description = "[ProcessNode] UpdateWithElements return this";
                }
                """
            }
        )
        self.assertEqual([], report["nodes"])
        self.assertEqual(0, report["summary"]["total_findings"])

    def test_other_return_data_and_direct_out_pin_name_are_reported_separately(self) -> None:
        report = self.run_audit(
            {
                "DataNode.cs": """
                [ProcessNode]
                public class DataNode
                {
                    public int Update(out int count) { count = 1; return 2; }
                    public string UpdateWithElements(out int total) { total = 1; return "done"; }
                }
                """
            }
        )
        self.assertNotIn("self_return_candidate", self.codes(report, "DataNode"))
        self.assertNotIn("duplicate_self_result_candidates", self.codes(report, "DataNode"))
        updates = [f for f in report["findings"] if f["code"] == "additional_public_update_method"]
        self.assertEqual(1, len(updates))
        node = report["nodes"][0]
        self.assertEqual(["Update", "UpdateWithElements"], [m["name"] for m in node["selected_public_methods"]])

    def test_duplicate_direct_out_names_and_update_overloads(self) -> None:
        report = self.run_audit(
            {
                "Overloads.cs": """
                [ProcessNode]
                public class Overloads
                {
                    public void Update(out int texture, [Pin(Name = "Texture")] out int other) { }
                    public void Update(int count) { }
                }
                """
            }
        )
        self.assertIn("duplicate_outputs_within_fragment", self.codes(report, "Overloads.Update"))
        self.assertIn("multiple_public_update_overloads", self.codes(report, "Overloads"))

    def test_partial_class_combines_methods_and_source_resolved_inheritance_is_reported(self) -> None:
        report = self.run_audit(
            {
                "Base.cs": "public class BaseNode { public BaseNode UpdateFromBase() => this; }",
                "Part1.cs": "[ProcessNode] public partial class SplitNode : BaseNode { public SplitNode Update() => this; }",
                "Part2.cs": "public partial class SplitNode { public SplitNode UpdateWithItems() => this; }",
            }
        )
        self.assertIn("duplicate_self_result_candidates", self.codes(report, "SplitNode"))
        self.assertIn("inherited_public_fragment_candidates", self.codes(report, "SplitNode"))
        split = next(node for node in report["nodes"] if node["symbol"] == "SplitNode")
        self.assertEqual(2, len(split["partial_declarations"]))

    def test_dynamic_factory_registration_is_reported_for_review(self) -> None:
        report = self.run_audit(
            {
                "Factory.cs": """
                [ProcessNodeFactory(typeof(NodeFactory))]
                public class Registration { }
                """
            }
        )
        self.assertIn("factory_registration_unresolved", self.codes(report))

    def test_static_and_hidden_methods_are_excluded_and_public_properties_are_inventoried(self) -> None:
        report = self.run_audit(
            {
                "Members.cs": """
                [ProcessNode]
                public class Members
                {
                    public void Update() { }
                    public static void StaticHelper() { }
                    [Fragment(IsHidden = true)] public void HiddenHelper() { }
                    public int Visible { get; private set; }
                    [Fragment(IsHidden = true)] public int HiddenProperty { get; set; }
                }
                """
            }
        )
        node = report["nodes"][0]
        self.assertEqual(["Update"], [method["name"] for method in node["selected_public_methods"]])
        self.assertEqual([("Visible", ["get"])], [
            (prop["name"], prop["accessors"]) for prop in node["selected_public_properties"]
        ])
        helper_finding = next(
            finding for finding in report["findings"]
            if finding["code"] == "public_helpers_imported_implicitly"
        )
        self.assertEqual(["Visible"], [entry["name"] for entry in helper_finding["details"]])

    def test_state_return_and_record_self_returns_do_not_assume_result_collision(self) -> None:
        report = self.run_audit(
            {
                "StateAndRecord.cs": """
                [ProcessNode]
                public class StatefulReturn
                {
                    [return: Pin(IsState = true)]
                    public StatefulReturn Update() => this;
                }
                [ProcessNode]
                public record RecordNode
                {
                    public RecordNode Update() => this;
                    public RecordNode UpdateMore() => this;
                }
                """
            }
        )
        self.assertIn("state_return_candidate", self.codes(report, "StatefulReturn"))
        self.assertNotIn("duplicate_self_result_candidates", self.codes(report, "StatefulReturn"))
        self.assertIn("immutable_self_return_output_unresolved", self.codes(report, "RecordNode"))
        self.assertNotIn("duplicate_self_result_candidates", self.codes(report, "RecordNode"))

    def test_explicit_return_pin_name_collision_is_reviewed(self) -> None:
        report = self.run_audit(
            {
                "ReturnNames.cs": """
                [ProcessNode]
                public class ReturnNames
                {
                    [return: Pin(Name = "Output")] public int Update(int value) => value;
                    [return: Pin(Name = "Output")] public string UpdateWithText(string value) => value;
                }
                """
            }
        )
        finding = next(
            item for item in report["findings"]
            if item["code"] == "duplicate_output_name_candidates"
        )
        self.assertEqual("review", finding["severity"])
        self.assertEqual("Output", finding["details"]["output_name"])

    def test_file_scoped_namespaces_keep_same_short_names_separate(self) -> None:
        report = self.run_audit(
            {
                "First.cs": "namespace First; [ProcessNode] public class Shared { public void Update() { } }",
                "Second.cs": "namespace Second; [ProcessNode] public class Shared { public void Update() { } }",
            }
        )
        self.assertEqual({"First.Shared", "Second.Shared"}, {node["symbol"] for node in report["nodes"]})
        self.assertEqual(2, report["summary"]["process_nodes"])


if __name__ == "__main__":
    print("Running ProcessNode audit parser tests")
    unittest.main()
