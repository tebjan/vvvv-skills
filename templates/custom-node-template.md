# Custom Node Template

Use this template as a starting point for creating custom nodes in vvvv gamma.

## Simple Operation Node

```csharp
using VL.Core;
using VL.Lib.Collections;

namespace YourNamespace
{
    /// <summary>
    /// Description of what this node does
    /// </summary>
    public class YourNodeName
    {
        /// <summary>
        /// Description of the operation
        /// </summary>
        /// <param name="input1">Description of input1</param>
        /// <param name="input2">Description of input2</param>
        /// <returns>Description of output</returns>
        public OutputType YourOperation(InputType1 input1, InputType2 input2)
        {
            // Your implementation here
            var result = /* calculate result from inputs */;
            return result;
        }
    }
}
```

## Stateful Process Node

```csharp
using VL.Core;
using VL.Lib.Collections;

namespace YourNamespace
{
    /// <summary>
    /// Description of what this node does
    /// </summary>
    public class YourStatefulNode
    {
        // State fields
        private int state;

        /// <summary>
        /// Update method called each frame
        /// </summary>
        /// <param name="input">Description of input</param>
        /// <returns>Description of output</returns>
        public OutputType Update(InputType input)
        {
            // Update state
            // Calculate output
            var result = /* calculate based on state and input */;
            return result;
        }
    }
}
```

## Node with Multiple Outputs

```csharp
using VL.Core;
using VL.Lib.Collections;

namespace YourNamespace
{
    /// <summary>
    /// Description of what this node does
    /// </summary>
    public class MultiOutputNode
    {
        /// <summary>
        /// Operation with multiple outputs using tuple
        /// </summary>
        public (OutputType1 Output1, OutputType2 Output2, OutputType3 Output3) Process(InputType input)
        {
            // Your implementation
            return (output1, output2, output3);
        }
    }
}
```

## Spread Processing Node

```csharp
using System.Linq;
using VL.Lib.Collections;

namespace YourNamespace
{
    /// <summary>
    /// Description of spread processing
    /// </summary>
    public class SpreadProcessor
    {
        /// <summary>
        /// Process a spread of values
        /// </summary>
        public Spread<OutputType> ProcessSpread(Spread<InputType> input)
        {
            var builder = new SpreadBuilder<OutputType>();
            
            foreach (var item in input)
            {
                // Process each item
                builder.Add(ProcessItem(item));
            }
            
            return builder.ToSpread();
        }

        private OutputType ProcessItem(InputType item)
        {
            // Process single item
            var result = /* transform item */;
            return result;
        }
    }
}
```

## Generic Node

```csharp
using VL.Core;

namespace YourNamespace
{
    /// <summary>
    /// Generic node that works with any type
    /// </summary>
    public class GenericNode
    {
        /// <summary>
        /// Generic operation
        /// </summary>
        public T Process<T>(T input)
        {
            // Your implementation
            var result = input; // Process and return modified input
            return result;
        }
    }
}
```

## Checklist

When creating a custom node, ensure:

- [ ] Namespace is appropriate and discoverable
- [ ] Class and method names are descriptive
- [ ] XML documentation comments are added
- [ ] Parameters have meaningful names
- [ ] Edge cases are handled (null, empty spreads, invalid values)
- [ ] Return types are appropriate
- [ ] Stateful nodes properly manage state
- [ ] Spread operations use SpreadBuilder for efficiency
- [ ] Code follows C# naming conventions
- [ ] Node is tested in a patch

## Related Skills
- [Custom Nodes](../skills/coding/custom-nodes.md)
- [.NET Integration](../skills/coding/dotnet-integration.md)
- [Working with Spreads](../skills/core/spreads.md)
