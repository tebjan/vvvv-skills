# Advanced .NET Integration

## Blittable Structs for GPU/Network

For data that crosses GPU or network boundaries, use blittable structs:

```csharp
[StructLayout(LayoutKind.Sequential)]
public struct AnimationBlendState
{
    public int ClipIndex1;      // 4 bytes
    public float ClipTime1;     // 4 bytes
    public int ClipIndex2;      // 4 bytes
    public float ClipTime2;     // 4 bytes
    public float BlendWeight;   // 4 bytes
}
```

Rules: no reference type fields, no `bool` (use `int`), explicit layout. Enables `Span<T>` access and zero-copy serialization via `MemoryMarshal`.

## COM Interop Pitfalls (DX11/DX12)

When working with COM objects (Direct3D, DXGI):

- `ComPtr<T>` is a struct with no finalizer — if it goes out of scope without `Dispose()`, the COM ref leaks
- Always return ComPtrs to pools or explicitly Dispose them
- `IDXGISwapChain::ResizeBuffers` fails if any command list on the queue is in recording state

## C++/CLI Interop

For wrapping native C/C++ libraries:

```bash
msbuild MyCLIWrapper/MyCLIWrapper.vcxproj /p:Configuration=Release /p:Platform=x64
```

C++/CLI projects require Visual Studio (not dotnet CLI) for building.

## Directory.Build.props

For multi-project solutions, centralize settings:

```xml
<Project>
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <ManagePackageVersionsCentrally>true</ManagePackageVersionsCentrally>
  </PropertyGroup>
</Project>
```

## Threading Considerations

- `Update()` is always called on the VL main thread
- Use `SynchronizationContext` to post back to the VL thread from background tasks:

```csharp
private SynchronizationContext _vlSyncContext;

public MyNode()
{
    _vlSyncContext = SynchronizationContext.Current!;
}

// From background thread:
_vlSyncContext.Post(_ => { /* runs on VL thread */ }, null);
```
