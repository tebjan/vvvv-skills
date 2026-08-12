# Advanced Node Patterns

## Contents
- FragmentSelection (explicit control over node operations)
- Smell Attribute (aspects from C#: Advanced / Internal / Hidden / Experimental)
- Dynamic Enums (runtime-updating dropdowns)
- Settings / Split() Pattern (JSON + vvvv pin control)
- Pin Name Derivation (camelCase to pin names)
- Node Browser Categories via ImportType

## FragmentSelection (Advanced Nodes)

For complex nodes where you need explicit control over which methods become node operations:

```csharp
[ProcessNode(Name = "RenderWindow", Category = "Stride.Rendering",
             FragmentSelection = FragmentSelection.Explicit)]
public sealed class RenderWindow : IDisposable
{
    [Fragment]
    public RenderWindow(NodeContext nodeContext) { }

    [Fragment]
    public void SomeMethod(out RectangleF clientBounds, ...) { }
}
```

Only methods marked `[Fragment]` are exposed. Without `FragmentSelection.Explicit`, all public methods become node operations.

## Smell Attribute — aspects from C#

`[Smell]` is how you apply a vvvv **aspect** (Advanced / Internal / Hidden / Experimental /
Obsolete / Adaptive) to an imported C# symbol. It is the per-symbol equivalent of naming a
category segment `Advanced`.

```csharp
using VL.Core;          // SymbolSmell
using VL.Core.Import;   // SmellAttribute  ← NOT VL.Core.CompilerServices

[ProcessNode]
[Smell(SymbolSmell.Internal)]
public sealed class SkiaRendererNode : IDisposable { /* ... */ }
```

> ⚠️ There are two `SmellAttribute` types. Use **`VL.Core.Import.SmellAttribute`**.
> `VL.Core.CompilerServices.SmellAttribute` is `[Obsolete(error: true)]` — binary
> compatibility only, and a compile error if you reference it.

`VL.Core.SymbolSmell` is a `[Flags]` enum; `[Smell]` is `AttributeTargets.All`:

| Flag | Effect on the symbol |
|---|---|
| `Default` | normal |
| `Advanced` | hidden until the user turns on the NodeBrowser's Advanced filter |
| `Hidden` | never offered in the NodeBrowser |
| `Internal` | only available inside the defining document / library |
| `Experimental` | listed, flagged as unstable / WIP |
| `Obsolete` | listed, flagged as deprecated |
| `Adaptive` | enrolls the node in adaptive type dispatch |

**Aspects filter the browser listing only.** The symbol is still imported, still usable as a
pin type, and existing links, IOBoxes and saved patches keep resolving. That is what makes
`Advanced` the right tool for enums and settings types the user configures via a pin but
should never have to find in the browser — as opposed to `internal`, which removes the type
from VL entirely and would break such a pin.

`[Smell]` on a type does **not** cascade to its members. To cover a whole group in one
declaration, put the keyword in the category or namespace instead — see
vvvv-node-libraries → *Aspects from C#*.

Real-world reference: `VL.StandardLibs/VL.Skia/src/SkiaRendererNode.cs` (`Internal`) and
`FormBoundsNotification.cs` (`Experimental`).

## Dynamic Enums

Runtime-updating dropdowns for vvvv:

```csharp
public class MyEnumDefinition : DynamicEnumDefinitionBase<MyEnumDefinition>
{
    protected override IReadOnlyDictionary<string, object> GetEntries() { ... }
}

public class MyEnum : DynamicEnumBase<MyEnum, MyEnumDefinition>
{
    public MyEnum(string value) : base(value) { }
}
```

Trigger updates via `SetEntries()` which calls `trigger.OnNext("")`.

The definition is a singleton — only one instance exists globally, ensuring all nodes share identical entries.

## Settings / Split() Pattern

When a settings class needs JSON serialization but should NOT auto-expose properties as vvvv pins:

```csharp
public class EffectSettings
{
    // Internal + [JsonInclude] = JSON works, but vvvv does NOT create pins
    [JsonInclude] internal Vector3 offset = new(0, 0, 0);
    [JsonInclude] internal float intensity = 0f;

    // Split() IS the vvvv-visible API — becomes a Split node
    public void Split(out Vector3 offset, out float intensity)
    {
        offset = this.offset;
        intensity = this.intensity;
    }
}
```

Public properties on classes get auto-exposed as pins by vvvv. Use `internal` + `[JsonInclude]` to prevent this.

## Pin Name Derivation

Parameter names are auto-split from camelCase into vvvv pin names:
- `settings` → pin "Settings"
- `settingsJson` → pin "Settings Json"
- `customInstanceId` → pin "Custom Instance Id"

This matters for `SetPinValue()` calls — the name must match exactly.

## Node Browser Categories via ImportType

Control where your node appears in the node browser:

```csharp
[assembly: ImportType(typeof(MyProcessor), Name = "MyProcessor", Category = "My.Category")]
```

Category uses dot notation: `IO.Ports`, `Stride.Textures.Source`, etc.

For library-level `ImportAsIs` namespace/category configuration, see vvvv-node-libraries.
