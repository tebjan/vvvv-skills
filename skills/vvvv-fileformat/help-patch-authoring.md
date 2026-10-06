# Human-quality vvvv help patches

Use this reference when creating or modifying user-facing `.vl` help patches. It
records conventions verified against human-authored vvvv package help, the vvvv
editor source, and working generated patches.

## Do not invent the node surface

### Porting a C# node example

When the reference example calls the package's node classes directly, those calls
are the graph specification: one persistent node instance becomes one process
call; its Update inputs become links or correctly typed IOBoxes; reused outputs
remain shared links. Preserve the source's explicit values, units, enum types,
collection dimensions and producer-before-consumer dependencies. Do not replace
the graph with a visually similar invented showcase or copy harness-only service
initialization into the patch.

Separate render-space parity (content, transforms, text layout, materials,
lighting and camera) from canvas layout. Use human-authored helper processes and
semantic grouping for readability, but keep the same rendering semantics. Record
any missing node surface rather than silently substituting an implementation.
Compare the resulting rendered image; XML and spatial checks alone cannot prove
visual parity. Performance investigations are a separate task unless requested.

Use descriptive vvvv help names such as `Example Area Lights`; C# test-launch
numbers are not user-facing patch identifiers. Do not blindly port harness-only
camera input plumbing: some renderer packages associate window input through the
existing view connection, while others require explicit input. Preserve
user-authored sources and verify contracts by dependency/category, not label.

### Text placement: units belong to the node contract

Different text renderers use different coordinate-space contracts. Check whether
Size, Transform, bounds and baseline offsets are in world units or pixels. A
world-anchored screen label may use pixel-sized text after projection; multiplying
its pixel font size by a layout descent and adding that to world Y is a unit error.
Keep world anchors separate from pixel offsets. Screen text can intentionally sit
at a viewport corner rather than on a scene object. Verify the actual renderer
instead of generalizing one package's text modes to all vvvv nodes.

A C# reference may itself contain a unit bug. Use it to map the graph, then verify
units against production node behavior and the rendered result. Compare every
affected row, including the far/back rows, rather than accepting the front row or
a matching static-input table as visual proof. Preserve already-correct content
and human canvas arrangements during a narrowly scoped repair.

### Verify the actual node contract

- Resolve nodes from the live registry, analyzer catalog, or production signature.
- Preserve public pin declaration order. Never sort pins alphabetically.
- The primary state/data output is first and therefore leftmost. Diagnostics such
  as `Error` and secondary outputs follow it.
- Do not infer pin names, types, directions, or shader entry-point suffixes from a
  screenshot. XML that parses can still describe a nonexistent node contract.
- Structural validation cannot prove package loading, type inference, shader
  compilation, or runtime rendering; use vvvv/runtime verification for those.

## Visible annotations are real canvas elements

An XML comment is source metadata and is invisible in the patch. User-facing help
must be serialized as canvas elements with bounds so it participates in layout and
collision checks.

### Comment and explanation

```xml
<Pad Id="..." Bounds="40,67,920,38" ShowValueBox="true" isIOBox="true"
     Value="Explain what the user is seeing and why the nodes are connected.">
  <p:TypeAnnotation LastCategoryFullName="Primitive" LastDependency="VL.CoreLib.vl">
    <Choice Kind="TypeFlag" Name="String" />
  </p:TypeAnnotation>
  <p:ValueBoxSettings>
    <p:fontsize p:Type="Int32">9</p:fontsize>
    <p:stringtype p:Assembly="VL.Core" p:Type="VL.Core.StringType">Comment</p:stringtype>
  </p:ValueBoxSettings>
</Pad>
```

Keep multiline prose in the Pad's `Value`. The `Comment` attribute on an ordinary
IOBox is not a substitute for this visible annotation form.

### Heading

A heading is the same String Comment Pad with a larger font. The verified helper
default is `15`; normal explanatory prose uses `9`.

### Clickable URL

Use a String Pad with `p:stringtype` set to `Link` and the complete HTTP(S) URL in
`Value`:

```xml
<p:ValueBoxSettings>
  <p:fontsize p:Type="Int32">9</p:fontsize>
  <p:stringtype p:Assembly="VL.Core" p:Type="VL.Core.StringType">Link</p:stringtype>
</p:ValueBoxSettings>
```

### Visual grouping overlay

A visual region is an `Overlay`, not an executable If/ForEach/Cache node:

```xml
<Overlay Id="..." Name="GPU-fed mesh shader" Bounds="1580,232,530,813" />
```

Use one compact overlay per technology only when a patch compares multiple
technologies. Keep shared setup, scene, lighting, collection, camera, and render
spines outside technology overlays. A single-concept patch needs an explanation,
not a decorative rectangle around the whole graph.

Do not confuse an `Overlay` with a control-flow region. Control-flow regions are
`Node` elements with a `StatefulRegion` NodeReference, an inner Patch, fragments,
and control points; they change evaluation semantics.

## Exact pin geometry

vvvv pins are left-aligned and stretch across the effective node width. They are
not centred as a group and do not use a fixed pitch.

For each rail (inputs at the top, outputs at the bottom):

1. Filter out hidden pins.
2. Preserve declaration/XML order.
3. Treat every pin as 5 pixels wide.
4. One visible pin has anchor `x + 2.5`.
5. For `count > 1`, pin `i` has anchor:

   `x + 2.5 + i * (width - 5) / (count - 1)`

6. Use the editor's rounding behavior when pixel-exact comparisons matter.

The input anchor Y is the node top. The output anchor Y is the node bottom. Use the
effective `NodeView` width: at least the serialized width, but expanded as required
for the label and the visible pin bar. Hidden pins consume no rail space.

Widening a node can be intentional: human authors use width to place specific pins
under their sources. Never normalize a deliberately wide node merely because its
label fits in less space.

## Layout hierarchy

Canvas position does not determine graph evaluation. For readable help patches,
show dependency flow top-to-bottom inside each subgraph and arrange peer subgraphs
left-to-right across the 2D canvas:

- sources, values, and shader nodes above consumers;
- sinks, collections, renderers, and windows below;
- independent technologies side-by-side as semantic subgraphs;
- connected value pads in a staircase when a multi-input rail would otherwise
  create crossings;
- common scene/render infrastructure outside technology overlays.

Within each semantic subgraph, align movable one-to-one source outputs to the exact
destination input anchor. Work bottom-up from a fixed sink so upstream adjustment
does not disturb the established convergence point.

Vertical links are a preference, not an absolute constraint. Keep a diagonal when
the topology genuinely has:

- one source fanning out to several differently placed inputs;
- different collection/Group slots;
- a cross-technology dependency;
- conflicting multi-pin order;
- a protected human-authored subgraph that would otherwise be damaged; or
- node/annotation overlap caused by forcing exact X alignment.

Small deliberate skew is better than overlapping boxes or an enormous stretched
region. Judge alignment using pin anchors, never node centres.

### Nested renderer groups for showcase scenes

`Group` nodes may feed other `Group` nodes. For a showcase with several hero
renderers plus shared scene infrastructure, a useful convention is:

```text
hero peer nodes -> wide hero Group
hero Group + ground/basic geometry + lights -> lower scene Group
scene Group -> renderer -> window
```

Place the hero subgraphs higher on the canvas and the scene Group close to the
renderer. Keep ground, utility geometry, and lights out of the hero Group so its
inputs describe only the feature being taught. This is readability guidance, not
a runtime rule: use one Group when an extra level would not clarify anything.
Nested groups must preserve the same top-to-bottom dataflow and real pin-anchor
alignment as ordinary nodes.

## Preserve human spatial authorship

### Keep a demonstration together, simplify its plumbing

A demo's creative inputs, feature nodes, result and optional guides belong in
one readable local cluster. Do not collect every layout at the top, every
renderer at the bottom, or every shared parameter in a remote fan-out row.
Helpers should remove repetitive plumbing, not hide the capability being taught.

- A Process input can have multiple local canvas placements of the **same
  signature parameter**. Put each read beside its consumer; do not add another
  signature pin, duplicate the producing Font/Material node, or draw a wire from
  a single distant placement through all other demonstrations.
  Apply this inside extracted helpers too: Font/Value near TextLayout,
  Translation near TransformSRT, Material/Color near RenderText, for example.
  A generic top-row input bank is not an improvement when it recreates long
  diagonals internally. Inspect the helper canvas separately.
- Named Slots can provide local reads of shared root resources. A Slot is real
  state, not an invisible wire: verify read/write ordering, first-frame defaults,
  null tolerance and producer lifetime. Reference identity alone does not make a
  delayed reference valid after its owner has disposed it. Keep frame-dependent
  transforms, camera/history data and GPU submission dependencies on explicit
  current-frame links unless a delay is deliberately part of their contract.
  An orphan warning must follow valid same-definition Slot read/write accessors:
  a Font or Material writer can feed all the demo helpers through local read Pads
  without a physical Link between Pads. This reachability is not a current-frame
  scheduling edge. Never delete a producer just because the physical-link-only
  graph is disconnected; inspect the shared Slot and its consumers first.
- Extract identical caption/placement/guide chains into small reusable Process
  helpers. Keep their creative controls next to each call. Use Repeat/ForEach
  when instances truly share one topology, with independent persistent state per
  iteration and coherent dimensions. Do not reuse one mutable renderer for many
  peers or turn genuinely different techniques into a universal mode switch.
- Prefer verified translation/scale/vector accessors to exposing all sixteen
  Matrix components. Preserve coordinate-space units and signed bounds semantics;
  a general matrix decomposition is not automatically the same operation.
- Keep showcase text visually distinct from captions and optional guide geometry.
  Translate established clusters rigidly if needed; do not scatter their members.

Before structural extraction, checkpoint the human save and record the original
creative values, shared resource/layout identities, group ordering and output
routes. Afterwards compare those invariants across helper boundaries, not only
raw node counts or old coordinate-based lookups. Static checks and previews do
not replace a vvvv compile/render check of the new helper signatures.

Opening an existing patch establishes a protected geometry baseline.

- Default layout may move only nodes, pads, and annotations created in the current
  edit session.
- Saving or externally reloading establishes the next protected baseline.
- Do not store tool-private ownership metadata in the `.vl` document.
- When space is required, translate an established connected subgraph rigidly so
  relative node positions, stretched widths, comment positions, and internal pin
  alignment stay intact.
- Reflow an existing selection only when explicitly targeted.
- Whole-patch reflow is an explicit destructive operation, never an incidental
  consequence of adding a node.

An agent should obtain a compact spatial view before editing: exact bounds, pin
anchors, links, overlays, free bands, crossings, upward links, and the current
movable/protected sets. After editing, report which elements actually moved.

### Learn from a human save without undoing it

Checkpoint the saved file, then compare persistent IDs, Bounds, values, call
selectors and link endpoints separately. vvvv can materialize pin/reference
metadata on save: a large textual diff is not evidence of a large graph change.
Distinguish position changes from width-only normalization and deliberate values.

In a repeated demo, read why the human arrangement works: destination-pin-order
staircases, shared controls above the earliest consumer, local resource reads,
and an offset helper lane that leaves the main dependency link unobstructed.
Treat those relationships as the template, not the literal values or a fixed
spacing grid. Copy geometry only to explicitly targeted semantic peers; preserve
the original exemplar and verify before/after crossings and label clearance.

Distinct input pins on the same consumer can have crossed wires. Crossing checks
must not suppress a pair merely because the wires share a node; only a genuine
shared endpoint is a junction. Report the scope and remaining defects: a reduced
crossing count is not a clean-canvas or runtime-correctness certificate.

## Help Browser taxonomy and paths

Use the five established document roles intentionally:

- `HowTo`: teaches a concrete task or node combination.
- `Explanation`: systematically explains a concept or family of alternatives.
- `Example`: showcases a broader finished result.
- `Reference`: provides a reference surface or documentation landing point.
- `Tutorial`: a guided multi-step learning route.

Keep the role in the filename and the `help.xml` topic. Do not add another
`HowTo`, `Explanation`, `Example`, `Reference`, or `Tutorial` directory layer.
One useful feature-owned organization is:

```text
help/<feature>/<Role> Descriptive Name.vl
help/<feature>/<shader-folder>/
```

When an explicit `help.xml` manifest is supplied, its category hierarchy can be
independent of the local paths; do not rely on role folders to define categories.
Patch entries use `<VLDocument link="...">`,
not an invented `<Document src="...">` form. Validate every manifest link against
the actual package help tree and use canonical path separators for that manifest.

The stock vvvv 7.3 Help Browser recognizes `UriItem` only for `http://` and
`https://`. A package-relative `file:` URL can be well-formed XML and still remain
invisible or unlaunchable. Keep offline HTML in the package for direct opening and
use a supported HTTPS entry when it must appear as a Help Browser URL.
Reverify this capability when the target vvvv version changes; do not generalize the
7.3 limitation to an uninspected future Help Browser.

When a human has corrected one patch and sibling packages need equivalent landing
patches, treat the saved human patch as the template. Preserve its graph and
top-down geometry; replace only package-specific values, dependencies, and
document-scoped IDs.

## Adjacent shader and asset ownership

Keep patch-owned shader nodes next to the patch, in the folder recognized by the
actual shader factory (`shaders_dx12/` for a factory using that convention).
Avoid stage/implementation subfolders unless the package owns a reusable library
that needs them. Shared includes may live at the nearest common owner; local
entry points should remain obvious when opening the feature folder. Harness-only
assets are not help-patch nodes unless the patch actually resolves and wires them.

Use the entry-point resolver's real naming behavior. Do not append `CS` or another
stage suffix to user-facing shader-node names merely from habit; verify the catalog
and generated node name.

## Verification gate

For an explicitly authorized document-wide layout pass, inventory all Process
and Application canvases, not only the root or first example. Transfer the human
exemplar by semantic role and actual pin anchors; adapt unique helper topology
instead of forcing it into the repeated demo template. Protect the exemplar and
already-correct human groups. Compare non-geometric XML before/after, inspect
per-canvas previews, and check that a second application has no geometry drift.
An analysis report alone does not complete a request to apply the layout.
Document any residual fanout/convergence crossings rather than claiming the
entire graph is crossing-free. Do not reorder pins or alter links just to improve
a geometric metric without authorization for a graph change.

Before accepting a generated or modified help patch, verify:

- XML parses and all IDs are unique valid base62 identifiers.
- A Process Application has Create and Update sibling patches plus enabled
  ProcessDefinition fragments for both; a visible canvas alone is not runnable.
- Every link endpoint exists and direction is output to input.
- Node and pin contracts came from real metadata.
- Pin ordering and anchors match the editor model.
- Visible comments, headings, links, and overlays use canonical XML.
- No operational node is orphaned unless the patch explicitly explains why.
- No node-node, node-annotation, or foreign-node/overlay overlap exists.
- No non-feedback link flows upward.
- Primary one-to-one links align exactly at pin anchors where geometry allows.
- Remaining crossings and long diagonals are intentional and identified.
- Existing protected geometry changed only as explicitly requested.
- `help.xml` paths resolve and taxonomy matches the filename/purpose.
- Output is deterministic UTF-8 without a BOM.
- A rendered spatial preview was inspected; when runtime behavior matters, the
  patch was also opened/compiled in the matching vvvv installation.

Static XML checks are necessary but not sufficient for runtime correctness.
