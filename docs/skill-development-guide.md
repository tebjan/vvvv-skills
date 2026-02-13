# Skill Development Guide

This guide explains how to create effective skills for AI agents to use with vvvv gamma.

## What Makes a Good Skill?

A good skill document should:

1. **Be Focused**: Cover one concept or task thoroughly
2. **Be Practical**: Include working examples and code
3. **Be Structured**: Follow consistent format
4. **Be Clear**: Explain concepts without assuming knowledge
5. **Be Complete**: Cover common cases and edge cases

## Skill Document Structure

Every skill document should follow this template:

```markdown
# [Skill Name]

## Description
Brief (2-3 sentences) overview of what this skill covers

## Key Concepts
- List of main concepts
- With brief explanations
- 3-7 concepts typically

## Examples
### [Example Name]
Working code or patch description with:
- What it does
- How it works
- Key points to notice

## Best Practices
- Do this
- Don't do that
- When to use X vs Y

## Common Pitfalls
- Problem: Description
  Solution: How to avoid/fix

## Related Skills
- [Link to related skill](path)
```

## Skill Categories

### Core Skills
**Purpose**: Fundamental concepts all AI agents must know

**Topics**:
- Language fundamentals
- Core data structures
- Basic patterns

**Characteristics**:
- High priority
- Few prerequisites
- Referenced by other skills

### Coding Skills
**Purpose**: Programming and development techniques

**Topics**:
- Writing code
- Using libraries
- Development patterns

**Characteristics**:
- Medium to high priority
- May require core skills as prerequisites
- Include code examples

### Patching Skills
**Purpose**: Visual programming techniques

**Topics**:
- Creating patches
- Node usage
- Visual patterns

**Characteristics**:
- Medium priority
- Visual descriptions
- Patch-specific examples

## Writing Examples

### Code Examples Should:
- Be complete and runnable
- Include comments explaining key parts
- Handle edge cases
- Follow best practices
- Be minimal but realistic

### Example Template:
```csharp
/// <summary>
/// Clear description
/// </summary>
public ReturnType MethodName(ParamType param)
{
    // Handle edge case
    if (param == null || param.Count == 0)
        return DefaultValue;
    
    // Main logic with comments
    var result = ProcessParam(param);
    
    return result;
}
```

## Best Practices Section

Format:
```markdown
## Best Practices

### [Category]
- **Practice Name**: Explanation and why it matters
- **Practice Name**: Explanation and why it matters

### [Another Category]
- **Practice Name**: Explanation
```

## Common Pitfalls Section

Format:
```markdown
## Common Pitfalls

### [Pitfall Name]
**Problem**: What goes wrong

**Solution**: How to fix/avoid
```csharp
// ❌ Bad example
// ✅ Good example
```
```

## Cross-Referencing

Link to related skills:
- Use relative paths: `[Skill Name](../category/skill.md)`
- Mention at end in "Related Skills" section
- Include context: "See X for more on Y"

## Metadata

Add to `skills-manifest.json`:
```json
{
  "name": "skill-name",
  "path": "skills/category/skill-name.md",
  "priority": "high|medium|low",
  "topics": ["topic1", "topic2"],
  "prerequisites": ["other-skill"]
}
```

## Testing Your Skill

Before submitting:
- [ ] Code examples are tested and work
- [ ] Format follows template
- [ ] Links to related skills are correct
- [ ] Added to skills-manifest.json
- [ ] Added to skills/README.md index
- [ ] Grammar and spelling checked
- [ ] Technical accuracy verified

## Examples of Good Skills

In this repository:
- `skills/core/fundamentals.md` - Comprehensive core concepts
- `skills/coding/custom-nodes.md` - Detailed coding guide
- `skills/core/spreads.md` - Focused on one data structure

## Common Mistakes to Avoid

❌ **Too broad**: Trying to cover everything in one skill
✅ **Focused**: One concept thoroughly covered

❌ **No examples**: Only theory and descriptions
✅ **Practical**: Working code and clear examples

❌ **Assuming knowledge**: Using unexplained jargon
✅ **Clear**: Explaining concepts from basics

❌ **Incomplete**: Missing edge cases or error handling
✅ **Complete**: Covering normal and edge cases

❌ **Outdated**: Using old APIs or patterns
✅ **Current**: Using latest best practices

## Contributing Your Skill

1. Create skill document following template
2. Add code examples and test them
3. Update `skills-manifest.json`
4. Update `skills/README.md` index
5. Submit pull request with clear description

## Questions?

If unsure about:
- Where a skill belongs → Open an issue
- How to structure content → Follow existing skills
- Technical accuracy → Reference official docs
- Best practices → See `skills/core/best-practices.md`

## Maintenance

Skills should be updated when:
- vvvv gamma APIs change
- Best practices evolve
- Users report issues
- Better examples are found
- Errors are discovered

---

Remember: Skills are for AI agents first, humans second. Be explicit, structured, and complete!
