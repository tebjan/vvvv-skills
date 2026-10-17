# Persisting runtime state through Create pins

A Create pin can hold the document's durable initial value for a running node.
The constructor restores that value. When something changes the corresponding
runtime state, the node can write the new value back to its own Create pin through
the document model. Normal document Save then preserves it for the next Create.
This is communication from the running application back to the authored patch,
independent of ordinary dataflow through links.

```text
saved Create-pin value -> constructor -> live state
          ^                                 |
          +--------- deliberate writeback <-+ change
```

The source of a change is independent of this mechanism. Moving or resizing a
window, manipulating a transform handle, capturing device calibration, an external
interaction, and editing a model in a custom UI can all produce state that belongs
with the patch. A settings dialog is one example; an editor UI is not required.

## Choose the persistent value

Store the state needed to recreate the intended behavior. Temporary resources,
per-frame outputs, caches and measurements need not become document state just
because they change at runtime. Define which changes should update the saved value.

Use the actual pin type when VL supports saving it: numbers, Booleans, vectors,
rectangles, matrices and other supported value types do not need conversion to
strings. A serialized String is useful for a structured object or versioned
snapshot, but neither strings nor JSON define this pattern. Keep native handles
and live service references out of the saved representation.

The usual lifecycle is:

1. Declare the persistent value on Create and restore it in the constructor.
2. Apply a relevant runtime change immediately to the live instance.
3. Write its updated durable value to the owning Create pin through the solution API.
4. Normal Save writes the document; the next constructor restores the latest saved value.

## Write to the owning pin

The essential API call is type-independent. This schematic helper assumes
`_nodeContext` was supplied to the constructor; call it for a relevant state change,
passing the exact Create-pin label and its supported value type:

```csharp
using VL.Lang.PublicAPI;
using VL.Model;

void StorePinValue<T>(string pinName, T value)
{
    var session = _nodeContext.AppHost.Services
        .GetService(typeof(IDevSession)) as IDevSession;
    var ownerStack = _nodeContext.Path.Stack;
    if (session == null || ownerStack.IsEmpty) return;

    session.CurrentSolution
        .SetPinValue(ownerStack, pinName, value)
        .Confirm(SolutionUpdateKind.DontCompile);
}
```

For example, `StorePinValue("Bounds", bounds)` preserves the rectangle directly;
`StorePinValue("Transform", transform)` can preserve a supported matrix value.
For a complex model, a String pin might instead receive a serialized snapshot.
Visibility is a separate decision: choose Visible, Optional or Hidden for the
saved Create pin and verify the imported node. A default argument does not hide it.

The path must identify the placed node whose pin owns the value. A direct C#
ProcessNode uses its full `NodeContext.Path.Stack`. If the C# instance is inside a
VL wrapper and the wrapper's Create pin owns the value, resolve that wrapper's
path instead. Do not copy a stack-pop operation without checking the owner.
Use the imported VL label, not the C# field name; parameter camelCase splitting
and an explicit `[Pin(Name = ...)]` affect that label.

`SetPinValue` returns a new solution; `Confirm` applies the document change.
`DontCompile` is the established choice for a saved initial value whose change
has already been applied to the live instance. It avoids restarting that instance;
it does not apply arbitrary runtime changes, save to disk, or replace a necessary
compilation. Other kinds of document edits may need another update mode.

## Ownership, lifetime and verification

- Resolve the real owner before writing. A connected input may get its value from
  another node; define whether edits are read-only, local overrides or explicit
  upstream writeback. The read-only Settings-dialog contract is one application,
  not a universal restriction on this mechanism.
- If multiple runtime instances share one physical Create pin, preserve their
  states together under appropriate stable instance keys. One write must not
  discard sibling state. This may require a collection or serialized snapshot.
- Commit relevant changes, using change detection or coalescing for frequent
  events. Do not turn every frame into a document edit. Order asynchronous writes
  so an old completion cannot replace newer state.
- Retain live state when writeback fails and report the failure as appropriate.
  Serialized snapshots also need safe defaults, schema migration and parse-error
  handling. Those concerns do not require every scalar pin to use a serializer.
- Follow the pinned VL version's editor-thread requirements. A change may come
  from any subsystem; that does not make solution edits safe on arbitrary threads.
- Exported apps can restore the saved initial value without an editor session.
  Persisting subsequent changes in an export requires a separate storage policy.
- Verify the actual change source, live result, correct pin value, Dispose/Create,
  and document Save/reopen. Do not equate a serializer test with editor writeback.
  Define synchronization with document Undo/Redo if that interaction is supported.

Window bounds and VL.OCIO's serialized color-grading state demonstrate the same
Create-pin pattern with different value representations and change sources.
