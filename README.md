# vvvv-skills

Skills for AI coding agents to master the [vvvv gamma](https://vvvv.org) ecosystem.

## What This Is

This repository contains **agent skills** — structured knowledge packages that AI coding agents load automatically when assisting with vvvv gamma development. Each skill covers a specific topic (Spreads, custom nodes, shaders, etc.) and follows the open [Agent Skills](https://agentskills.io) standard.

Skills work with any compatible coding AI agent, including Claude Code, OpenAI Codex CLI, Cursor, Windsurf, GitHub Copilot, and [many others](https://skills.sh).

vvvv gamma is a live programming environment for .NET — programs run continuously while you build them. C# source files are compiled by vvvv itself via Roslyn and take effect without restart. The ecosystem spans 3D/2D rendering, hardware control (DMX, lasers, depth cameras, robotics), networking (OSC, MQTT, WebSocket), computer vision, audio, and the full .NET NuGet package catalog.

## Installation

### Via skills.sh (recommended)

```bash
npx skills add tebjan/vvvv-skills
```

### Manual Installation

Clone the repo and copy the `skills/` contents into your agent's skills directory:

```bash
# Claude Code (Windows)
git clone https://github.com/tebjan/vvvv-skills %TEMP%\vvvv-skills
xcopy /E /I %TEMP%\vvvv-skills\skills\* %USERPROFILE%\.claude\skills\

# Claude Code (Mac/Linux)
git clone https://github.com/tebjan/vvvv-skills /tmp/vvvv-skills
cp -r /tmp/vvvv-skills/skills/* ~/.claude/skills/
```

Each skill folder (e.g. `vvvv-fundamentals/`, `vvvv-shaders/`) must be placed directly inside `~/.claude/skills/` so that each `SKILL.md` is one level deep. You can also copy skills into a project-local `.claude/skills/` directory for per-project scope.

## Available Skills

| Skill | Description |
| --- | --- |
| `vvvv-fundamentals` | Core concepts — data types, execution model, pads, links, node browser |
| `vvvv-spreads` | Spread\<T\> and SpreadBuilder\<T\> — iteration, mapping, filtering, zipping, Span conversion |
| `vvvv-custom-nodes` | Writing C# node classes — ProcessNode, Update(), pins, change detection, NodeContext services |
| `vvvv-patching` | Visual programming — dataflow patterns, regions, patch organization |
| `vvvv-dotnet` | .NET integration — NuGet packages, .csproj config, vector type interop, async patterns |
| `vvvv-shaders` | SDSL shaders — TextureFX, shader mixins, compute shaders, ShaderFX composition |
| `vvvv-node-libraries` | Library project setup — AssemblyInitializer, service registration, ImportAsIs config, node factories |
| `vvvv-channels` | Public channels — IChannelHub, [CanBePublished], hierarchical propagation, subscriptions, bang channels |
| `vvvv-editor-extensions` | Editor plugins — .HDE.vl naming, Command nodes, SkiaWindow types, docking, Session API |
| `vvvv-troubleshooting` | Error diagnosis — C# node issues, shader compilation failures, runtime problems |

## How It Works

Once installed, skills activate automatically when the AI agent detects relevant context in your vvvv gamma project. The agent uses each skill's `description` field to decide when to load it — no manual invocation needed.

In Claude Code, each installed skill also becomes available as a slash command (e.g. `/vvvv-shaders`, `/vvvv-custom-nodes`) for explicit activation.

Example tasks the agent can help with:

- "How do I process a Spread with LINQ?"
- "Create a stateful counter node"
- "Write an SDSL shader that blends two textures"
- "Set up a new node library project"

## AI Agent Workflow

When the project uses source project references (.csproj), vvvv's live compilation enables a tight feedback loop with AI agents:

1. **Agent writes .cs files** — ProcessNode classes, static methods, shader files
2. **vvvv auto-recompiles** — on file save, Roslyn compiles source into in-memory assemblies
3. **Nodes hot-swap** — updated nodes replace old ones in the running program
4. **User sees results live** — visual output, 3D scenes, hardware signals update in real-time

No build step is needed for source project references — vvvv handles compilation internally. For projects using pre-compiled DLLs, the agent runs `dotnet build` and the user restarts vvvv. Either way, small modular nodes (each a single C# class) compose into complex systems through visual patching, making it practical to build and iterate on individual pieces with an AI agent.

## Contributing

### Adding a New Skill

1. Create a directory under `skills/` with a descriptive name (lowercase, hyphens)
2. Add a `SKILL.md` with YAML frontmatter:

   ```yaml
   ---
   name: vvvv-your-topic
   description: What this skill does and when to use it. Be specific — agents use this to decide when to activate.
   license: CC-BY-SA-4.0
   compatibility: Designed for coding AI agents assisting with vvvv gamma development
   metadata:
     author: Your Name
     version: "1.0"
   ---

   Your instructions here (under 500 lines).
   ```

3. Add supporting files (`examples.md`, `reference.md`, `templates/`) as needed
4. Reference supporting files from `SKILL.md` so the agent knows when to load them

### Guidelines

- **One topic per skill** — focused skills compose better than large ones
- **Keep SKILL.md under 500 lines** — move details to supporting files
- **Progressive disclosure** — metadata (name + description) is always loaded; SKILL.md body loads on activation; supporting files load on demand. Put "when to use" info in `description`, not the body.
- **Don't explain general programming** — AI agents already know C#, .NET, LINQ. Only add vvvv-specific knowledge.
- **Write descriptions in third person** — "Helps write..." not "I help you..."
- **Test with real tasks** — ask an AI agent to do vvvv work and verify the skill activates correctly

See [Agent Skills Specification](https://agentskills.io/specification) for the full format reference.

### Skill Structure Reference

```text
skills/your-skill/
├── SKILL.md           # Required — frontmatter + instructions
├── examples.md        # Optional — code examples (loaded on demand)
├── reference.md       # Optional — detailed reference (loaded on demand)
└── templates/         # Optional — files the agent can copy/adapt
    └── template.cs
```

## Resources

### Skill Development

- [Agent Skills Specification](https://agentskills.io/specification) — SKILL.md format, frontmatter fields, progressive disclosure, directory structure
- [Agent Skills Documentation Index](https://agentskills.io/llms.txt) — complete docs sitemap (fetch this for full reference)
- [skills.sh — Open Agent Skills Ecosystem](https://skills.sh) — browse, install, and publish skills
- [skills-ref Validation Library](https://github.com/agentskills/agentskills/tree/main/skills-ref) — validate SKILL.md frontmatter and structure (`skills-ref validate ./my-skill`)

If you use Claude Code, the built-in `/skill-creator` command can scaffold and validate new skills interactively.

### vvvv gamma

- [vvvv gamma Documentation](https://thegraybook.vvvv.org/)
- [Writing Nodes (ProcessNode Guide)](https://thegraybook.vvvv.org/reference/extending/writing-nodes.html)
- [Node Factories](https://thegraybook.vvvv.org/reference/extending/node-factories.html)
- [vvvv Package Catalog](https://vvvv.org/packs)

## License

CC BY-SA 4.0 — see [LICENSE](LICENSE) for details.
