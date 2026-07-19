---
name: Update PR Documentation
description: Detects user-facing changes in pull requests and updates their documentation
emoji: "📝"
on:
  pull_request:
    types: [opened, reopened, synchronize, ready_for_review]
if: >-
  github.event.pull_request.base.ref == github.event.repository.default_branch &&
  !github.event.pull_request.draft
permissions:
  contents: read
  issues: read
  pull-requests: read
strict: true
engine:
  id: copilot
timeout-minutes: 30
steps:
  - name: Install Python
    uses: actions/setup-python@v5
    with:
      python-version: "3.13"
  - name: Install uv
    uses: astral-sh/setup-uv@v4
  - name: Install documentation dependencies
    run: uv sync --no-default-groups --group docs
network:
  allowed:
    - defaults
    - github
tools:
  cli-proxy: true
  edit:
  bash:
    - "git diff *"
    - "git log *"
    - "git status *"
    - "find *"
    - "grep *"
    - "cat *"
    - "ls *"
    - "uv run *"
    - "make docs"
  github:
    mode: gh-proxy
    toolsets: [default]
safe-outputs:
  push-to-pull-request-branch:
    patch-format: bundle
    commit-title-suffix: " [skip ci]"
    allowed-files:
      - README.md
      - "**/README.md"
      - "docs/**"
      - "examples/**"
      - AGENTS.md
      - "**/AGENTS.md"
      - "**/SKILL.md"
    protected-files:
      policy: blocked
  noop: {}
features:
  gh-aw-detection: true
---

# Pull Request Documentation Updater

Review the current pull request for user-facing additions, removals, or behavioral changes. Keep
documentation accurate in the same pull request whenever the change needs documentation.

## Scope

Documentation includes all of the following:

- Published MkDocs content under `docs/` and its navigation in `mkdocs.yaml`.
- Repository and package `README.md` files.
- Runnable examples and example documentation under `examples/`.
- AI context: every relevant `AGENTS.md` and `SKILL.md` file.

Do not update documentation for internal-only refactors, test-only changes, CI-only changes, or
formatting-only changes unless they make existing documentation inaccurate.

## Procedure

1. Inspect the PR title and description, changed-file list, commits, and diff supplied by the
   GitHub pull-request tools. Ignore generated workflow lock files.
2. Identify additions, removals, API/CLI/configuration changes, behavior changes, and breaking
   changes. Read the affected implementation and relevant tests before deciding what users must
   know.
3. Locate existing related documentation across all scope locations. Use `grep` and `find` to
   check `docs/`, every `README.md`, `examples/`, `AGENTS.md`, and `SKILL.md`.
4. Decide whether each user-facing change requires a documentation update. If no update is
   required, call `noop` with a concise reason and stop.
5. Make only the necessary documentation changes:
   - Keep MkDocs pages accurate and update `mkdocs.yaml` when adding a page.
   - Keep README instructions and examples consistent with the changed behavior.
   - Update or add runnable examples when they demonstrate a changed public workflow.
   - Update AI context only when the change alters agent-relevant architecture, conventions,
     commands, or supported capabilities.
   - Do not alter generated files or unrelated documentation.
6. Validate changed Markdown links and code snippets against the implementation. If MkDocs content
   changed, run `make docs`; the workflow installs its documentation dependencies before the agent
   starts.
7. If documentation was changed, commit only the allowed documentation files and call
   `push_to_pull_request_branch` with the current PR number and a concise commit message. If the
   PR originates from a fork or the safe output cannot push to its branch, call `noop` explaining
   that limitation and list the required files and changes.

## Rules

- Be precise: document confirmed behavior, not assumptions or speculative APIs.
- Preserve the existing tone, structure, and level of detail of each target file.
- Do not add a documentation change solely to satisfy this workflow.
- Never modify application code, tests, dependencies, workflow configuration, or files outside the
  safe-output allowlist.
- Always finish with exactly one safe output: `push_to_pull_request_branch` after changes, or
  `noop` when no changes are necessary or cannot be pushed.
