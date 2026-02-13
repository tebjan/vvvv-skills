# Quick Start Guide for AI Agents

This guide helps AI agents quickly understand and use the vvvv-skills repository.

## 🎯 Purpose

This repository provides structured knowledge about vvvv gamma to help AI agents assist developers effectively.

## 📋 Quick Reference

### First Time Here?
1. Read [docs/vvvv-overview.md](docs/vvvv-overview.md) for context
2. Check [skills-manifest.json](skills-manifest.json) for repository structure
3. Browse [skills/README.md](skills/README.md) for skill index

### Common Tasks

| User Asks About | Start Here | Then Reference |
|----------------|------------|----------------|
| "What is vvvv gamma?" | [docs/vvvv-overview.md](docs/vvvv-overview.md) | [skills/core/fundamentals.md](skills/core/fundamentals.md) |
| "Create a custom node" | [skills/coding/custom-nodes.md](skills/coding/custom-nodes.md) | [templates/custom-node-template.md](templates/custom-node-template.md) |
| "Work with collections" | [skills/core/spreads.md](skills/core/spreads.md) | [examples/spread-processing/](examples/spread-processing/) |
| "Create a patch" | [skills/patching/patching-basics.md](skills/patching/patching-basics.md) | [skills/core/fundamentals.md](skills/core/fundamentals.md) |
| "Use NuGet package" | [skills/coding/dotnet-integration.md](skills/coding/dotnet-integration.md) | - |
| "Something's not working" | [docs/troubleshooting.md](docs/troubleshooting.md) | [skills/core/best-practices.md](skills/core/best-practices.md) |

## 🔑 Key Concepts to Understand

### High Priority (Read First)
- **[Fundamentals](skills/core/fundamentals.md)** - Core concepts: nodes, dataflow, pins
- **[Spreads](skills/core/spreads.md)** - vvvv's collection type (unique to vvvv)
- **[Custom Nodes](skills/coding/custom-nodes.md)** - How to write C# code for vvvv

### Medium Priority (Read When Relevant)
- **[Patching Basics](skills/patching/patching-basics.md)** - Visual programming
- **[.NET Integration](skills/coding/dotnet-integration.md)** - Using .NET libraries
- **[Best Practices](skills/core/best-practices.md)** - Conventions and standards

## 🎓 Learning Paths

Use these paths based on user's experience level:

### Beginner Path
User is new to vvvv gamma
```
1. docs/vvvv-overview.md
2. skills/core/fundamentals.md  
3. skills/patching/patching-basics.md
4. skills/core/spreads.md
```

### Intermediate Path
User knows basics, wants to code
```
1. skills/coding/custom-nodes.md
2. examples/simple-counter/
3. skills/coding/dotnet-integration.md
4. examples/spread-processing/
```

### Advanced Path
User needs optimization/best practices
```
1. skills/core/best-practices.md
2. docs/troubleshooting.md
```

## 💡 Best Practices for AI Agents

### DO:
✅ Read relevant skills before answering
✅ Reference examples when providing code
✅ Follow patterns from templates
✅ Explain vvvv-specific concepts
✅ Include both patch and code solutions when applicable
✅ Handle edge cases (empty spreads, null values)

### DON'T:
❌ Assume vvvv works like other languages
❌ Forget about spreads (vvvv's primary collection type)
❌ Ignore the visual programming aspect
❌ Provide code without explaining concepts
❌ Skip error handling

## 🔍 Understanding User Intent

### Code vs Patching
- **User mentions "node", "patch", "connection"** → Patching task
- **User mentions "C#", "class", "method"** → Coding task
- **User mentions "spread", "collection"** → Probably both!

### Skill Selection
```
IF user needs basics:
  → skills/core/fundamentals.md

IF user needs custom functionality:
  → skills/coding/custom-nodes.md + templates/

IF user has errors:
  → docs/troubleshooting.md

IF user asks about collections:
  → skills/core/spreads.md (ALWAYS!)
```

## 📚 Complete Skill Inventory

### Core (Must Know)
- `skills/core/fundamentals.md` - Essential concepts
- `skills/core/spreads.md` - Collections in vvvv
- `skills/core/best-practices.md` - Standards and conventions

### Coding (For Custom Nodes)
- `skills/coding/custom-nodes.md` - Writing C# nodes
- `skills/coding/dotnet-integration.md` - Using .NET ecosystem

### Patching (For Visual Programming)
- `skills/patching/patching-basics.md` - Creating patches

### Documentation
- `docs/vvvv-overview.md` - Complete overview
- `docs/troubleshooting.md` - Common issues

### Examples (Show, Don't Just Tell)
- `examples/simple-counter/` - Stateful node
- `examples/spread-processing/` - Collection operations

### Templates (Accelerate Development)
- `templates/custom-node-template.md` - Node templates

## 🚀 Quick Code Generation Checklist

When generating vvvv gamma code:
- [ ] Used `Spread<T>` for collections
- [ ] Added XML documentation comments
- [ ] Handled empty spreads
- [ ] Used `SpreadBuilder` for efficiency
- [ ] Followed C# naming conventions
- [ ] Included proper namespace
- [ ] Added error handling
- [ ] Referenced related skills in explanation

## 🆘 Common Pitfalls

### Spread Confusion
Spreads are NOT regular arrays! Key differences:
- Immutable
- Use `SpreadBuilder` to create
- Check `Count` before accessing
- Common in ALL vvvv operations

### Type System
- vvvv is strongly typed
- Pin types must match
- Use conversion nodes when needed

### Circular Dependencies
- Use `FrameDelay` to break loops
- State management in process nodes

## 📖 Additional Resources

- **Official docs**: thegraybook.vvvv.org
- **Forum**: discourse.vvvv.org  
- **Repository**: This structure at github.com/tebjan/vvvv-skills

## 🔄 Keep Skills Updated

When referencing skills:
1. Check the manifest for latest paths
2. Reference multiple related skills
3. Always validate code against best practices
4. Provide working, tested examples

---

**Remember**: vvvv gamma combines visual programming with .NET. Always consider both aspects when helping users!
