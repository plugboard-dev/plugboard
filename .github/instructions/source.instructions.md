---
applyTo: "plugboard/**/*.py"
---
# GitHub Copilot Instructions for the Plugboard Repository

This document provides guidelines for using AI coding agents to contribute to the Plugboard project. Following these instructions will help ensure that contributions are consistent with the project's architecture, conventions, and style.

## Project Overview & Architecture

Plugboard is an event-driven framework in Python for simulating and orchestrating complex processes. The core architectural concepts are `Component`, `Process`, and `Connector`.

-   **`Component`**: The fundamental building block for modeling logic. Found in `plugboard/component/`.
    -   Components have a defined lifecycle: `__init__`, `init`, `step`, `run`, and `destroy`.
    -   I/O (inputs, outputs, events) is declared via a class-level `io: IOController` attribute.
    -   The `step` method contains the primary logic and is executed repeatedly.
    -   The framework is asynchronous (`asyncio`), so all lifecycle methods (`init`, `step`, `destroy`) must be `async`.

-   **`Process`**: Manages a collection of `Component`s and their interconnections. Found in `plugboard/process/`.
    -   A `Process` orchestrates the execution of components.
    -   `LocalProcess` runs all components in a single process. Other process types may support distributed execution.

-   **`Connector`**: Defines the communication channels between component outputs and inputs. Found in `plugboard/connector/`.
    -   Connectors link a source (`component_name.output_name`) to a target (`component_name.input_name`).

-   **State Management**: The `StateBackend` (see `plugboard/state/`) tracks the status of all components and the overall process. This is crucial for monitoring and for distributed execution.

-   **Configuration**: Processes can be defined in Python or declared in YAML files for execution via the CLI (`plugboard process run ...`).

## Developer Workflow

-   **Setup**: The project uses `uv` for dependency management. Set up your environment and install dependencies from `pyproject.toml`.
-   **Testing**: Tests are written with `pytest` and are located in the `tests/` directory.
    -   Run all tests with `make test`.
    -   Run integration tests with `make test-integration`.
    -   When adding a new feature, please include corresponding unit and/or integration tests.
-   **Linting & Formatting**: The project uses `ruff` for formatting and linting, and `mypy` for static type checking.
    -   Run `make lint` to check for issues.
    -   Run `make format` to automatically format the code.
    -   All code must be fully type-annotated.
-   **CLI**: The command-line interface is defined using `typer` in `plugboard/cli/`. Use `plugboard --help` to see available commands.

## Code Conventions & Patterns

-   **Asynchronous Everywhere**: The entire framework is built on `asyncio`. All I/O operations and component lifecycle methods should be `async`.
-   **Dependency Injection**: The project uses `that-depends` for dependency injection. See `plugboard/utils/DI.py` for the container setup.
-   **Immutability**: Use `msgspec.Struct(frozen=True)` for data structures that should be immutable.
-   **Extending Components**: When creating a new component, inherit from `plugboard.component.Component` and implement the required `async` methods. Remember to call `super().__init__()`.
-   **Events**: Components can communicate via an event system. Define custom events by inheriting from `plugboard.events.Event` and add handlers to your component using the `@Event.handler` decorator.
-   **Logging**: Use the `structlog` logger available through dependency injection: `self._logger = DI.logger.resolve_sync().bind(...)`.

By adhering to these guidelines, you can help maintain the quality and consistency of the Plugboard codebase.
