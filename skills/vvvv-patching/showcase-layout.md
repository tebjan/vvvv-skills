# Readable showcase patches

Use this when creating, polishing or extracting helpers in a visual example.
Preserve the scene's creative values and behavior while making its structure
easier to read. These are composition guidelines, not a fixed template or pin limit.

## Separate the subject from its stage

Keep the feature the user wants to explore in a named hero Process. Shared room,
floor, lights, environment and camera belong to scene setup outside that Process.
Extract a room helper when its construction would distract from the main graph;
keep light nodes and their useful controls visible when users will adjust them.

```text
Hero content       Room          Lights
     |               |             |
     +---------------+-------------+
                  Scene Group
                       |
                    Renderer
                       |
                  Window / output
```

Place peer content left-to-right and its collection below. Keep producer-before-
consumer execution order when a Group is ordered; never reorder dependent GPU
stages merely to remove crossings. Add a separate hero Group only when several
hero peers need collecting. One source does not need an extra Group.

Choose boundaries by responsibility: `CubeStreams`, `StudioRoom`, `StreamShader`
describe recognizable parts. Avoid extracting every node into its own helper or
burying the feature being taught behind generic names such as `Setup` or `Helper1`.
Keep the common render/output spine outside the hero helper.

## Compact a large shader without removing its controls

Wrap the full shader and its owned state resources in a local Process when its
pin rail overwhelms the example. Expose a small front panel there; retain the full
shader and its existing values inside for advanced editing. Do not delete working
shader options or change the global shader factory just to narrow one example.

Keep the compact shader call above the instancer, in the same left-hand lane.
Put shared mesh/material/model construction in a separate lane to the right.
Align Shader -> instancer.Shader vertically; align the model bank with Models.
Forward or visibly display shader errors where edits happen, especially when
KeepLastGood can retain the previous result after a failed compile.

Preserve the state/resource owner and lifetime during extraction. Do not replace
one persistent buffer with a new allocation each frame, duplicate a shared
producer, or introduce a Slot/frame delay just to shorten a wire.

## Choose IOBoxes for exploration

Expose controls whose changes make a noticeable, useful difference to this scene:
main colors, speed, width/scale, seed, flow direction, roughness or a visible layer.
Choose for the user's goal; nine controls in one example is not a universal rule.
Leave secondary tuning and rarely changed values on the full node.

- Put IOBoxes with their consumers, above the destination pins in pin order.
  Stagger heights when labels would overlap; keep vertical wires where possible.
- Use actual public types: color pickers for RGBA, vectors for vector values,
  Float32/Integer32 for ordinary vvvv numeric controls unless the contract requires
  another type. Do not split a vector into unrelated scalar controls.
- Copy effective values into the wrapper defaults and linked IOBoxes. An extraction
  must not change the image because a newly exposed input defaults to zero.
- Label the creative meaning and units, not private implementation identifiers.
  Check live numeric precision: a width of .004 displayed as 0.00 is misleading
  even when the stored value is exact. Use verified editor settings for precision;
  do not invent serialization attributes.
- Allow room for real color/vector displays and labels. Their live width may be
  larger than the stored pad rectangle; inspect the editor before calling it tidy.

For scene lights, color and intensity are often enough on the main canvas. Room
material controls belong with the room. Do not copy every optional pin into an IOBox.

## Align links using the editor's geometry

Work from the consumer upward. Align source and destination **pin anchors**, not
node centers or left edges. Widen nodes only enough to separate useful controls
or align their inputs; preserve a deliberate human-authored width.

For vvvv's five-pixel pin rail, visible pin i has X anchor
`x + 2.5 + i * (effectiveWidth - 5) / (visibleCount - 1)` for two or more pins;
a single pin is at `x + 2.5`. Hidden pins do not occupy the rail. Use the actual
effective width and rounding from the editor/tool, including intrinsic expansion.

Imported nodes retain their real API declaration order. Local Process calls can
be normalized by vvvv according to their input portals' X positions. Plan that
spatial order before creating the call; match its saved pin rail to it and then
align IOBoxes. Never alphabetize pins. A stale saved rail can pass file-only
checks while the live editor draws crossing wires.

Match a Group's actual collection-pin count to its connected peers. Unused trailing
slots change every anchor. Align independent peers with their intended slots;
allow diagonals for genuine fan-out or shared resources. Do not damage a good
cluster, stretch a node across the whole canvas or change execution semantics
solely to reach a zero-crossing score.

## Comments that earn their space

Use short headings naming the subject, such as `Room`, `Warm key` or `Cube streams`.
Comments should explain a non-obvious interaction, a useful gesture, a constraint
or a deliberate creative choice. One or two sentences usually suffice.

Useful examples:

- `Changing the seed restarts the flow.`
- `The lattice is drawn only outside the body.`
- `Hold R to reset the camera.`

Delete comments such as `The linked controls are exposed here`, `Other pins remain
editable` or `Connect the output to the input`. They explain ordinary vvvv behavior
without helping the user decide or act. Do not narrate every wire, repeat pin
names/defaults, or fill the canvas with a settings manual.

Use normal capitalization; keep established acronyms such as GPU. Refer to public
nodes and scene names. Private C# test numbers and inaccessible implementation
files have no place in help annotations, shipped shader comments or instructions.

## Author and verify

Use the skill-owned Python PatchSession/MCP editor. Create local Processes with
typed boundaries; disconnect crossing links before moving a closed selection with
`move_subgraph`, then reconnect through the new portals. Preserve placed node IDs,
creative values, unknown metadata and unrelated human layout. Discover supported
operations instead of writing XML or guessing attributes.

Inspect each Application/helper Canvas separately: their coordinates are independent.
Check overlaps including labels, upward flow, pin-anchor alignment, crossings and
unexpected long wires. Keep structural checks separate from live type inference,
pin ordering, numeric display, shader compilation and rendering verification.

After a live editor save, recheck its canonical pin order and rerun the targeted
alignment if needed. Reapplying a layout helper should not create nodes or drift
geometry. Report any justified diagonal links or remaining display limitation
accurately; do not claim live verification from an XML preview alone.

Before showing a patch, preview and check the exact document variant and Canvas
that will be opened, including internal proof patches. Keep diagnostic IOBoxes
next to the stage they describe; checking a different help document does not
validate the displayed variant.
