# Writing Custom Nodes in C#

## Description
Guide for AI agents on how to write custom nodes in C# for vvvv gamma, extending the functionality of patches with custom code.

## Key Concepts

### Node Definition
- Custom nodes are C# classes
- Use attributes to define node behavior
- Implement operations as methods
- Define pins as method parameters and return values

### Basic Node Structure
```csharp
using VL.Core;
using VL.Lib.Collections;

namespace MyNodes
{
    public class MyCustomNode
    {
        // Simple operation node
        public float Add(float a, float b)
        {
            return a + b;
        }
    }
}
```

### Process Nodes (Stateful)
```csharp
public class Counter
{
    private int count = 0;
    
    public int Update(bool increment)
    {
        if (increment)
            count++;
        return count;
    }
}
```

### Working with Spreads
```csharp
using VL.Lib.Collections;

public class SpreadProcessor
{
    public Spread<float> MultiplySpread(Spread<float> input, float factor)
    {
        var result = new SpreadBuilder<float>();
        foreach (var value in input)
        {
            result.Add(value * factor);
        }
        return result.ToSpread();
    }
}
```

### Observable Pattern
```csharp
using System;
using System.Reactive.Linq;

public class ObservableNode
{
    public IObservable<int> CreateSequence(int count)
    {
        return Observable.Range(0, count);
    }
}
```

## Best Practices

- **Use appropriate naming**: Follow C# and vvvv naming conventions
- **Handle edge cases**: Check for null, empty spreads, invalid ranges
- **Immutability**: Prefer immutable operations where possible
- **Performance**: Consider performance for operations on large spreads
- **Documentation**: Add XML comments to document node behavior
- **Type safety**: Use strong typing and avoid dynamic types when possible

## Common Patterns

### Input/Output Pins
```csharp
// Multiple outputs via tuple
public (float Sum, float Average) Calculate(Spread<float> values)
{
    var sum = values.Sum();
    var avg = values.Count > 0 ? sum / values.Count : 0;
    return (sum, avg);
}
```

### Optional Inputs
```csharp
public float ProcessValue(float input, float multiplier = 1.0f)
{
    return input * multiplier;
}
```

### Generic Nodes
```csharp
public T PassThrough<T>(T input)
{
    return input;
}
```

## Common Pitfalls

- **Forgetting to handle empty spreads**: Always check spread count before accessing elements
- **Mutating input data**: Avoid modifying input spreads directly
- **Heavy computation in Update**: Keep update methods lightweight
- **Not using SpreadBuilder**: Use SpreadBuilder for efficient spread creation
- **Incorrect namespace**: Ensure nodes are in a namespace that vvvv can discover

## Related Skills
- [.NET Integration](dotnet-integration.md)
- [Spreads and Collections](../core/spreads.md)
