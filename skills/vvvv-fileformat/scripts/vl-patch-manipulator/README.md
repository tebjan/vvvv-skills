# Persistent vvvv patch tools

`vl-patch-manipulator` is a reusable, loss-preserving engine and local MCP
server for vvvv gamma `.vl` files. An agent opens a patch once, keeps its XML,
graph indexes, aliases, catalog and spatial model hot, performs a typed batch of
edits, validates, and saves atomically. It does not need to write Python or
exchange raw XML for every edit.

Use the established `HowTo`, `Explanation`, `Example`, `Reference` and `Tutorial`
help roles intentionally. Keep the filename prefix and Help.xml topic aligned
with the purpose users see in the Help Browser.

The implementation is independent of KopfFarben / digitalwannabe's vvvv MCP
research repository; its dual-licensed parser, writer and services are not copied
or vendored. No private graphics-engine checkout or catalog is required.

## Agent surface

The complete Python project is bundled under the `vvvv-fileformat` skill's
`scripts/` directory. Run the persistent stdio server from this directory:

```powershell
uv sync --extra server --group test
uv run --extra server vlpatch-server
```

Pass an optional analyzer catalog with `--catalog <catalog.json>` when one is
available. The tool never assumes a workstation-specific checkout path. The same
command is exposed by `.codex-plugin/plugin.json` and the example `.mcp.json`.
Configure the client working directory as this tool directory, or use
`uv --directory <absolute-tool-directory> run --extra server vlpatch-server`.
The example `cwd="."` is relative to the configured client/plugin working
directory; it is not a universal installed path. The server owns sessions until the
process exits. Its compact MCP contract is:

- `vl_open(path, handle?, catalog_path?)` — open/reuse and return a handle,
  revision and tiny overview.
- `vl_capabilities(operations?)` — discover exact semantic operation arguments,
  defaults, aliases and donor-reference formats from the Python signatures.
- `vl_canvases(handle)` — discover Process canvases, owning Patch IDs, signature
  endpoints and Slots for scoped edits and previews.
- `vl_view(handle, level?, focus?, region?, canvas?)` — describe exact operations, pins,
  dependencies and dataflow without dumping the whole XML. `level="spatial"`
  returns a token-compact whole-canvas map, exact element bounds, visible pin
  anchors, intentional width expansion, links, free bands and layout defects.
  `level="layout"` reports the exact movable/protected sets and connected
  movable components before any coordinates change.
- `vl_catalog(query, handle?, category?, exact?, limit?)` — search or exact
  lookup. Adding an unresolved node is refused rather than guessed.
- `vl_edit(handle, operations, expected_revision?)` — one atomic typed batch.
  All public semantic mutations are registered, including `add_process`,
  `add_slot`, `add_slot_read`, `add_input_placement`, `add_matrix_repeat_builder`,
  `move_subgraph`, `set_node_reference` and `set_placement_position`, alongside
  basic node/link/annotation/layout edits. Use discovery rather than guessing
  arguments. Every
  edit response includes the moved-node set plus before/after overlap,
  upward-flow, exact pin-offset, long-link and crossing metrics. `connect` is a
  graph dataflow link; `add_link_annotation` creates the visible clickable URL
  IOBox used by real help patches.
- `vl_check(handle, compile?, canvas?)` — structural diagnostics and, when a bridge
  provider is configured, separate live-vvvv diagnostics, plus exact spatial
  diagnostics including the two crossing links for every crossing.
- `vl_preview(handle, path?, canvas?)` — render the live model as a BOM-free SVG. With
  no path it writes to the system temp directory, never beside the patch.
- `vl_changes(handle, since_revision?, wait_ms?)` — compact bounded long-poll
  feed for tool and external-file changes.
- `vl_save(handle, expected_revision?, path?)` — validated atomic save;
  this writes a file and does not imply live vvvv compilation or reload.
- `vl_sessions()` / `vl_close(handle, discard?)` — inspect/release tool sessions.
  Unsaved edits prevent close unless explicitly discarded; neither closes vvvv.

Python `session.edit_batch`, MCP `vl_edit` and CLI `vlpatch edit` use one operation
dispatcher. Builders return JSON objects with persistent IDs. Set `"as": "demo"`
on an operation and reuse `"$demo.body"` / `"$demo.inputs.Value"` later in the same
batch; `$$` escapes a literal leading dollar sign. Use returned IDs across calls,
not aliases whose assignment can change after reopening. Scoped tools accept a
Canvas, owning Patch or Process definition ID. A scoped `vl_view` returns that
canvas's spatial snapshot; structural checks still validate the entire document.
Type/reference properties are copied from verified donor element IDs or
`{"path":"donor.vl","id":"..."}`, never guessed overload XML. An existing MCP
process needs restart/reconnection after a tool update.

The CLI exposes the same editing, discovery and scoped inspection surface:

```powershell
uv run vlpatch capabilities add_process add_slot add_input_placement
uv run vlpatch canvases scene.vl
uv run vlpatch edit scene.vl --operations edits.json
uv run vlpatch view scene.vl --canvas CANVAS_ID
uv run vlpatch preview scene.vl --canvas CANVAS_ID --output preview.svg
```

`edits.json` is the same operation array accepted by `vl_edit`. Existing legacy
CLI commands remain compatible; no second XML authoring engine is introduced.

Spatial pin geometry follows vvvv's editor implementation rather than a generic
graph-layout convention. Visible pins retain declaration/XML order. A single pin
starts at the left edge; two or more 5-pixel pins stretch across the complete
effective node width with `(width - 5) / (count - 1)`. Hidden pins do not consume
space. Node width expands to fit the label and the larger visible pin bar before
anchors, crossings, overlaps, or previews are calculated.

Every session has a monotonic revision. Mutations can require
`expected_revision`; stale writes fail locally. A polling watcher debounces
external files, retains the last valid model during transient invalid writes,
reports conflicts when unsaved in-memory edits meet external edits, and never
blindly overwrites another writer.

Layout is incremental and human-preserving. Every node and IOBox already
present at `vl_open` is a protected baseline. A successful save or external
reload promotes the current geometry to the next protected baseline. The default `layout` and
`layout_value_pads` operations move only entities created in that live session;
an externally edited/reloaded document establishes a fresh baseline. Supply an
exact `targets` list for a deliberate local reflow. Whole-patch layout requires
`force=true`. Use `translate_group` when space is needed around an established
subgraph: all selected entities move by one `(dx, dy)` delta, so their internal
spacing, alignment and deliberately stretched widths remain unchanged.

Regions communicate semantic ownership; they are not decorative canvas frames.
When one patch compares several technologies, give each technology one compact
region around only its own subgraph. Keep shared setup, scene, lighting and render
spines outside those regions. A single-concept patch needs a clear explanation,
not a region around the entire graph. Prefer staggered vertical placement and a
slightly diagonal link over a straight link that forces nodes or groups to overlap.
Within each semantic group, align movable one-to-one source outputs to the exact
destination input-pin anchor. Reserve diagonals for genuine fan-out, collection-slot
spacing, cross-group dependencies, or cases where exact alignment would overlap a
protected human-authored subgraph. Validate this as pin-anchor geometry, not node-centre
geometry.

## Python API

The MCP layer is an adapter; `PatchSession` is the primary reusable class API:

```python
from vl_patch_manipulator import PatchSession

session = PatchSession.load("scene.vl")
print(session.describe(level="summary"))
with session.transaction():
    session.add_annotation("heading", text="Scene inputs", x=60, y=40)
    session.add_annotation("comment", text="Multiline\nexplanation", x=60, y=90)
    session.layout()
session.save()
```

The class API keeps exact 22-character base62 IDs underneath stable session
aliases (`n1`, `p1`, `r1`). It indexes endpoint ownership and adjacency, supports
focused subgraphs, layout/align/distribute, safe clone/remap, undo/redo and
incremental validation. Unknown XML content remains in the lxml tree.

## Visible help annotations

The format is evidence-based from 285 resolved package help patches. Proven
canvas forms are:

- `Comment`: a String `Pad`/IOBox with `p:ValueBoxSettings/p:stringtype` set to
  `Comment`; multiline text is stored in the Pad `Value`.
- `Heading`: the same Comment Pad with the corpus convention of a larger
  `p:fontsize` (the helper defaults to 15 instead of the normal 9).
- `Link`: a String Pad with `stringtype=Link` and a URL in `Value`.
- `Region`: an `Overlay` with `Name` and `Bounds`.

XML comments are preserved independently and are not presented as visible help
text. No unsupported annotation representation is invented.

## Guarantees and limits

- XML is parsed before mutation and written only after validation; writes use a
  same-directory temporary file, `fsync`, and atomic `os.replace`.
- Failed batches restore XML, graph indexes, aliases and undo history together.
  Undo/redo are standalone batches; local helper catalogs refresh after edits,
  rollback and reload.
- Serialization is deterministic, UTF-8 and BOM-free. Python text writers use
  `encoding="utf-8"`, never `utf-8-sig`; tests scan generated bytes.
- Validation covers root/version/namespaces, direct Document dependencies,
  duplicate/invalid IDs, link endpoint existence and direction, fragment refs,
  canonical namespaced comment settings, visible annotation round-trips and
  operational orphans.
- The offline catalog adapter reads the analyzer JSON shape emitted by
  KopfFarben's research project. A future live catalog/bridge can implement the
  same provider interface. Structural validity is not a substitute for vvvv
  compilation or GPU/runtime validation.
- The initial live-vvvv provider is a clearly marked file-only boundary. It does
  not pretend that static XML can prove package loading, pin type inference or
  runtime rendering.

## Tests and benchmark

```powershell
uv run --extra server pytest -q
uv run python -m vl_patch_manipulator.benchmark
```

Tests cover unknown-content round-trip, ID remapping, annotation creation,
server batch edits, revision conflicts, external-file notifications,
undo/redo, atomic save and BOM rejection. The benchmark reports open,
description, add/connect/validate and notification latency for a representative
fixture without respawning Python or reparsing between operations.

`tests/test_surface_parity.py` guards operation/signature coverage, exercises the
actual MCP protocol in-process, CLI parity, named builder IDs, scoped geometry,
donor rebinding, typed loop construction, rollback and saved round trips. New
public mutations must extend this contract and pass adapter tests. Static tests
do not establish live vvvv compiler or renderer correctness.
