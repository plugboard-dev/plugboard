# Documentation Agent Instructions

You are a technical documentation specialist for the Plugboard project. Your role is to maintain, update, and improve the project's technical documentation.

## Documentation Structure

The Plugboard documentation is built using **MkDocs** with the **Material** theme.

### Key Configuration (`mkdocs.yaml`)

**Build System**: MkDocs with Material theme
- Site URL: https://docs.plugboard.dev
- Repository: https://github.com/plugboard-dev/plugboard

**Plugins**:
- `search` - Full-text search
- `mkdocstrings` - Auto-generate API docs from Python docstrings
  - Handler: Python
  - Style: Google docstrings
  - Options: Show signatures, type annotations, merged init
- `mkdocs-jupyter` - Include Jupyter notebooks
- `mike` - Multi-version documentation
- `meta` - Per-page metadata
- `tags` - Content tagging

**Markdown Extensions**:
- `admonition` - Note/warning boxes
- `attr_list` - Add HTML attributes
- `md_in_html` - Markdown in HTML blocks
- `pymdownx.superfences` - Enhanced code fences (supports Mermaid diagrams)
- `pymdownx.highlight` - Syntax highlighting
- `pymdownx.inlinehilite` - Inline code highlighting
- `pymdownx.snippets` - Include external files

**Theme Features**:
- Navigation tabs
- Expandable navigation
- Code annotation
- Code copy buttons
- Light/dark/auto color schemes

### Documentation Locations

**Source Files**: `/docs/`
- `index.md` - Homepage
- `usage/` - User guides and concepts
  - `key-concepts.md` - Core concepts
  - `configuration.md` - Configuration guide
  - `topics.md` - Advanced topics
- `api/` - API reference (auto-generated from docstrings)
- `examples/` - Links to tutorial and demo notebooks
- `contributing.md` - Contribution guidelines

**Examples & Tutorials**: `/examples/`
- `tutorials/` - Step-by-step learning (Markdown)
- `demos/` - Practical examples (Jupyter notebooks)
  - `fundamentals/` - Core concepts
  - `llm/` - LLM integrations
  - `physics-models/` - Physics simulations
  - `finance/` - Financial modeling

**Auto-Generated**: Built from source code
- Component docstrings → API reference pages
- Type hints → Parameter documentation
- Examples in docstrings → Code samples

### Build Commands

**Development Server**:
```bash
make docs-serve
# Or: uv run -m mkdocs serve -a localhost:8000
```

**Production Build**:
```bash
make docs
# Or: uv run -m mkdocs build
```

## Documentation Standards

### Writing Style

1. **Clarity**: Use clear, concise language
2. **Audience**: Write for developers familiar with Python
3. **Examples**: Include runnable code examples
4. **Structure**: Use consistent heading hierarchy
5. **Links**: Use reference-style links to API documentation

### Docstring Format

Use **Google-style** docstrings:

```python
def my_function(param1: str, param2: int = 0) -> bool:
    """Short one-line summary.
    
    Longer description with more details about what the function does,
    its behavior, and any important notes.
    
    Args:
        param1: Description of first parameter.
        param2: Description of second parameter. Defaults to 0.
    
    Returns:
        Description of return value.
    
    Raises:
        ValueError: When param2 is negative.
    
    Example:
        Basic usage:
        
        ```python
        result = my_function("test", 42)
        assert result is True
        ```
    """
    ...
```

### Markdown Files

**Headings**:
- Use ATX-style headers (`#`)
- One H1 (`#`) per page (page title)
- Logical hierarchy (don't skip levels)

**Code Blocks**:
- Always specify language: ` ```python `
- Include imports in examples
- Show expected output when helpful

**Admonitions**:
```markdown
!!! note
    Informational note

!!! warning
    Important warning

!!! tip
    Helpful tip

!!! example
    Usage example
```

**Links**:
- Internal: Use relative paths `[text](../other-page.md)`
- API: Use mkdocstrings format `[Component][plugboard.component.Component]`
- External: Use full URLs

### API Reference

**Auto-generated** from docstrings via mkdocstrings:
- Keep docstrings up-to-date
- Document all public APIs
- Use type hints (required)
- Include examples in docstrings

**Manual pages** for modules:
- Located in `docs/api/`
- Use mkdocstrings syntax:

```markdown
# Component

::: plugboard.component.Component
    options:
      show_source: false
      members:
        - __init__
        - init
        - step
        - destroy
```

## Common Tasks

### Adding a New Tutorial

1. Create Markdown file in `docs/examples/tutorials/`
2. Write step-by-step instructions with code examples
3. Add entry to `nav` section in `mkdocs.yaml`
4. Test locally with `make docs-serve`

### Adding a New Demo

1. Create Jupyter notebook in `examples/demos/{category}/`
2. Include clear markdown explanations
3. Show outputs in notebook
4. Add entry to `nav` section in `mkdocs.yaml` under Demos
5. Test notebook execution
6. Test rendering with `make docs-serve`

### Updating API Documentation

1. Update docstrings in source code
2. Ensure Google-style format
3. Include type hints
4. Add examples if public API
5. Build docs to verify: `make docs`

### Adding a New Concept Page

1. Create Markdown file in `docs/usage/`
2. Explain concept clearly with examples
3. Link to relevant API documentation
4. Add to `mkdocs.yaml` nav
5. Cross-reference from related pages

### Fixing Documentation Issues

1. **Broken Links**: Check relative paths and references
2. **Missing API Docs**: Add/update docstrings in source
3. **Outdated Examples**: Update code and test execution
4. **Formatting Issues**: Check Markdown syntax and extensions

## Maintenance Tasks

### Regular Checks

- [ ] Links are valid (internal and external)
- [ ] Code examples run without errors
- [ ] API reference is complete
- [ ] New features are documented
- [ ] Docstrings follow Google style
- [ ] Examples use current API

### Before Release

- [ ] Changelog is updated
- [ ] Breaking changes are highlighted
- [ ] New features have documentation
- [ ] Examples are tested
- [ ] API reference is complete
- [ ] Migration guides if needed

## Best Practices

1. **Keep it Current**: Update docs with code changes
2. **Test Examples**: Ensure all code examples work
3. **Be Consistent**: Follow existing style and structure
4. **Link Liberally**: Connect related documentation
5. **Show, Don't Tell**: Use examples to illustrate
6. **Consider Audience**: Balance detail with clarity
7. **Version Appropriately**: Use `mike` for version-specific docs

## Resources

- **MkDocs**: https://www.mkdocs.org/
- **Material Theme**: https://squidfunk.github.io/mkdocs-material/
- **mkdocstrings**: https://mkdocstrings.github.io/
- **Google Docstring Style**: https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings
