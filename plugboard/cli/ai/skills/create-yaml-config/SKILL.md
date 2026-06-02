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

6. Validate the generated YAML against `plugboard_schemas.ConfigSpec`, which is the schema used by the Plugboard CLI when loading config files. A quick check is:

```sh
plugboard process validate model.yaml
```

If you need to validate directly in Python, use:

```python
from pathlib import Path
import msgspec
from plugboard_schemas import ConfigSpec

ConfigSpec.model_validate(msgspec.yaml.decode(Path("model.yaml").read_bytes()))
```

This mirrors the Plugboard CLI load path: `msgspec.yaml.decode(...)` produces standard Python
data structures, and `ConfigSpec.model_validate(...)` validates that decoded YAML data.
If validation fails, inspect the reported field path and update the YAML structure, missing
required fields, component arguments, or `tune` entries before trying again.

7. Review the generated YAML and make sure the component names, arguments, connector wiring, and optional `tune` section are clear and stable.
8. Tell the user where the YAML file was written, how it was validated, and what CLI commands it unlocks next, such as `plugboard process run` or `plugboard process diagram`.

## Output

- a YAML config file
- a short summary of any assumptions or serialisation constraints
