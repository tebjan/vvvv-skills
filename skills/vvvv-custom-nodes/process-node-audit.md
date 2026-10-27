# ProcessNode static audit helper

Use `scripts/audit_process_nodes.py` to inventory C# `[ProcessNode]` types and
review likely fragment/output hazards across one or more source roots. It uses
tree-sitter's C# grammar, so comments and string literals are not mistaken for
declarations. It does not invoke vvvv, compile C#, load assemblies, or prove that
an imported node fails at runtime.

## Setup and run

From the skill directory, install the two pinned parser packages into its local
dependency folder, then pass the source directories to audit:

```powershell
python -m pip install --target scripts/.deps -r scripts/requirements.txt
python scripts/audit_process_nodes.py path/to/package-a/src path/to/package-b/src `
  --repo-root path/to/repository --json-out process-node-audit.json
```

The dependency installation is local to `scripts/.deps`; it does not install
packages globally. The scanner reads one `.cs` file at a time and prunes common
build, dependency, generated, and vendored directories. It reports the exact
relative source path and line for candidates. `--include-examples` also scans
each `src` root's sibling `examples` directory; examples are otherwise outside
the requested roots. Pass an additional `--exclude-dir NAME` only when the
source tree has another generated or vendored directory to omit.

## Reading the report

- `nodes` inventories each discovered ProcessNode class, including partial
  declarations, fragment selection, `HasStateOutput`, base types, selected
  public methods, direct `out`/`ref` names, and selected public properties with
  their accessors.
- `error` marks a likely import hazard: duplicate known outputs inside one
  fragment, multiple public `Update` overloads under implicit selection, or
  multiple implicit fragments returning `this` with the same ordinary mutable
  class `Result` name. This is static evidence, not a runtime reproduction.
- `review` includes additional public `Update*` members, all visible self-return
  methods, public methods/properties selected implicitly, repeated output names,
  state-return pins, unresolved base types, factories, dynamic registrations,
  and unsupported expressions. C# parse failures are reported as errors and
  make that file's findings incomplete.

An intentional multi-fragment node can be valid. A `self_return_candidate` is
not an error by itself: returning `this` can be part of the node's result
contract. `HasStateOutput` is recorded separately, and a return marked
`[return: Pin(IsState = true)]` is not treated as an ordinary `Result`. Record,
struct, or `Immutable`-hinted definitions are reviewed without assuming the
mutable-class `Result` naming rule. Explicit return pin names are compared for
possible collisions, but their importer behavior still needs inspection.

The audit resolves partial classes and source-local base types when unique. It
cannot resolve aliases, generated or runtime registrations, external assemblies,
the complete importer type system, saved patch compatibility, evaluation order,
or rendering. A clean report is therefore not a substitute for placing the
affected node in the supported vvvv version and checking its generated surface.

From the skill folder, run the focused parser regressions:

```powershell
python scripts/test_audit_process_nodes.py
```
