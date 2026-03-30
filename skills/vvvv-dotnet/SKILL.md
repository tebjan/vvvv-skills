---
name: vvvv-dotnet
description: "Helps with .NET integration in vvvv gamma — NuGet packages, library references, .csproj project configuration, the [assembly: ImportAsIs] attribute, vector type interop, and async patterns. Use when adding NuGet packages, configuring build settings, referencing external .NET libraries, setting up the ImportAsIs assembly attribute, working with System.Numerics/Stride type conversions, or when nodes aren't appearing in the node browser due to missing assembly configuration."
license: CC-BY-SA-4.0
compatibility: Designed for coding AI agents assisting with vvvv gamma development
metadata:
  author: Tebjan Halm
  version: "1.1"
---

# .NET Integration in vvvv gamma

## Troubleshooting — Nodes Not Appearing in Node Browser

1. **Check `[assembly: ImportAsIs]`** — without this attribute, vvvv cannot discover your nodes
2. **Verify .csproj references** — ensure `VL.Core` and `VL.Core.Import` are referenced
3. **Run `dotnet build`** — check for compilation errors (you cannot see vvvv's compiler output)
4. **Check node naming** — ProcessNode class names must NOT have a "Node" suffix
5. **Restart vvvv** — if using binary references, a restart is required after `dotnet build`

## .csproj Configuration for vvvv Plugins

Minimal `.csproj`:

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <OutputPath Condition="'$(Configuration)'=='Release'">..\..\lib\net8.0\</OutputPath>
    <AppendTargetFrameworkToOutputPath>false</AppendTargetFrameworkToOutputPath>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="VL.Core" Version="2025.7.*" />
    <PackageReference Include="VL.Stride" Version="2025.7.*" />
  </ItemGroup>
</Project>
```

- **Target framework**: `net8.0` (required for vvvv gamma 6+)
- **Output path**: Point to `lib/net8.0/` relative to your `.vl` document
- Use wildcard versions (`2025.7.*`) to stay compatible with patch releases

### How vvvv Uses C# Code

**Source project reference** (live reload): The .vl document references a .csproj. vvvv compiles .cs files via Roslyn into in-memory assemblies — no `dotnet build` needed. On .cs file save, vvvv recompiles automatically.

**Binary reference** (no live reload): The .vl document references a pre-compiled DLL or NuGet package. Rebuild externally (`dotnet build`) and restart vvvv.

**For AI agents**: always run `dotnet build` to verify your code compiles. For source project references, vvvv picks up changes on file save (no restart). For binary references, `dotnet build` + restart is required.

## Required Global Usings

```csharp
global using VL.Core;
global using VL.Core.Import;
global using VL.Lib.Collections;
```

## Required Assembly Attribute

```csharp
[assembly: ImportAsIs]
```

Without this, your nodes will not appear in the vvvv node browser.

## NuGet Package Sources

Add to your `NuGet.config`:

```xml
<configuration>
  <packageSources>
    <add key="nuget.org" value="https://api.nuget.org/v3/index.json" />
    <add key="vvvv" value="https://teamcity.vvvv.org/guestAuth/app/nuget/v1/FeedService.svc/" />
  </packageSources>
</configuration>
```

## Essential VL Packages

| Package | Purpose |
|---|---|
| `VL.Core` | Core types, ProcessNode attribute, Spread |
| `VL.Core.Import` | ImportAsIs attribute |
| `VL.Lib.Collections` | Spread, SpreadBuilder |
| `VL.Stride` | 3D rendering, shader integration |

For the full catalog, see [vvvv.org/packs](https://vvvv.org/packs).

## Vector Types & SIMD Strategy

- **Internal hot paths**: Use `System.Numerics.Vector3/Vector4/Quaternion` (SIMD via AVX/SSE)
- **External API** (Update method params): Use `Stride.Core.Mathematics` types (required by VL)
- **Zero-cost conversion**:

```csharp
using System.Runtime.CompilerServices;

// Stride → System.Numerics (zero-cost reinterpret)
ref var numericsVec = ref Unsafe.As<Stride.Core.Mathematics.Vector3, System.Numerics.Vector3>(ref strideVec);

// System.Numerics → Stride (zero-cost reinterpret)
ref var strideVec = ref Unsafe.As<System.Numerics.Vector3, Stride.Core.Mathematics.Vector3>(ref numericsVec);
```

## IDisposable and Resource Management

Any node holding native/unmanaged resources must implement `IDisposable`:

```csharp
[ProcessNode]
public class NativeWrapper : IDisposable
{
    private IntPtr _handle;

    public NativeWrapper()
    {
        _handle = NativeLib.Create();
    }

    public void Update(out int result)
    {
        result = NativeLib.Process(_handle);
    }

    public void Dispose()
    {
        if (_handle != IntPtr.Zero)
        {
            NativeLib.Destroy(_handle);
            _handle = IntPtr.Zero;
        }
    }
}
```

vvvv calls `Dispose()` when the node is removed or the document closes.

## Async Patterns in vvvv

Since `Update()` runs on the main thread at 60 FPS, long-running operations must be async:

```csharp
[ProcessNode]
public class AsyncLoader
{
    private Task<string>? _loadTask;
    private string _cachedResult = "";

    public void Update(
        out string result,
        out bool isLoading,
        string url = "",
        bool trigger = false)
    {
        if (trigger && (_loadTask == null || _loadTask.IsCompleted))
        {
            _loadTask = Task.Run(() => LoadFromUrl(url));
        }

        isLoading = _loadTask != null && !_loadTask.IsCompleted;

        if (_loadTask?.IsCompletedSuccessfully == true)
            _cachedResult = _loadTask.Result;

        result = _cachedResult;
    }
}
```

## Referencing vvvv-Loaded DLLs

Use `<Private>false</Private>` to prevent copying DLLs already loaded by vvvv:

```xml
<Reference Include="Fuse">
    <HintPath>..\..\path\to\Fuse.dll</HintPath>
    <Private>false</Private>
</Reference>
```

## Build Commands

```bash
# Build a plugin project
dotnet build src/MyPlugin.csproj -c Release

# Build an entire solution
dotnet build src/MyPlugin.sln -c Release
```

## NuGet Packaging

```bash
nuget pack MyPlugin/deployment/MyPlugin.nuspec
```

The `.nuspec` should reference your `.vl` document, compiled DLLs, shader files, and help patches.

For advanced topics (blittable structs, COM interop, C++/CLI, Directory.Build.props, threading), see [advanced.md](advanced.md).
For forwarding .NET libraries into VL, see [forwarding.md](forwarding.md).
