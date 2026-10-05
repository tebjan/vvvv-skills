# Local inputs, Slots and readable helper processes

Verified against vvvv gamma 2025.7.1 model/compiler/editor source and saved VL
documents. Recheck the target version before changing serialization contracts.

## Choose the right mechanism

| Intention | Mechanism | Not equivalent |
| --- | --- | --- |
| Use one Process input in several local clusters | Multiple placements of the same signature parameter | Extra signature pins or copied values |
| Store/read shared Process state | One Slot with local read/write Pads | A hidden current-frame wire |
| Expose an editable constant | Correctly typed IOBox | Plain Slot Pad |
| Reuse identical plumbing | Process helper or loop with appropriate state per instance | One mutable output object reused for every peer |

## Repeat the placement, not the parameter

Keep the original signature InputPin. Add a new ControlPoint at the consumer and
a hidden reference Link from that original Pin to the new ControlPoint, in the
owning Process Patch. Then connect the placement to the consumer normally:

```xml
<!-- Schematic IDs: generate real unique VL-encoded IDs in a document. -->
<ControlPoint Id="localInputPlacement" Bounds="420,180" />
<Link Id="referenceLink" Ids="originalSignatureInputPin,localInputPlacement"
      IsHidden="true" />
<Link Id="consumerLink" Ids="localInputPlacement,consumerInputPin" />
```

Do not add another signature Pin, copy the source value into a Slot, or put an
invented DefinitionId on the ControlPoint. The model's `Patch.AddProxy` and
`GetOrAddLink(..., isReference:true)` establish this identity relationship.
Place inputs beside their actual consumers inside helpers as well as on the root.

## Slots are state, not wiring shortcuts

A Slot belongs to its owning Process Patch. Multiple plain Pads can share that
Slot's ID through `SlotId`; generate a unique element ID for each Pad:

```xml
<Slot Id="sharedSlot" Name="Shared Resource" />
<Pad Id="localReader" SlotId="sharedSlot" Bounds="420,180" />
<Pad Id="localWriter" SlotId="sharedSlot" Bounds="620,350" />
```

An incoming ordinary link makes the Pad a writer; a Pad used as a source reads.
Keep these distinct from value IOBoxes (`isIOBox="true"`, four-value Bounds).
In the inspected compiler, `PatchState.ReadSlot` uses an earlier assignment
expression if present, otherwise the stored field; reads are local snapshots.
Canvas coordinates do not guarantee read order or a one-frame delay. Uninitialized
reference state starts null. Verify initialization and producer lifetime, including
Dispose/recreation: delaying a pointer does not keep its owner alive.

`IsFeedback="true"` alone does not synthesize a delay; the inspected compiler
skips that assignment. Use real state and inspect compiled behavior.

Orphan analysis must follow valid same-definition Slot read/write accessors for
reachability. A resource producer writing a Slot can feed helpers through other
read Pads without any physical Link between those Pads. Do not delete it based
on a physical-link-only warning. Model this separately from directed execution
dependencies: shared state does not invent a current-frame scheduling edge or
repair a cycle. Confirm the tool/server actually loaded its updated implementation
before changing a human-saved patch to satisfy a stale diagnostic.

## Construct nodes from contracts

Resolve full node names, dependencies, categories, input/output types and pin order
from actual metadata or a matching saved reference. Do not invent outputs from a
picture. Process calls need persistent state and correct enabled lifecycle
fragments; loops need independent state per iteration and coherent dimensions.
An alias to one repeatedly updated renderer is not a collection of renderers.

Group collection slot order is execution order. Only for explicitly independent
renderer peers, assign slots left-to-right by source anchors to reduce crossings.
Keep GPU producers before their consumers; never globally sort Groups by canvas X.
This changes wiring order, so make it an intentional graph edit rather than an
automatic geometry cleanup.

## Geometry and collaboration

Dependency chains read top-to-bottom; peer subgraphs sit left-to-right. Preserve
existing stretched widths, relative positions, comments and IDs. Move an established
group rigidly when space is needed; reflow only an explicitly requested selection.
Repeated input placements and Slot Pads use position-only `Bounds="x,y"`; retain
that form when moving them, rather than inventing a wide value box.

Pins are left-aligned across the effective node width. Hidden pins occupy no rail
space; preserve declaration order. For a 5-pixel pin width, anchor X is `x+2.5`
for one pin, or `x+2.5+i*(width-5)/(count-1)` for multiple pins, subject to editor
rounding. Inputs are above and outputs below. Respect label/pin-bar minimum width
as well as serialized width. Font-width estimates are not exact editor metrics.
Align actual anchors when possible; a deliberate diagonal is better than overlap.

Inspect one actual canvas at a time: different Process bodies have independent
coordinate systems. Hidden reference links are not visible wires. Include visible
comments, labels and grouping overlays in collision review; rectangle-only checks
do not prove readability. Compare new collisions with the human-saved baseline.

Learn from a human save by comparing stable IDs, position changes, width-only
changes, values, call references and link endpoints separately. Editor-generated
pin/reference metadata can make a text diff large without changing graph topology.
For repeated clusters, preserve the human exemplar and transfer relationships
only to explicitly targeted semantic peers: pin-order staircases, local reads,
shared values above the earliest consumer, and unobstructed helper lanes.

Count crossings between wires attached to different pins even when they share
one node. Only a shared endpoint is a junction; sharing a consumer is not grounds
to skip the comparison. Review labels and wires through unrelated boxes too.
State the inspected canvas and remaining defects; fewer crossings do not prove
that the whole document is tidy or that it compiles.

Validate and inspect the persisted document, then compile/render in the matching
vvvv version and test save/reopen. XML, pin geometry and SVG previews alone do
not prove type resolution, runtime execution or visual parity. Emit BOM-free UTF-8
and preserve unknown XML content rather than reconstructing the document.
