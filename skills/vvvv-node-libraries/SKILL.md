---
name: vvvv-node-libraries
description: "Helps set up C# library projects that provide nodes to vvvv gamma — project directory structure, Initialization.cs with AssemblyInitializer, service registration via RegisterService, IResourceProvider factories, ImportAsIs / ImportNamespace / ImportType selection, category organization, .csproj setup, and dynamic node factories via RegisterNodeFactory. Use when creating a new vvvv library, VL package, NuGet package for vvvv, deciding which import attribute to use, organizing categories, controlling which public types become nodes, registering services or node factories, or setting up the project structure. Trigger when the user says 'create a package', 'make a library', 'distribute nodes', 'organize categories', 'hide internal helpers from the node browser', or 'publish a VL package'."
license: CC-BY-SA-4.0
compatibility: Designed for coding AI agents assisting with vvvv gamma development
metadata:
  author: Tebjan Halm
  version: "1.2"
---

# Creating vvvv gamma Node Libraries

A node library is a project that provides multiple nodes to vvvv gamma as a distributable package. This skill covers the project-level concerns: directory structure, naming conventions, category organization, service registration, and node factories.

For writing individual node classes (ProcessNode, Update, pins, change detection), see vvvv-custom-nodes. For consuming services inside node constructors (IFrameClock, Game, logging), see vvvv-custom-nodes/services.md.

## Library Recognition Pattern

vvvv recognizes a directory as a library when the **folder name, .vl file, and .nuspec all share the same name**:

```
VL.MyLibrary/                       # Folder name = package name
├── VL.MyLibrary.vl                 # .vl document — MUST match folder name
├── VL.MyLibrary.nuspec             # NuGet spec — MUST match folder name
├── lib/
│   └── net8.0/                     # Compiled DLLs go here
│       └── VL.MyLibrary.dll
├── src/
│   ├── Initialization.cs           # [assembly:] attributes + AssemblyInitializer
│   ├── Nodes/
│   │   ├── MyProcessNode.cs        # [ProcessNode] classes
│   │   └── MyOperations.cs         # Static methods (stateless nodes)
│   ├── Services/
│   │   └── MyService.cs            # Per-app singletons
│   └── VL.MyLibrary.csproj
├── shaders/                         # Optional: SDSL shaders (auto-discovered)
│   └── MyEffect_TextureFX.sdsl
└── help/                            # Optional: .vl help patches
    └── HowTo Use MyNode.vl
```

**Critical conventions**:
- Folder name, `.vl` file, and `.nuspec` must be identical (e.g., all `VL.MyLibrary`)
- The `.csproj` must output DLLs to `lib/net8.0/` relative to the package root
- No `.vl` file within a package should reference a `.csproj` — this forces the package into editable mode
- The library directory must be in a configured **package-repository** directory for vvvv to find it

### .csproj Output Path

The `.csproj` must compile into the library's `lib/net8.0/` folder:

```xml
<PropertyGroup>
  <TargetFramework>net8.0</TargetFramework>
  <OutputPath>..\..\lib\net8.0\</OutputPath>
  <AppendTargetFrameworkToOutputPath>false</AppendTargetFrameworkToOutputPath>
</PropertyGroup>
```

## What gets imported as a node — the foundational rule

A type becomes a node in vvvv's node browser when **two** conditions are both true:

1. The type is `public` (and lives in an imported assembly).
2. The type's C# namespace is covered by an `[assembly: ImportAsIs]` / `[assembly: ImportNamespace]` declaration, OR the type is listed by an `[assembly: ImportType]` declaration.

If either condition is false, the type is invisible to vvvv. **Importing is opt-in by namespace, not by type accessibility alone.** A `public` class in a namespace nobody imports is just as hidden from the node browser as an `internal` class.

When a type IS imported, vvvv generates nodes from its full public surface:

- Public classes and structs → constructor + public methods/properties become nodes
- Public static methods → operation nodes
- Public enums → split + values become nodes
- Public records and interfaces → handled like classes

**`[ProcessNode]` does NOT gate node visibility.** It is purely lifecycle sugar — it tells vvvv "this is a stateful class with an `Update()` method, manage one instance per node, call Update() each frame". A plain `public class Foo { public Foo() {} public int Bar(int x) => x; }` in an imported namespace becomes a node browser entry exactly the same as one decorated with `[ProcessNode]`. The attribute affects *how* the node is invoked, not *whether* it appears.

**Implication for library design:** the primary lever for "what shows up in the node browser" is **which namespaces you import**, not which types are `public`. Partition your code into a "public-API" namespace (imported) and a "helpers" namespace (NOT imported), and you can keep helpers `public` for cross-assembly use, testing, or refactoring without polluting the user's node browser.

Source: [VL.StandardLibs ImportAsIsAttribute](https://github.com/vvvv/VL.StandardLibs/blob/main/VL.Core/src/Import/ImportAsIsAttribute.cs), [Gray Book — Writing nodes using C#](https://thegraybook.vvvv.org/reference/extending/writing-nodes.html).

## Initialization.cs — The Entry Point

Every node library needs assembly-level attributes. Combine in one file:

```csharp
using VL.Core;
using VL.Core.CompilerServices;
using VL.Core.Import;

// Required: tells vvvv to scan this assembly for nodes
[assembly: ImportAsIs(Namespace = "MyCompany.MyLibrary", Category = "MyLibrary")]

// Optional: register services before any node runs
[assembly: AssemblyInitializer(typeof(MyCompany.MyLibrary.Initialization))]

namespace MyCompany.MyLibrary;

public sealed class Initialization : AssemblyInitializer<Initialization>
{
    public override void Configure(AppHost appHost)
    {
        var services = appHost.Services;

        // Register per-app singletons (created lazily on first access)
        services.RegisterService<MyService>(serviceProvider =>
        {
            return new MyService(serviceProvider);
        });
    }
}
```

## Choosing the right import attribute

vvvv provides three assembly-level attributes for declaring what becomes a node. Pick based on how much control you need.

### `[assembly: ImportAsIs]` — single, namespace-rooted

```csharp
[assembly: ImportAsIs(Namespace = "VL.MyLib", Category = "MyLib")]
```

| Property | Behaviour |
|---|---|
| `AllowMultiple` | **`false`** — at most ONE per assembly |
| Scope | All public types in `Namespace` (and its children) |
| Category | `Category` parameter is the root; sub-namespaces below `Namespace` extend it |

Use when the whole library lives under one root namespace and you want one root category. **You cannot stack two `ImportAsIs` to split sub-namespaces into different categories.**

### `[assembly: ImportNamespace]` — per-namespace, multi-use

```csharp
[assembly: ImportNamespace("VL.MyLib.Renderers",  Category = "MyLib.Rendering")]
[assembly: ImportNamespace("VL.MyLib.Resources",  Category = "MyLib.Resources")]
[assembly: ImportNamespace("VL.MyLib.Experimental", Category = "MyLib.Experimental")]
```

| Property | Behaviour |
|---|---|
| `AllowMultiple` | **`true`** — declare as many as you need |
| Scope | Public types whose namespace **starts with** the given prefix |
| Resolution | Most specific (longest) prefix wins for nested namespaces |

Use when one library has multiple sub-namespaces and you want each to land in a distinct category — without polluting the browser with C# folder names. This is the right tool for multi-category libraries.

### `[assembly: ImportType]` — per-type, hand-picked

```csharp
[assembly: ImportType(typeof(MyRenderer),  Category = "MyLib.Rendering")]
[assembly: ImportType(typeof(MyResource),  Category = "MyLib.Resources", Name = "Resource")]
```

| Property | Behaviour |
|---|---|
| `AllowMultiple` | **`true`** — declare as many as you need |
| Scope | Only the listed types — nothing else from the assembly is auto-imported |
| Use with | Either alone (no `ImportAsIs`/`ImportNamespace`) for closed-list libraries, or alongside the namespace attributes to override category/name for specific types |

Use for surgical control — e.g. when you want to expose only a curated subset of a large internal codebase, or to force one outlier into a different category than its namespace siblings.

### Decision matrix

| Library shape | Recommended attribute(s) |
|---|---|
| One namespace, one category, all public types are intentional | `[assembly: ImportAsIs(Namespace, Category)]` |
| One library, several distinct sub-categories | One `[assembly: ImportNamespace]` per sub-namespace |
| Curated set of nodes, lots of public helpers you don't want exposed | `[assembly: ImportType]` per node, no `ImportAsIs` |
| Mostly auto-imported, a few outliers | `[assembly: ImportAsIs]` + `[assembly: ImportType]` overrides |

## Excluding helpers from the node browser

There is no `ExcludeFromImport` / `IgnoreType` / `[Hidden]` attribute in VL — the importer has no per-type opt-out. But you have two strong levers, in order of preference:

1. **Partition by namespace and import selectively (preferred).** Put helpers in a sibling namespace and just don't import it. Both halves can be `public`; only the imported namespace becomes nodes.

   ```csharp
   namespace VL.MyLib;          // user-facing nodes
   public sealed class Renderer { /* ... */ }

   namespace VL.MyLib.Internal; // helpers, public for cross-assembly use
   public sealed class BufferPool { /* ... */ }

   // Initialization.cs
   [assembly: ImportNamespace("VL.MyLib", Category = "MyLib")]
   // VL.MyLib.Internal is NOT imported → BufferPool is invisible to the node browser
   ```

   This is the workhorse pattern: it's how you keep classes `public` for testability, cross-assembly use, or future refactors without leaking them as nodes. **`ImportNamespace` matches by exact namespace prefix** — `VL.MyLib.Internal` is NOT a child of `VL.MyLib` for matching purposes when there's no second `ImportNamespace` covering it.

2. **`ImportType`-only for small / curated libraries.** Skip `ImportAsIs`/`ImportNamespace` entirely and list each user-facing type explicitly. Everything not listed stays invisible regardless of namespace or accessibility.

   ```csharp
   [assembly: ImportType(typeof(Renderer),  Category = "MyLib")]
   [assembly: ImportType(typeof(Settings),  Category = "MyLib")]
   // Nothing else is imported.
   ```

3. **Use `internal` (last resort).** Only use `internal` when you ALSO want to hide the type from C# consumers — e.g. truly private implementation details that no other assembly should reference. `internal` is a heavier hammer than namespace partitioning because it also breaks tests in separate assemblies (forcing `[InternalsVisibleTo]` plumbing).

**Decision shortcut:** If you ever say "this class is `public` only because tests in another assembly need it, but I don't want users to see it as a node" — the answer is namespace partitioning + selective import, not `internal` + `[InternalsVisibleTo]`.

## Category resolution rules

For any class that vvvv decides to import, the final node-browser category is resolved in this priority order:

1. **`[ProcessNode(Category = "X")]`** on the class itself — wins over assembly-level config.
2. **`[assembly: ImportType(typeof(T), Category = "X")]`** for the specific type — overrides namespace-level category.
3. **`[assembly: ImportNamespace("VL.MyLib.Sub", Category = "X")]`** matching the class's namespace — wins by longest prefix.
4. **`[assembly: ImportAsIs(Namespace = "VL.MyLib", Category = "X")]`** — applies to all types under `VL.MyLib` not covered above. Sub-namespaces extend the category (e.g. class in `VL.MyLib.Particles` lands at `X.Particles`).
5. **No category attribute** — the C# namespace structure is used directly as the category path.

When debugging "why did my node end up in `MyLib.Internal`?", walk the priority list top-down — almost always the answer is "no explicit category was set and the C# namespace bled into the browser".

## Service Registration Patterns

Services are registered in `Configure(AppHost)` and consumed by nodes via `NodeContext`. This section covers registration only — for consumption patterns, see vvvv-custom-nodes/services.md.

### Direct Singleton (Recommended)

```csharp
services.RegisterService<MyService>(serviceProvider =>
{
    // Created lazily on first GetService<MyService>() call
    return new MyService(serviceProvider);
});
```

### IResourceProvider Pattern (For Managed Lifecycle)

When the service wraps a resource that needs explicit disposal:

```csharp
services.RegisterService<IResourceProvider<MyGPUService>>(serviceProvider =>
{
    var gameProvider = serviceProvider.GetService<IResourceProvider<Game>>();
    return gameProvider.Bind(game =>
    {
        var service = MyGPUService.Create(game);
        return ResourceProvider.Return(service, disposeAction: s => s?.Dispose());
    });
});
```

## Dynamic Node Factories

Register programmatic node generation for dynamic node sets:

```csharp
public override void Configure(AppHost appHost)
{
    // Dynamic node factory from shader files or other sources
    appHost.RegisterNodeFactory("VL.MyLibrary.ShaderNodes",
        init: MyShaderNodeFactory.Init);
}
```

Use node factories when nodes are generated from external files (shaders, configs) rather than written as C# classes. For details, see the [vvvv Node Factories docs](https://thegraybook.vvvv.org/reference/extending/node-factories.html).

## Extension Methods for Service Access

Provide typed accessors for your services:

```csharp
public static class MyLibraryExtensions
{
    public static MyService? GetMyService(this ServiceRegistry services)
        => services.GetService(typeof(MyService)) as MyService;

    public static MyService? GetMyService(this IServiceProvider services)
        => services.GetService(typeof(MyService)) as MyService;
}
```

## .csproj Essentials

Full library `.csproj` with output to `lib/net8.0/`:

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <OutputPath>..\..\lib\net8.0\</OutputPath>
    <AppendTargetFrameworkToOutputPath>false</AppendTargetFrameworkToOutputPath>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="VL.Core" Version="2025.7.*" />
    <PackageReference Include="VL.Core.Import" Version="2025.7.*" />
    <!-- For Stride integration: -->
    <PackageReference Include="VL.Stride.Runtime" Version="2025.7.*" />
  </ItemGroup>
</Project>
```

Match VL package versions to your vvvv installation version. The `OutputPath` places compiled DLLs in the library's `lib/net8.0/` folder where vvvv expects to find them.

## Real-World Example: Custom Rendering Library

Library initialization with service registration and node factory:

```csharp
[assembly: AssemblyInitializer(typeof(Initialization))]
[assembly: ImportAsIs(Namespace = "VL.MyRendering", Category = "MyRendering")]

public sealed class Initialization : AssemblyInitializer<Initialization>
{
    public override void Configure(AppHost appHost)
    {
        appHost.Services.RegisterService<CustomGameSystem>(sp =>
        {
            var vlGame = sp.GetService<VLGame>();
            if (vlGame == null) return null!;
            var customGame = CustomGameSystem.Create(vlGame, sp);
            vlGame.GameSystems.Add(customGame);
            return customGame;
        });

        // Dynamic node factory from shader files
        appHost.RegisterNodeFactory("VL.MyRendering.ShaderNodes",
            init: ShaderNodeFactory.Init);
    }
}
```

For naming conventions, pin rules, aspects, and standard types, see [design-guidelines.md](design-guidelines.md).
For publishing NuGets, help patches, and library structure, see [publishing.md](publishing.md).
For complete real-world examples (VL.IO.MQTT, VL.Audio), see [examples.md](examples.md).
