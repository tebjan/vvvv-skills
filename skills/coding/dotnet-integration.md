# .NET Integration in vvvv gamma

## Description
Guide for integrating .NET libraries and leveraging the .NET ecosystem within vvvv gamma patches.

## Key Concepts

### NuGet Package Integration
- vvvv gamma can use any NuGet package
- Packages are referenced in project dependencies
- Automatically available in node browser after installation
- Version management through NuGet

### Using .NET Types
- .NET types appear as nodes in vvvv
- Static methods become operation nodes
- Instance methods work with object instances
- Extension methods are available
- Generic types can be used

### Common .NET Namespaces
- `System` - Core types and primitives
- `System.Collections.Generic` - Lists, Dictionaries, etc.
- `System.Linq` - Query operations
- `System.IO` - File and stream operations
- `System.Reactive` - Reactive programming

## Examples

### Using LINQ
```csharp
// In custom node
using System.Linq;

public Spread<int> FilterEven(Spread<int> numbers)
{
    return numbers.Where(n => n % 2 == 0).ToSpread();
}
```

### File Operations
```csharp
using System.IO;

public string ReadTextFile(string path)
{
    if (File.Exists(path))
        return File.ReadAllText(path);
    return string.Empty;
}
```

### Using NuGet Packages
```csharp
// After installing Newtonsoft.Json via NuGet
using Newtonsoft.Json;

public string SerializeObject<T>(T obj)
{
    return JsonConvert.SerializeObject(obj);
}

public T DeserializeObject<T>(string json)
{
    return JsonConvert.DeserializeObject<T>(json);
}
```

### Generic Collections
```csharp
using System.Collections.Generic;

public Dictionary<string, int> CreateDictionary(
    Spread<string> keys, 
    Spread<int> values)
{
    var dict = new Dictionary<string, int>();
    for (int i = 0; i < Math.Min(keys.Count, values.Count); i++)
    {
        dict[keys[i]] = values[i];
    }
    return dict;
}
```

## Best Practices

- **Choose appropriate packages**: Select well-maintained NuGet packages
- **Version compatibility**: Ensure packages target compatible .NET versions
- **Minimize dependencies**: Only add necessary packages
- **Error handling**: Wrap .NET calls with appropriate try-catch
- **Async operations**: Use Task-based async for I/O operations
- **Resource disposal**: Properly dispose IDisposable objects

## Common Patterns

### Async/Await Pattern
```csharp
using System.Threading.Tasks;

public async Task<string> FetchDataAsync(string url)
{
    using var client = new HttpClient();
    return await client.GetStringAsync(url);
}
```

### IObservable Pattern
```csharp
using System;
using System.Reactive.Linq;

public IObservable<long> CreateTimer(int intervalMs)
{
    return Observable.Interval(TimeSpan.FromMilliseconds(intervalMs));
}
```

### Extension Methods
```csharp
public static class StringExtensions
{
    public static string Reverse(this string str)
    {
        return new string(str.Reverse().ToArray());
    }
}
```

## Common Pitfalls

- **Blocking operations**: Avoid blocking the main thread with synchronous I/O
- **Memory leaks**: Remember to dispose resources and unsubscribe from events
- **Version conflicts**: Watch for NuGet package version conflicts
- **Platform dependencies**: Some packages may not work on all platforms
- **Large dependencies**: Heavy packages can increase application size

## Package Recommendations

### General Purpose
- `Newtonsoft.Json` - JSON serialization
- `System.Reactive` - Reactive programming
- `Microsoft.Extensions.*` - Dependency injection, logging, etc.

### Math and Science
- `MathNet.Numerics` - Advanced math operations
- `Accord.NET` - Machine learning and statistics

### Graphics
- `SkiaSharp` - 2D graphics
- `ImageSharp` - Image processing

### Networking
- `RestSharp` - REST API client
- `SignalR` - Real-time communication

## Related Skills
- [Custom Nodes](custom-nodes.md)
- [Async Operations](async-operations.md)
