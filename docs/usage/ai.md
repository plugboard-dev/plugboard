# AI-Assisted Development

Plugboard ships with tooling to help AI coding agents understand how to build models using the framework. The `plugboard ai` command group provides utilities for setting up AI-assisted development workflows.

## Initialising a project

The `plugboard ai init` command creates an `AGENTS.md` file and a `skills/` directory in your project directory. Together they give AI coding agents the context they need to help you build, export, visualise, run, and tune Plugboard models.

`AGENTS.md` is a convention used by AI coding tools (such as [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview), [Codex](https://openai.com/index/codex/), and [Gemini CLI](https://github.com/google-gemini/gemini-cli)) to discover project-specific instructions automatically.

### Usage

To create an `AGENTS.md` file in the current working directory:

```bash
plugboard ai init
```

To create the file in a specific directory:

```bash
plugboard ai init /path/to/project
```

!!! note
    The command will not overwrite an existing `AGENTS.md` file or `skills/` directory. If either already exists in the target directory, the command exits with an error.

### What's installed?

The generated `AGENTS.md` covers:

- **Planning a model** — how to break a problem down into components, inputs, outputs, and data flows.
- **Model structure** — how to map real-world entities onto separate components instead of monolithic logic.
- **YAML-friendly design** — why component arguments should usually be serialisable so processes can be defined in YAML.
- **Implementing components** — using built-in library components and creating custom ones by subclassing [`Component`][plugboard.component.Component].
- **Assembling a process** — connecting components together and running a [`LocalProcess`][plugboard.process.LocalProcess].
- **Event-driven models** — defining custom [`Event`][plugboard.events.Event] types, emitting events, and writing event handlers.
- **Exporting models** — saving process definitions to YAML and running them via the CLI.

The generated `skills/` directory includes reusable task guides for:

- creating a YAML config from a model defined in Python
- generating a process diagram with `plugboard process diagram`
- running a model for a user-specified scenario with `plugboard process run`
- adding and shaping a `tune` section in a YAML config

These files are intended to be committed to version control alongside your project code so that any AI agent working in the repository has immediate access to Plugboard conventions.

### Customising

After generating the file you can edit it freely to add project-specific instructions — for example, domain context, coding standards, or pointers to your own components and data sources.
