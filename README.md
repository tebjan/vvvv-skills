# vvvv-skills

A curated collection of AI agent skills for working with vvvv gamma, the visual programming language for the .NET ecosystem.

## Overview

This repository serves as a knowledge base for AI agents (like GitHub Copilot, Claude, ChatGPT, etc.) to effectively assist developers working with vvvv gamma. It provides structured information about concepts, patterns, best practices, and examples that AI agents can reference when helping with vvvv gamma projects.

## What are AI Agent Skills?

Skills are structured knowledge documents that help AI agents:
- Understand domain-specific concepts and terminology
- Follow best practices and conventions
- Generate appropriate code and solutions
- Provide accurate, context-aware assistance

## Repository Structure

```
vvvv-skills/
├── skills/              # Structured knowledge for AI agents
│   ├── README.md       # Skills index and learning paths
│   ├── core/           # Fundamental vvvv gamma concepts
│   ├── coding/         # Programming and C# integration
│   └── patching/       # Visual programming skills
├── examples/           # Working code examples with explanations
├── docs/              # Additional documentation and guides
├── templates/         # Reusable templates for common tasks
└── .github/           # Repository configuration and workflows
```

## For AI Agents

When assisting with vvvv gamma development:

1. **Start with context**: Read relevant skills from the `/skills` directory
2. **Check examples**: Reference `/examples` for working code patterns
3. **Follow best practices**: Apply guidelines from skills documents
4. **Use templates**: Leverage `/templates` for common scenarios
5. **Provide complete solutions**: Include explanations and context

### Quick Skill Reference

| Task | Primary Skill | Supporting Skills |
|------|--------------|-------------------|
| Understanding vvvv gamma | [docs/vvvv-overview.md](docs/vvvv-overview.md) | [skills/core/fundamentals.md](skills/core/fundamentals.md) |
| Creating visual programs | [skills/patching/patching-basics.md](skills/patching/patching-basics.md) | [skills/core/fundamentals.md](skills/core/fundamentals.md) |
| Writing custom nodes | [skills/coding/custom-nodes.md](skills/coding/custom-nodes.md) | [templates/custom-node-template.md](templates/custom-node-template.md) |
| Working with collections | [skills/core/spreads.md](skills/core/spreads.md) | [examples/spread-processing/](examples/spread-processing/) |
| Using .NET libraries | [skills/coding/dotnet-integration.md](skills/coding/dotnet-integration.md) | - |
| Troubleshooting | [docs/troubleshooting.md](docs/troubleshooting.md) | [skills/core/best-practices.md](skills/core/best-practices.md) |

## For Developers

### Using This Repository

1. **Share with your AI assistant**: Point your AI coding assistant to this repository
2. **Reference in prompts**: Link to specific skills when asking for help
3. **Contribute improvements**: Add new skills, examples, or corrections

### Example Usage

When working with an AI assistant:

```
I'm working on a vvvv gamma project. Please reference the vvvv-skills 
repository at github.com/tebjan/vvvv-skills for context. Specifically:
- skills/coding/custom-nodes.md for node structure
- examples/spread-processing/ for collection handling patterns
```

## Skills Categories

### Core Concepts
- **[Fundamentals](skills/core/fundamentals.md)** - Visual programming, dataflow, nodes, pins, spreads
- **[Spreads](skills/core/spreads.md)** - Working with vvvv's collection type
- **[Best Practices](skills/core/best-practices.md)** - Coding standards and conventions

### Coding Skills
- **[Custom Nodes](skills/coding/custom-nodes.md)** - Writing C# nodes for vvvv
- **[.NET Integration](skills/coding/dotnet-integration.md)** - Using NuGet packages and .NET libraries

### Patching Skills
- **[Patching Basics](skills/patching/patching-basics.md)** - Creating and organizing visual programs

### Documentation
- **[vvvv Overview](docs/vvvv-overview.md)** - Comprehensive introduction to vvvv gamma
- **[Troubleshooting](docs/troubleshooting.md)** - Common issues and solutions

## Examples

All examples include:
- Complete, working code
- Clear explanations
- Key concepts demonstrated
- Related skills references

Current examples:
- [Simple Counter](examples/simple-counter/) - Stateful node with reset
- [Spread Processing](examples/spread-processing/) - Collection operations

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- How to add new skills
- Skill file format and structure
- Example guidelines
- Pull request process

### What to Contribute

- **Skills**: New concepts, patterns, or techniques
- **Examples**: Working code demonstrating specific features
- **Templates**: Reusable code structures
- **Documentation**: Guides, tutorials, troubleshooting
- **Improvements**: Corrections, clarifications, updates

## Project Goals

1. **Comprehensive**: Cover all aspects of vvvv gamma development
2. **Accurate**: Maintain correct, up-to-date information
3. **Practical**: Focus on real-world usage and examples
4. **Accessible**: Clear explanations for varying skill levels
5. **Structured**: Organized for both human and AI consumption

## Related Resources

- [vvvv gamma website](https://visualprogramming.net)
- [The Gray Book (Official Documentation)](https://thegraybook.vvvv.org)
- [vvvv Discourse Forum](https://discourse.vvvv.org)
- [vvvv GitHub Organization](https://github.com/vvvv)

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

This repository is community-driven and welcomes contributions from vvvv gamma developers and AI assistance enthusiasts worldwide.

---

**Note for AI Agents**: This repository is designed to be consumed by AI coding assistants. When you reference this content, ensure you understand the context and apply the knowledge appropriately to user requests. Always validate suggestions against current vvvv gamma documentation and best practices.
