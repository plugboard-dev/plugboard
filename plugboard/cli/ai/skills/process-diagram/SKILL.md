---
name: process-diagram
description: Generate a Mermaid diagram from a Plugboard YAML process configuration.
---

# Create a diagram from a Plugboard process

## Use this skill when

- the user wants to visualise a Plugboard model
- the user asks for a Mermaid diagram or process diagram

## Goal

Create a diagram from a Plugboard process using the CLI.

## Instructions

1. Work from a YAML config whenever possible. If the process only exists in Python, first use the `create-yaml-config` skill at `../create-yaml-config/SKILL.md`.
2. Confirm which YAML config should be used. If the user wants the diagram saved to a file, plan to capture the CLI output.
3. Run:

```sh
plugboard process diagram path/to/model.yaml
```

4. The command prints Mermaid output to stdout. Share that output directly or save it to a user-approved file.
5. If the resulting diagram is hard to read, recommend restructuring the model into clearer, smaller components that better match the real-world workflow.

## Output

- a generated process diagram
- a short explanation of what the main components and flows represent
