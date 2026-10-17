# Persisting a custom node's editor settings in its `.vl` document

Use this pattern when an editor UI changes settings owned by one placed C# node and
those settings should survive the node's Dispose/constructor cycle. A runtime
field alone resets on code reload. Give the constructor a serialized snapshot
input (for example `string settings = ""`), parse it on Create, and apply later
UI edits to the live instance immediately. On each meaningful edit, write the
new snapshot back to that same Create pin through the editor solution API.

The general shape, verified in a vvvv gamma node implementation, is:

```csharp
public MyNode(NodeContext nodeContext, string settings = "")
{
    _nodeContext = nodeContext;
    _settings = ParseOrDefault(settings);
}

// Called on a user edit, after updating this instance's runtime state.
var session = IDevSession.Current;
if (session != null && !parentStack.IsEmpty)
{
    session.CurrentSolution
        .SetPinValue(parentStack, "Settings", Serialize(_settings))
        .Confirm(SolutionUpdateKind.DontCompile);
}
```

`parentStack` above must identify the *placed node whose Create pin owns the
value*. A direct C# ProcessNode can use its `NodeContext.Path.Stack`. When a
C# instance lives inside a VL wrapper whose Create pin owns the snapshot,
resolve that wrapper's path instead; one verified service pops the inner node
stack once for this reason. Check the actual saved document and reload the
node to establish that the intended pin was updated.

`"Settings"` is the VL pin label derived from the `settings` constructor
parameter, not a C# member name. Use the exact pin name in the imported node;
an explicit `[Pin(Name = ...)]` changes it. The defaulted constructor argument
is optional, but that alone does not hide the pin. If it is an implementation
snapshot, choose pin visibility deliberately and verify the imported UI.

Keep the runtime edit and document edit as separate operations. The runtime
object gives immediate output; `SetPinValue` returns a new `ISolution`, and
`Confirm` commits that edit to the editor's current solution. This marks the
document for normal Save. `DontCompile` avoids a compile
for this edit; it is not a disk save or an automatic restart. Handle a missing
editor session or unresolved owner by retaining the current runtime state and
reporting persistence failure if that matters to the user. Exported apps need
their own explicitly designed persistence route if persistence is required.

Design the snapshot boundary before implementing it:

- Store one owned snapshot per placed node. An external settings source is
  read-only input; never overwrite it to persist edits from this node.
- If one physical Create pin backs multiple runtime instances (for example
  spreading or a loop), aggregate their states under stable instance keys and
  update that shared snapshot without discarding siblings.
- Parse empty, older and malformed payloads safely. Decide how to migrate old
  schemas and preserve a recoverable value on parse or write failure.
- Serialize and call the solution API on changes, with bounded/debounced edits
  when appropriate. Never write the document on every frame.
- If persistence is asynchronous, order writes so an older completion cannot
  replace a newer edit. Verify UI edit, runtime output, Dispose/Create reload,
  document Save/reopen and export behavior separately.

The solution API is an editor operation. Follow the pinned VL version's
`IDevSession`, `ISolution` and threading requirements; the example establishes
the call shape, not a general guarantee that background threads may edit the
solution directly. Use the editor's supported dispatch route where required.
