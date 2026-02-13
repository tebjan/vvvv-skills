# Spread Processing Example

This example shows how to process spreads of data in vvvv gamma.

## Description
Various operations on spreads including filtering, mapping, and aggregation.

## C# Code

```csharp
using System.Linq;
using VL.Lib.Collections;

namespace Examples.SpreadProcessing
{
    /// <summary>
    /// Collection of spread processing operations
    /// </summary>
    public class SpreadOperations
    {
        /// <summary>
        /// Filter spread to only include values above threshold
        /// </summary>
        public Spread<float> FilterAbove(Spread<float> input, float threshold)
        {
            return input.Where(v => v > threshold).ToSpread();
        }

        /// <summary>
        /// Multiply all values in spread by a factor
        /// </summary>
        public Spread<float> Scale(Spread<float> input, float factor)
        {
            return input.Select(v => v * factor).ToSpread();
        }

        /// <summary>
        /// Calculate statistics for a spread
        /// </summary>
        public (float Sum, float Average, float Min, float Max) CalculateStats(Spread<float> input)
        {
            if (input.Count == 0)
                return (0, 0, 0, 0);

            return (
                Sum: input.Sum(),
                Average: input.Average(),
                Min: input.Min(),
                Max: input.Max()
            );
        }

        /// <summary>
        /// Combine two spreads element-wise
        /// </summary>
        public Spread<float> Combine(Spread<float> a, Spread<float> b, string operation)
        {
            return operation switch
            {
                "Add" => a.Zip(b, (x, y) => x + y).ToSpread(),
                "Multiply" => a.Zip(b, (x, y) => x * y).ToSpread(),
                "Max" => a.Zip(b, (x, y) => Math.Max(x, y)).ToSpread(),
                _ => a
            };
        }

        /// <summary>
        /// Create a range of values
        /// </summary>
        public Spread<float> CreateRange(float start, float end, int count)
        {
            if (count <= 0)
                return Spread<float>.Empty;

            var builder = new SpreadBuilder<float>();
            var step = (end - start) / (count - 1);
            
            for (int i = 0; i < count; i++)
            {
                builder.Add(start + i * step);
            }
            
            return builder.ToSpread();
        }
    }
}
```

## Usage Examples

### Filter Above Threshold
- Input: [1.5, 3.2, 0.8, 4.1, 2.3]
- Threshold: 2.0
- Output: [3.2, 4.1, 2.3]

### Scale Values
- Input: [1.0, 2.0, 3.0]
- Factor: 2.5
- Output: [2.5, 5.0, 7.5]

### Calculate Statistics
- Input: [10, 20, 30, 40, 50]
- Output: Sum=150, Avg=30, Min=10, Max=50

## Key Concepts Demonstrated

- LINQ operations on spreads
- SpreadBuilder for efficient construction
- Tuple returns for multiple outputs
- Pattern matching with switch expressions
- Edge case handling (empty spreads)

## Related Skills
- [Working with Spreads](../skills/core/spreads.md)
- [.NET Integration](../skills/coding/dotnet-integration.md)
