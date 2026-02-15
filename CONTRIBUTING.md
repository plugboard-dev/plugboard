# Contributing

Thank you for your interest in Plugboard. Contributions are welcomed and warmly received! For bug fixes and smaller feature requests feel free to open an issue on our [Github repo](https://github.com/plugboard-dev/plugboard/issues). For any larger changes please get in touch with us to discuss first.

## 😻 PR process

We use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) on our main branch, so prefix your pull request titles with a commit type: `feat`, `fix`, `chore`, etc.

## 💻 Development setup

For small changes or to get up-and-running quickly, we recommend [GitHub codespaces](https://github.com/codespaces/), which provides you with a ready-to-use development environment.

For local development we recommend [VSCode](https://code.visualstudio.com/).

### Python dependencies

Dependencies are managed using [uv](https://docs.astral.sh/uv/). Install the project using
```sh
uv sync --all-extras
```

### Testing

Tests are run in [pytest](https://docs.pytest.org/en/stable/), which you can run with
```sh
uv run pytest .
```

### Linting

We use [ruff](https://github.com/astral-sh/ruff) for code formatting and style. Install the pre-commit hook by running
```sh
uv run pre-commit install
```

### Documentation

The package documentation uses [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/) and can be viewed locally by running
```sh
uv run mkdocs serve
```

### AI-assisted development

This repo includes custom AI agent prompts to assist with development:

- [AGENTS.md](AGENTS.md) - General guidelines for working with the Plugboard codebase.
- [examples/AGENTS.md](examples/AGENTS.md) - Specific guidance for building example models and demos.
- Copilot-specific agents `docs`, `lint` and `test` which you can @-mention in a pull request.

If you use GitHub Copilot or other AI coding assistants that support the AGENTS.md convention, these prompts can help you build Plugboard models from a description of the process and/or the components that you would like to implement. We recommend using Copilot in agent mode and allowing it to implement the boilerplate code from your input prompt.
