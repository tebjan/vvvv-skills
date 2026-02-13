# Simple Counter Example

This example demonstrates creating a simple stateful counter node in vvvv gamma.

## Description
A counter that increments when triggered and can be reset.

## C# Code

```csharp
using VL.Core;

namespace Examples.Counter
{
    /// <summary>
    /// A simple counter that increments on each update when enabled
    /// </summary>
    public class SimpleCounter
    {
        private int currentCount = 0;

        /// <summary>
        /// Update the counter
        /// </summary>
        /// <param name="increment">Whether to increment the counter</param>
        /// <param name="reset">Reset counter to zero</param>
        /// <returns>Current count value</returns>
        public int Update(bool increment, bool reset)
        {
            if (reset)
            {
                currentCount = 0;
            }
            else if (increment)
            {
                currentCount++;
            }
            
            return currentCount;
        }
    }
}
```

## Usage in Patch

1. Create a SimpleCounter node
2. Connect a Toggle to the increment input
3. Connect a Button to the reset input
4. Connect the output to an IOBox to display the count

## Key Concepts Demonstrated

- Stateful node (maintains count between updates)
- Multiple boolean inputs
- Conditional logic
- State reset functionality

## Related Skills
- [Custom Nodes](../../skills/coding/custom-nodes.md)
- [Patching Basics](../../skills/patching/patching-basics.md)
