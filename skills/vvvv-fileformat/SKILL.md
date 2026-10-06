---
name: vvvv-fileformat
description: "Describes and safely edits the vvvv gamma .vl XML format, including document structure, IDs, nodes, pins, pads, links, visible help annotations, exact editor pin geometry, Help Browser registration, and human-preserving layout. Use when generating, parsing, validating, or modifying .vl files programmatically."
license: CC-BY-SA-4.0
metadata:
  author: Kopffarben 
  version: "1.1"
---

# VL File Format (.vl)

## Overview

A `.vl` file is an XML document encoding a visual dataflow program for vvvv gamma. Key elements:

- **Document** — root element, contains dependencies and one top-level Patch
- **Patch** — container for visual elements (Nodes, Pads, Links, Canvases)
- **Node** — operation calls, type definitions, or regions
- **Pin** — input/output on a Node (defined at definition site)
- **Pad** — visual data element (IOBox) for displaying/editing values
- **Link** — connects two endpoints by referencing their IDs
- **Canvas** — visual grouping container (no logical scope)
- **ProcessDefinition** — lifecycle definition (Create, Update) via Fragments
- **Slot** — state field within a type definition

When editing an existing document, preserve unknown XML, declaration order, IDs,
node widths, and established geometry unless the requested change requires them to
move. XML validity alone does not prove that a node surface, pin order, or layout is
correct.

This skill includes its reusable Python editor and matching MCP/CLI adapters.
On first use with no successful collection-wide upstream check in seven days,
follow the [shared maintenance policy](https://github.com/tebjan/vvvv-skills/blob/main/CONTRIBUTING.md).
Compare upstream selectively; never overwrite project-owned extensions. Contribute
verified generic findings with versions/reproduction and publishing authorization;
keep renderer-specific facts in the owning project. Installed copies update only
through their authorized installation/update workflow.

## XML Root and Namespaces

```xml
<?xml version="1.0" encoding="utf-8"?>
<Document xmlns:p="property" xmlns:r="reflection" Id="C2vqbtoStWoOI1eKIKZBBM"
          LanguageVersion="2024.6.0" Version="0.128">
  <!-- dependencies and patch -->
</Document>
```

| Prefix | URI | Purpose |
|--------|-----|---------|
| `p` | `property` | **Required.** Complex properties as child elements (`<p:NodeReference>`) |
| `r` | `reflection` | Optional. Only when using `r:IsNull="true"` for explicit null values |

Root attributes: `Id` (base62 GUID), `LanguageVersion` (e.g. `"2024.6.0"`), `Version` (always `"0.128"`).

## ID System

Every element has a unique `Id` — a **22-character VL-encoded GUID** using `[0-9A-Za-z]`. All IDs must be unique within the document. Generate via `GUIDEncoders.GuidTobase62(Guid.NewGuid())` or the manipulator's `new_vl_id()`. VL's encoding is not ordinary base62 of one 128-bit integer: it uses the alphabet `ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789`, `Guid.ToByteArray()` byte order, and two independently encoded 64-bit halves of 11 characters each. The source is `VL.Lang/src/ImmutableModel/Internal/GUIDEncoders.cs` in a matching vvvv source checkout; do not invent an ID codec from the 22-character shape alone.

Link `Ids` is a comma-separated sequence of two or more data-hub IDs. VL's `Link.SourceId` is the first and `SinkId` is the last; intervening IDs are valid routing data hubs, not extra or malformed links. An empty or one-ended `<Link>` can be written by an unfinished editor drag; `vlpatch validate` rejects it. Use the manipulator's explicit `apply --remove-incomplete-links --connect SOURCE_ID TARGET_ID` only after verifying the intended endpoints; never infer a missing endpoint from proximity. Never discard a three-ID link merely because it is not a pair. Reopen the patch in vvvv to verify that each new ProcessNode's output actually reaches the renderer group: XML parse success alone does not establish an active contribution.

## Element Hierarchy

```
Document
├── NugetDependency (0..n)
├── DocumentDependency (0..n)
├── PlatformDependency (0..n)
└── Patch (exactly 1, top-level)
    ├── Canvas (DefaultCategory, CanvasType="FullCategory")
    └── Node (Name="Application")
        └── Patch (inner)
            ├── Canvas (CanvasType="Group")
            │   ├── Node (operation calls)
            │   ├── Pad (IOBoxes)
            │   └── ...
            ├── Patch (Name="Create")
            ├── Patch (Name="Update")
            ├── ProcessDefinition
            │   ├── Fragment → Create patch
            │   └── Fragment → Update patch
            └── Link (0..n)
```

**Critical**: Dependencies are direct children of `Document`, NOT inside `Patch`.

## Dependencies

```xml
<NugetDependency Id="..." Location="VL.CoreLib" Version="2024.6.0" />
<DocumentDependency Id="..." Location="./MyOtherFile.vl" />
<PlatformDependency Id="..." Location="VL.Core.dll" />
```

Almost every document needs `VL.CoreLib`. Use `IsForward="true"` to re-export types to consumers.

## NodeReference System (Choices)

The `<p:NodeReference>` property defines what a Node IS. It contains `<Choice>` elements that identify the target symbol.

### Operation Call

```xml
<p:NodeReference LastCategoryFullName="Primitive.Math" LastDependency="CoreLibBasics.vl">
  <Choice Kind="NodeFlag" Name="Node" Fixed="true" />
  <Choice Kind="OperationCallFlag" Name="+" />
</p:NodeReference>
```

- First Choice: `Kind="NodeFlag"` with `Fixed="true"` (shape indicator)
- Second Choice: `ProcessAppFlag` (stateful) or `OperationCallFlag` (stateless)

Custom Process/node registration names use PascalCase without spaces. Preserve
actual stock/imported names. Use `rename_local_process` for a local helper so its
definition and matching call selectors change together; a display label alone
does not rename a registered node. See [semantic edits](programmatic-editing.md#local-process-helpers-all-authoring-surfaces).

`LastCategoryFullName`/`LastDependency` are last-seen editor hints, not a complete
overload selector. Preserve the actual saved Choices, CategoryReference and any
PinReference selectors from a working call. Adaptive and explicit-overload calls
are different contracts; do not indiscriminately add/remove `Fixed`. For scalar
Cons versus sequence Concat, Spread-to-memory adaptive calls and the separate
MutableArray overload, read
[collection dimensions and adaptive conversions](programmatic-editing.md#collection-dimensions-and-adaptive-conversion-calls).

### Type Definitions

```xml
<!-- Process -->
<Choice Kind="ContainerDefinition" Name="Process" />
<CategoryReference Kind="Category" Name="Primitive" />

<!-- Class / Record / Interface / Forward -->
<Choice Kind="ClassDefinition" Name="Class" />
<Choice Kind="RecordDefinition" Name="Record" />
<Choice Kind="InterfaceDefinition" Name="Interface" />
<Choice Kind="ForwardDefinition" Name="Forward" />
```

### Regions

```xml
<Choice Kind="StatefulRegion" Name="Region (Stateful)" Fixed="true" />
<CategoryReference Kind="Category" Name="Primitive" />
<Choice Kind="ApplicationStatefulRegion" Name="If" />  <!-- or ForEach, Cache -->
```

Regions use `StatefulRegion` as the FIRST Choice (not `NodeFlag`). Use `ApplicationStatefulRegion` for If/ForEach or `ProcessStatefulRegion` for Cache.

## Node Element

```xml
<Node Name="MyNode" Bounds="300,200,65,19" Id="...">
  <p:NodeReference>...</p:NodeReference>
  <Pin Id="..." Name="Input" Kind="InputPin" />
  <Pin Id="..." Name="Output" Kind="OutputPin" />
</Node>
```

Key attributes: `Id`, `Name`, `Bounds` (`"X,Y"` or `"X,Y,W,H"`), `Summary`, `Tags`.

## Pin Element

```xml
<Pin Id="..." Name="Value" Kind="InputPin" DefaultValue="42" />
<Pin Id="..." Name="Result" Kind="OutputPin" />
```

Kind values: `InputPin`, `OutputPin`, `StateInputPin`, `StateOutputPin`, `ApplyPin`.

Visibility: `Visible` (default), `Optional`, `OnCreateDefault`, `Hidden`.

## Pad Element (IOBox)

```xml
<Pad Id="..." Bounds="200,160,80,20" ShowValueBox="true" isIOBox="true" Value="3.14"
     Comment="My Value">
  <p:TypeAnnotation LastCategoryFullName="Primitive" LastDependency="CoreLibBasics.vl">
    <Choice Kind="TypeFlag" Name="Float32" />
  </p:TypeAnnotation>
</Pad>
```

Note the lowercase `i` in `isIOBox`. Common types: `Boolean`, `Int32`, `Float32`, `Float64`, `String`, `Vector2`, `Vector3`.

### Comment Pad

```xml
<Pad Id="..." Bounds="100,100,400,25" ShowValueBox="true" isIOBox="true"
     Value="Title text here">
  <p:TypeAnnotation><Choice Kind="TypeFlag" Name="String" /></p:TypeAnnotation>
  <p:ValueBoxSettings>
    <p:fontsize p:Type="Int32">9</p:fontsize>
    <p:stringtype p:Assembly="VL.Core" p:Type="VL.Core.StringType">Comment</p:stringtype>
  </p:ValueBoxSettings>
</Pad>
```

A visible heading uses the same structure with `fontsize` 15. A clickable URL
uses the same String Pad with `stringtype` set to `Link`.

## Link Element

```xml
<Link Id="..." Ids="outputPinId,inputPinId" />
```

`Ids` format: `"sourceId,sinkId"` or `"sourceId,intermediateHubId,sinkId"` (and longer routes) — source first, sink last. Use `IsHidden="true"` for reference links. `IsFeedback="true"` is not a delay for arbitrary node links: the inspected compiler skips that link's assignment; it does not create stored state. First check the actual camera/input contract. If the renderer already associates window input with its connected camera, no backward link or Slot is needed. For cameras requiring explicit window-input feedback, copy a verified Slot pattern: one Slot on the Process's inner Patch, separate read/write pads sharing its SlotId, and ordinary links. The read pad feeds the camera; the window feeds the write pad. Do not close a direct camera/window cycle and merely label it feedback.

## ProcessDefinition and Fragments

```xml
<Patch Id="innerPatchId">
  <Canvas Id="..." CanvasType="Group" />
  <Patch Id="createId" Name="Create" />
  <Patch Id="updateId" Name="Update" />
  <ProcessDefinition Id="...">
    <Fragment Id="..." Patch="createId" Enabled="true" />
    <Fragment Id="..." Patch="updateId" Enabled="true" />
  </ProcessDefinition>
</Patch>
```

Fragment `Patch` attribute references a sibling `<Patch>` element's `Id`.

For an `Application` whose container is `Process`, this lifecycle block is
mandatory, even when Create and Update are empty. A Group canvas by itself is
only displayable XML: vvvv can open it and draw every node and link, but it has
no execution entry point, so the whole dataflow remains grey and never runs.
Validators and generators must require both named sibling patches plus enabled
fragments targeting both of them.

## Control-flow Regions

Regions use 4-value Bounds (`"X,Y,W,H"`) and have ControlPoints at borders:

```xml
<Node Bounds="100,200,400,300" Id="...">
  <p:NodeReference LastCategoryFullName="Primitive" LastDependency="Builtin">
    <Choice Kind="StatefulRegion" Name="Region (Stateful)" Fixed="true" />
    <CategoryReference Kind="Category" Name="Primitive" />
    <Choice Kind="ApplicationStatefulRegion" Name="If" />
  </p:NodeReference>
  <Patch Id="...">
    <Canvas Id="..." CanvasType="Group"><!-- content --></Canvas>
    <Patch Id="thenId" Name="Then" />
    <Fragment Id="..." Patch="thenId" Enabled="true" />
  </Patch>
  <ControlPoint Id="..." Bounds="150,200" Alignment="Top" />
  <ControlPoint Id="..." Bounds="150,500" Alignment="Bottom" />
</Node>
```

Region patch names: If uses `Then`/`Else`, ForEach uses `Create`/`Update`/`Dispose`, Cache uses `Create`/`Update`.

`ControlPoint` is a bidirectional region portal, not a conventional input pin.
Links legitimately target it outside a region and source from it inside (or the
reverse for region outputs). For CPU instancer transforms, use the bundled
`PatchSession.add_matrix_repeat_builder(...)`: it creates the canonical
Cache/Repeat/MutableArray structure, uses one count for allocation and iteration,
and returns a stable `ReadOnlyMemory<Matrix>` endpoint.
Its position input is a Vector2 spread relayed into Repeat's `XyZ.Input`, not
a direct TransformSRT translation. Its scalar Y and scaling endpoints are
separate. Keep the explicit `MutableArray<T> -> ReadOnlyMemory<T>` overload
references; structural XML validation alone cannot prove vvvv type resolution.

## TypeAnnotation

```xml
<!-- Simple type -->
<p:TypeAnnotation>
  <Choice Kind="TypeFlag" Name="Float32" />
</p:TypeAnnotation>

<!-- Generic type: Spread<RGBA> -->
<p:TypeAnnotation LastCategoryFullName="Collections" LastDependency="VL.Collections.vl">
  <Choice Kind="TypeFlag" Name="Spread" />
  <p:TypeArguments>
    <TypeReference LastCategoryFullName="Color" LastDependency="CoreLibBasics.vl">
      <Choice Kind="TypeFlag" Name="RGBA" />
    </TypeReference>
  </p:TypeArguments>
</p:TypeAnnotation>
```

## Slot Element (State Fields)

For shared resources, multiple accessor Pads can read one named Slot locally.
Slots are real state: initialization, read/write compiler ordering and resource
lifetime still matter. They are not guaranteed one-frame delays by placement.
Use `PatchSession.add_slot_read(...)` instead of duplicating resource producers.

Within a local Process, repeat a placement of the same input using
`PatchSession.add_input_placement(...)`. It creates a fresh ControlPoint with a
hidden reference link to the existing signature Pin, not another parameter or an
invented `DefinitionId`. Keep the read beside its consumer and related creative
controls together. See [programmatic-editing.md](programmatic-editing.md).

```xml
<Slot Id="..." Name="MyField">
  <p:TypeAnnotation><Choice Kind="TypeFlag" Name="Float32" /></p:TypeAnnotation>
  <p:Value>0.5</p:Value>
</Slot>
```

## Complete Minimal Example

```xml
<?xml version="1.0" encoding="utf-8"?>
<Document xmlns:p="property" Id="A1b2C3d4E5f6G7h8I9j0Kl"
          LanguageVersion="2024.6.0" Version="0.128">
  <NugetDependency Id="B2c3D4e5F6g7H8i9J0k1Lm" Location="VL.CoreLib"
                   Version="2024.6.0" />
  <Patch Id="C3d4E5f6G7h8I9j0K1l2Mn">
    <Canvas Id="D4e5F6g7H8i9J0k1L2m3No" DefaultCategory="Main"
            BordersChecked="false" CanvasType="FullCategory" />
    <Node Name="Application" Bounds="100,100" Id="E5f6G7h8I9j0K1l2M3n4Op">
      <p:NodeReference>
        <Choice Kind="ContainerDefinition" Name="Process" />
        <CategoryReference Kind="Category" Name="Primitive" />
      </p:NodeReference>
      <Patch Id="F6g7H8i9J0k1L2m3N4o5Pq">
        <Canvas Id="G7h8I9j0K1l2M3n4O5p6Qr" CanvasType="Group" />
        <Patch Id="H8i9J0k1L2m3N4o5P6q7Rs" Name="Create" />
        <Patch Id="I9j0K1l2M3n4O5p6Q7r8St" Name="Update" />
        <ProcessDefinition Id="J0k1L2m3N4o5P6q7R8s9Tu">
          <Fragment Id="K1l2M3n4O5p6Q7r8S9t0Uv"
                   Patch="H8i9J0k1L2m3N4o5P6q7Rs" Enabled="true" />
          <Fragment Id="L2m3N4o5P6q7R8s9T0u1Vw"
                   Patch="I9j0K1l2M3n4O5p6Q7r8St" Enabled="true" />
        </ProcessDefinition>
      </Patch>
    </Node>
  </Patch>
</Document>
```

## Validation Rules

1. All IDs must be unique (22-char base62 GUIDs)
2. `xmlns:p="property"` must be on `Document`
3. `Version="0.128"` always required
4. Fragment `Patch` must reference existing sibling Patch IDs
5. Link `Ids`: at least two non-empty data-hub IDs — source first, sink last; preserve intermediate hubs
6. `CanvasType="FullCategory"` only for root canvas
7. Every document needs `VL.CoreLib` dependency
8. Application node is the entry point (Name="Application", ContainerDefinition), and a Process Application must have Create + Update sibling patches and enabled ProcessDefinition fragments for both
9. Element names are case-sensitive (`Patch` not `patch`)
10. `isIOBox` uses lowercase `i`
11. Dependencies are children of `Document`, not `Patch`
12. Repository-owned text is UTF-8 without a byte-order mark
13. Public pins and their order come from a live/reflected catalog or production signature, never invention
14. Visible help prose uses String Pad annotations; XML comments are not canvas help
15. Link endpoint types must be compatible. In the verified gamma version, `Integer32` and `Integer32 (Unsigned)` are not implicitly interchangeable: a refused link passes no value. A typed IOBox may need its TypeAnnotation corrected to the real consumer contract, not a new Link representation. Shader factories determine pin types from their actual reflection rules; compare the shader signature and live node metadata. When a pin type changes, migrate affected IOBoxes/consumers together. The editor's [link-type diagnostic](programmatic-editing.md#minimum-diagnostics) checks only catalog-known endpoint types and remains silent when the real signature is unavailable.

## Common Mistakes

- Forgetting `xmlns:p="property"` namespace declaration
- Putting dependencies inside `Patch` instead of `Document`
- Reversed Link direction (first ID must be source/output)
- Treating a visible Application Group canvas as executable while omitting its Create/Update patches or enabled ProcessDefinition fragments
- Wrong Bounds format (use commas, no spaces: `"100,200,65,19"`)
- Using `IsIOBox` instead of `isIOBox`
- Treating node centres as pin positions
- Sorting pins alphabetically or placing the main output after diagnostic outputs
- Running a whole-document layout over an already hand-arranged patch
- Using a control-flow region when a visual `Overlay` was intended, or vice versa
- Writing a visible comment as an XML `<!-- comment -->`
- Treating `GridSpread (2D)` Width as the distance between the outer cell centres. With centred alignment, `Center` is the grid midpoint and cell-centre spacing is `Width / Count` on each axis. To align a 3-by-2 grid with positions x = -1.6, 0, 1.6 and z = 0, -2.5, use Center = (0, -1.25), Width = (4.8, 5.0), Count = (3, 2). Verify against the rendered patch, not just XML links.

For the complete element reference with all attributes, Choice kinds, and serialization details, see [format-reference.md](format-reference.md).
For layout, exact pin anchors, node sizing, and human-preserving edit rules, read [best-practices.md](best-practices.md) before changing coordinates.

For documents with local Process definitions, inspect geometry per attached
Canvas using `layout_analysis(canvas=...)` and `render_svg(..., canvas=...)`.
Independent helper coordinates must not be treated as one global canvas.
Repeated input placements and Slot pads retain two-coordinate Bounds when moved;
their labels must be included in collision review. See
[programmatic-editing.md](programmatic-editing.md#inspect-one-actual-canvas-at-a-time).
For help-patch taxonomy, visible annotations, overlays, Help Browser manifests, adjacent assets, and verification, read [help-patch-authoring.md](help-patch-authoring.md).
For loss-preserving automated editing and the repository's persistent patch manipulator, read [programmatic-editing.md](programmatic-editing.md). Python `edit_batch`, MCP `vl_edit` and CLI `vlpatch edit` share one discoverable semantic contract. Use `vl_capabilities` / `vlpatch capabilities` for current arguments and `vl_canvases` for scope IDs; new authoring APIs must be exposed and parity-tested across all three surfaces in the same change. An already-running MCP process needs restart/reconnection to load added tools. File-only validation is not live vvvv compilation.
