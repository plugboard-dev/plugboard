# AI Agent Instructions for Plugboard

This document provides guidelines for AI coding agents working on the Plugboard project. Following these instructions ensures contributions are consistent with the project's architecture, conventions, and style.

## Project Overview

Plugboard is an event-driven framework in Python for simulating and orchestrating complex processes with interconnected stateful components.

### Core Architecture

**Component**: The fundamental building block for modeling logic (see `plugboard/component/`)
- Lifecycle: `__init__` → `init` → `step` (repeated) → `destroy`
- I/O declaration: Use class-level `io: IOController` attribute
- Business logic: Implement in the `step` method
- Asynchronous: All lifecycle methods (`init`, `step`, `destroy`) must be `async`

**Process**: Orchestrates execution of components (see `plugboard/process/`)
- Manages collections of components and their interconnections
- `LocalProcess`: Runs all components in a single process
- Supports distributed execution via other process types

**Connector**: Defines communication channels between components (see `plugboard/connector/`)
- Links outputs to inputs: `component_name.output_name` → `component_name.input_name`
- Various connector types available for different execution contexts

**State Management**: Tracks component and process status (see `plugboard/state/`)
- Critical for monitoring and distributed execution
- Uses `StateBackend` abstraction

**Configuration**: Flexible process definition
- Python-based: Direct component instantiation
- YAML-based: Declarative configuration for CLI execution (`plugboard process run ...`)

## Development Environment

### Setup
- **Package Manager**: Uses `uv` for dependency management
- **Dependencies**: Defined in `pyproject.toml`
- **Python Version**: Requires Python ≥3.12

### Testing
- **Framework**: `pytest`
- **Location**: `tests/` directory
- **Commands**:
  - `make test` - Run all tests
  - `make test-integration` - Run integration tests
- **Best Practice**: Always include tests with new features

### Linting & Formatting
- **Tools**: 
  - `ruff` - Formatting and linting
  - `mypy` - Static type checking
- **Commands**:
  - `make lint` - Check for issues
  - `make format` - Auto-format code
- **Requirement**: All code must be fully type-annotated

### CLI
- **Framework**: Built with `typer`
- **Location**: `plugboard/cli/`
- **Usage**: `plugboard --help`

## Code Standards

### Async Pattern
- Entire framework built on `asyncio`
- All I/O operations must be async
- All component lifecycle methods must be async

### Dependency Injection
- Uses `that-depends` for DI
- Container setup: `plugboard/utils/DI.py`
- Access logger: `self._logger = DI.logger.resolve_sync().bind(...)`

### Data Structures
- Prefer immutable structures: `msgspec.Struct(frozen=True)`
- Use Pydantic models for validation where needed

### Components
When creating components:
1. Inherit from `plugboard.component.Component`
2. Always call `super().__init__()` in `__init__`
3. Declare I/O via class-level `io` attribute
4. Implement required async methods
5. Use type hints throughout

Example:
```python
import typing as _t
from plugboard.component import Component, IOController as IO
from plugboard.schemas import ComponentArgsDict

class MyComponent(Component):
    io = IO(inputs=["input_a"], outputs=["output_x"])
    
    def __init__(
        self, 
        param: float = 1.0, 
        **kwargs: _t.Unpack[ComponentArgsDict]
    ) -> None:
        super().__init__(**kwargs)
        self._param = param
    
    async def step(self) -> None:
        # Business logic here
        self.output_x = self.input_a * self._param
```

### Events
- Event system for component communication
- Define events by inheriting from `plugboard.events.Event`
- Add handlers with `@Event.handler` decorator
- Emit events via `self.io.queue_event()` or return from handlers

## Best Practices

1. **Minimal Changes**: Make surgical, focused changes
2. **Type Safety**: Maintain full type annotations
3. **Testing**: Add tests for new functionality
4. **Documentation**: Update docstrings and docs for public APIs
5. **Async Discipline**: Never use blocking I/O operations
6. **Immutability**: Prefer immutable data structures
7. **Logging**: Use structured logging via `structlog`
8. **Error Handling**: Use appropriate exception types from `plugboard.exceptions`

## Common Tasks

### Adding a New Component
1. Create class inheriting from `Component`
2. Define `io` with inputs/outputs
3. Implement `__init__` with proper signature
4. Implement async `step` method
5. Add tests in `tests/`
6. Update documentation if public API

### Modifying Core Framework
1. Understand impact on existing components
2. Ensure backward compatibility where possible
3. Update type stubs if needed
4. Run full test suite
5. Update relevant documentation

### Working with Events
1. Define event class with data model
2. Declare in component's `io` (input_events/output_events)
3. Implement handlers with decorators
4. Use `EventConnectorBuilder` for wiring

## Resources

- **Repository**: https://github.com/plugboard-dev/plugboard
- **Documentation**: https://docs.plugboard.dev
- **Issue Tracker**: GitHub Issues
- **Discussions**: GitHub Discussions
