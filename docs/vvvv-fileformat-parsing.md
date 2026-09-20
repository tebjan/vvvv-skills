# vvvv gamma `.vl` file format — parsing reference

A practitioner's guide to reading vvvv gamma's on-disk `.vl` format. Distilled from parsing production-scale projects — dozens of files, tens of thousands of nodes, single documents well over 100k lines. Covers what the XML actually looks like, which parts are load-bearing, and every non-obvious trap worth knowing before writing a parser.

This is the document you would want before writing your own tool. It is not a spec (there isn't one) — it is a catalogue of observed behaviour.

---

## 1. Big picture

A `.vl` file is a single XML document serialised by the vvvv gamma editor. It records:

- **Dependencies** — other `.vl` files, NuGet packages, platform DLLs.
- **Definitions** — the records, classes, operations, and processes the user has drawn.
- **Composition** — how those definitions are *called* and wired together inside patches.
- **Visual layout** — node bounds, control points for wires, canvas groupings.
- **Metadata** — authors, version numbers, language version.

Scale: a 10-year production project can easily reach ~180k lines / ~20k nodes / ~6k patches in a single file. Parsers must be pragmatic about cost — a full `ElementTree.parse()` of a large file works but takes seconds; sub-problems that only need file-level dependencies can often get away with tail-scanning the last few hundred lines. Match the approach to the question you're asking.

---

## 2. Root shape

```xml
<?xml version="1.0" encoding="utf-8"?>
<Document xmlns:p="property" xmlns:r="reflection"
          Id="A6t9PrsdBGePhNmWOOtWGx"
          LanguageVersion="2025.7.1"
          Version="0.128">
  <NugetDependency Id="..." Location="VL.CoreLib" Version="..."/>
  <DocumentDependency Id="..." Location="./Other.vl"/>
  <PlatformDependency Id="..." Location="System.Reflection"/>
  <Patch Id="Th8hpfHvBF4Lk6VOwDCc9D">
    <Canvas Id="..." DefaultCategory="MyProject" CanvasType="FullCategory">
      ... everything lives here ...
    </Canvas>
  </Patch>
  <!-- more dependencies may also be emitted at the tail -->
</Document>
```

Key facts:

- **Namespaces**: `xmlns:p="property"` and `xmlns:r="reflection"`. vvvv uses `property` and `reflection` as literal namespace URIs — not URLs. ElementTree prefixes these onto element tags as `{property}NodeReference`, etc. In Python: `ref = node.find("{property}NodeReference")`.
- **`Id` attributes are everywhere.** Every Patch, Node, Pin, Pad, Link, ControlPoint, definition, dependency, and fragment has a unique base62 GUID-like id (22 chars). These IDs are **stable across saves** unless the user explicitly duplicates or regenerates. Persist anything you want to survive re-scans (annotations, screenshots) against these IDs.
- **`LanguageVersion` / `Version`**: editor version & document schema version. Useful for compatibility gates — old files may lack fields added in newer vvvv releases.
- **Exactly one top-level `<Patch>` per document.** Its child `<Canvas>` has `CanvasType="FullCategory"` — this is the marker that distinguishes the document root from any other patch. See § 4.
- **Dependency elements are scattered**: NuGet dependencies typically cluster near the top *and* the tail. Always scan all direct children of `<Document>`, not just the first few.

---

## 3. Parsing prerequisites (traps)

### 3.1 Backslash closers — vvvv bug

vvvv occasionally emits `<\p:NodeReference>` (literal backslash instead of slash) when a patch is saved while mid-edit. ElementTree rejects this as malformed XML. Before parsing, normalise:

```python
_BACKSLASH_CLOSER_RE = re.compile(r"<\\(/?[\w:]+)")

def _repair_backslash_closers(text: str) -> str:
    return _BACKSLASH_CLOSER_RE.sub(r"</\1", text)
```

Only run the repair if `"<\\"` appears in the source — skip the regex otherwise to avoid the cost on clean files.

### 3.2 BOM + encoding

Files are UTF-8 with a BOM. Read with `encoding="utf-8"` and tolerate both BOM'd and non-BOM'd files; use `errors="ignore"` (or equivalent) to handle the very rare invalid byte sequence in a comment.

### 3.3 Size

A typical large `.vl` file is several MB raw. Full parse is fine (~1-2 s on modern hardware). If you need only file-level dependencies, tail-scan: read the last few hundred lines and regex for `<DocumentDependency`, `<NugetDependency`, `<PlatformDependency`.

### 3.4 Namespace normalisation

Elementtree tags come back as `{property}NodeReference`. Helper:

```python
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if tag.startswith("{") else tag
```

Use this whenever you compare tag names — never match the qualified string.

---

## 4. Document root: the top `<Patch>`

The one `<Patch>` that is a direct child of `<Document>` is the **document root patch**. Identify it by:

- It is a direct child of `<Document>`. (There is exactly one such.)
- Its `<Canvas>` child has `CanvasType="FullCategory"` (optional check — the position check alone is sufficient in practice).

Everything user-authored hangs off this patch, either inside its `<Canvas>` (definitions + lifecycle) or as direct children after the canvas (Application entry point — see § 11).

---

## 5. The core grammar

Inside a `<Patch>`, the interesting children live in two places:

1. Inside the patch's `<Canvas>` element — the normal case.
2. Direct children of the `<Patch>` itself, after the `<Canvas>` — where vvvv places the `Application` entry-point Node, and where it sometimes emits member-operation patches (see § 12).

Both locations must be walked. Inside those locations, expect:

| Tag | Role | Notes |
|---|---|---|
| `Node` | A placed node — either a definition, a call, or a region | Carries a `<p:NodeReference>` that tells you *what kind* |
| `Patch` (nested inside a Node) | The body of that node when it is a definition or has a visual lambda | Walk recursively |
| `Patch` (direct child of another Patch) | "Patch-as-operation" form — a member op serialised without a Node wrapper | Also walk recursively; attribute to owning definition via parent |
| `Pad` | An IOBox / value box — a literal that feeds into nodes | Carries `<p:TypeAnnotation>`, not `<p:NodeReference>` |
| `Pin` (inside Node) | That node's input/output ports | Direction & state live in the `Kind` attribute |
| `Pin` (direct child of Patch) | The patch's **interface** pin — the patch's outer surface when embedded | Same attributes, different semantic |
| `Link` | A wire between two pins | `Ids="outPin,inPin"` comma-joined |
| `ControlPoint` | Visual waypoint on a wire | Safe to ignore unless drawing wires |
| `Canvas` | Visual grouping container | Can appear nested inside `Canvas` for group panels |
| `ProcessDefinition` | Declares fragments for a stateful process | See § 10 |
| `Fragment` | Associates a body Patch with a lifecycle slot | Inside `ProcessDefinition` |

Ignorable for most purposes: `ControlPoint`, `Comment`, `Overlay`, animation metadata elements.

---

## 6. `<Node>` — the workhorse

A `<Node>` is polymorphic. It can be a **definition** (the node where something is declared), a **call** to a definition (usage), a **region** (control-flow construct), a **literal** value, etc. The `<p:NodeReference>` child tells you which.

```xml
<Node Name="CreateWithMappings" Bounds="-544,100,174,136" Id="Sbvi8h9l75JQTXCNdOFHYj">
  <p:NodeReference LastCategoryFullName="Primitive" LastDependency="VVVV.Value.ParameterDemo.vl">
    <Choice Kind="OperationDefinition" Name="Operation"/>
  </p:NodeReference>
  <Patch Id="...">...</Patch>  <!-- the body -->
</Node>
```

Attributes of the `<Node>` itself:

- `Id` — stable GUID.
- `Name` — the user-set label. May be absent: a `<Node>` with no `Name` is an anonymous helper (hide by default in structure views, see `shouldHideNode`).
- `Bounds="x,y,w,h"` — position + size in canvas coords. May be `"x,y"` only (no size).
- `Comment` — optional docstring-like label the user attached.

### 6.1 `<p:NodeReference>` — the classification hinge

Read the attributes first:

- `LastCategoryFullName` — the fully qualified category the node lives in. For calls, the last segment is the owning type; e.g. `MyProject.Settings` → the call is on a record named `Settings`. For definitions, it can be `Primitive`, `Application`, or a path like `VL.CoreLib.Spreads`.
- `LastDependency` — the filename the target definition lives in: `VL.CoreLib.vl`, the local file's own name, an external `.vl`, or the literal `"Builtin"`.

Then read the children:

- One or more `<Choice Kind="..." Name="...">` elements — these encode the node's *role*. Multiple Choices may appear; the interesting one depends on Kind.
- Zero or more `<CategoryReference Kind="..." Name="..."/>` — cross-references to types (records, classes, type flags).

#### Choice `Kind` values — the taxonomy

Observed and what they mean:

| Kind | Meaning |
|---|---|
| `RecordDefinition` | This Node declares a record |
| `ClassDefinition` | This Node declares a class |
| `OperationDefinition` | This Node declares an operation (standalone or member) |
| `ForwardRecordDefinition` / `ForwardClassDefinition` | Forward declaration (for cyclic type graphs) |
| `ContainerDefinition` | Process / container (stateful runtime entity). `Name="Process"` is typical; also `Application` |
| `ProcessDefinition` / `EnumDefinition` | Other definition kinds |
| `OperationCallFlag` | This Node is a **call** to an operation (primary usage marker) |
| `NodeFlag` | Marks the node as a generic callable — often appears alongside other flags |
| `ProcessAppFlag` | Marks a process-application call |
| `RegionFlag` | Marker that node is a region (control flow — If, ForEach, etc.) |
| `StatefulRegion` | Stateful region variant (most common for user control-flow) |
| `ApplicationStatefulRegion` / `ApplicationRegion` / `ProcessStatefulRegion` | Variants for Application / Process contexts |
| `ApplicationFlag` | Entry-point / outer Application shell marker |
| `TypeFlag` | Bare type reference (`String`, `Integer`, `Boolean`, etc.) |

Any Choice whose Kind **ends with `Definition`** marks this Node as a definition site — this is the canonical check:

```python
def _is_definition_kind(k: str | None) -> bool:
    return bool(k) and k.endswith("Definition")
```

#### `<CategoryReference>` Kinds

| Kind | Meaning |
|---|---|
| `RecordType` / `ClassType` | The call targets an operation on this record/class (used together with `OperationCallFlag`) |
| `TypeFlag` | Reference to a primitive or type flag |
| `Category` | Namespace/category breadcrumb |

`NeedsToBeDirectParent="true"` on a CategoryReference means the target type must be immediately nested in the listed category — matters only for disambiguating resolution across deep namespaces.

### 6.2 Extracting a node's identity

To get the human-readable name and a resolution key:

```python
choice_name = None           # first semantic Choice Name
call_op = None               # OperationCallFlag / ProcessAppFlag Name
call_type = None             # bare type reference (RecordType/ClassType/TypeFlag)
call_owner = None            # owning record/class (RecordType/ClassType CategoryReference)

for choice in ref.findall("Choice"):
    k = choice.get("Kind")
    if k in ("OperationCallFlag","ProcessAppFlag",
             "ApplicationStatefulRegion","ApplicationRegion","ProcessStatefulRegion"):
        choice_name = choice_name or choice.get("Name")
    if k in ("OperationCallFlag","ProcessAppFlag"):
        call_op = call_op or choice.get("Name")

for cat in ref.findall("CategoryReference"):
    ck = cat.get("Kind")
    if ck in ("RecordType","ClassType"):
        call_owner = call_owner or cat.get("Name")
    if ck in ("RecordType","ClassType","TypeFlag"):
        call_type = call_type or cat.get("Name")
```

Then `node_name = Name attr or choice_name or call_type or "(unnamed)"`. The literal string `"(unnamed)"` appears in extracted data — filter it when displaying.

---

## 7. Two serialisations of member operations (critical)

This is the trap that cost us 38% of definitions before we caught it.

vvvv serialises operations that belong to a Record/Class in **two different forms**. Both exist in the same file. Any extractor that wants the full picture must handle both:

### Form A — Node-wrapped (the "classic" form)

```xml
<Node Name="Split" Id="...">
  <p:NodeReference>
    <Choice Kind="OperationDefinition" Name="Operation"/>
  </p:NodeReference>
  <Patch Id="...">...body...</Patch>
</Node>
```

Detected by: a `<Node>` with a `<Choice Kind="OperationDefinition"/>`. This is the form most tools look for.

### Form B — Patch-as-operation

```xml
<Node Name="AllParameters" Id="...">
  <p:NodeReference>
    <Choice Kind="RecordDefinition" Name="Record"/>
  </p:NodeReference>
  <Patch Id="...">  <!-- record body -->
    <Canvas>...</Canvas>
    <Patch Id="..." Name="SetDropdownByName">...body of the operation...</Patch>
    <Patch Id="..." Name="Split">...</Patch>
    <Patch Id="..." Name="Create">...</Patch>     <!-- lifecycle — skip -->
    <Patch Id="..." Name="Update">...</Patch>     <!-- lifecycle — skip -->
  </Patch>
</Node>
```

Detected by: a named `<Patch>` that is a **direct child of another `<Patch>`** (not inside a `<Node>` or `<Canvas>`), whose `Name` is not in the lifecycle set `{Create, Update, Dispose, Then, Else}`. Walk it as if it were `<Node Name="X"><Choice Kind="OperationDefinition"/></Node>`.

### Detection & handling

In a walker, at every `<Patch>`, scan its direct `<Patch>` children:

```python
for child in patch.findall("Patch"):
    if child.get("Id") and child.get("Name") and child.get("Name") not in _LIFECYCLE_NAMES:
        # Treat as operation definition; attribute to the owning record via the parent context
```

Miss this and you miss a large fraction of record/class members (names like `SetDropdownByName`, `SetMinMaxByName`, `Split` are commonly serialised this way).

**Observed impact on a large real-world file**: form A alone yielded 298 definitions; adding form B yielded 762 — a ~40% coverage gap. Any tool that only looks for form A will be silently wrong about what a record contains.

---

## 8. `<Pin>` and `<Link>` — wiring

### Pins

```xml
<Pin Id="NFGxNUerEiuQUUPrwmAfEJ" Name="Input" Kind="InputPin"/>
<Pin Id="PoGE9Tp06OoL9HxMEOSC0h" Name="Output" Kind="OutputPin" IsHidden="true"/>
<Pin Id="..." Name="Input" Kind="StateInputPin"/>
<Pin Id="..." Name="Output" Kind="StateOutputPin"/>
```

The `Kind` attribute encodes direction and stateful-ness in one string:

- `InputPin` / `OutputPin` — stateless flow.
- `StateInputPin` / `StateOutputPin` — stateful (the value persists / accumulates across frames).
- `ConfigurationInputPin` — compile-time config (common on regions).

Derive direction by substring test:

```python
direction = "in" if "Input" in kind else "out" if "Output" in kind else "unknown"
state = "State" in kind
```

`IsHidden="true"` — pin not shown on the canvas (saves space when patches are compact).

Pins live in **two locations**:

1. **Inside a `<Node>`** — that node's ports.
2. **Direct children of a `<Patch>`** — the patch's **interface** pins, which appear as the outer surface when the patch is embedded into a parent via a Node call.

Both conventions are used; walkers must handle both.

### Links

```xml
<Link Id="..." Ids="outPinId,inPinId"/>
<Link Id="..." Ids="...,..." IsHidden="true"/>
```

The `Ids` attribute is **comma-joined** (not space-joined, not dash-joined). Split once on the first comma. The order is `from,to` — source pin first, destination pin second. Hidden links (`IsHidden="true"`) exist when the user has routed wires through hidden channels (typically record/dict value plumbing).

Links appear either inside `<Canvas>` or as direct `<Patch>` children — older serialisations vary. Scan both.

To resolve a link's endpoints to nodes, build a `pinId → (nodeId, direction)` index when loading the patch, then look up both endpoints.

---

## 9. `<Pad>` — IOBoxes / literals

```xml
<Pad Id="..." Bounds="226,76,310,15" ShowValueBox="true" isIOBox="true"
     Value="Tx,Ty,Tz,Rx,Ry,Rz">
  <p:TypeAnnotation LastCategoryFullName="Primitive" LastDependency="VL.CoreLib.vl">
    <Choice Kind="TypeFlag" Name="String"/>
    <CategoryReference Kind="Category" Name="Primitive"/>
  </p:TypeAnnotation>
</Pad>
```

Pads carry a `<p:TypeAnnotation>` (not `<p:NodeReference>`). The type is derived from the `<Choice Kind="TypeFlag" Name="...">` child. `Value` holds the literal.

`SlotId` links the pad to a shared slot elsewhere in the patch (variable-like behaviour — multiple pads referencing the same SlotId are different display sites for the same underlying value).

`ShowValueBox` / `isIOBox` — cosmetic flags controlling editor display.

---

## 10. Lifecycle patches and `<ProcessDefinition>`

Stateful definitions (`RecordDefinition`, `ClassDefinition`, `ContainerDefinition`) carry up to three lifecycle sub-patches:

- `Create` — runs once on instantiation.
- `Update` — runs every frame (or every invocation, depending on context).
- `Dispose` — runs on teardown.

They appear as named `<Patch>` children *inside* the definition's body Patch:

```xml
<Patch Id="...body...">
  <Canvas>...</Canvas>
  <Patch Id="..." Name="Create">...</Patch>
  <Patch Id="..." Name="Update">...</Patch>
  <Patch Id="..." Name="Dispose">...</Patch>
</Patch>
```

Two additional names (`Then`, `Else`) are used by If-regions for the two branches and must also be treated as lifecycle (skip when detecting member operations in form B).

**`<ProcessDefinition>` / `<Fragment>`**: an alternative serialisation where lifecycle slots are named by cross-reference:

```xml
<ProcessDefinition Id="..." IsHidden="true">
  <Fragment Id="..." Patch="JnNM4unjMe2M24Gl3ZYrwd" Enabled="true"/>
  ...
</ProcessDefinition>
```

The `Patch` attribute on each `<Fragment>` is the **`Id` of a sibling `<Patch>`** that holds the body. To detect lifecycle flags: iterate fragments, resolve their `Patch` attribute against the surrounding `<Patch>` tree, and check the named Patch's `Name` against the lifecycle set.

Large real-world files use this form heavily — 12+ fragments per `ProcessDefinition` is not unusual.

---

## 11. The `Application` entry point

The runtime entry point of a `.vl` file — what vvvv actually executes when you press play — is a **direct child `<Node>` of the top-level `<Patch>`, AFTER the `<Canvas>`, with `<Choice Kind="ContainerDefinition" Name="Process">` and the Node `Name="Application"`**.

Its **inner `<Patch>`** is the runtime root — the entry you want to start rendering from when producing an architecture view. This is distinct from the outer Canvas (which holds *definitions*, the "library" face of the file).

Detection:

```python
root_patch_record = patches[root_patch_id]
for node in root_patch_record["nodes"]:
    if node["kind"] == "ContainerDefinition" and node["displayName"] == "Application":
        app_inner_patch_id = node["innerPatchIds"][0]
        break
```

If no Application node is present (library-only files), fall back to the outer root patch — it holds definitions that can still be browsed.

**Why it's easy to miss**: naive walkers that only descend into `<Canvas>` will never see the Application node, because it sits *outside* the Canvas as a direct child of the outer `<Patch>`. Our walker has both the Canvas and the Patch itself in its source list.

---

## 12. Origin classification — the definition gotcha

Classifying where a node "comes from" from `LastDependency` is mostly trivial:

```python
if dep == "VL.CoreLib.vl": origin = "core"
elif dep == "Builtin":     origin = "builtin"
elif dep == filename:      origin = "local"
elif dep.endswith(".vl"):  origin = "external"
```

**Trap**: this is wrong for definition nodes. A `<Node>` with `<Choice Kind="RecordDefinition"/>` carries `LastDependency="Builtin"` — because vvvv instantiates the *definition form itself* (the act of declaring a record) from its Builtin templates. The `Builtin` here refers to the *meta-kind*, not to a library the declared record depends on.

Result of naïve classification: every Record in the user's own file is tagged `origin=builtin`. Structure view would then filter them out as VL stdlib noise.

**Fix**: any Choice `Kind` ending in `Definition` forces `origin=local`, regardless of `LastDependency`:

```python
def _classify_origin(dep, filename, kind):
    if kind and kind.endswith("Definition"):
        return "local"
    # ... then the normal rules
```

---

## 13. Regions — operational vs annotational

Nodes marked with one of these Choice Kinds are **regions** (control-flow constructs):

- `StatefulRegion`, `ApplicationStatefulRegion`, `ProcessStatefulRegion`
- `ApplicationRegion`, `RegionFlag`

Names you see in practice: `If`, `ForEach`, `Switch`, `Repeat`, `Accumulator`, `Cache`, `Do`, `ManageProcess`.

A region's `innerPatchIds` array can hold **multiple patches** — an If has two (Then, Else), a Switch can have N. When building a semantic-children view, you typically want to **dissolve** regions: iterate all their inner patches and surface the contained nodes at the enclosing scope, so `Splash → If → Integrity` reads as `Splash → Integrity` without the ceremony of the control-flow node.

**Exception — `Comment` regions**: vvvv emits documentation-only regions as `<Choice Kind="StatefulRegion" Name="Comment"/>` — identical XML signature to an operational region. These are purely annotational; their bodies contain notes and illustrative dummy nodes that must **not** surface as real call-graph children. A real observed case: a documentation Comment region sitting inside an Application patch contained a handful of example nodes that, if dissolved, would appear in the call graph as legitimate siblings of the Application's actual children — complete nonsense.

Distinguish by `Name`, not by `Kind`. Maintain an annotational-names set and skip those regions entirely during dissolution:

```python
ANNOTATIONAL_REGION_NAMES = {"Comment"}
```

Extend as new docs-only region types surface.

---

## 14. The semantic tree vs the XML tree — the #1 conceptual gotcha

**The XML nesting does not match what a user thinks of as the call chain.**

In vvvv, all top-level definitions — the Application node, every Record, every top-level Operation — live as **siblings** directly under the document's outer `<Canvas>`. What the user experiences as `Application → MainPatch → Rendering` is a chain of `<p:NodeReference>` *calls*, each resolving to one of those sibling definitions. It is **not** XML parent-child.

Concretely: walking `parentPatchId` / `parentNodeId` from a deeply nested call node takes you up through its enclosing definition's body patch, then to the Canvas, then to the document root — you skip straight past any intermediate definition you thought was "on the path". That path only exists via resolution.

Consequence for any tool that wants to show "the tree a user recognises":

1. During scanning, build two indexes over the patches:
   - `defs_by_name: {name → {nodeId, innerPatchId, ...}}` — top-level definitions.
   - `defs_by_member: {"Owner::Member" → {...}}` — member ops on records/classes.
2. For each non-definition node (anything that is a call), derive `(call_owner, call_op, call_type)` from its `<p:NodeReference>` (§ 6.2) and resolve it to a definition entry using a fallback ladder:
   - `owner+op` → `defs_by_member["Owner::Op"]`
   - `op` alone → `defs_by_name[op]`
   - `type` alone → `defs_by_name[type]`
   - `owner` alone → `defs_by_name[owner]`
3. Write the resolved `nodeId` and `innerPatchId` back onto the call node as `resolvedDefinitionId` / `resolvedInnerPatchId`.
4. When descending "semantically", follow `resolvedInnerPatchId` instead of `innerPatchIds[0]`.

Do this as a single document-wide post-pass at scan time so downstream consumers (viewers, analyses) can traverse without re-deriving resolution.

**Cross-file resolution** (e.g. `Shared.vl::Integrity` called from a sibling `.vl`) is a second, larger problem — it needs a scan-wide index keyed by `(file, name)`. A useful intermediate: synthesise a reference-target string like `"<dependency>::<owner>::<name>"` on each call node, so an external consumer can join against a global definitions index when it exists; actually chasing the link still requires all files to be loaded together at query time.

---

## 15. Naming quirks

### `(Internal)` suffix

vvvv appends `(Internal)` to a node's display name to mark it as hidden/internal — common on private helpers and lifecycle-bearing definitions (`MainPatch (Internal)`, `Splash (Internal)`). The suffix is cosmetic; strip it for display:

```python
_INTERNAL_SUFFIX_RE = re.compile(r"\s*\(Internal\)\s*$")
_INTERNAL_SUFFIX_RE.sub("", name or "").strip()
```

Mark the original-vs-stripped difference on the node (`isInternal=True`) so UIs can badge them.

### `(unnamed)`

When a `<Node>` has no `Name` attribute, extractors often substitute the literal string `"(unnamed)"`. This is a convention (not emitted by vvvv) but propagates into JSON outputs. Filter it when building user-facing lists:

```python
if not label or label == "(unnamed)":
    hide = True
```

### Lifecycle + suffix interaction

`MainPatch (Internal)` is both internal AND hosts lifecycle fragments. Strip the suffix; keep the `isInternal` flag; treat it as a regular definition for structural purposes.

---

## 16. `LastCategoryFullName` as a disambiguation hint

Call-site `<p:NodeReference>` carries two breadcrumb attributes that are the **hinge for cross-file resolution when names collide**:

- `LastCategoryFullName="MyProject.Settings"` — the last dotted segment (`Settings`) is the owning record → `targetMemberOf`.
- `LastDependency="MyProject.vl"` — the file the target lives in → `targetFileHint`.

A three-factor resolution ladder works well in practice:

- `(name, memberOf, fileHint)` match → **EXTRACTED** (full confidence).
- `(name, memberOf)` or `(name, fileHint)` match → **EXTRACTED** (partial but decisive).
- `(name)` single candidate → **INFERRED**.
- `(name)` multi-candidate → **AMBIGUOUS**; attach the candidate list so the user (or a later pass) can disambiguate.

Without these hints, a project with many `Create` operations (every record has one) is a resolution nightmare. With them, it collapses to near-deterministic.

---

## 17. Visual classification (SVG exports)

When vvvv exports a patch as SVG, `<text>` elements follow a consistent size/colour convention:

| Role | font-size (pt) | fill |
|---|---|---|
| `title` | 19–32 | any (typically `#555` or `#DCDCDC`) |
| `comment` | 11–13 | `#DCDCDC` |
| `nodeName` | 8.5–10 | `#DCDCDC` / `#FFF` / `white` |
| `pinLabel` | 6.5–8 | `#999` / `#888` / `#AAA` |

Two-line node labels (operation on a record) render as **two stacked `<text>` elements sharing an identical translation matrix**, differing only in `y`:

```
SetDropdownByName        9.33pt #DCDCDC  y=11.97  ← nodeName
AllParameters            7.33pt #999     y=20.94  ← qualifier
```

Both elements carry `transform="matrix(0.693 0 0 0.693 2236.44 849.427)"` (identical `(tx, ty)`). To pair them: group text entries by rounded translation; within each group, a nodeName with a smaller `y` and a pinLabel with a larger `y` is a (label, qualifier) pair. The qualifier reclassifies from "pinLabel" to "qualifier" and is what disambiguates a call-site name.

This is what makes `SetDropdownByName` + qualifier `AllParameters` resolve to exactly one definition.

---

## 18. Dependency elements (file-level)

Direct children of `<Document>`, interleaved with `<Patch>`:

```xml
<DocumentDependency Id="..." Location="./MyProject_UI.vl"/>
<NugetDependency    Id="..." Location="VL.CoreLib" Version="2023.5.3-..."/>
<PlatformDependency Id="..." Location="System.Threading.Tasks.Parallel"/>
```

- `DocumentDependency.Location` — always a relative POSIX path, typically `./Sibling.vl`. Normalise by joining with the document's directory and resolving.
- `NugetDependency.Location` — NuGet package name (no path, no filename).
- `PlatformDependency.Location` — platform DLL name (e.g. `mscorlib`, `System.Reflection`).

These elements cluster near the start AND end of the file. vvvv rewrites them on every save. If you only need file-level deps, tail-scan the last ~400 lines.

A real `.vl` may also carry NuGet deps that are **transitively** used but not directly imported — vvvv serialises the full closure. Don't treat this as a bug.

---

## 19. Pipeline-shaped takeaways

Different questions about a `.vl` file want different parsing strategies. A useful split:

| Question | Strategy | Sections |
|---|---|---|
| **File-level dependencies** — what other `.vl` / NuGet / platform DLLs does this file pull in? | Tail regex of `.vl` (+ `.csproj` for C# siblings) | § 3.3, § 18 |
| **Definition graph** — what does this file *declare*, and what does each declaration *use*? | Full XML walk; emit nodes for definitions, edges for call-sites | § 6, § 7, § 12, § 16 |
| **Composition tree** — for a given entry, what runs, and what does it call in turn? | Full XML walk + post-pass call resolution | § 4, § 5, § 6, § 11, § 13, § 14 |
| **Visual evidence** — what does the on-canvas text of a patch say? | SVG `<text>` classification by font-size / fill | § 17 |

A minimum-viable composition-tree parser is a few hundred lines of straightforward stdlib code in any language with an XML parser. The conceptual bulk is in the classification rules (§ 6, § 12, § 13) and the resolution post-pass (§ 14), not in the XML walking itself.

---

## 20. What NOT to do

- Don't trust XML parent/child as the call chain (§ 14).
- Don't only look inside `<Canvas>` — the Application entry and member-op Patches live as Patch-direct children (§ 5, § 11, § 7).
- Don't assume `LastDependency` alone classifies origin — definitions always read `Builtin` (§ 12).
- Don't treat `Name="Comment"` regions as operational — they are docs (§ 13).
- Don't forget to handle the backslash-closer bug (§ 3.1) — ET will refuse to parse ~1 in 50 files otherwise.
- Don't split `Link.Ids` on whitespace — it's a comma-join (§ 8).
- Don't assume every member operation has a `<Node>` wrapper — form B (§ 7) accounts for ~40% of members on records.
- Don't collapse `(Internal)` nodes out of sight — they *are* the stateful runtime definitions the user cares about; just strip the suffix (§ 15).

---

## 21. Minimum-viable parser recipe

If you're implementing from scratch, the shortest path to a working tool is:

1. Parse with ElementTree after the backslash-closer repair.
2. Build a `{Id: element}` index of every `<Patch>` and `<Node>` by walking the whole tree once.
3. Find the document root patch (direct child of `<Document>`).
4. Depth-first walk from the root, at each `<Patch>`:
   - Collect nodes (inside Canvas + direct children of Patch).
   - Collect pads, links, interface pins.
   - Recurse into each Node's inner `<Patch>` children.
   - Recurse into named, non-lifecycle direct-child `<Patch>` elements (form B).
5. Classify each node via `<p:NodeReference>` → kind, origin, is-region, is-definition.
6. Detect the `Application` Node among the root patch's nodes; record its inner patch id as the runtime entry.
7. Post-pass: build `defs_by_name` + `defs_by_member`, then for each non-definition node resolve its call and write `resolvedDefinitionId` / `resolvedInnerPatchId`.
8. Export JSON. Done.

Add dependency-tail scanning (§ 18) for a file-level view. Add SVG classification (§ 17) if you want to link textual scans to visual evidence.

