---
name: vvvv-patching
description: "Explains vvvv gamma visual programming patterns — dataflow, node connections, regions (ForEach/If/Switch/Repeat/Accumulator), channels for reactive data flow, event handling (Bang/Toggle/FrameDelay/Changed), patch organization, and common anti-patterns (circular dependencies, polling vs reacting, ignoring Nil). Use when the user asks about patching best practices, dataflow patterns, event handling, or how to structure visual programs."
license: CC-BY-SA-4.0
compatibility: Designed for coding AI agents assisting with vvvv gamma development
metadata:
  author: Tebjan Halm
  version: "1.0"
---

# vvvv Patching Patterns

## Dataflow Basics

- **Left-to-right, top-to-bottom** execution order
- **Links** carry data between pads (input/output connection points)
- **Spreading** — connecting a `Spread<T>` to a single-value input auto-iterates the node
- Every frame, the entire connected graph evaluates; disconnected subgraphs are skipped

## When to Patch vs Write C#

| Patch | Code (C#) |
|---|---|
| Data flow routing, visual connections | Performance-critical algorithms |
| Prototyping and parameter tweaking | Complex state machines |
| UI composition and layout | .NET library interop |
| Simple transformations | Native resource management |

As a rule: **patch the data flow, code the algorithms**.

## Regions

Regions control execution flow inside patches:

| Region | Purpose | C# Equivalent |
|---|---|---|
| **ForEach** | Iterate over Spread elements | `foreach` loop |
| **If** | Conditional execution | `if/else` |
| **Switch** | Multi-branch selection | `switch` |
| **Repeat** | Loop N times | `for` loop |
| **Accumulator** | Running aggregation | `Aggregate/Fold` |

### ForEach — Processing a Spread

1. Create a ForEach region around the nodes you want to iterate
2. Connect a `Spread<T>` to an input splicer on the region boundary — each iteration receives one element
3. Place processing nodes inside the region
4. Connect results to an output splicer — the region collects them back into a `Spread<T>`

**Validation:** The output Spread count should match the input Spread count (for map operations). If it doesn't, check that you connected the splicers correctly.

### If — Conditional Execution

1. Create an If region
2. Connect a boolean condition to the region's Condition pin
3. Place nodes inside — they only execute when the condition is true
4. Use the Else output for the false branch

## Event Handling

| Node | Behavior | Use When |
|---|---|---|
| **Bang** | One-frame `true` pulse | Triggering actions (load file, reset state, send message) |
| **Toggle** | Alternates `true`/`false` | Toggling visibility, play/pause, enable/disable |
| **FrameDelay** | Delays value by one frame | Breaking circular dependencies, feedback loops |
| **Changed** | Detects value changes | Reacting only when input actually changes between frames |

### Breaking a Circular Dependency

When two nodes depend on each other's output:

1. Identify the circular link (vvvv shows an error)
2. Insert a **FrameDelay** node on one of the feedback links
3. Connect the output through FrameDelay before feeding it back
4. **Verify:** The error disappears and the output stabilizes after 1-2 frames

### Reacting to Changes (Not Polling)

Instead of checking a value every frame:

1. Use **Changed** node on the input you want to monitor
2. Connect Changed's bang output to trigger the downstream operation
3. This ensures work only happens when the value actually changes

## Channels — Reactive Data Flow

- `IChannel<T>` — observable value container
- `.Value` — read or write the current value
- Channels persist state across sessions
- Connect channels between nodes for reactive updates without explicit links

### Setting Up a Channel Connection

1. Create a **Channel** node (or use a GlobalChannel for cross-document sharing)
2. Connect it to a consuming node's channel input
3. Write to the channel from one location — all connected readers update automatically
4. Use **ChannelOfValue** to convert between channels and plain values

## Patch Organization

### Naming Conventions
- Use PascalCase for patch names and node names
- Group related operations under a common category
- Use descriptive names that indicate the operation (verb + noun)

### Structure
- Keep patches focused — one purpose per patch
- Extract reusable logic into sub-patches
- Use **IOBox** nodes for exposing parameters
- Add **Pad** nodes to create input/output pins on the patch boundary

### Debugging a Patch That Isn't Updating

1. Check that the node is **connected** — disconnected subgraphs don't evaluate
2. Hover over links to inspect values flowing through them
3. Insert **IOBox** nodes at intermediate points to visualize data
4. Check for **Nil** (null) inputs — they silently skip evaluation in many nodes
5. Verify region splicers are connected on both sides

## Common Anti-Patterns

| Anti-Pattern | Problem | Fix |
|---|---|---|
| Circular dependencies | Execution deadlock | Insert **FrameDelay** to break the cycle |
| Too many nodes in one patch | Hard to read and maintain | Extract sub-patches by selecting nodes → right-click → Group |
| Polling instead of reacting | Wasted computation every frame | Use **Changed** node or **Channels** for reactive updates |
| Ignoring Nil | Silent failures, missing data | Add Nil checks or default values before processing |

For more patterns (state machines, caching, animation, resource lifecycle), see [patterns.md](patterns.md).
