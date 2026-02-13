# Core vvvv gamma Concepts

## Description
This skill covers the fundamental concepts of vvvv gamma that AI agents need to understand to provide effective assistance with vvvv gamma development.

## Key Concepts

### Visual Programming Language
- vvvv gamma is a node-based visual programming environment
- Programs are called "patches" and consist of connected nodes
- Data flows through connections from left to right, top to bottom
- Nodes process data and pass results to connected nodes

### Dataflow Programming
- vvvv uses a dataflow paradigm where data flows through the graph
- Changes propagate automatically through the patch
- No explicit execution order - determined by data dependencies
- Reactive updates when inputs change

### .NET Integration
- vvvv gamma is built on .NET (primarily .NET 6+)
- Can use any .NET library via NuGet packages
- Custom nodes can be written in C#
- Full access to the .NET ecosystem

### Node Types
1. **Operation Nodes** - Perform calculations or transformations
2. **Source Nodes** - Generate or input data
3. **Sink Nodes** - Output or consume data
4. **Region Nodes** - Group and organize patches
5. **Process Nodes** - Define reusable sub-patches

### Pins
- Nodes have input pins (left side) and output pins (right side)
- Pins have types (string, float, boolean, etc.)
- Type-safe connections between compatible pins
- Default values can be set on input pins

### Spreads
- vvvv's primary data structure for collections
- Similar to arrays or lists in other languages
- Can represent sequences of values
- Operations can work on entire spreads at once
- Spread operators handle iteration automatically

## Best Practices

- Keep patches organized and well-structured
- Use meaningful node names and comments
- Group related functionality into regions
- Create reusable process nodes for common operations
- Follow dataflow from left to right

## Common Pitfalls

- **Circular dependencies**: Avoid creating loops in dataflow without proper framedelay
- **Type mismatches**: Ensure pin types are compatible when making connections
- **Spread count mismatches**: Be aware of spread counts in operations
- **Missing null checks**: Handle null or empty spreads appropriately

## Related Skills
- [Patching Basics](../patching/patching-basics.md)
- [.NET Integration](../coding/dotnet-integration.md)
