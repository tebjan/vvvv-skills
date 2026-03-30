---
name: vvvv-editor-extensions
description: "Helps create vvvv gamma editor extensions — .HDE.vl file naming, Command node registration with keyboard shortcuts, SkiaWindow/SkiaWindowTopMost window types, docking with WindowFactory, and API access to hovered/selected nodes via VL.Lang Session nodes. Use when building editor plugins, custom tooling windows, HDE customization, visual programming editor tools, or automating editor workflows in vvvv."
license: CC-BY-SA-4.0
compatibility: Designed for coding AI agents assisting with vvvv gamma development
metadata:
  author: Tebjan Halm
  version: "1.0"
---

# Editor Extensions

Extensions are standard VL patches saved with a `.HDE.vl` suffix. They run automatically when open in the editor.

## Quick Start — Creating an Extension

1. **Create file:** Name it `VL.MyExtension.HDE.vl` (the `.HDE.vl` suffix is required)
2. **Add references:** Add `VL.HDE` dependency (provides Command, window types, WindowFactory)
3. **Add a Command node:** This registers your extension in the editor menu
4. **Connect to a window:** Wire the Command's bang output to open a SkiaWindow
5. **Test:** Press **Shift+F9** to restart all extensions and verify your command appears in the menu

## File Naming

| Context | Required Name |
|---|---|
| Standalone extension | `VL.MyExtension.HDE.vl` |
| Extension-only NuGet | `VL.MyExtension.HDE` (package ID) |
| Mixed NuGet main doc | `VL.MyPackage.vl` |
| Mixed NuGet extension doc | `VL.MyPackage.HDE.vl` |

## Required NuGet References

- **VL.HDE** — provides `Command` node, window types, `WindowFactory`
- **VL.Lang** — provides API nodes under the `Session` category (for reading/writing node data)

## Command Node

Registers a command in the editor menu:

| Pin | Purpose |
|---|---|
| `Label` | Menu text (e.g. "My Tool") |
| `Visible` | Show/hide the command in the menu |
| `Shortcut` | Keyboard binding (e.g. Ctrl+Shift+T) |
| Output | Bang — fires when the user activates the command |

Multiple `Command` nodes can live in one `.HDE.vl` document.

**Warning**: A runtime error in one command may affect all others in the same document.

## Window Types

| Type | Behavior |
|---|---|
| `SkiaWindow` | Slimmed-down Skia renderer window for custom UI |
| `SkiaWindowTopMost` | Always-on-top, no focus steal — useful for floating tools and overlays |

## Docking

To dock a window into the editor layout:

1. Create a **WindowFactory** node
2. Connect your **SkiaWindow** to the WindowFactory's `Window` input
3. Connect the **WindowContext** (from the extension's environment) to the `WindowContext` input
4. The window now appears as a dockable panel in the editor

**Template:** Use `VL.HDE/Template.HDE.vl` as a starting point — it includes a pre-wired Command, SkiaWindow, and WindowFactory setup.

## API Access — Reading Editor State

Access hovered/selected nodes and pin values via `VL.Lang` `Session` category nodes:

- **HoveredNode** — returns the node currently under the cursor
- **SelectedNodes** — returns all selected nodes in the active patch
- **ReadPin / WritePin** — read or write pin values programmatically

Browse the full API in the HelpBrowser's `API` section.

## Developer Shortcuts

- **Shift+F9** — restarts all extensions simultaneously (use during development)

## Limitations

- Settings panel integration is not yet possible
- Extensions only run in the editor, not in exported applications
