# vvvv gamma

vvvv gamma is a visual programming environment for .NET. It combines node-based patching with C# code live compilation, using Stride (3D engine) and .NET 8.

## When to Patch vs Code

- **Patch**: Prototyping, data flow, visual connections, real-time parameter tweaking, UI composition
- **Code (C#)**: Custom nodes, performance-critical operations, complex algorithms, .NET library interop

## Core Concepts

- **Spreads**: vvvv's immutable collection type (`Spread<T>`). Use `SpreadBuilder<T>` to create.
- **Process Nodes**: Stateful C# classes with an `Update()` method. Annotated with `[ProcessNode]`.
- **Pins**: Input/output connection points on nodes
- **Links**: Data flow connections between pads
- **Channels**: Observable value containers for reactive data flow
- **Adaptive Nodes**: Nodes that adapt their implementation based on input types

## Live Environment

- Patch edits apply immediately with state preserved
- Shader (.sdsl) changes always live-reload
- **C# has two workflows** depending on how the .vl document references the code:
  - **Source project reference** (.csproj) — vvvv compiles .cs files itself via Roslyn into in-memory assemblies. Changes live-reload on save. Node lifecycle restarts: Dispose() → new Constructor → Update() resumes. Static fields reset.
  - **Binary reference** (pre-compiled DLL or NuGet package) — loaded once at startup. Changes require restarting vvvv. Common for larger projects and stable libraries.
- The choice depends on project size and workflow — both are common in practice

## Important Conventions

- Process node name must NOT have a "Node" suffix
- `out` parameters come FIRST in `Update()`, value inputs with defaults come AFTER
- Zero allocations in the Update loop — cache everything, no LINQ in hot paths
- Change detection: only do work when parameters actually change
- Always output latest data (cached) even when no work is done

## Stride / Shader Integration

- Shaders use SDSL (Stride Shading Language), a superset of HLSL
- `static const` at shader root scope, `const` only inside functions
- Enum binding: `[EnumType("Namespace.EnumName, AssemblyName")]`
- Shader mixins for composition (not inheritance)

## Ecosystem

vvvv packages are NuGet packages containing .vl documents, C# nodes, and shaders. Key domains:

- **3D**: VL.Stride (Stride engine), VL.Fuse (GPU visual programming)
- **2D**: VL.Skia, ImGui, Avalonia, CEF/HTML
- **Hardware**: DMX/Art-Net, ILDA lasers, depth cameras (Azure Kinect, ZED), robotics, hand tracking, LiDAR
- **Network**: OSC, MIDI, MQTT, Redis, WebSocket, HTTP, TCP/UDP, ZeroMQ, Ableton Link
- **CV/ML**: OpenCV, MediaPipe, YOLO (v8–v11), ONNX Runtime
- **Audio**: NAudio, VST hosting, SuperCollider
- Standard NuGet packages (100k+) work directly via .csproj references.

## File Types

- `.vl` — vvvv gamma documents (XML-based, version controlled)
- `.sdsl` — Stride shader files
- `.cs` — C# source files for custom nodes
- `.csproj` — .NET project files

## Skill Development

This repository follows the [Agent Skills Specification](https://agentskills.io/specification). When creating or editing skills:

- `description` in frontmatter is what agents use to decide activation — be specific about when to use the skill
- SKILL.md body loads only after activation — don't repeat "when to use" info there
- Progressive disclosure: metadata (~100 tokens) → SKILL.md body (<500 lines) → supporting files (on demand)
- Only add vvvv-specific knowledge — agents already know C#, .NET, LINQ
- Reference supporting files from SKILL.md so agents know when to load them
- Validate with [skills-ref](https://github.com/agentskills/agentskills/tree/main/skills-ref): `skills-ref validate ./skills/your-skill`
