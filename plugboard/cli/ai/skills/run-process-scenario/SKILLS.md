# Skill: Run a Plugboard process for a specific scenario

## Use this skill when

- the user wants to run a model with specific parameters, assumptions, or scenarios
- the user gives a set of values and wants the process executed through the CLI

## Goal

Create or update a YAML config for the requested scenario, then run it with `plugboard process run`.

## Instructions

1. Make sure a YAML config exists for the model. If the model only exists in Python, create the YAML first using the `skills/create-yaml-config/SKILLS.md` guidance.
2. Ask for any missing scenario inputs before running anything.
3. Update the YAML config with the exact parameter values the user requested.
4. Preserve a clear component structure that matches the real-world model. Do not collapse multiple entities into one component just to make the config shorter.
5. Run:

```sh
plugboard process run path/to/model.yaml
```

6. Report what configuration was used, what command was run, and the key outputs or generated artifacts.
7. If the scenario required new parameters, confirm that the final config remains YAML-friendly and reusable.

## Output

- an updated YAML config for the requested scenario
- the command used to run it
- a summary of the results
