# vvvv gamma Overview for AI Agents

This document provides AI agents with an overview of vvvv gamma to help them assist developers effectively.

## What is vvvv gamma?

vvvv gamma is a visual programming environment for .NET that combines:
- **Visual Programming**: Node-based patching interface
- **.NET Integration**: Full access to .NET libraries and ecosystem
- **Dataflow Programming**: Reactive, declarative programming model
- **Live Programming**: Immediate feedback and hot-reload capabilities

## Target Use Cases

- Interactive installations and exhibitions
- Media art and creative coding
- Data visualization
- Prototyping and experimentation
- Education and research
- Real-time graphics and audio

## Key Characteristics

### Visual First
- Programs (patches) are created by connecting nodes
- No need to write code for many tasks
- Visual representation of data flow and logic

### .NET Powered
- Built on modern .NET (6+)
- Can use any NuGet package
- Custom nodes written in C#
- Interoperability with .NET libraries

### Reactive and Live
- Changes take effect immediately
- No compile-wait-run cycle for patches
- Dataflow automatically propagates changes

### Type Safe
- Strong typing throughout
- Type errors caught at patch time
- IntelliSense-like features in node browser

## Core Concepts

### Nodes
- Basic building blocks
- Have inputs (left) and outputs (right)
- Perform operations on data
- Can be built-in or custom

### Patches
- Visual programs made of connected nodes
- Can be saved and reused
- Can be nested (patches within patches)
- Support regions for organization

### Spreads
- Primary collection type
- Immutable sequences of values
- Automatically handled by many operations
- Similar to arrays/lists but with special semantics

### Pins
- Inputs and outputs on nodes
- Typed (int, float, string, custom types, etc.)
- Can have default values
- Support spreads

## Development Workflow

1. **Create Patch**: Start with a new patch file (.vl)
2. **Add Nodes**: Double-click to open node browser, select nodes
3. **Connect Nodes**: Wire outputs to inputs
4. **Set Values**: Configure input values
5. **Test Live**: See results immediately
6. **Refine**: Adjust and iterate
7. **Export**: Create executable or library

## When to Write Code vs Patch

### Use Patching For:
- Data flow and transformations
- Visual logic and connections
- Quick prototyping
- Combining existing functionality
- UI and interaction logic

### Write Custom Nodes For:
- Complex algorithms
- Performance-critical operations
- Integration with specific .NET libraries
- Reusable components
- Stateful operations

## Common Patterns

### Input → Process → Output
Basic dataflow pattern

### State Management
Use process nodes with internal state

### Event Handling
Use Observable pattern from .NET

### Collections Processing
Use spread operations and ForEach

### Conditional Logic
Use If nodes and switches

## Best Practices for AI Assistance

When helping developers with vvvv gamma:

1. **Understand the Context**: Is this about patching or coding?
2. **Suggest Appropriate Approach**: Patch-based or code-based solution
3. **Provide Working Examples**: Complete, tested examples
4. **Explain Concepts**: Don't assume prior knowledge
5. **Follow Conventions**: Use vvvv naming and patterns
6. **Consider Performance**: Efficient spread operations
7. **Handle Edge Cases**: Empty spreads, null values, etc.

## Resources

- Official Website: visualprogramming.net
- Documentation: thegraybook.vvvv.org
- Forum: discourse.vvvv.org
- GitHub: github.com/vvvv

## Common Misconceptions

❌ **vvvv is only for graphics** - It's a general-purpose programming environment
❌ **Can't use text-based code** - C# nodes are fully supported
❌ **Limited to simple tasks** - Can build complex applications
❌ **Slow performance** - .NET performance with JIT compilation
❌ **Isolated from .NET** - Full .NET ecosystem access

## Questions AI Agents Should Ask

Before providing assistance:
- What are you trying to achieve?
- Do you prefer a patching or coding solution?
- What data types are you working with?
- Are there performance constraints?
- Do you have existing code/patches to build on?
