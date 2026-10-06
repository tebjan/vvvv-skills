# Programmatic `.vl` editing

Use a semantic, loss-preserving document model rather than string replacement or
ad-hoc XML reconstruction. A correct editor keeps unknown elements and properties,
namespace-qualified values, declaration order, existing IDs, and all geometry it
was not explicitly asked to change.

## Skill-owned editing surface

This skill ships its editor at `scripts/vl-patch-manipulator`, relative to this
`SKILL.md`. Use that implementation for `.vl` authoring. Do not create a second
XML writer in an example generator, documentation renderer, or one-off Python
script. Keeping the implementation inside the skill makes these instructions and
their executable contract travel together.

Change to the installed skill's `scripts/vl-patch-manipulator` directory. For a
checkout of this skills repository:

```powershell
cd skills/vvvv-fileformat/scripts/vl-patch-manipulator
uv sync --extra server --group test
uv run vlpatch --help
uv run --extra server vlpatch-server
```

The optional node catalog is supplied at runtime with `--catalog <catalog.json>`
or per document through `vl_open(..., catalog_path=...)`; no workstation path is
embedded in the skill.

The persistent server keeps one parsed session hot and exposes compact operations:

- open/reuse a patch and receive a handle plus monotonic revision;
- inspect summary, exact graph, spatial map, pin anchors, and layout ownership;
- resolve real nodes through a catalog and refuse unresolved guesses;
- batch typed edits atomically with an optional expected revision;
- add canonical comments, headings, clickable links, and overlays;
- add a canonical Cache/Repeat MutableArray Matrix builder with one shared
  allocation/iteration count and a stable `ReadOnlyMemory<Matrix>` result;
- align links, distribute new nodes, move a connected group rigidly, and fit an
  overlay around an explicit semantic set;
- validate structure and spatial invariants;
- preview the live model as BOM-free SVG; and
- save atomically or observe external-file updates through a bounded change feed.

The MCP layer is an adapter. `PatchSession` is the reusable Python API when code is
the most token-efficient client. Agents should not have to rewrite parsing,
catalog, layout, conflict, or serialization logic per task.

### Know which surface is actually available

| Work | Current surface |
| --- | --- |
| Compact views, catalogs, basic edit batches, previews, change feed and conflict-checked saves | Bundled MCP adapter (`vl_*`), when connected |
| Scoped local Process creation, Slots, local placements, closed-subgraph moves and verified reference rebinding | Shared batch contract: Python `edit_batch`, MCP `vl_edit`, CLI `vlpatch edit` |
| Live compiler diagnostics | Only a configured live bridge; default `VvvvBridgeProvider.check()` reports `available=False` |
| Editor inspection, inferred-type/error tooltips, reload and screenshots | Available vvvv connector or computer-use tools; the XML editor does not operate the UI |

Use the existing surface for the task, batch coherent edits, and avoid repeated
shell launches for individual XML mutations. Python scripting still uses the
canonical editor; it is not permission to hand-rewrite `.vl` XML. Do not claim a
live compiler check succeeded merely because the file-only MCP validated XML.

### One discoverable contract across Python, MCP and CLI

Use `vl_capabilities(operations=[...])` to fetch only the needed operation signatures;
`vlpatch capabilities add_process add_slot` returns the same contract. Use
`vl_canvases(handle)` (CLI: `vlpatch canvases PATCH.vl`) to discover Process scopes,
signature endpoints and Slots. Scope arguments accept the attached Canvas, owning
Patch or Process definition ID, never a guessed global coordinate system.

Submit the same JSON array to `session.edit_batch(operations)`,
`vl_edit(handle, operations, expected_revision=revision)`, or
`vlpatch edit PATCH.vl --operations edits.json`. For example:

```json
[
  {"op": "add_process", "name": "Demo",
   "inputs": [{"name": "Value", "type_name": "Float32"}], "as": "demo"},
  {"op": "add_input_placement", "existing_input": "$demo.inputs.Value",
   "position": [420, 180], "patch": "$demo.body", "as": "local_value"}
]
```

Builders return JSON objects containing persistent IDs, not XML elements or Python
reprs. `as` names a result inside this batch; `$name.field` reuses it. Use `$$` for
a literal leading dollar sign. Across calls, use the returned IDs (session aliases
can change after reopening). Process pins use JSON `PinSpec` objects; supply real
types/catalog contracts. Namespaced type annotations and node references use a
verified donor element ID or `{ "path": "donor.vl", "id": "..." }`, not invented XML.
Failed batches restore the tree, graph indexes, aliases and undo history together.
Undo/redo must be standalone batches. Saves remain revision/conflict checked.

The operation registry is the adapter source of truth; `test_surface_parity.py`
checks public mutations/signatures, actual MCP protocol calls, CLI, scoped views
and persisted round trips. Every new authoring operation must extend that contract
and test its adapters before being documented as supported. Restart/reconnect an
already-running MCP server after updating its implementation to load new tools.

For a broken saved link, use the same tool instead of hand-editing XML. `vlpatch
validate` reports incomplete drags as `link-shape`; determine the intended IDs
from the exact source/output and target/input pins, then run `vlpatch apply
PATCH.vl --remove-incomplete-links --connect SOURCE_ID TARGET_ID`. This discards
only links with fewer than two non-empty data hubs, preserves valid links with
intermediate routing hubs, preserves an existing correct connection, writes a
VL-encoded ID for a new link, and refuses invalid output-to-input direction.
Check the diff before reopening vvvv: an added instancer is still disconnected
unless its state output reaches a `Group` input that reaches the renderer.

The ID generator must match `VL.Model.Internal.GUIDEncoders`, not generic
128-bit base62. The serializer keeps vvvv's XML declaration and empty-tag
spacing while removing BOMs; a simple link edit should yield a small diff.

## Safe edit loop

1. Open once; do not reparse for every edit.
2. Request a compact spatial/layout view before deciding coordinates.
3. Distinguish protected baseline elements from new/movable elements.
4. Resolve full node names and pin contracts from the catalog.
5. Submit one coherent typed batch with the current revision.
6. Inspect the returned moved set and before/after spatial metrics.
7. Validate and render an SVG preview.
8. Save atomically, reload, and validate the persisted document.
9. Use matching vvvv compilation/runtime verification when behavior matters.

Never treat an SVG preview or static validator as proof that vvvv resolved types,
compiled shaders, or rendered correctly.

For an `Application` Process document, structural validation must also prove the
execution hierarchy: its inner patch has a Group canvas, sibling `Patch`
elements named `Create` and `Update`, and a `ProcessDefinition` with enabled
fragments targeting both IDs. Without that hierarchy vvvv still displays the
canvas, which makes the defect easy to miss, but no dataflow executes.

## Local Process helpers (all authoring surfaces)

Choose the mechanism before editing: repeated input placement means the same
signature parameter, Slot means real shared state, typed IOBox means editable
constant, and a helper/loop means reusable topology with persistent per-instance
state. These are not interchangeable layout shortcuts. Local reads must be near
their consumers inside helper canvases too.

Use `PatchSession.add_process(...)` for a reusable local helper rather than
constructing lifecycle XML in a migration. It creates the editor-saved Plates
pattern: enabled Create/Update fragments, typed Update signature, ControlPoint
boundary portals and a matching local call node. `ProcessBuilder` returns its
`body`, `inputs`/`outputs` portals and `call_inputs`/`call_outputs` IDs.
Supply real `PinSpec` contracts; namespaced or generic types need their exact
`type_annotations`, not an invented type name.

`add_node`, `add_pad`, `add_annotation` and `add_matrix_repeat_builder` accept
`patch=builder.body` for scoped authoring. `move_subgraph` moves a closed selection
into a destination canvas while retaining IDs and relative geometry, and rejects
crossing links before mutation. Disconnect and replace boundary links explicitly.
`remove` supports ControlPoints and cleans their incident links.

`add_process` and `move_subgraph` are also shared batch operations exposed by MCP
and CLI. Their structural tests do not prove live VL compilation.

`add_process` requires a PascalCase name without spaces. For an existing helper,
use `rename_local_process(definition_id, "Demo", document_name="Example.vl")`:
it updates the definition and matching local call selectors together, preserving
IDs, pins, links, values and geometry. `document_name` supplies the dependency
name for an unsaved document. Imported library calls with the same spelling stay
unchanged; renaming an instance label alone does not rename its registration.
This operation is in the same Python/MCP/CLI registry, not a Python-only helper.

For a verified independent renderer peer collection,
`order_group_inputs_by_x(group_id, independent_peers=True)` assigns existing
Group slots in source-anchor X order, preserving pin/link IDs, routing hubs,
source membership and geometry. This is also a shared batch operation. The
explicit opt-in matters: for renderer groups that traverse children sequentially,
input order is execution order. Preserve GPU producer-before-consumer stages;
never apply a global X sort to renderer Groups.

Verify every explicitly requested local canvas separately: ordering one helper's
Group does not establish that a sibling helper is ordered. In an independent
demo collection, text, captions and guides belong to their source-X column;
appending all guides after all hero outputs recreates cross-column wires. Preserve
stable ties, source membership and human Bounds, and report scoped before/after
crossings rather than claiming complete tidiness from one corrected Group.

For directly imported CLR settings, use the installed importer's real constructor
and accessor contracts. Cache a constructor's output; a constructor operation in
Update creates a new object each evaluation. Direct-import setter pin names may
be the converted property name rather than `Value`. Thread the returned state
through the setters and into the renderer so the values are not disconnected.

An `IsFeedback="true"` attribute alone does not create previous-frame state.
The inspected compiler skips its assignment; it does not synthesize a delay.
Check the production camera/input contract before adding feedback. Some renderer
packages associate window input automatically through the existing view link;
others require explicit input. Do not add or remove a Slot/backward wire based
only on a visible name such as OrbitCamera. Preserve intentional programmatic
input and verify the specific node's dependency/category and real signature.

For a camera requiring Window input feedback, use the working patch's Slot:
one Slot on the Process's inner Patch, separate read/write pads sharing SlotId,
and ordinary links. Read the stored input above the camera and write the window's
output below the window. This breaks the current-frame dependency without
inventing a delayed renderer. Dashed preview styling for a feedback flag is only
metadata, not proof of a valid runtime cycle break.

`PatchSession.add_slot("Input Source", read_position=(x, y),
write_position=(x, y))` creates this canonical state field and returns `read_pad`
and `write_pad` IDs. Connect the producer to `write_pad` and `read_pad` to the
consumer with ordinary links. It accepts an explicit owning Process `patch=`;
types may be inferred from the real endpoints, as in the saved reference patch.
Validation rejects flag-only node feedback rather than treating it as a delay.
Local Process bodies are checked against their own output boundaries, separately
from root RenderWindow reachability; disconnected branches still produce warnings.

Remove obsolete state through `remove_slot(existing_slot, accessor_ids=())`.
With the default empty accessor set it removes only an unused Slot. To remove
dedicated obsolete plumbing, supply the exact set of all its accessor Pad IDs;
the operation rejects missing, duplicate, extra or foreign accessors before any
mutation, then removes the Slot, those pads and their incident links. It is
shared by Python, MCP `vl_edit` and CLI `vlpatch edit`, not a raw XML escape hatch.
Before migrating camera input, prove the Slot serves only that camera connection
and preserve every retained node's values, selectors, pin order and geometry.

### Repeat a parameter placement, not its declaration

`add_input_placement(existing_input, position=(x, y), patch=body)` takes either
the existing Update signature InputPin ID or an existing input ControlPoint ID.
It adds one plain ControlPoint and a hidden reference link from the **original
signature Pin**, in the owning Process Patch. No new signature Pin, value copy or
Slot is created. Use local placements beside consumers to avoid canvas-wide
fan-out; preserve the visible output-to-input links inside each demo cluster.

```python
local_font = session.add_input_placement(process.inputs["Font"],
                                         position=(420, 180), patch=process.body)
session.connect(local_font, "text_layout.Font")
local_material = session.add_slot_read(material_slot, position=(780, 240))
session.connect(local_material, "family.Material")
```

`add_slot_read(slot_builder_or_id, position=(x, y), patch=owner)` adds a plain
Pad sharing the existing SlotId. Connect it as a source; an incoming link makes
a Slot Pad a writer. Both operations are exposed through the shared batch contract;
discover their arguments with `vl_capabilities` instead of writing XML glue.

The schema is verified against `VL.Model.Patch.AddProxy` (`Nodes.cs:1017`) and
`GetOrAddLink(..., isReference:true)`, plus eight placements of one Input in the
saved `VVVV.VL.DynamicBuffersAndTextures.vl` donor. `DefinitionId` on a ControlPoint
is **not** this mechanism. Slot reads are order-dependent: `PatchState.ReadSlot`
uses an earlier assignment expression if present, otherwise the field; Pad reads
are local snapshots. Canvas position does not determine compiler execution order
or guarantee a frame delay. Uninitialized reference fields start null.

## CPU transform loops

For a CPU instancer, do not connect a spread-producing transform node directly
to `AsReadOnlyMemory` and do not duplicate the array length and loop count. Use
the skill-owned operation instead:

```python
loop = session.add_matrix_repeat_builder(x=520, y=650, count=100)
session.graph.add_link(vector2_positions, loop.translation_input)
session.graph.add_link(plate_height_scalar, loop.height_input)
session.graph.add_link(scale_scalar, loop.scaling_input)
session.graph.add_link(loop.result_output, instancer_transforms_input)
```

The builder creates `Cache(Create MutableArray)` plus
`Repeat(Create/Update/Dispose, Index)` and `MutableArray.SetItem`, then exposes
the cached storage through `AsReadOnlyMemory`. Its count IOBox fans out to both
the cache allocation and `Repeat.Iteration Count`, so every dimension remains
coherent. Region `ControlPoint` elements are bidirectional typed portals: they
may be link targets on one side of the region and link sources on the other.
They must never be validated as ordinary one-way input pins.

The Vector2 position spread must enter `Repeat` through a top ControlPoint and
feed `XyZ.Input` (`StateInputPin`) inside the region. `XyZ.Output` then feeds
`TransformSRT.Translation`; `XyZ.Y` receives a scalar height. Do not link the
spread directly to `TransformSRT.Translation`: XML endpoint validity does not
prove vvvv resolved the dimensions or types. The `AsReadOnlyMemory` overload
must carry its `MemoryUtils` `CategoryReference` and the explicit
`MutableArray<T> -> ReadOnlyMemory<T>` `PinReference` type signatures from a
vvvv-saved example. A plain operation name does not select this overload.

## Collection dimensions and adaptive conversion calls

`Cons (Collections.Spread)` constructs a spread from **scalar** Input/Input 2/…
peers. `FromValue(scalar)` already returns a one-element spread; feeding those
spreads into Cons adds dimensions rather than concatenating them. For two existing
sequences use `Concat` with `Output` (not Cons's `Result`). Clone the saved stock
reference, including category selectors; inspect the runtime inferred types.

For a Spread-to-memory adapter, the working public adaptive reference is:

```xml
<p:NodeReference LastCategoryFullName="System" LastDependency="VL.CoreLib.vl">
  <Choice Kind="NodeFlag" Name="Node" Fixed="true" />
  <Choice Kind="OperationCallFlag" Name="AsReadOnlyMemory" />
</p:NodeReference>
```

The operation choice is unfixed. Do not invent a name-only MemoryUtils call or
assume an overload selector from its C# method signature will resolve in vvvv.
The loop builder's separately verified explicit MutableArray overload remains
valid; do not replace it indiscriminately. `set_node_reference(node, saved_ref,
pin_renames={...})` rebinds through the canonical model while preserving geometry,
node/pin IDs, defaults and outgoing wires. It clones the donor reference and rejects
missing/duplicate pin renames before mutation. A static signature/value check does
not validate adaptive constraints or collection dimensions: reopen in vvvv and
inspect red calls, inferred types and resulting rendered contributions.

## IDs and aliases

The document stores 22-character base62 IDs. A live editing session may expose
short aliases such as `n1`, `p1`, and `r1`, but aliases are session-local and must
map one-to-one to elements. New elements inserted earlier in XML order must still
receive unique aliases; never derive an alias only from the current count.

When cloning a subgraph, generate new IDs for every cloned element and remap all
internal references. Do not leak source IDs or rewrite references outside the
clone boundary.

## Concurrency and external edits

- Mutations should accept an expected revision and reject stale writes.
- Debounce transient external writes and retain the last valid parsed model.
- If unsaved in-memory changes meet an external edit, report a conflict; never
  silently overwrite either author.
- A successful save or accepted external reload establishes a new protected
  geometry baseline.
- Undo/redo belongs to the live session and must not rely on destructive Git
  operations.

Before reloading a dirty editor document, preserve any unknown unsaved human
changes. A Save As backup can retain the original Document Id: keep it recoverable
on disk, but avoid loading it alongside the original as a second active document.
Discard only inspection changes known to be yours; never save an old in-memory
graph over a newer conflict-checked disk repair.

## Serialization

- Parse before mutation and validate before write.
- Write through a same-directory temporary file, flush it, then atomically replace
  the destination.
- Emit deterministic UTF-8 without a BOM (`encoding="utf-8"`, never
  `utf-8-sig`).
- Preserve unknown XML content and namespace-qualified property elements.
- Do not use Windows PowerShell 5.1 `Set-Content -Encoding UTF8` for repository
  text; it emits a BOM. Use a BOM-less UTF-8 writer.

## Minimum diagnostics

Crossing diagnostics compare actual endpoint anchors. Two wires feeding
different pins of the same node can cross: skip only a shared endpoint/junction,
not a shared node owner. The shared `PatchSession.layout_analysis` implements
this for Python, MCP and CLI; adapters must not add divergent filtering. Compare
before/after in the same canvas with the same checker version, and identify
remaining crossings rather than declaring the whole patch tidy. Hidden reference
links are not visible wires. Static previews still need human/runtime review.

Structural checks:

- root/version/namespaces and direct Document dependencies;
- unique valid IDs;
- fragment references;
- link endpoint existence and output-to-input direction;
- link source/target **type** compatibility (`link-type-mismatch`, including the
  verified signed/unsigned integer mismatch when real endpoint types are known);
- node resolution and operational orphans;
- canonical visible annotation XML; and
- BOM absence.

The link-type check (`PatchSession._check_link_type_mismatches`) is
catalog-dependent and silent by design, never a guess: a Pad's type is always
in the file (`TypeAnnotation`), but a Node pin's type is **never** stored
inline — vvvv resolves it from the node's own reflection at load time — so it
can only be answered when `self.catalog` carries real pin types for that node
(as a generator script's hardcoded `NodeSpec` additions do). Opening a plain
`.vl` with no external catalog uses the auto `DocumentCatalog`, which has no
per-pin types at all (every node pin comes back `"Object"`), so the check
correctly stays silent rather than reporting a false negative *or* guessing a
false positive. When writing a generator's own `NodeSpec` pin types, keep them
in sync with the actual shader/node signature — a stale type here (e.g. an
`Integer32 (Unsigned)` pin the real node has since made signed) makes this
diagnostic false-positive on the generator's own output.

Spatial checks:

- effective node bounds and exact visible pin anchors;
- node-node, node-annotation, and foreign-node/overlay overlaps;
- upward non-feedback links;
- crossing and long-link endpoint pairs;
- exact alignment of primary one-to-one links; and
- explicit movable/protected sets and moved elements.

Metrics guide review; they do not replace visual inspection. A graph can have zero
rectangle overlaps and still look poor if links miss their destination pins or a
semantic group is visually incoherent.

### Inspect one actual canvas at a time

Independent Process bodies have independent coordinate systems. A document-wide
overlap count can report collisions between nodes that never appear together.
Select the attached Canvas for each Application/helper body:

```python
report = session.layout_analysis(canvas=process.body)
session.render_svg("preview.svg", canvas=process.body)
```

The scoped view includes executable nested regions but excludes independent
definitions. Only visible links with both endpoints in that scope are drawn;
hidden signature-reference links are identity plumbing, not visible wires.
MCP `vl_view`, `vl_check` and `vl_preview`, and CLI `view/check/preview`, accept
the same scope as a `canvas` ID. A scoped view returns a spatial snapshot of that
canvas. Structural validation still covers the whole document; geometry is scoped.

Plain input placements and Slot pads use two-coordinate `Bounds="x,y"`.
Position-only moves must retain that form, not invent a 100-pixel IOBox. The
explicit `set_placement_position(id, x, y)` repair restores two-value Bounds
on a ControlPoint or real Slot pad only, preserving shared identities and links.
Do not apply it to ordinary value IOBoxes. The
inspected editor uses a 9-pixel body centered at `(x+.5,y-.5)`; source and sink
anchors are `(x+.5,y+4)` and `(x+.5,y-5)`. Slot names and referenced input names
must appear in previews. Label envelopes use estimated font dimensions, so
review them visually; they are not exact editor text metrics. Source evidence:
`VL.UI.Forms/PatchEditor/Constants.cs`, `DataHubView.GetLinkAnchorPosition`,
`PadView` and `ControlPointView` in the local vvvv source checkout.

Inspect new helpers as well as the root patch. A helper with all inputs in a
generic top row can reproduce the same remote fan-out internally. Put each
parameter placement and constant beside its consumer, keeping top-down flow
and enough label clearance. Compare pre-existing collision pairs against the
saved human baseline; repair new collisions without silently reflowing old work.

Orphan checks include valid same-definition Slot hubs for reachability only.
Shared Font/Material writers used by separate read Pads are not unused nodes.
Directed dependencies/cycle detection remain based on real links: state access
does not invent current-frame edges. The existing Python `validate`, MCP
`vl_check` and CLI `check` share this document implementation; no new command is
needed. A server process that imported older code must be restarted before it
uses the update. If its findings disagree with the current canonical local tool,
check the loaded implementation before editing the saved document.
