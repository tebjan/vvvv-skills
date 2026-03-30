---
name: vvvv-fundamentals
description: "Explains vvvv gamma core concepts — data types, frame-based execution model, pins, pads, links, node browser, live compilation (source project vs binary reference workflows), .vl document structure, file types (.vl/.sdsl/.cs/.csproj), ecosystem overview, and AppHost runtime detection. Use when the user asks about vvvv basics, how vvvv works, the live reload model, when to patch vs code, or needs an overview of the visual programming environment."
license: CC-BY-SA-4.0
compatibility: Designed for coding AI agents assisting with vvvv gamma development
metadata:
  author: Tebjan Halm
  version: "1.0"
---

# vvvv gamma Fundamentals

## What Is vvvv gamma

vvvv gamma is a live programming environment for .NET 8 that combines node-based visual patching with C# code. It targets Stride (3D engine) and the full .NET ecosystem. Programs run continuously while you build them — edits take effect immediately.

## Quick Start — Adding a C# Node to a Project

1. Create a `.cs` file with a `[ProcessNode]` class (see vvvv-custom-nodes)
2. Ensure the `.csproj` has `[assembly: ImportAsIs]` (see vvvv-dotnet)
3. Save the file — vvvv detects the change and recompiles via Roslyn
4. Open the **Node Browser** (double-click canvas) and search for your node name
5. **Verify:** The node appears and can be connected to other nodes in the patch

## Execution Model

- **Frame-based** — the mainloop evaluates the entire graph every frame (~60 FPS)
- **Data flows left-to-right, top-to-bottom** through links
- **Process nodes** maintain state between frames (constructor → Update loop → Dispose)
- **Operation nodes** are stateless functions evaluated each frame
- Connected nodes always evaluate; disconnected subgraphs are skipped

## Live Compilation Model

### Patch and Shader Changes
- Patch edits apply immediately with node state preserved
- `.sdsl` shader files always live-reload on save

### C# — Two Workflows

**Source project reference** (live reload):
A .vl document references a .csproj. vvvv compiles .cs files via Roslyn into in-memory assemblies — no `dotnet build` needed.

On .cs file save:
1. vvvv detects the change and recompiles (gray indicator = building, orange = emitting)
2. `Dispose()` called on old node instances
3. New constructor runs with fresh `NodeContext`
4. `Update()` resumes next frame
5. Static fields reset (entire assembly is replaced)
6. On compile error → program continues with last valid code

**Binary reference** (no live reload):
The .vl document references a pre-compiled DLL or NuGet package. Rebuild externally (`dotnet build`) and restart vvvv to pick up changes.

## Node Categories

### Process Nodes
- Have Create (constructor), Update (per-frame), and Dispose lifecycle
- `[ProcessNode]` attribute, maintain internal state
- Use change detection to avoid redundant work

### Operation Nodes
- Static C# methods, auto-discovered by vvvv
- No state, no `[ProcessNode]` attribute needed

### Adaptive Nodes
- Adapt implementation based on connected input types (e.g., `+` works with int, float, Vector3, string)
- Resolved at link-time, not runtime

## Pins, Pads, and Links

- **Pins** — inputs and outputs on nodes and regions
- **Pads** — visual nodes for reading/writing Properties inside operation patches; all pads with the same name refer to the same property
- **Links** — connections between pins defining data flow and execution order
- **Spreading** — `Spread<T>` connected to a single-value input auto-iterates the node

## When to Patch vs Write C#

| Use Patching | Use C# Code |
|---|---|
| Prototyping, data flow | Custom nodes, performance-critical code |
| Visual connections, UI composition | Complex algorithms |
| Real-time parameter tweaking | .NET library interop |
| Dataflow routing and spreading | Native/unmanaged resource management |

## Key Data Types

| Type | Usage |
|---|---|
| `Spread<T>` / `SpreadBuilder<T>` | vvvv's immutable collection (see vvvv-spreads) |
| `Vector2/3/4`, `Color4` | Stride.Core.Mathematics spatial and color types |
| `IChannel<T>` | Observable value container for reactive data flow (see vvvv-channels) |

## File Types

| Extension | Purpose |
|---|---|
| `.vl` | vvvv gamma documents (XML-based, version controlled) |
| `.sdsl` | Stride shader files |
| `.cs` | C# source files for custom nodes |
| `.csproj` | .NET project files |

## Ecosystem Overview

vvvv extends through NuGet packages bundling .vl documents, C# nodes, and shaders:

- **3D**: VL.Stride, VL.Fuse (GPU visual programming)
- **2D**: VL.Skia, ImGui, Avalonia
- **Hardware**: DMX/Art-Net, depth cameras, robotics, LiDAR
- **Network**: OSC, MIDI, MQTT, WebSocket, HTTP, TCP/UDP
- **CV/ML**: OpenCV, MediaPipe, YOLO, ONNX Runtime
- **Audio**: NAudio, VST hosting
- **General .NET**: Any of 100k+ NuGet packages via .csproj reference

To add a package: reference it in your `.vl` document's Dependencies, or add a `<PackageReference>` to your `.csproj`. See vvvv-dotnet for details.

## AppHost & Runtime Detection

```csharp
// Detect if running as exported .exe vs editor
bool isExported = nodeContext.AppHost.IsExported;

// Register per-app singleton services
nodeContext.AppHost.Services.RegisterService(myService);
```

For detailed reference, see [reference.md](reference.md).
