# Common Troubleshooting Guide

This guide helps AI agents assist with common issues in vvvv gamma development.

## Compilation Errors

### "Cannot find type or namespace"
**Problem**: Missing reference to .NET library or namespace

**Solutions**:
- Add required NuGet package to dependencies
- Check namespace imports in custom nodes
- Verify package version compatibility with .NET version

### "Type mismatch" in connections
**Problem**: Trying to connect incompatible pin types

**Solutions**:
- Use type conversion nodes (ToInt, ToFloat, ToString)
- Check if spread vs single value is causing issue
- Verify generic type parameters match

## Runtime Issues

### Null Reference Exceptions
**Problem**: Accessing null objects or empty spreads

**Solutions**:
```csharp
// Check before accessing
if (spread.Count > 0)
{
    var value = spread[0];
}

// Use null-conditional operator
var result = obj?.Method();

// Provide defaults
var value = spread.FirstOrDefault();
```

### Circular Dependency
**Problem**: Feedback loop in patch causing infinite update

**Solutions**:
- Insert FrameDelay node to break the cycle
- Redesign dataflow to avoid circular reference
- Use proper state management in process nodes

### Spread Count Mismatch
**Problem**: Operations expecting same-sized spreads

**Solutions**:
- Use Zip for element-wise operations
- Use Cons to create matching spread sizes
- Handle different sizes explicitly in custom nodes

## Performance Issues

### Slow Frame Rate
**Problem**: Patch updating too slowly

**Solutions**:
- Profile to find bottleneck
- Reduce spread sizes if possible
- Move complex operations to custom nodes
- Use caching for expensive calculations
- Consider async operations for I/O

### Memory Leaks
**Problem**: Memory usage growing over time

**Solutions**:
```csharp
// Dispose resources properly
public class ResourceUser : IDisposable
{
    private IDisposable resource;
    
    public void Dispose()
    {
        resource?.Dispose();
    }
}

// Unsubscribe from events
observable.Subscribe(handler); // Store subscription
subscription.Dispose(); // Clean up
```

## Patching Issues

### Nodes Not Appearing in Browser
**Problem**: Custom nodes not visible

**Solutions**:
- Check namespace is correct
- Ensure class and methods are public
- Verify .NET project is referenced correctly
- Rebuild custom node project
- Restart vvvv gamma

### Connections Won't Connect
**Problem**: Cannot create connection between pins

**Solutions**:
- Verify types are compatible
- Check if conversion node is needed
- Ensure output → input direction
- Look for type constraints

### Values Not Updating
**Problem**: Changes not reflected in patch

**Solutions**:
- Check if Enable pin is true
- Verify upstream nodes are updating
- Look for disabled regions
- Check if value is being overwritten

## Common Code Issues

### SpreadBuilder Not Working
**Problem**: Spread building produces errors

**Solution**:
```csharp
// Correct usage
var builder = new SpreadBuilder<float>();
builder.Add(1.0f);
builder.Add(2.0f);
var spread = builder.ToSpread(); // Don't forget ToSpread()
```

### Async/Await Issues
**Problem**: Async code not working properly

**Solutions**:
```csharp
// Use Task-based async
public async Task<string> FetchAsync(string url)
{
    using var client = new HttpClient();
    return await client.GetStringAsync(url);
}

// Don't block in update methods
// ❌ Bad
public string Update(string url)
{
    return FetchAsync(url).Result; // Blocks!
}

// ✅ Good - return Task
public Task<string> Update(string url)
{
    return FetchAsync(url);
}
```

### LINQ Enumeration Issues
**Problem**: Multiple enumeration causing performance issues

**Solution**:
```csharp
// ❌ Bad - enumerates twice
var filtered = input.Where(x => x > 0);
var count = filtered.Count();
var first = filtered.First();

// ✅ Good - enumerate once
var filtered = input.Where(x => x > 0).ToSpread();
var count = filtered.Count;
var first = filtered[0];
```

## Debugging Tips

### Using Tooltips
- Hover over pins to see current values
- Useful for tracking data through patch
- Shows spread contents

### IOBoxes for Inspection
- Add IOBox nodes to visualize intermediate values
- Can show spreads, objects, primitives
- Toggle visibility as needed

### Stepping Through Custom Nodes
- Attach debugger to vvvv gamma process
- Set breakpoints in custom node code
- Inspect variables and state

### Logging
```csharp
using System.Diagnostics;

public void LogDebug(string message)
{
    Debug.WriteLine($"[MyNode] {message}");
    // View in Output window when debugging
}
```

## Error Message Reference

| Error | Meaning | Solution |
|-------|---------|----------|
| "Pin type mismatch" | Incompatible types | Add conversion node |
| "Circular dependency detected" | Feedback loop | Add FrameDelay |
| "Object reference not set" | Null value | Add null check |
| "Index out of range" | Invalid spread index | Check Count first |
| "Cannot convert type" | Type conversion failed | Use proper conversion |

## When to Ask for Help

If you encounter:
- Repeated crashes
- Unclear error messages
- Performance issues after optimization
- Platform-specific problems
- Complex architectural questions

Suggest consulting:
- vvvv forums (discourse.vvvv.org)
- Gray Book documentation
- Community chat
- GitHub issues for specific packages
