---
name: vvvv-debugging
description: "Set up debugging for vvvv gamma C# node projects -- generate VS Code launch.json and tasks.json configurations, attach debugger to running vvvv, configure Visual Studio debug profiles, and use debugging best practices. Use when setting up a debugger for vvvv, creating launch configurations, attaching to vvvv process, or troubleshooting breakpoints in C# nodes. Supports multiple launch configs for different test scenarios/patches."
license: CC-BY-SA-4.0
compatibility: Designed for coding AI agents assisting with vvvv gamma development
metadata:
  author: Tebjan Halm
  version: "1.0"
---

# Debugging vvvv gamma C# Projects

For CLI arguments and session files, see the **vvvv-startup** skill.

## Context-Aware Setup Workflow

When the user asks to set up debugging, follow this workflow:

### 1. Detect vvvv Installation

Find vvvv.exe automatically:

```powershell
# Check registry first
Get-ChildItem "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\vvvv_gamma_*" |
  ForEach-Object { $_.GetValue("InstallLocation") } |
  Where-Object { Test-Path $_ }

# Fallback: scan Program Files
Get-ChildItem "C:\Program Files\vvvv\vvvv_gamma_*" -Directory |
  Sort-Object Name -Descending | Select-Object -First 1
```

Pick the latest version. Directory name format: `vvvv_gamma_MAJOR.MINOR[-PREVIEW-HASH-PLATFORM]`. Filter out `-beta`, `-alpha`, `-rc`, `-test`, `-dev` variants. Sort by major DESC, minor DESC, preview number DESC.

After detection, ask the user which vvvv to use, recommend the latest one, or ask for the path to vvvv.exe when non is found.

### 2. Scan Workspace

Detect what exists in the workspace:
- `.csproj` / `.sln` files (may or may not need build tasks -- see step 3)
- `.vl` files (candidates for `--open`)
- `help/` folders (common location for test patches)
- Existing `.vscode/launch.json` (extend rather than overwrite)
- Package names from repo folder name, main *.vl file or `.csproj` `<PackageId>` or folder name (for `--editable-packages`)

### 3. Determine C# Build Mode

This is critical -- ask the user which setup they have:

**Source project reference (no build task needed):** The .vl document references the .csproj directly. vvvv compiles the C# files at runtime via Roslyn. Changes live-reload on save. This is the most common and convenient workflow for small to medium C# projects. In this case, **omit `preLaunchTask`** from launch.json -- vvvv handles compilation itself.

**Binary/DLL reference (build task needed):** The .vl document references a pre-compiled DLL or NuGet package. The C# project must be built externally before launching vvvv. This is needed when:
- The project has native dependencies (C++/CLI, P/Invoke)
- Complex build scenarios (multi-project solutions, platform-specific targets)
- Performance testing with Release builds

In this case, **add `preLaunchTask: "build"`** and generate a tasks.json.

Note: Even with source project references, the agent may want to run `dotnet build` in the chat to detect build errors quickly, but this is separate from the F5 launch workflow.

### 4. Ask User

Ask the user:
- Which `.vl` patch(es) to open on launch (suggest help patches if found)
- Whether they need multiple launch configs for different test scenarios
- Any additional package repositories needed
- Whether their .vl document references the .csproj directly (source reference) or uses a pre-built DLL

### 5. Generate Configuration

Generate `.vscode/launch.json` and optionally `.vscode/tasks.json` (only if build task is needed).

## VS Code launch.json

### Source Reference (vvvv compiles C# -- most common)

No build task needed. vvvv compiles the .csproj at runtime:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Debug with vvvv",
      "type": "coreclr",
      "request": "launch",
      "program": "C:\\Program Files\\vvvv\\vvvv_gamma_7.0-win-x64\\vvvv.exe",
      "args": [
        "--package-repositories",
        "${workspaceFolder}",
        "--editable-packages",
        "VL.MyPackage*",
        "-o",
        "${workspaceFolder}/help/HowTo Use MyFeature.vl",
        "--debug",
        "--allowmultiple"
      ],
      "cwd": "${workspaceFolder}",
      "stopAtEntry": false,
      "console": "internalConsole"
    }
  ]
}
```

### DLL/Binary Reference (external build required)

Add `preLaunchTask` to build C# before launching vvvv:

```json
{
  "name": "Debug with vvvv (pre-build)",
  "type": "coreclr",
  "request": "launch",
  "preLaunchTask": "build",
  "program": "C:\\Program Files\\vvvv\\vvvv_gamma_7.0-win-x64\\vvvv.exe",
  "args": [
    "--package-repositories",
    "${workspaceFolder}",
    "--editable-packages",
    "VL.MyPackage*",
    "-o",
    "${workspaceFolder}/help/HowTo Use MyFeature.vl",
    "--debug",
    "--allowmultiple"
  ],
  "cwd": "${workspaceFolder}",
  "stopAtEntry": false,
  "console": "internalConsole"
}
```

Key points:
- **Omit `preLaunchTask`** for source references -- vvvv handles C# compilation via Roslyn
- **Add `preLaunchTask: "build"`** only for DLL/binary references or complex build scenarios
- `--debug` enables debug symbols (needed for breakpoints, but slows down patching -- see below)
- `--package-repositories` tells vvvv where to find your package (parent folder)
- `--editable-packages` loads specified packages from source (glob patterns supported)
- `-o` opens the specified .vl patch on startup
- Use array items for args (not a single string) for readability

### Always Generate Multiple Configurations

Always create at least a **Debug** and a **Release/Performance** configuration so the user can choose based on their current goal. Add additional configs for different test patches as needed:

```json
{
  "configurations": [
    {
      "name": "Debug with vvvv",
      "type": "coreclr",
      "request": "launch",
      "program": "C:\\Program Files\\vvvv\\vvvv_gamma_7.0-win-x64\\vvvv.exe",
      "args": [
        "--package-repositories", "${workspaceFolder}",
        "--editable-packages", "VL.MyPackage*",
        "-o", "${workspaceFolder}/help/HowTo Basic Feature.vl",
        "--debug", "--allowmultiple"
      ],
      "cwd": "${workspaceFolder}",
      "console": "internalConsole"
    },
    {
      "name": "Release / Performance Test",
      "type": "coreclr",
      "request": "launch",
      "program": "C:\\Program Files\\vvvv\\vvvv_gamma_7.0-win-x64\\vvvv.exe",
      "args": [
        "--package-repositories", "${workspaceFolder}",
        "--editable-packages", "VL.MyPackage*",
        "-o", "${workspaceFolder}/help/HowTo Basic Feature.vl",
        "--allowmultiple"
      ],
      "cwd": "${workspaceFolder}",
      "console": "internalConsole"
    },
    {
      "name": "Attach to vvvv",
      "type": "coreclr",
      "request": "attach",
      "processName": "vvvv.exe"
    }
  ]
}
```

### Attach to Running vvvv

Use attach when vvvv is already running and you want to debug without restarting:

```json
{
  "name": "Attach to vvvv",
  "type": "coreclr",
  "request": "attach",
  "processName": "vvvv.exe"
}
```

## VS Code tasks.json (only for DLL/binary reference setups)

Only generate tasks.json when the project requires external building (DLL references, native dependencies, Release builds). Skip this entirely for source project references where vvvv compiles C# at runtime.

### Build with dotnet

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "build",
      "command": "dotnet",
      "type": "process",
      "args": ["build", "${workspaceFolder}/src/MyProject.csproj", "-c", "Debug"],
      "problemMatcher": "$msCompile",
      "group": { "kind": "build", "isDefault": true }
    },
    {
      "label": "build-release",
      "command": "dotnet",
      "type": "process",
      "args": ["build", "${workspaceFolder}/src/MyProject.csproj", "-c", "Release"],
      "problemMatcher": "$msCompile"
    }
  ]
}
```

### Build with MSBuild (for .sln or projects requiring Visual Studio toolchain)

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "build",
      "type": "shell",
      "command": "& 'C:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\MSBuild\\Current\\Bin\\MSBuild.exe' '${workspaceFolder}/src/MyProject.sln' -p:Configuration=Debug -p:Platform=x64 -t:Rebuild -v:minimal",
      "options": {
        "shell": { "executable": "powershell.exe", "args": ["-Command"] }
      },
      "problemMatcher": "$msCompile",
      "group": { "kind": "build", "isDefault": true }
    }
  ]
}
```

Prefer `dotnet build` unless the project requires MSBuild-specific features or a .sln with platform targets.

## Visual Studio Setup

### Debug via External Program

1. Open `.csproj` in Visual Studio
2. **Debug** > **Debug Properties** (or Project Properties > Debug > General)
3. Create a new launch profile:
   - **Command**: path to `vvvv.exe`
   - **Command line arguments**: `--allowmultiple -o YourPatch.vl` (add `--debug` when breakpoints are needed)
   - **Working directory**: project folder
4. Press F5 to launch with debugger attached

### Attach to Process

1. Launch vvvv normally (add `--debug` if you need breakpoints)
2. **Debug** > **Attach to Process** (Ctrl+Alt+P)
3. Find `vvvv.exe` in the process list
4. Select **Managed (.NET Core, .NET 5+)** as code type
5. Click Attach

### launchSettings.json (dotnet tooling)

```json
{
  "profiles": {
    "Debug vvvv": {
      "commandName": "Executable",
      "executablePath": "C:\\Program Files\\vvvv\\vvvv_gamma_6.8-win-x64\\vvvv.exe",
      "commandLineArgs": "--allowmultiple --editable-packages \"VL.MyLib*\"",
      "workingDirectory": "$(ProjectDir)"
    }
  }
}
```

## Debugging Tips

- **`--debug`** -- forces debug symbol emission for reliable breakpoints, but adds overhead. Use in the Debug config; omit for performance/deployment testing.
- **`--stoppedonstartup`** -- launch paused so you can set breakpoints before any Update() runs
- **`--nocache`** -- if breakpoints won't bind, force recompilation from source
- **`Debugger.Break()`** -- add to C# code to programmatically trigger a breakpoint
- **Conditional breakpoints in Update()** -- Update() runs every frame, so use hit counts or conditions
- **Constructor breakpoints** -- fire on each live-reload cycle too (Dispose then new Constructor)
- **`console: "internalConsole"`** -- captures Console.WriteLine output in VS Code debug console
- **Debugger-attached behavior** -- when a .NET debugger is attached, vvvv initialization runs synchronously (no async exception trapping), so startup breakpoints work reliably
