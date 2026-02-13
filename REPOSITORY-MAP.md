# Repository Map

Visual guide to navigating the vvvv-skills repository.

## 🗺️ Navigation Guide

```
START HERE
    ↓
┌─────────────────────────────────────┐
│  👤 Are you a human or AI agent?   │
└─────────────────────────────────────┘
         ↓                    ↓
    [HUMAN]              [AI AGENT]
         ↓                    ↓
    README.md          AI-QUICKSTART.md
         ↓                    ↓
         └────────┬───────────┘
                  ↓
         What do you need?
                  ↓
    ┌─────────────┼─────────────┐
    ↓             ↓             ↓
[LEARN]      [CREATE]      [SOLVE]
    ↓             ↓             ↓
```

## 🎯 By Goal

### LEARN About vvvv gamma
```
docs/vvvv-overview.md
    ↓
skills/core/fundamentals.md
    ↓
skills/patching/patching-basics.md
    ↓
examples/*
```

### CREATE Something New
```
What are you creating?
    ↓
┌───────┬──────────┬─────────┐
│       │          │         │
Patch   Node    Integration
│       │          │
↓       ↓          ↓
skills/ skills/    skills/
patching/ coding/  coding/
patching- custom-  dotnet-
basics.md nodes.md integration.md
    ↓       ↓          ↓
examples/ templates/ examples/
```

### SOLVE a Problem
```
docs/troubleshooting.md
    ↓
Search for your issue
    ↓
Found? ──No──→ skills/core/best-practices.md
  ↓
 Yes
  ↓
Apply solution
```

## 📁 Directory Purpose

| Directory | Purpose | When to Use |
|-----------|---------|-------------|
| `skills/core/` | Fundamental concepts | Learning basics, understanding architecture |
| `skills/coding/` | Programming guide | Writing C# code, custom nodes |
| `skills/patching/` | Visual programming | Creating patches, connecting nodes |
| `examples/` | Working code | Need real examples, want to see patterns |
| `templates/` | Code starters | Quick start for new components |
| `docs/` | Deep dives | Need comprehensive understanding |

## 🎓 Learning Paths

### Path 1: Complete Beginner
```
1. docs/vvvv-overview.md          [15 min read]
2. skills/core/fundamentals.md     [10 min read]
3. skills/patching/patching-basics.md [15 min read]
4. skills/core/spreads.md          [10 min read]
5. Try: examples/simple-counter/   [Practice]
```
**Total time**: ~1 hour

### Path 2: Programmer (knows C#, new to vvvv)
```
1. docs/vvvv-overview.md          [15 min read]
2. skills/core/fundamentals.md     [10 min read]
3. skills/core/spreads.md          [10 min read]
4. skills/coding/custom-nodes.md   [15 min read]
5. Try: examples/spread-processing/ [Practice]
```
**Total time**: ~1 hour

### Path 3: Visual Programmer (knows visual tools, new to vvvv)
```
1. docs/vvvv-overview.md          [15 min read]
2. skills/core/fundamentals.md     [10 min read]
3. skills/patching/patching-basics.md [15 min read]
4. skills/coding/custom-nodes.md   [10 min read - optional]
```
**Total time**: ~45 min

### Path 4: Quick Reference
```
skills/README.md → Quick Reference Table → Specific Skill
```
**Total time**: 2 minutes to find what you need

## 🔍 Find Information By Topic

### Collections / Spreads
- Primary: `skills/core/spreads.md`
- Example: `examples/spread-processing/`
- Related: `skills/coding/dotnet-integration.md` (LINQ section)

### Custom Nodes
- Primary: `skills/coding/custom-nodes.md`
- Template: `templates/custom-node-template.md`
- Example: `examples/simple-counter/`
- Related: `skills/core/best-practices.md`

### Visual Programming
- Primary: `skills/patching/patching-basics.md`
- Related: `skills/core/fundamentals.md`
- Overview: `docs/vvvv-overview.md`

### .NET Integration
- Primary: `skills/coding/dotnet-integration.md`
- Related: `skills/coding/custom-nodes.md`
- Example: `examples/spread-processing/` (uses LINQ)

### Best Practices
- Primary: `skills/core/best-practices.md`
- Related: ALL skill documents have "Best Practices" sections
- Guide: `docs/skill-development-guide.md`

### Troubleshooting
- Primary: `docs/troubleshooting.md`
- Related: All skills have "Common Pitfalls" sections

## 🤖 AI Agent Decision Tree

```
User asks about vvvv
    ↓
Do I understand vvvv? ──No──→ Read docs/vvvv-overview.md
    ↓
   Yes
    ↓
What's the task type?
    ↓
┌─────────┬──────────┬─────────┬────────────┐
│         │          │         │            │
Concept  Coding   Patching  Problem
│         │          │         │
↓         ↓          ↓         ↓
skills/   skills/  skills/   docs/
core/     coding/  patching/ troubleshooting.md
    ↓         ↓          ↓         ↓
Read skill → Generate solution → Reference examples
```

## 📊 File Relationships

```
README.md (entry point)
    │
    ├─→ AI-QUICKSTART.md (AI agents start here)
    │
    ├─→ skills-manifest.json (machine-readable structure)
    │       │
    │       └─→ Lists all skills with metadata
    │
    ├─→ skills/ (knowledge base)
    │       │
    │       ├─→ core/ (fundamentals, spreads, best-practices)
    │       ├─→ coding/ (custom-nodes, dotnet-integration)
    │       └─→ patching/ (patching-basics)
    │
    ├─→ examples/ (working code)
    │       │
    │       ├─→ simple-counter/
    │       └─→ spread-processing/
    │
    ├─→ templates/ (starting points)
    │       │
    │       └─→ custom-node-template.md
    │
    └─→ docs/ (deep documentation)
            │
            ├─→ vvvv-overview.md
            ├─→ troubleshooting.md
            └─→ skill-development-guide.md
```

## 🚀 Quick Actions

| I want to... | Go to... |
|--------------|----------|
| Understand vvvv gamma | `docs/vvvv-overview.md` |
| Write a custom node | `templates/custom-node-template.md` |
| Work with collections | `skills/core/spreads.md` |
| Create a patch | `skills/patching/patching-basics.md` |
| Fix an error | `docs/troubleshooting.md` |
| Learn best practices | `skills/core/best-practices.md` |
| See working code | `examples/` |
| Contribute a skill | `docs/skill-development-guide.md` |
| Find all skills | `skills/README.md` |
| Quick AI reference | `AI-QUICKSTART.md` |

## 📈 Skill Priority Matrix

### High Priority (Start Here)
- ⭐⭐⭐ `skills/core/fundamentals.md`
- ⭐⭐⭐ `skills/core/spreads.md`
- ⭐⭐⭐ `skills/coding/custom-nodes.md`

### Medium Priority (Common Tasks)
- ⭐⭐ `skills/patching/patching-basics.md`
- ⭐⭐ `skills/coding/dotnet-integration.md`
- ⭐⭐ `skills/core/best-practices.md`

### Reference (As Needed)
- ⭐ `docs/troubleshooting.md`
- ⭐ `docs/vvvv-overview.md`

## 🔄 Update Workflow

When adding new content:
```
1. Create skill/example/template
2. Update skills-manifest.json
3. Update skills/README.md
4. Update this map if needed
5. Update CONTRIBUTING.md if workflow changes
```

---

**Tip**: Bookmark this page for quick navigation!
