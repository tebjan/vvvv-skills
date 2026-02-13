# Patching Basics

## Description
Essential skills for creating and working with patches in vvvv gamma's visual programming environment.

## Key Concepts

### Creating a Patch
1. Open vvvv gamma
2. Create a new document or patch
3. Add nodes from the node browser (double-click or right-click)
4. Connect nodes by dragging from output pins to input pins
5. Set input values by clicking on pins

### Node Browser
- Double-click in patch to open node browser
- Type to search for nodes
- Categories: Control, Animation, Graphics, Math, String, etc.
- Shows available operations, processes, and custom nodes

### Making Connections
- Click and drag from an output pin to an input pin
- Type-compatible pins will highlight
- Middle-click or right-click a connection to delete
- Connections show data flow direction

### Setting Values
- Click on input pins to set constant values
- Right-click pins for more options
- Use IOBoxes for interactive value control
- Create configuration pins for process nodes

### Regions and Organization
- Create regions to group related nodes
- Collapse regions to simplify complex patches
- Name regions descriptively
- Use regions to manage visual complexity

### Process Nodes
- Define reusable sub-patches
- Have their own inputs and outputs
- Can maintain state between updates
- Encapsulate functionality

## Common Node Categories

### Math Operations
- `+`, `-`, `*`, `/` - Basic arithmetic
- `Damper` - Smooth value changes
- `Map` - Remap value ranges
- `Clamp` - Limit values to range

### Logic
- `AND`, `OR`, `NOT` - Boolean operations
- `If` - Conditional execution
- `Switch` - Select between inputs

### Collections (Spreads)
- `Cons` - Create spreads
- `GetSlice` - Extract elements
- `Count` - Get spread size
- `ForEach` - Iterate over spreads

### Time and Animation
- `LFO` - Low-frequency oscillator
- `Delay` - Frame delay
- `Timer` - Time-based operations
- `Stopwatch` - Measure time

### Input/Output
- `IOBox` - Interactive value boxes
- `Button`, `Toggle` - User controls
- `FileDialog` - File selection

## Best Practices

- **Top to bottom, left to right**: Arrange dataflow clearly
- **Use descriptive names**: Rename nodes and regions meaningfully
- **Group related logic**: Use regions to organize patches
- **Avoid crossing connections**: Keep patch layout clean
- **Add comments**: Use text annotations for complex logic
- **Test incrementally**: Build and test patches step by step
- **Create sub-patches**: Extract complex logic into process nodes

## Common Patterns

### Value Smoothing
```
Value -> Damper -> Output
```

### Conditional Processing
```
Condition -> If (Condition) -> Result
             Input Value
```

### Spread Iteration
```
Spread -> ForEach -> Process Each -> Collect Results
```

### Frame Delay (Break Cycles)
```
Output -> FrameDelay -> Input
```

## Common Pitfalls

- **Circular dependencies**: Use FrameDelay to break feedback loops
- **Type mismatches**: Ensure connected pins have compatible types
- **Uninitialized values**: Set default values or handle null cases
- **Too many nodes in one patch**: Split complex patches into sub-patches
- **Missing error handling**: Check for invalid inputs or edge cases
- **Forgetting to enable**: Some nodes need explicit enable/update triggers

## Keyboard Shortcuts

- **Double-click**: Open node browser
- **Ctrl+G**: Create region
- **Ctrl+Shift+G**: Expand region
- **Delete**: Remove selected nodes/connections
- **Ctrl+D**: Duplicate selected nodes
- **F9**: Show help for selected node

## Related Skills
- [Core Concepts](../core/fundamentals.md)
- [Working with Spreads](spreads-operations.md)
- [Animation Techniques](animation.md)
