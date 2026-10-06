# VL File Best Practices

Layout, positioning, and visual organization guide for generating well-structured
`.vl` files. Based on production VL.StandardLibs files, human-authored package help,
and the vvvv editor's node/pin layout implementation.

---

## Data Flow Direction

**Links and dependency flow inside each subgraph run top-to-bottom.** This is the
most important layout rule. Independent or sequential subgraphs are placed
left-to-right beside each other, so the whole patch uses both dimensions without
turning individual dataflow chains sideways.

Canvas coordinates do not determine runtime evaluation order; graph dependencies do.

- Inputs at the **top**, outputs at the **bottom**
- Input Pads above the nodes they feed
- Output Pads below the nodes they receive from
- Links go from smaller Y to larger Y (top → bottom)
- Feedback uses a real state boundary (for example paired Slot read/write pads).
  Do not add a direct bottom-to-top node cycle and assume `IsFeedback="true"`
  creates a delay; that attribute alone does not synthesize stored state.
- Peer technologies or alternatives read left-to-right as separate vertical groups

```
[Input Pad]        y = 200
     |
     v
[Processing Node]  y = 300
     |
     v
[Output Pad]       y = 370
```

---

## Coordinate System

- Origin `(0,0)` at **top-left**
- X increases right, Y increases down
- Editor geometry is measured in pixels; serialize whole-pixel Bounds using
  the canonical rounding policy below
- Do not impose a universal grid on human-authored positions
- For code generation, use round numbers (multiples of 5 or 10) for readability
- Content area typically spans X:100-700, Y:120-600

---

## Vertical Spacing

| Connection Type | Recommended | Observed Median |
|----------------|------------|-----------------|
| Input Pad → Node | **50 px** | 47 px |
| Node → Node (chain) | **40 px** | 41 px |
| Node → Output Pad | **65 px** | 66 px |
| Comment → First element | **100 px** | ~80 px |

---

## Node Positioning

### Horizontal Alignment

Align movable one-to-one links at the actual output/input pin anchors, not at node
centres. vvvv's `PinBarView` places visible pins on each rail as follows:

- pin width is 5 px;
- hidden pins do not participate;
- declaration/XML order is preserved;
- one visible pin has anchor `x + 2.5`;
- for `count > 1`, pin `i` has anchor
  `x + 2.5 + i * (effectiveWidth - 5) / (count - 1)`.

Inputs use the top rail and outputs the bottom rail. Use the editor's effective
node width, including expansion for the label and minimum pin-bar width. A
deliberately widened node is layout information and may be necessary to align a
specific source with a specific pin.

Diagonal links remain appropriate for fan-out, different collection slots,
cross-subgraph dependencies, conflicting multi-pin order, or overlap avoidance.

### Staircase Pattern (Multiple Inputs)

When a node has multiple inputs, arrange pads diagonally to avoid crossing links:

```
Pad "Red"      Bounds="112,187,35,15"
Pad "Green"    Bounds="139,216,35,15"    offset: +27x, +29y
Pad "Blue"     Bounds="165,243,35,15"    offset: +26x, +27y
Pad "Alpha"    Bounds="192,270,35,15"    offset: +27x, +27y
     ↓ ↓ ↓ ↓
Node "RGBA Join"  Bounds="110,305,73,26"
```

The staircase follows **destination pin order and dependencies**, not a uniform
grid. Stagger heights to leave labels and wires clear; the example offsets are
not universal spacing constants. A value feeding several stages belongs above
its earliest consumer, not beside only the final node. Keep a helper/vector/
transform chain in a nearby offset lane when putting it directly underneath
would obstruct the main data link. Short diagonals are often the clean solution.

When a human improves one repeated cluster, compare elements by semantic role,
actual links and pin identity, then reuse its relative arrangement only for
explicitly targeted matching peers. Do not match by current value or old X alone,
copy creative values, flatten the controls back into rows, or normalize saved
widths. Keep the human exemplar unchanged. Compare label clearance, crossings
and wires through unrelated boxes as well as rectangle overlap.

### Multiple Outputs

Spread output pads horizontally:

```
        [Node]              y=298
       /      \
 [Output A]  [Output B]    y=367
 x=150       x=255
```

Typical X-gap between side-by-side output pads: 80-120 px.

---

## Element Sizes

### Node Sizes (Width x Height)

| Node Type | Width | Height | Example |
|-----------|-------|--------|---------|
| Simple operation (+, -, *) | 22-25 | 19 | `"200,300,25,19"` |
| Standard CoreLib node | 45-85 | 19 | `"200,300,65,19"` |
| Long-named node | 85-165 | 19 | `"200,300,145,19"` |
| Join/Split/stateful ops | 41-73 | 26 | `"200,300,52,26"` |
| Skia primitive | 105-145 | 13 | `"200,300,105,13"` |

Standard node height is **19 px** (~80% of all nodes).

Serialized width is not always rendered width. Before calculating anchors,
crossings, or overlaps, expand it to the label minimum and the visible pin-bar
minimum. Never shrink a human-stretched width automatically.

**Sizing model** (implemented in `PatchSession._intrinsic_node_width`, used
by `add_node` and `normalize_node_sizes`):

```
title_width = 12 + len(node_name) * 5.2
pin_count   = max(visible_input_count, visible_output_count)   # hidden pins excluded
pin_width   = 5 * pin_count + 15 * (pin_count - 1)              # vvvv PinBarView: 5px pin, 15px min gap
width       = max(25, title_width, pin_width)
```

The pin-bar minimum follows the inspected editor constants; `title_width` is a
font-metric approximation, not a pixel-exact measurement. Preserve a larger saved
width and inspect labels visually. Verify the actual pin list before tuning size.

Verified 2026-09 against seven owner hand-fixes to a generated patch
("HowTo Procedural Mesh and SDF.vl") once each node's pin count is correct —
0px error on every sample, from `ProcGridInputAS` (P=18 → 345px) down to
`CpuTemplateInstancer` (P=9 → 165px). A generated node coming out narrower
than vvvv's own save can be a **pin-list bug** (the generator's catalog entry is
missing pins the real node/shader has); check real metadata and label measurement
before changing constants. A freshly created node
should never be seeded at a flat placeholder width (too wide for a 2-pin
node, too narrow for a 20-pin one); size it from this formula immediately.

### Pad Sizes (Width x Height)

| Pad Type | Width | Height | Example |
|----------|-------|--------|---------|
| Float32 / Integer32 (short value) | 35 | 15 | `"200,160,35,15"` |
| Float32 / Integer32 (long value, e.g. `"1000000"`) | grows, see below | 15 | `"200,160,61,15"` |
| Boolean (toggle/bang) | 35 | 35 | `"200,160,35,35"` |
| Vector2 | 35 | 28 | `"200,160,35,28"` |
| Vector3 | 35 | 43 | `"200,160,35,43"` |
| Vector4 | 35 | 57 | `"200,160,35,57"` |
| RGBA / Color | 136 | 15 | `"200,160,136,15"` |
| String (value) | 64-273 | 15-20 | `"200,160,170,20"` |
| String (heading, font=15) | 139-632 | 25-39 | `"100,100,400,25"` |
| String (comment, font=9) | 95-472 | 19-312 | `"100,140,350,40"` |
| Enum (e.g. `EnvironmentMapPreset`, `ToneMapOperator`) | 49-174, per type | 15 | `"200,160,116,15"` |

**Sizing policy** (implemented in `PatchSession._pad_size_for_value`, used by
`add_pad`): never a flat `100,20` placeholder regardless of type.

- **Vector2/3/4, RGBA/Color, Boolean are a FIXED size**, independent of the
  current value's text. vvvv never grows these — sizing a Vector3 to fit
  `"-5, -0.35, -5"` invents a box vvvv itself would not save.
- **Enum-like pads size to the widest choice in their enum type**, not to the
  current value's text (`EnvironmentMapPreset`'s current value can be longer
  than `DLSSPreset`'s yet render narrower) — they are looked up per type, not
  computed from text length. Only list a type here once you have measured it
  from a real vvvv-saved patch.
- **Scalar numeric and string pads grow with the value's text** past a short
  base (35px holds up to ~4 characters, e.g. `"0.33"`, `"1.22"`); calibrated
  on real vvvv-saved samples `"100"` (3 chars → 41px) and `"1000000"` (7
  chars → 61px). This is an approximation of vvvv's real font-metric-based
  measurement, not a pixel-exact reproduction — it is still a large
  improvement over a flat placeholder, and it is intentionally biased toward
  under- rather than over-estimating a short value so it never invents a size
  vvvv would render narrower.

### Bounds Convention

- **Definition nodes** (Application, type defs): 2-value `"X,Y"`
- **Processing nodes** (operation calls): 4-value `"X,Y,W,H"`
- **Value IOBoxes**: 4-value `"X,Y,W,H"`; plain Slot Pads use 2-value `"X,Y"`
- **ControlPoints**: 2-value `"X,Y"`
- **Numbers are always whole-pixel integers, comma-joined with no space**:
  `"48,790,225,19"`, never `"47.5, 790, 225, 19"`. vvvv always rounds canvas
  geometry to whole pixels; a fractional or space-separated coordinate in
  generated output makes every one of those lines show as changed the moment
  a human opens and re-saves the patch in vvvv, even though nothing actually
  moved. `document._format_bounds()` is the one place this repo's generator
  formats a `Bounds` string — every writer in `PatchSession` and `VlGraph`
  routes through it (round-half-away-from-zero, not Python's banker's
  rounding) rather than hand-building the string.

---

## Comment and Title Placement

### Title Comment (font=15)

```xml
<Pad Id="..." Bounds="119,100,400,25" ShowValueBox="true" isIOBox="true"
     Value="HowTo Do Something">
  <p:TypeAnnotation><Choice Kind="TypeFlag" Name="String" /></p:TypeAnnotation>
  <p:ValueBoxSettings>
    <p:fontsize p:Type="Int32">15</p:fontsize>
    <p:stringtype p:Assembly="VL.Core" p:Type="VL.Core.StringType">Comment</p:stringtype>
  </p:ValueBoxSettings>
</Pad>
```

### Description Comment (font=9)

```xml
<Pad Id="..." Bounds="119,145,350,40" ShowValueBox="true" isIOBox="true"
     Value="This example shows how to...">
  <p:TypeAnnotation><Choice Kind="TypeFlag" Name="String" /></p:TypeAnnotation>
  <p:ValueBoxSettings>
    <p:fontsize p:Type="Int32">9</p:fontsize>
    <p:stringtype p:Assembly="VL.Core" p:Type="VL.Core.StringType">Comment</p:stringtype>
  </p:ValueBoxSettings>
</Pad>
```

### Inline Annotation

Use `&lt; ` prefix in Value for arrow-style annotations next to nodes:
```xml
Value="&lt; this is important"
```

---

## Canvas Organization

| Context | CanvasType | Other Attributes |
|---------|-----------|------------------|
| Root (document level) | `FullCategory` | `DefaultCategory="Main"`, `BordersChecked="false"` |
| Inside Application/Process | `Group` | — |
| Sub-category (packages) | (default) | `Name="SubCategory"`, `Position="X,Y"` |

Category hierarchy via nesting:
```xml
<Canvas DefaultCategory="Graphics.Skia" CanvasType="FullCategory">
  <Canvas Name="Drawing" Position="100,100">         <!-- Graphics.Skia.Drawing -->
    <Canvas Name="Primitives" Position="200,200">     <!-- Graphics.Skia.Drawing.Primitives -->
      <Node Name="Circle" ... />
    </Canvas>
  </Canvas>
</Canvas>
```

---

## Multi-Section Layouts

When showing multiple related concepts side by side:

- Arrange sections **left-to-right** with 350-400 px horizontal gaps
- Y-align corresponding layers when it improves comparison
- Stagger heights when rigid alignment would overlap nodes, pads, or links
- Each section has its own title, inputs, processing nodes, outputs

```
y=100:  [Title A]                   [Title B]
y=145:  [Description A]            [Description B]
y=200:  [Input Pads A]             [Input Pads B]
y=300:  [Node A]                   [Node B]
y=370:  [Output A]                 [Output B]

        x: 100-350                 x: 550-800
```

For render help patches, semantic hierarchy can also be expressed with nested
renderer `Group` nodes. A wide upper Group may collect only the hero/demo peers;
a lower scene Group then collects that hero Group together with ground, basic
scene geometry, and lights before feeding the renderer. This keeps the feature
being taught separate from shared scene setup. It is a convention, not a mandate:
do not add a Group level when it does not improve the reading of the patch.

For explicitly independent renderer peers, collection slots ordered by source
anchor X can reduce convergence crossings. For renderer groups that traverse
children sequentially, slot order is also execution order; preserve GPU
producer-before-consumer stages. Never sort every Group by position.
Use the opt-in [semantic operation](programmatic-editing.md#local-process-helpers-all-authoring-surfaces)
when that graph change is intended, preserving the human source geometry.

### Fan-Out Pattern

One source feeding multiple parallel nodes:

- Keep consumers in their semantic clusters; stagger Y to avoid overlap
- Prefer local repeated-input placements or verified Slot reads for shared resources
- Align short links by their real pin anchors; horizontal spacing is not a fixed rule

---

## Control-flow Region Layout

Executable regions use 4-value Bounds with explicit size:

| Region Type | Typical Size | Minimum |
|-------------|-------------|---------|
| If | 300-530 x 200-530 | 200 x 150 |
| ForEach | 190-400 x 120-300 | 150 x 100 |
| Cache | 200-350 x 150-250 | 150 x 100 |

ControlPoint placement:
- Top: `Alignment="Top"`, Y = region top
- Bottom: `Alignment="Bottom"`, Y = region top + height
- Leave 20-30 px padding from region borders for content
- Treat each ControlPoint as a bidirectional typed portal. Its XML link direction
  depends on which side of the region boundary is being connected.

For CPU Matrix collections, prefer the canonical Cache/Repeat pattern generated
by `PatchSession.add_matrix_repeat_builder(...)`: one count drives both
`MutableArray.Create.Length` and `Repeat.Iteration Count`; the Update index feeds
`MutableArray.SetItem.Index`; and the cached array leaves through
`AsReadOnlyMemory`. This keeps collection dimensions consistent and makes the
dataflow explicit to both users and agents.
The position spread crosses into Repeat via a top ControlPoint and enters
`XyZ.Input` as a state input; `XyZ` selects a Vector2 per iteration and adds
a scalar Y before `TransformSRT.Translation`. Use the explicit
`MemoryUtils.AsReadOnlyMemory` overload references copied from a vvvv-saved
patch. An XML-valid link or operation name alone does not prove type resolution.

### Visual overlays are different

A help-patch frame is an `<Overlay Name="..." Bounds="x,y,w,h" />`; it is not a
control-flow region and changes no evaluation semantics. Use compact overlays only
to distinguish multiple technologies or alternatives. Keep shared setup and sink
spines outside them. Do not wrap a single-concept patch in a decorative full-canvas
overlay.

**Reserve a title band on the top edge.** vvvv draws the Overlay's `Name`
label inside its own top edge, over the content underneath. Fitting a region
with the same padding on all four sides leaves that label sitting directly on
top of the first row of nodes/IOBoxes. `PatchSession.fit_region(...,
padding=16)` therefore keeps `padding` (16px) on the left/right/bottom but
reserves `top_padding` (default `max(padding, 50)`) on top — measured from
three owner hand-fixes to generated regions, which moved the top edge up
40-46px beyond the side/bottom padding (46-56px of total top clearance)
while never moving the bottom edge. Pass an explicit `top_padding` only when
you have measured a different label height for a non-default font size.

---

## Process Definition Patterns

### Standard Process (Create + Update)

Application node at `Bounds="100,100"`. Inner Patch contains:
1. Canvas (`CanvasType="Group"`) with visual content
2. Named Patches (`Create`, `Update`)
3. ProcessDefinition with Fragments referencing those Patches

### Additional Fragments

| Patch Name | Purpose |
|-----------|---------|
| `Dispose` | Cleanup |
| `Notify` | Event handler |
| `Render` | Skia/Stride rendering |
| `Split` | Decomposition |

### Forward Types

Use `<ProcessDefinition Id="..." IsHidden="true" />` to hide from node browser.

---

## Package File Organization

### Aggregator Documents

Facade files with minimal content, forwarding dependencies:
```xml
<DocumentDependency Id="..." Location="./VL.Animation.vl" IsForward="true" />
```

### Type Definition Files

Organize via Canvas hierarchy:
```
Canvas (FullCategory, DefaultCategory="Domain")
├── Canvas (Name="Sub1", Position="100,100")
│   ├── Node (ForwardDefinition "TypeA")
│   └── Node (ForwardDefinition "TypeB")
└── Canvas (Name="Sub2", Position="300,100")
    └── Node (ContainerDefinition "ProcessC")
```

Forward definitions use 2-value Bounds and always include:
```xml
<p:ForwardAllNodesOfTypeDefinition p:Type="Boolean">true</p:ForwardAllNodesOfTypeDefinition>
```

---

## Naming Conventions

| Context | Convention | Examples |
|---------|-----------|----------|
| Process | PascalCase noun | `OrbitCamera`, `Sequencer` |
| Operation | PascalCase verb | `CircleContainsPoint` |
| Overload | Parenthetical suffix | `Create (KeyComparer)` |
| Forward type | Match .NET name | `LabelAttribute` |
| Pin names | PascalCase with spaces | `"Near Plane"`, `"Key Comparer"` |
| State pins | `(this)` suffix | `"Input (this)"` |
| Root categories | Dotted paths | `"Graphics.Skia"`, `"IO"` |

Standard patch names: `Create`, `Update`, `Dispose`, `Then`, `Else`, `Split`, `Render`, `Notify`.

Custom Process/operation names use PascalCase without spaces. This is not a
license to rename imported library nodes, pin labels or explanatory prose.
Renaming a local Process requires its definition and all matching call selectors
to change together; changing an instance's `Name` alone is not a reliable visible
rename. Use `rename_local_process` to update the definition and matching local
selectors together. Preserve existing public names through
[compatible aliases](../vvvv-custom-nodes/advanced.md#compatible-processnode-renames)
unless the owner explicitly requests a breaking migration of dependent files;
this is separate from renaming a local helper.

---

## Human-preserving edits

Existing geometry is authored information, not disposable output of a layout pass.

- Treat everything present when a patch is opened as protected.
- Default auto-layout moves only elements added in the current edit session.
- Saving or externally reloading establishes the next protected baseline.
- Translate an established connected subgraph rigidly when space is required.
- Reflow existing elements only through an explicit target selection.
- Whole-patch reflow is an explicit destructive action, never an edit side effect.
- Preserve relative positions, stretched widths, comment placement, and internal
  pin alignment; do not add tool-private ownership metadata to the `.vl` file.

Before and after a spatial edit, inspect exact bounds, pin anchors, overlays,
crossings, upward links, overlaps, and the movable/protected sets. Rectangle-only
checks are insufficient: also detect foreign nodes covered by an overlay.

---

## Complete Layout Recipe

### Help File Y-Position Guidelines

```
y = 100    [Title Comment]         font=15, stringtype=Comment
y = 145    [Description Comment]   font=9, stringtype=Comment
y = 200    [Input Pad 1]           isIOBox=true
y = 230    [Input Pad 2]           offset +30y
y = 300    [Processing Node]       Main operation
y = 350    [Processing Node 2]     Chained (if needed)
y = 420    [Output Pad]            Display result
y = 800    [Renderer Node]         (if visual, e.g. Skia)
```

### Spacing Checklist

- Input pads: 50-80 px above target node
- Sequential nodes: 40-50 px apart vertically
- Output pads: 60-70 px below source node
- Primary one-to-one links: exact pin-anchor alignment when geometry allows
- Multi-input pads: staircase pattern
- Multiple sections: 350-400 px horizontal gap
- Title/description: top of canvas (y=100-190)
- Renderer: bottom (y=800+)

---

## Quick Reference: Layout Dimensions

| Metric | Value |
|--------|-------|
| Application node position | `Bounds="100,100"` |
| Title comment Y | ~100-120 |
| Description comment Y | ~140-190 |
| First input pad Y | ~200-250 |
| Main processing area Y | ~280-400 |
| Output display area Y | ~370-500 |
| Renderer Y | ~800-900 |
| Vertical pad-to-node gap | 50-80 px |
| Vertical node-to-node gap | 40-50 px |
| Vertical node-to-output gap | 60-70 px |
| Horizontal section gap | 350-400 px |
| Standard node height | 19 px |
| Boolean pad size | 35x35 px |
| Primary link X-alignment | exact pin anchors (within editor rounding) |
| Output pad X-offset | +2 px |
| Fan-out spacing | 100-165 px |
