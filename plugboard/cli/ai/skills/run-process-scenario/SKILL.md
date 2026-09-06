---
name: run-process-scenario
description: Update a Plugboard YAML config for a requested scenario and run it with the CLI.
---

# Run a Plugboard process for a specific scenario

## Use this skill when

- the user wants to run a model with specific parameters, assumptions, or scenarios
- the user gives a set of values and wants the process executed through the CLI

## Goal

Create or update a YAML config for the requested scenario, then run it with `plugboard process run`.

## Instructions

1. Make sure a YAML config exists for the model. If the model only exists in Python, create the YAML first by using the `create-yaml-config` skill at `../create-yaml-config/SKILL.md`.
2. Ask for any missing scenario inputs before running anything.
3. Prefer overriding process parameters or component fields on the CLI with repeated `--param` / `-p` `name=value` flags when only values change for a scenario. Use a bare `<name>` (short for `process.default.parameter.<name>`) or `component.<name>.<arg|initial_value|parameter>.<field>`. Later flags win for the same field. Values are parsed as YAML; quote collections for the shell and retain YAML quotes for strings that would otherwise be coerced. Edit the YAML when component structure, connectors, or defaults need to change.
4. Preserve a clear component structure that matches the real-world model. Do not collapse multiple entities into one component just to make the config shorter.
5. Validate the YAML against `plugboard_schemas.ConfigSpec` before running it.
6. Run, for example:

```sh
plugboard process run path/to/model.yaml --param scale=2.0 -p component.simulation.arg.max_iters=10
```

7. Report what configuration was used, what validation was performed, what command was run (including any `--param` overrides), and the key outputs or generated artifacts.
8. If the scenario required new parameters, confirm that the final config remains YAML-friendly and reusable.

## Output

- an updated YAML config for the requested scenario
- the command used to run it
- a summary of the results
