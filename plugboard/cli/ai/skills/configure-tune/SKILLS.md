# Skill: Add a `tune` section to a Plugboard YAML config

## Use this skill when

- the user wants to tune a model
- the user wants certain parameters to become configurable or optimisable

## Goal

Work with the user to decide what should be tunable, then add an appropriate `tune` section to the YAML config.

## Instructions

1. Start by asking questions to understand:
   - which outcomes matter
   - which component parameters are candidates for tuning
   - valid ranges, choices, or distributions for each parameter
   - any constraints between parameters
2. Make sure the parameters being tuned are serialisable and already represented cleanly in the YAML config.
3. If the current model structure hides tunable behavior inside a monolithic component, suggest splitting the logic into clearer components before or alongside tuning.
4. Add a `tune` section that reflects the agreed tunable parameters and their search spaces.
5. Keep the rest of the config readable and preserve stable component names so the tuning setup remains understandable.
6. Summarise which questions were answered, which defaults were assumed, and what the user may still need to refine.

## Output

- an updated YAML config with a `tune` section
- a concise summary of the tuning choices and any open questions
