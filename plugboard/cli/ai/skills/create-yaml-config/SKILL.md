---
name: create-yaml-config
description: Create a YAML configuration from a Plugboard process defined in Python code.
---

# Create a YAML config from a Python-defined Plugboard model

## Use this skill when

- the user has a process defined in Python and wants a YAML configuration
- the user wants to run, share, tune, or diagram a process through the CLI

## Goal

Produce a YAML config that faithfully represents the Python-defined process and is ready for CLI use.

## Instructions

1. Inspect the Python model and identify the process type, components, connectors, events, and arguments.
2. Check that component arguments are serialisable. Prefer strings, numbers, booleans, lists, dictionaries, and other YAML-friendly values.
3. If the current Python process uses non-serialisable arguments, explain the limitation and propose the smallest change needed to make the configuration exportable.
4. Prefer a process structure where each real-world entity or stage is represented by its own component.
5. Export the YAML using Plugboard's supported APIs, for example:

```python
process.dump("model.yaml")
```

6. Review the generated YAML and make sure the component names, arguments, and connector wiring are clear and stable.
7. Tell the user where the YAML file was written and what CLI commands it unlocks next, such as `plugboard process run` or `plugboard process diagram`.

## Output

- a YAML config file
- a short summary of any assumptions or serialisation constraints
