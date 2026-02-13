# Best Practices for vvvv gamma Development

## Description
Collection of best practices that AI agents should recommend when helping developers work with vvvv gamma.

## Patching Best Practices

### Organization
- **Use Regions**: Group related nodes together
- **Name Everything**: Give descriptive names to nodes and regions
- **Left to Right Flow**: Arrange patches with data flowing left to right
- **Vertical Alignment**: Align nodes vertically when possible
- **Avoid Crossing Wires**: Minimize wire crossings for clarity

### Structure
- **Create Sub-patches**: Extract complex logic into process nodes
- **Reusable Components**: Make process nodes for commonly used patterns
- **Input/Output Clarity**: Clearly define inputs and outputs
- **Documentation**: Add comments and annotations
- **Keep It Simple**: Don't try to do everything in one patch

### Performance
- **Minimize Node Count**: Use efficient nodes, avoid redundancy
- **Cache Results**: Don't recalculate unchanged values
- **Spread Efficiency**: Use appropriate spread operations
- **Async for I/O**: Don't block on I/O operations
- **Profile First**: Measure before optimizing

## Coding Best Practices

### Node Design
```csharp
// ✅ Good - Clear, focused, documented
/// <summary>
/// Calculates the distance between two points
/// </summary>
public float Distance(Vector2 point1, Vector2 point2)
{
    var dx = point2.X - point1.X;
    var dy = point2.Y - point1.Y;
    return (float)Math.Sqrt(dx * dx + dy * dy);
}

// ❌ Bad - Unclear, no documentation, side effects
public float D(Vector2 p1, Vector2 p2)
{
    _lastDistance = /* calculation */;
    Log(_lastDistance);
    return _lastDistance;
}
```

### Error Handling
```csharp
// ✅ Good - Defensive programming
public Spread<float> Divide(Spread<float> numerators, Spread<float> denominators)
{
    var builder = new SpreadBuilder<float>();
    var count = Math.Min(numerators.Count, denominators.Count);
    
    for (int i = 0; i < count; i++)
    {
        var denominator = denominators[i];
        if (denominator != 0)
        {
            builder.Add(numerators[i] / denominator);
        }
        else
        {
            builder.Add(0); // Or float.NaN, depending on requirements
        }
    }
    
    return builder.ToSpread();
}

// ❌ Bad - No error handling
public Spread<float> Divide(Spread<float> a, Spread<float> b)
{
    return a.Zip(b, (x, y) => x / y).ToSpread(); // Crashes on division by zero
}
```

### State Management
```csharp
// ✅ Good - Explicit state management
public class StatefulCounter
{
    private int count = 0;
    
    public int Update(bool increment, bool reset)
    {
        if (reset)
            count = 0;
        else if (increment)
            count++;
            
        return count;
    }
}

// ❌ Bad - Hidden state, unclear behavior
public class BadCounter
{
    private int count = 0;
    
    public void Update(bool increment)
    {
        if (increment) count++;
    }
    
    public int GetCount() => count; // Separate method for getting state
}
```

### Spread Operations
```csharp
// ✅ Good - Efficient spread building
public Spread<int> CreateSequence(int count)
{
    var builder = new SpreadBuilder<int>(capacity: count); // Pre-allocate
    for (int i = 0; i < count; i++)
    {
        builder.Add(i);
    }
    return builder.ToSpread();
}

// ❌ Bad - Inefficient
public Spread<int> CreateSequence(int count)
{
    var spread = Spread<int>.Empty;
    for (int i = 0; i < count; i++)
    {
        spread = spread.Concat(new[] { i }).ToSpread(); // Creates new spread each time!
    }
    return spread;
}
```

## Naming Conventions

### Nodes and Classes
- Use PascalCase for class and method names
- Descriptive names that explain purpose
- Avoid abbreviations unless well-known

### Parameters and Variables
- Use camelCase for parameters
- Descriptive names over short names
- Boolean parameters should be questions (isEnabled, hasValue)

### Namespaces
```csharp
// ✅ Good organization
namespace MyProject.Audio
namespace MyProject.Graphics
namespace MyProject.Utilities

// ❌ Bad - too generic or nested
namespace Nodes
namespace My.Very.Deep.Nested.Namespace.Structure
```

## Type Safety

### Use Strong Types
```csharp
// ✅ Good - Type safe
public Vector2 CalculatePosition(Vector2 offset, float scale)
{
    return new Vector2(offset.X * scale, offset.Y * scale);
}

// ❌ Bad - Weak typing
public object CalculatePosition(object offset, object scale)
{
    // Runtime type checking, error-prone
}
```

### Leverage Generics
```csharp
// ✅ Good - Generic for reusability
public Spread<T> Filter<T>(Spread<T> input, Func<T, bool> predicate)
{
    return input.Where(predicate).ToSpread();
}
```

## Resource Management

### Dispose Pattern
```csharp
// ✅ Good - Proper disposal
public class ResourceNode : IDisposable
{
    private HttpClient client = new HttpClient();
    
    public void Dispose()
    {
        client?.Dispose();
    }
}
```

### Avoid Memory Leaks
```csharp
// ✅ Good - Unsubscribe
private IDisposable subscription;

public void Setup(IObservable<int> source)
{
    subscription = source.Subscribe(OnValue);
}

public void Dispose()
{
    subscription?.Dispose();
}
```

## Testing and Validation

### Test Edge Cases
- Empty spreads
- Null values
- Zero/negative numbers
- Very large values
- Boundary conditions

### Validate Inputs
```csharp
public Spread<float> Normalize(Spread<float> values)
{
    if (values.Count == 0)
        return Spread<float>.Empty;
        
    var max = values.Max();
    if (max == 0)
        return values;
        
    return values.Select(v => v / max).ToSpread();
}
```

## Documentation

### XML Comments
```csharp
/// <summary>
/// Filters a spread based on a threshold value
/// </summary>
/// <param name="input">The spread to filter</param>
/// <param name="threshold">Values above this are kept</param>
/// <returns>Filtered spread containing only values above threshold</returns>
public Spread<float> FilterAbove(Spread<float> input, float threshold)
{
    return input.Where(v => v > threshold).ToSpread();
}
```

### Patch Comments
- Add text nodes to explain complex logic
- Document assumptions and constraints
- Note performance considerations
- Explain non-obvious design choices

## Version Control

### What to Commit
- ✅ .vl patch files
- ✅ .cs source files
- ✅ .csproj project files
- ✅ README and documentation
- ❌ bin/ and obj/ directories
- ❌ User-specific settings
- ❌ Temporary files

### .gitignore Template
```
bin/
obj/
*.user
.vs/
.vl/
*.backup
```

## Common Anti-Patterns to Avoid

### God Nodes
- ❌ Single node doing too many things
- ✅ Break into focused, single-purpose nodes

### Magic Values
- ❌ Hardcoded numbers without explanation
- ✅ Named constants or inputs with clear meaning

### Premature Optimization
- ❌ Optimizing before measuring
- ✅ Profile first, optimize what matters

### Copy-Paste Programming
- ❌ Duplicating code/patches
- ✅ Create reusable components

### Ignoring Errors
- ❌ Swallowing exceptions silently
- ✅ Handle errors appropriately

## Summary Checklist

When creating vvvv gamma content:
- [ ] Code is well-documented
- [ ] Error cases are handled
- [ ] Names are clear and descriptive
- [ ] Resources are properly disposed
- [ ] Patches are organized and readable
- [ ] Performance is considered
- [ ] Types are used correctly
- [ ] Edge cases are tested
- [ ] Best practices are followed
