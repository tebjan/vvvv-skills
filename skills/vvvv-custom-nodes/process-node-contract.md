# ProcessNode update, state and result contract

## Normal node design

Expose one canonical Update on a normal stateful node. Keep implementation helpers
private/internal. Public methods and property accessors are potential fragments
under implicit selection, even when their names do not equal Update. Changing a
helper's name alone does not exclude it. Use explicit fragment selection or
`[Fragment(IsHidden = true)]` when a public member must remain outside the process.
Explicit selection must include the constructor and intended lifecycle members.

A class member operation already has implicit instance/state flow in VL. Returning
this merely to chain the same instance is usually redundant. For a ProcessNode
whose instance must be available to downstream nodes, prefer:

```csharp
[ProcessNode(HasStateOutput = true)]
public sealed class Processor
{
    public void Update(float amount = 1f) { /* update the existing instance */ }
}
```

The instance output is normally Output. If a regular fragment already owns Output,
the state pin becomes State Output. HasStateOutput can also change member visibility
in the node browser; inspect the actual browser surface and retain intentional
visibility metadata. Do not replace an existing state pin with an ordinary out
parameter without considering saved selectors and pin kinds.

Returning this is permitted when the method's actual contract needs that result.
Returning a different object or value is a normal result output. An unannotated
return from an ordinary mutable-class method is generally Result, even when its
implementation returns this. Do not confuse that result with implicit state flow
or the process-level HasStateOutput pin. Immutable definitions and explicit return
pin metadata have different import rules; inspect them rather than applying a ban.

## Failure shape to catch

```csharp
[ProcessNode]
public sealed class BrokenDispatcher
{
    public BrokenDispatcher Update(int groups = 1) => this;
    public BrokenDispatcher UpdateWithElements(int count = 1) => this;
}
```

This illustrates the problematic public surface: two implicit update fragments,
each with an ordinary Result return, both modifying the same node state. Renaming
one return pin may conceal the collision while leaving both update paths exposed.
Preserve the two capabilities through an intentional node contract, such as one
Update with agreed mode semantics or separate nodes, rather than removing a feature.
Do not broaden this into a prohibition on deliberately designed multi-fragment nodes.

The reported package failure is `Sequence contains no elements` from
`PatchCompiler.GenerateObjectCreationOrMethodInvocationStatements` when placing
ComputeDispatcher. In the investigated importer, process outputs are deduplicated
by name; a fragment return can then have no corresponding output at code generation.
The helper name is not an overload selector. Other nodes with the same exception
still require their own fragment/output inspection.

Evidence: [public reproduction and follow-up](https://forum.vvvv.org/t/vl-nvidia-pathtracing-real-time-path-tracing-in-vvvv-gamma/25110/24).
The report covers Bridge 0.7.1/0.7.2 on vvvv 7.3/7.4; placing the published 0.7.2
ComputeDispatcher was also reproduced on preview 8.0-0262. The small class above is
a structural illustration, not a separately executed reproduction. The guidance
correction does not itself fix or prove the package implementation.

## Verification boundary

Review the public imported methods/properties, inherited importable members,
fragment selection, return/out names and state pin kinds together. Verify newly
placed and saved nodes, unconnected/default inputs and each supported mode in the
target vvvv. Static inventory and C# compilation do not prove VL code generation,
evaluation order, saved-patch compatibility or correct rendering.

## Output naming rules

- `[ProcessNode(HasStateOutput = true)]` exposes the class instance as **Output**
  automatically. Do not add a return attribute to name that state pin. If a
  fragment already defines a non-state Output, the instance pin becomes State Output.
- `HasStateOutput` defaults to false. An ordinary unannotated mutable-class `Update()` return
  is a separate **Result**, even if its implementation returns `this`.
- Static operation returns usually become **Result**. Without an explicit return
  pin attribute, the importer can derive **Output** when the first input type
  matches the return type. Inspect the generated surface before overriding it.
- `out` parameters use their parameter names: `out T output` becomes Output.
  For an authored node's main method result, use `[return: Pin(Name = "Output")]`
  only when the generated name would otherwise differ. Secondary outputs keep
  meaningful names such as Texture and Error. Preserve imported/stock names.

These are importer rules (`ProcessUtils.GetOutputs`, `ImportedSymbol.CreateOutputs`),
not an instruction to decorate every instance method. For an instance-state output,
prefer HasStateOutput and a void Update over returning `this` just to expose it.


## Static audit helper

Run the [parser-based audit](process-node-audit.md) across the relevant source
roots to inventory candidate fragments, output collisions and unresolved coverage.
Review findings against the generated node; the scanner does not prove runtime behavior.
