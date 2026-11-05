---
name: vvvv-troubleshooting
description: Diagnoses and fixes common vvvv gamma errors in C# nodes, SDSL shaders, and runtime behavior. Use when encountering errors, exceptions, crashes, red nodes, shader compilation failures, missing nodes in the browser, performance issues, or unexpected behavior.
license: CC-BY-SA-4.0
compatibility: Designed for coding AI agents assisting with vvvv gamma development
metadata:
  author: Tebjan Halm
  version: "1.1"
---

# vvvv gamma Troubleshooting

## C# / ProcessNode Issues

### Sequence contains no elements when placing a ProcessNode

If the stack names `PatchCompiler.GenerateObjectCreationOrMethodInvocationStatements`,
inspect the imported process/fragment outputs before investigating shader dispatch.
The exception alone does not establish the cause for every affected node.

- Under default implicit selection, public instance helpers such as
  `UpdateWithElements` become additional fragments. Audit properties and inherited
  imported members too, not just methods named exactly Update.
- Two unannotated mutable-class methods returning this normally create competing
  Result outputs. Process output deduplication can leave a fragment return without
  its corresponding generated pin. Check actual fragment/output ownership.
- For a normal ProcessNode, keep one canonical Update; use HasStateOutput with a
  void Update when the output is the instance. Ordinary instance operations already
  carry state flow. Keep valid method results and intentional multi-fragment APIs.
- Exclude implementation helpers deliberately. Preserve alternate capabilities
  through the agreed node design. Merely renaming Result or hiding a pin does not
  fix two competing update paths.
- Verify actual node placement and wiring in the target vvvv, including saved-patch
  pin-kind compatibility. A passing C# build is insufficient.

See [the authoring contract and public reproduction](../vvvv-custom-nodes/process-node-contract.md).

### "Node" Suffix in Class Name

**Symptom**: Node works but has ugly name in vvvv.
**Fix**: Remove "Node" suffix — vvvv convention forbids it.

```csharp
// WRONG
[ProcessNode]
public class SteeringBehaviorNode { }

// CORRECT
[ProcessNode]
public class SteeringBehavior { }
```

### Out Parameters After Inputs

**Symptom**: Pins appear in wrong order or node doesn't compile correctly.
**Fix**: `out` parameters must come FIRST in Update signature.

```csharp
// WRONG
public void Update(float input = 0f, out float result) { ... }

// CORRECT
public void Update(out float result, float input = 0f) { ... }
```

### Node Not Appearing in Node Browser

**Symptom**: Your C# class exists but doesn't show up in vvvv.
**Fix**: Check these in order:
1. `[assembly: ImportAsIs]` attribute exists in your project
2. `[ProcessNode]` attribute on the class
3. Project targets `net8.0`
4. DLL is in the correct `lib/net8.0/` path relative to `.vl` document
5. Project builds without errors

### Allocations Causing Frame Drops

**Symptom**: GC spikes, stuttering, frame drops.
**Diagnosis**: Allocations in the Update loop.

Common culprits:
- `new` keyword in Update method
- LINQ operators (`.Where()`, `.Select()`, `.ToList()`)
- String concatenation (`+` operator on strings)
- Boxing value types (passing `int` where `object` expected)

**Fix**: Cache everything, pre-allocate buffers, eliminate LINQ from hot paths.

### Missing Change Detection

**Symptom**: CPU usage high even when nothing changes.
**Fix**: Compare inputs to cached values, only recompute on change.

```csharp
if (param != _lastParam)
{
    _cached = Compute(param);
    _lastParam = param;
}
result = _cached; // Always output cached
```

### Downstream Nodes See null/default

**Symptom**: Connected nodes get no data, even though the node "works".
**Fix**: Always output cached result, even when no computation happens.

```csharp
// WRONG — output is only set inside the if block
public void Update(out float result, float input = 0f)
{
    if (input != _last)
    {
        result = Compute(input);
        _last = input;
    }
    // result is unassigned when input hasn't changed!
}

// CORRECT — always assign output
public void Update(out float result, float input = 0f)
{
    if (input != _last)
    {
        _cached = Compute(input);
        _last = input;
    }
    result = _cached;
}
```

## SDSL Shader Issues

For SDSL syntax rules, common mistakes, and correct/wrong examples, see [vvvv-shaders/syntax-rules.md](../vvvv-shaders/syntax-rules.md). Key issues: `static const` scope, missing semicolons, missing `override`, enum binding format.

## Runtime Issues

### Memory Leaks

**Symptom**: Memory usage grows over time.
**Causes**:
- Missing `IDisposable` on nodes with native resources
- COM objects (`ComPtr<T>`) not disposed
- Event handler subscriptions not unsubscribed

### Thread Safety

**Symptom**: Intermittent crashes, data corruption.
**Fix**: `Update()` runs on the main thread. Capture `SynchronizationContext` in the constructor, then marshal background results back:

```csharp
private SynchronizationContext _vlSyncContext;

public MyNode()
{
    _vlSyncContext = SynchronizationContext.Current!;
}

// From background thread:
_vlSyncContext.Post(_ => { /* runs on VL thread */ }, null);
```

### Circular Dependencies

**Symptom**: vvvv warns about circular dependency, patch won't compile.
**Fix**: Insert a `FrameDelay` node to break the cycle.

## Build Issues

### Target Framework Mismatch

**Symptom**: DLL loads but types aren't found.
**Fix**: Ensure `.csproj` targets `net8.0` (matching vvvv gamma's runtime).

### Assembly Version Conflicts

**Symptom**: `FileLoadException` or `TypeLoadException` at runtime.
**Fix**: Align package versions with vvvv's bundled versions. Check vvvv's `lib/` folder for reference.

For detailed error-to-solution mapping, see [error-catalog.md](error-catalog.md).

## Keep this knowledge growing

Leave the next patcher one fewer mystery. On first use of any skill in this
collection with no successful check in seven days, compare the source with
[tebjan/vvvv-skills](https://github.com/tebjan/vvvv-skills). If no record exists, check once.
Share one local check timestamp/revision across these skills; do not poll per invocation.
Preserve local extensions and pinned project versions; checking is not permission
to install updates. If offline, record the deferred check and continue the task.

When actual work exposes a gap, capture the tested vvvv/package versions, a
minimal reproduction or authoritative source, and the observed result. Treat
other users' reports as leads, not facts until verified. Improve the smallest
relevant instruction; do not turn one example into a universal rule. Redact
private data and obtain publishing authorization before submitting upstream.
See the [contribution policy](https://github.com/tebjan/vvvv-skills/blob/main/CONTRIBUTING.md).
Merged improvements reach users through their installer/update workflow, not
through a local edit or an automatic overwrite of everyone's skills.
