---
name: vvvv-node-libraries
description: "Helps set up C# library projects that provide nodes to vvvv gamma — project directory structure, Initialization.cs with AssemblyInitializer, service registration via RegisterService, IResourceProvider factories, ImportAsIs / ImportNamespace / ImportType selection, category organization, aspects (Advanced/Internal/Hidden) via [Smell] and category keywords, .csproj setup, and dynamic node factories via RegisterNodeFactory. Also covers contributing changes to an existing/upstream vvvv library — fork → branch → PR workflow, editable source packages (--package-repositories / --editable-packages), and the .vl-document diff problem. Use when creating a new vvvv library, VL package, NuGet package for vvvv, deciding which import attribute to use, organizing categories, controlling which public types become nodes, registering services or node factories, setting up the project structure, or contributing a fix/feature/PR to a library you don't own (e.g. VL.StandardLibs). Trigger when the user says 'create a package', 'make a library', 'distribute nodes', 'organize categories', 'hide internal helpers from the node browser', 'mark nodes advanced', 'clean up the node browser', 'publish a VL package', 'contribute to vvvv', 'file a PR on a vvvv library', or 'edit an existing library'."
license: CC-BY-SA-4.0
compatibility: Designed for coding AI agents assisting with vvvv gamma development
metadata:
  author: Tebjan Halm
  version: "1.4"
---

# Creating vvvv gamma Node Libraries

A node library is a project that provides multiple nodes to vvvv gamma as a distributable package. This skill covers the project-level concerns: directory structure, naming conventions, category organization, service registration, and node factories.

For writing individual node classes (ProcessNode, Update, pins, change detection), see vvvv-custom-nodes. For consuming services inside node constructors (IFrameClock, Game, logging), see vvvv-custom-nodes/services.md.

**Creating your own library vs. contributing to one you don't own** are different tasks. This SKILL.md and its design/publishing references cover *creating and distributing* a package. To change or submit a PR to an **existing/upstream** library (fork → branch → PR workflow, editable source packages, the `.vl` diff problem), see [contributing.md](contributing.md).

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

**Implication for library design:** the primary lever for "what shows up in the node browser" is **which namespaces you import**, not which types are `public`. But note that importing is **recursive** — declaring one root namespace pulls in every namespace nested below it, so a `.Internal` sub-namespace is *not* a hiding place. See [Excluding helpers from the node browser](#excluding-helpers-from-the-node-browser--four-levers) for the four levers that actually work.

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

Both parameters are optional; all four combinations are legal and each does something different:

```csharp
[assembly: ImportAsIs]                                            // the scaffolded default:
                                                                  // nothing stripped, no root →
                                                                  // VL.MyLib.Particles ⇒ "VL.MyLib.Particles"
[assembly: ImportAsIs(Namespace = "VL.MyLib")]                    // strip only →
                                                                  // VL.MyLib.Particles ⇒ "Particles" (top level!)
[assembly: ImportAsIs(Category = "MyLib")]                        // root only →
                                                                  // VL.MyLib.Particles ⇒ "MyLib.VL.MyLib.Particles"
[assembly: ImportAsIs(Namespace = "VL.MyLib", Category = "MyLib")] // ✅ strip + root →
                                                                  // VL.MyLib.Particles ⇒ "MyLib.Particles"
```

The last form is what you almost always want. Use `ImportAsIs` when the whole library lives
under one root namespace and you want one root category. **You cannot stack two `ImportAsIs`
to split sub-namespaces into different categories** — it is `AllowMultiple = false`.

### `[assembly: ImportNamespace]` — per-namespace, multi-use

```csharp
// ⚠️ Order matters — first declaration wins. Specific before general.
[assembly: ImportNamespace("VL.MyLib.Renderers",    Category = "MyLib.Rendering")]
[assembly: ImportNamespace("VL.MyLib.Resources",    Category = "MyLib.Resources")]
[assembly: ImportNamespace("VL.MyLib.Experimental", Category = "MyLib.Experimental")]
[assembly: ImportNamespace("VL.MyLib",              Category = "MyLib")]   // catch-all, LAST
```

| Property | Behaviour |
|---|---|
| `AllowMultiple` | **`true`** — declare as many as you need |
| Scope | Public types in that namespace **and every namespace nested below it** (recursive) |
| Resolution | **First declaration wins**, not longest prefix — declare specific before general |

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

## 🛑 Importing is RECURSIVE — a nested namespace is NOT a hiding place

This is the single most common way a library's node browser gets polluted, and the mistake is
easy to make because the intent reads as obviously correct.

`ImportFromNamespace` in [AssemblySymbolSource.cs](https://github.com/vvvv/VL.StandardLibs)
walks the namespace tree until it finds the node whose full name **equals** the declared
namespace, then calls `ImportAll` on it — and `ImportAll` recurses through *every* nested
namespace and nested type below that point.

```csharp
[assembly: ImportNamespace("VL.MyLib", Category = "MyLib")]

namespace VL.MyLib;              // → category "MyLib"
namespace VL.MyLib.Internal;     // → category "MyLib.Internal"     ← STILL IMPORTED
namespace VL.MyLib.Internal.Gpu; // → category "MyLib.Internal.Gpu" ← STILL IMPORTED
```

**Putting helpers in a sub-namespace hides nothing.** It only moves them into a
sub-*category*, where the user still finds them by typing into the NodeBrowser search box —
along with every public member of every one of those types.

A *sibling* namespace (`VL.MyLibInternals`) genuinely is not imported by
`ImportNamespace("VL.MyLib")`… except `IsMatch` is `ns.StartsWith(Namespace)` with no
boundary check, so `ImportNamespace("VL.Foo")` still false-matches `VL.FooBar` when
computing the category. Sibling-namespace partitioning is fragile. Use one of the four
real levers below instead.

## Excluding helpers from the node browser — four levers

Pick by *who else* needs the type.

### 1. `internal` — the type never enters VL at all

`ImportAll` bails on its first line:

```csharp
if (s.DeclaredAccessibility != Accessibility.Public)
    return;
```

An `internal` type has no node, no category, no member nodes, no IOBox, no serialisation
surface. There is nothing about vvvv left to reason about. This is the strongest and cheapest
lever — reach for it first.

If a test or examples assembly needs the type, keep it `internal` and add
`[assembly: InternalsVisibleTo("MyLib.Tests")]`. VL stays blind; C# can still see it.

### 2. `[Smell(...)]` — public in C#, filtered in the browser

`VL.Core.Import.SmellAttribute` (`AttributeTargets.All`) **is** the per-type / per-member
opt-out. The type stays `public` and stays imported — it can still be a pin type, still flow
through links, still be referenced cross-assembly — it just isn't offered in the NodeBrowser.

```csharp
using VL.Core;          // SymbolSmell
using VL.Core.Import;   // SmellAttribute

[ProcessNode]
[Smell(SymbolSmell.Internal)]
public sealed class SkiaRendererNode : IDisposable { /* ... */ }
```

That is real VL.StandardLibs code (`VL.Skia/src/SkiaRendererNode.cs`). See
[Aspects from C#](#aspects-from-c--smell-and-category-keywords) below for the full flag list.

> ⚠️ Import `SmellAttribute` from **`VL.Core.Import`**. The identically-named
> `VL.Core.CompilerServices.SmellAttribute` is `[Obsolete(error: true)]` and exists only for
> binary compatibility — using it is a compile error.

### 3. Aspect keyword in the category — hide a whole group in one line

A category segment named `Internal`, `Hidden`, `Advanced`, `Experimental`, `Obsolete` or
`Adaptive` applies that aspect to everything in the category and is then **stripped** from the
resolved category name. Smell is inherited by every symbol in the category
(`ImportedSymbol.GetSmell()` starts from `ParentCategory.Smell`), so one declaration covers
an arbitrary number of types:

```csharp
[assembly: ImportNamespace("VL.MyLib.Plumbing", Category = "MyLib.Internal")]
// every public type under VL.MyLib.Plumbing → category "MyLib", smell Internal
```

Because the sub-namespace tail is appended to `Category` and *then* keyword-parsed, a plain
C# namespace segment works just as well — no attribute needed:

```csharp
[assembly: ImportNamespace("VL.MyLib", Category = "MyLib")]

namespace VL.MyLib.Particles;          // → "MyLib.Particles", normal
namespace VL.MyLib.Particles.Advanced; // → "MyLib.Particles", Advanced aspect
namespace VL.MyLib.Internal;           // → "MyLib",           Internal aspect
```

This makes the C# folder layout and the vvvv category tree the same artefact, which is the
most maintainable arrangement for a large library.

### 4. `ImportType`-only — closed allow-list

Skip `ImportAsIs`/`ImportNamespace` entirely and list each user-facing type. Everything not
listed stays invisible regardless of namespace or accessibility.

```csharp
[assembly: ImportType(typeof(Renderer), Category = "MyLib")]
[assembly: ImportType(typeof(Settings), Category = "MyLib")]
// Nothing else is imported.
```

Best for a small curated surface over a large internal codebase. Costs one line per node.

### Decision shortcut

| Situation | Lever |
|---|---|
| Nothing outside this assembly needs it | `internal` (1) |
| Tests / examples need it, users must never see it | `internal` + `[InternalsVisibleTo]` (1) |
| It's a legitimate pin type or cross-assembly API, just not browsable | `[Smell(SymbolSmell.Internal)]` (2) |
| A whole namespace of plumbing | aspect keyword in the category / namespace (3) |
| Big codebase, tiny node surface | `ImportType`-only (4) |

## Category resolution rules — verified from vvvv source

Priority order (highest first):

1. **`[ProcessNode(Category = "X")]`** / `[Category("X")]` on the class itself — wins outright.
2. **`[assembly: ImportType(typeof(T), Category = "X", NamespacePrefixToStrip = "...")]`** — per-type override.
3. **`[assembly: ImportNamespace("X.Sub", Category = "Y")]`** — for types under `X.Sub`, *if this attribute is the one that imported them* (see first-wins below).
4. **`[assembly: ImportAsIs(Namespace = "X", Category = "Y")]`** — the single whole-library default. It runs **before** every `ImportNamespace`, so it claims everything under `X` first.
5. **No import attribute matched the type** — the raw C# namespace is used verbatim as the category and stamped `SymbolSmell.External`. Aspect keywords are *not* parsed in this path.

The two whole-library forms, for reference:

```csharp
// Explicit — the recommended default. Strips "VL.MyLib", roots everything under "MyLib".
[assembly: ImportAsIs(Namespace = "VL.MyLib", Category = "MyLib")]

// Bare — what vvvv's own project template scaffolds. Nothing stripped, no category root:
// a class in VL.MyLib.Particles lands in the top-level category "VL.MyLib.Particles".
[assembly: ImportAsIs]
```

### 🛑 First-wins, NOT longest-prefix

`DirectImportSymbolSource` imports in a fixed order and passes the already-imported list as an
exclusion set, so **the first attribute to claim a type owns its category** — later attributes
silently no-op on it:

```csharp
if (importAsIsAttribute != null)
    ImportFromNamespace(builder, …, importAsIsAttribute.Namespace, importAttribute: importAsIsAttribute);

foreach (var a in importNamespaceAttributes)          // ← declaration order
    ImportFromNamespace(builder, …, a.Namespace, alreadyImported: builder, a);

foreach (var a in importTypeAttributes)
    ImportAll(builder, …, alreadyImported: builder, a);
```

```csharp
// ImportAll, first two lines:
if (s.DeclaredAccessibility != Accessibility.Public) return;
if (alreadyImported != null && alreadyImported.Any(c => …Equals(c.Symbol, s))) return;
```

Order is: `ImportAsIs` → `ImportNamespace` **in declaration order** → `ImportType`.

**Therefore: declare the most specific `ImportNamespace` FIRST.** A broad root declaration
placed above narrower ones swallows everything and turns the narrower lines into dead code:

```csharp
// ❌ BROKEN — the root line imports everything recursively; lines 2-3 never fire.
[assembly: ImportNamespace("VL.MyLib",          Category = "MyLib")]
[assembly: ImportNamespace("VL.MyLib.Plumbing", Category = "MyLib.Internal")]   // dead
[assembly: ImportNamespace("VL.MyLib.Config",   Category = "MyLib.Settings")]   // dead

// ✅ CORRECT — specific first, catch-all last.
[assembly: ImportNamespace("VL.MyLib.Plumbing", Category = "MyLib.Internal")]
[assembly: ImportNamespace("VL.MyLib.Config",   Category = "MyLib.Settings")]
[assembly: ImportNamespace("VL.MyLib",          Category = "MyLib")]
```

This failure is silent — no warning, no error. The symptom is sub-namespace names showing up
as node browser folders you thought you had remapped. To confirm where a type *actually*
landed, drop it in a patch, save, and read `LastCategoryFullName` out of the `.vl` XML.

For levels 3 and 4 (`ImportAsIs` / `ImportNamespace`), the resulting category is computed by **`GetCategory(typeNamespace)`** in [VL.Core/src/Import/ImportAsIsAttribute.cs](https://github.com/vvvv/VL.StandardLibs/blob/main/VL.Core/src/Import/ImportAsIsAttribute.cs):

```csharp
// Pseudocode of the actual VL.Core implementation:
root = Category ?? "";
if (typeNamespace == "")           return root;
if (Namespace == "")               cat = typeNamespace;
else if (typeNamespace.Length > Namespace.Length)
                                   cat = typeNamespace.Substring(Namespace.Length + 1);
else /* typeNamespace == Namespace */ cat = "";
if (cat == "")                     return root;
if (root == "")                    return cat;
return $"{root}.{cat}";
```

What this means in practice — the **non-obvious** consequence:

| `[assembly: ImportAsIs(...)]` | C# namespace | vvvv category | Surprise? |
|---|---|---|---|
| `Namespace = "VL.MyLib", Category = "MyLib"` | `VL.MyLib` | `MyLib` | no |
| `Namespace = "VL.MyLib", Category = "MyLib"` | `VL.MyLib.Particles` | `MyLib.Particles` | no |
| `Namespace = "VL.MyLib"` *(no Category)* | `VL.MyLib` | `""` (root) | yes — empty/root |
| `Namespace = "VL.MyLib"` *(no Category)* | `VL.MyLib.Particles` | `Particles` | **yes — top-level** |
| `Namespace = "VL.MyLib"` *(no Category)* | `VL.MyLib.Internal.Helpers` | `Internal.Helpers` | **yes — top-level "Internal" leak!** |

**Without `Category=`, the prefix is just stripped — there is no fallback that prepends the last segment of `Namespace`.** So `[ImportAsIs(Namespace = "VL.MyLib")]` with classes in `VL.MyLib.Config` puts them at top-level `Config`, NOT `MyLib.Config`. This is the most common surprise — always set `Category` explicitly unless you really want top-level pollution from sub-namespaces.

When debugging "why did my node end up at top-level `Helpers` instead of `MyLib.Helpers`?", check: did you forget the `Category =` parameter on `ImportAsIs`?

## Aspects from C# — `[Smell]` and category keywords

Aspects control NodeBrowser visibility and node status. The Gray Book documents them for
*patched* symbols; from C# there are two ways to apply the same thing.

### The flags

`VL.Core.SymbolSmell` is a `[Flags]` enum:

| Flag | Value | Effect |
|---|---|---|
| `Default` | 0 | normal |
| `Obsolete` | 1 | deprecated; kept for backwards compatibility |
| `Experimental` | 2 | unstable / WIP |
| `Advanced` | 4 | **hidden from the NodeBrowser until the user enables the Advanced filter** |
| `Hidden` | 8 | never offered in the NodeBrowser |
| `Internal` | 16 | only available inside the defining document / library |
| `Adaptive` | 512 | enrolls the node in adaptive type dispatch |

`Advanced` is the one library authors reach for most: the Gray Book's rationale is that
*"any library developer provides a few super cool nodes and types that 90% of all users of a
library should use"* — everything else goes `Advanced` rather than being deleted.

### Way 1 — `[Smell(SymbolSmell.X)]` on the symbol

```csharp
using VL.Core;
using VL.Core.Import;

[Smell(SymbolSmell.Experimental)]
public sealed class FormBoundsNotification { /* ... */ }
```

Applies to types, methods, properties — `AttributeUsage(AttributeTargets.All)`.
A `[Smell]` on a type does **not** cascade to its members; set it per symbol, or use a
category (way 2) to cover a whole group.

### Way 2 — keyword as a category / namespace segment

`Symbols.ToSmell` recognises exactly these segment names, case-sensitive:

| Segment | Aspect |
|---|---|
| `Internal` | `SymbolSmell.Internal` |
| `Advanced` | `SymbolSmell.Advanced` |
| `Experimental` | `SymbolSmell.Experimental` |
| `Obsolete` | `SymbolSmell.Obsolete` |
| `Hidden` | `SymbolSmell.Hidden` |
| `Adaptive` | `SymbolSmell.Adaptive` |

The matching segment is removed from the resolved category, so `MyLib.Particles.Advanced` and
`MyLib.Advanced.Particles` both resolve to category `MyLib.Particles` with the `Advanced`
aspect. Smell is inherited: `ImportedSymbol.GetSmell()` starts from `ParentCategory.Smell` and
ORs the symbol's own `[Smell]` on top — so one keyword covers every type in the category.

⚠️ **Keyword parsing only happens for attribute-supplied categories.** In
`GetCategoryAndSmellForFullName(name, isAssemblyCategory)`, the keyword loop is inside the
`else` branch — when `isAssemblyCategory: true` (the raw-namespace fallback used when *no*
import attribute matched) the name is taken verbatim and stamped `SymbolSmell.External`
instead. In practice: a `.Advanced` namespace segment works **because** an `ImportAsIs` /
`ImportNamespace` produced the category. It does nothing for a type that was never imported.

### Way 3 — keyword in the node's version segment

`NameVersionAndSmell.Split` parses the version portion of a node name, so this works too:

```csharp
[ProcessNode(Name = "GetBytes (Advanced)")]
```

### What aspects do NOT do

An `Advanced` / `Hidden` / `Internal` symbol is **still fully functional**. It is still
imported, still has a category, still works as a pin type, and existing links, IOBoxes and
saved patches keep resolving. Aspects filter the **NodeBrowser listing only**. That makes
`Advanced` the correct tool for enums and settings types that a user configures through a pin
but should never have to hunt for in the browser.

### Two aspects vvvv applies for you

- **`[ProcessNode]` without `HasStateOutput` hides the type.** `ImportedSymbol.GetSmell()`
  adds `SymbolSmell.Hidden` to the *type* when a `ProcessNodeAttribute` is present and
  `HasStateOutput == false`, so only the process node shows. Setting `HasStateOutput = true`
  un-hides the type **and every public member as an individual node** — a real, easily
  overlooked source of browser clutter.
- **Enum operators are auto-`Advanced`.** The generated `=`, `!=`, `|`, `&`, `^` operations on
  imported enums get `SymbolSmell.Advanced` automatically (devvvvs/vvvv#3885), so you never
  need to hide those yourself.

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
For contributing changes/PRs to an existing upstream library, see [contributing.md](contributing.md).
For complete real-world examples (VL.IO.MQTT, VL.Audio), see [examples.md](examples.md).
