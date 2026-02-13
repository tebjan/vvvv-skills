# Contributing to vvvv-skills

Thank you for your interest in contributing to vvvv-skills! This repository aims to collect knowledge and skills that help AI agents assist developers working with vvvv gamma.

## Quick Start

1. Read the [Skill Development Guide](docs/skill-development-guide.md) for detailed instructions
2. Check [skills-manifest.json](skills-manifest.json) to understand repository structure
3. Review existing skills for examples and patterns
4. Submit your contribution via pull request

## How to Contribute

### Adding New Skills

Skills are structured knowledge files that help AI agents understand vvvv gamma concepts.

**Before You Start**:
- Read the [Skill Development Guide](docs/skill-development-guide.md)
- Review similar existing skills
- Check if the topic is already covered

**Steps**:
1. Choose the appropriate category in the `skills/` directory:
   - `core/` - Fundamental concepts
   - `coding/` - Programming-related skills
   - `patching/` - Visual programming skills

2. Create a markdown file with a descriptive name (e.g., `node-creation.md`)

3. Structure your skill file following the template in [Skill Development Guide](docs/skill-development-guide.md):
   - Clear title and description
   - Key concepts
   - Working examples
   - Best practices
   - Common pitfalls to avoid
   - Related skills links

4. Update repository metadata:
   - Add entry to `skills-manifest.json`
   - Update `skills/README.md` index

### Adding Examples

Examples help demonstrate real-world usage:

1. Place examples in the `examples/` directory
2. Include both code and patch files when applicable
3. Add a README in your example directory explaining what it demonstrates
4. Include comments in your code

### Adding Documentation

Additional documentation goes in the `docs/` directory:

1. Reference materials
2. Guides and tutorials
3. API documentation
4. Architecture overviews

### Adding Templates

Templates for common tasks go in the `templates/` directory:

1. Project templates
2. Node templates
3. Patch templates
4. Configuration templates

## Skill File Format

Each skill file should follow this structure:

```markdown
# [Skill Name]

## Description
Brief description of what this skill covers

## Key Concepts
- Concept 1
- Concept 2

## Examples
Code or patch examples

## Best Practices
- Practice 1
- Practice 2

## Common Pitfalls
- Pitfall 1 and how to avoid it
- Pitfall 2 and how to avoid it

## Related Skills
- Link to related skill 1
- Link to related skill 2
```

## Pull Request Process

1. Fork the repository
2. Create a feature branch
3. Add your content
4. Test that your examples work (if applicable)
5. Submit a pull request with a clear description

## Code of Conduct

- Be respectful and constructive
- Focus on accuracy and clarity
- Provide working examples when possible
- Keep content focused on vvvv gamma

## Questions?

If you have questions about contributing, please open an issue for discussion.
