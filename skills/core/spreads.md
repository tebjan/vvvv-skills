# Working with Spreads

## Description
Understanding and working with Spreads, vvvv gamma's fundamental collection type for handling sequences of data.

## Key Concepts

### What are Spreads?
- Spreads are immutable sequences of values
- Similar to arrays or lists in other languages
- Type-safe collections: `Spread<T>` where T is the element type
- Can be empty, contain one element, or many elements

### Creating Spreads
- Use `SpreadBuilder<T>` to construct spreads efficiently
- Operations automatically handle spread semantics
- Literal values become single-element spreads

### Spread Count
- `Count` property returns number of elements
- Empty spread has Count = 0
- Operations can work on spreads of different counts

### Slicing and Indexing
- Zero-based indexing: first element is at index 0
- Negative indices count from end: -1 is last element
- Slicing operations can extract ranges

## Examples

### Creating Spreads in C#
```csharp
using VL.Lib.Collections;

// Using SpreadBuilder
public Spread<int> CreateSpread(int count)
{
    var builder = new SpreadBuilder<int>();
    for (int i = 0; i < count; i++)
    {
        builder.Add(i);
    }
    return builder.ToSpread();
}

// From existing collection
public Spread<string> FromList(List<string> items)
{
    return items.ToSpread();
}

// Empty spread
public Spread<float> CreateEmpty()
{
    return Spread<float>.Empty;
}
```

### Spread Operations
```csharp
// Map operation
public Spread<float> MultiplyAll(Spread<float> values, float factor)
{
    return values.Select(v => v * factor).ToSpread();
}

// Filter operation
public Spread<int> FilterPositive(Spread<int> values)
{
    return values.Where(v => v > 0).ToSpread();
}

// Reduce operation
public float Sum(Spread<float> values)
{
    return values.Sum();
}

// Combine spreads
public Spread<float> Add(Spread<float> a, Spread<float> b)
{
    return a.Zip(b, (x, y) => x + y).ToSpread();
}
```

### Spread Slicing
```csharp
// Get single element
public float GetAt(Spread<float> values, int index)
{
    if (index >= 0 && index < values.Count)
        return values[index];
    return 0;
}

// Get range
public Spread<T> GetRange<T>(Spread<T> values, int start, int count)
{
    return values.Skip(start).Take(count).ToSpread();
}
```

## Common Patterns

### Default Spread Behavior
- When counts don't match, operations typically use the shorter spread
- Some operations repeat the shorter spread to match the longer
- Check documentation for specific node behavior

### Spread Iteration
```
Input Spread -> ForEach -> Process Element -> Output Spread
```

### Spread Building
```csharp
var builder = new SpreadBuilder<Vector2>();
foreach (var point in points)
{
    if (IsValid(point))
        builder.Add(point);
}
return builder.ToSpread();
```

### Spread Combination
```csharp
// Zip two spreads together
var combined = spread1.Zip(spread2, (a, b) => new { A = a, B = b })
                     .ToSpread();
```

## Best Practices

- **Use SpreadBuilder**: Most efficient way to build spreads
- **Immutability**: Don't modify spreads, create new ones
- **Null safety**: Check for empty spreads before accessing elements
- **LINQ operations**: Leverage LINQ for transformations
- **Avoid repeated enumeration**: Cache spread results if used multiple times
- **Type consistency**: Keep spread element types consistent

## Common Nodes for Spreads

### Creation
- `Cons` - Construct spreads from individual values
- `LinearSpread` - Create evenly spaced values
- `RandomSpread` - Generate random spreads

### Access
- `GetSlice` - Extract elements by index
- `Count` - Get spread size
- `First`, `Last` - Get first/last elements

### Transformation
- `ForEach` - Apply operation to each element
- `Select` - Map transformation
- `Where` - Filter elements
- `Zip` - Combine spreads element-wise

### Aggregation
- `Sum`, `Average` - Reduce to single value
- `Min`, `Max` - Find extremes
- `Any`, `All` - Boolean checks

## Common Pitfalls

- **Index out of bounds**: Always check spread count before accessing
- **Empty spread operations**: Handle empty spreads appropriately
- **Count assumptions**: Don't assume spreads have specific counts
- **Modifying inputs**: Remember spreads are immutable
- **Performance**: Avoid creating large spreads in hot loops
- **Type mismatches**: Ensure spread element types are compatible

## Related Skills
- [Core Concepts](../core/fundamentals.md)
- [LINQ Operations](../coding/linq-usage.md)
- [Iteration Patterns](iteration-patterns.md)
