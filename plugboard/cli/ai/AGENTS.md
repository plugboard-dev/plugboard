# AI Agent Instructions for Plugboard Models

This file gives AI coding agents a shared set of instructions for building Plugboard models. Keep the guidance tool-agnostic so it works well with Claude, Gemini, Codex, GitHub Copilot, and other agents that read `AGENTS.md`.

## Core modeling principles

1. **Model the real system explicitly.** When planning a process, split the logic into separate Plugboard `Component`s that map to the real-world entities or stages in the problem. For example, a production line with three machines should normally be represented by three machine components, not one monolithic component.
2. **Prefer serialisable component arguments.** Component constructor arguments should usually be plain serialisable values such as strings, numbers, booleans, lists, dictionaries, or other YAML-friendly structures so the same model can be defined and run from YAML.
3. **Reuse built-in components first.** Before creating a custom component, check `plugboard.library` for an existing component that already matches the need.
4. **Ask clarifying questions early.** If the real-world workflow, data flow, stopping condition, or tuning goals are unclear, ask the user before implementing.

## Recommended workflow

Use this sequence when helping a user plan, implement, and run a Plugboard model:

1. **Plan the model**
   - Identify the real-world entities, stages, or responsibilities that should become separate components.
   - Define the process inputs, outputs, parameters, events, and stopping conditions.
   - Describe the data flow between components, including any feedback loops.
   - Prefer designs that can be exported cleanly to YAML.
2. **Implement components**
   - Use `plugboard.library` components where possible.
   - Create custom components only for domain-specific behavior that is not already available.
   - Keep component arguments serialisable unless there is a strong reason not to.
3. **Assemble the process**
   - Unless the user asks otherwise, prefer `LocalProcess`.
   - Wire components together with connectors or events.
   - Check for circular loops and resolve them with explicit initial values where needed.
4. **Export, visualise, and run**
   - Prefer producing a YAML configuration when the user wants repeatable runs, CLI execution, diagrams, or tuning.
   - Use `plugboard process diagram` for diagrams and `plugboard process run` for execution when working from YAML.

## Skill files

Additional task-specific instructions are available in `./skills/`. When a user asks for one of these tasks, read the matching `SKILLS.md` file and follow it:

- `skills/create-yaml-config/SKILLS.md`
- `skills/process-diagram/SKILLS.md`
- `skills/run-process-scenario/SKILLS.md`
- `skills/configure-tune/SKILLS.md`

## Planning a model

When planning a Plugboard model, include:

- the process inputs and outputs
- the components needed for each part of the workflow
- the inputs, outputs, events, and parameters for each component
- the connectors or event flows between components
- any feedback loops, initial values, and completion signals

Prefer plans where each component has a clear responsibility that matches the user's domain language.

## Implementing components

Always check whether the functionality already exists in `plugboard.library`. Common examples include:

- `FileReader` and `FileWriter` for CSV or parquet I/O
- `SQLReader` and `SQLWriter` for SQL I/O
- `LLMChat` for standard LLM interactions

### Using a built-in component

```python
from plugboard.library import FileReader

data_loader = FileReader(name="input_data", path="input.csv", field_names=["x", "y", "value"])
```

### Creating a custom component

Custom components should inherit from `plugboard.component.Component`. Add helpful structured logging with `self._logger` where appropriate.

```python
import typing as _t
from plugboard.component import Component, IOController as IO
from plugboard.schemas import ComponentArgsDict

class Offset(Component):
    """Adds a constant offset to an input value."""

    io = IO(inputs=["a"], outputs=["x"])

    def __init__(
        self,
        offset: float = 0,
        **kwargs: _t.Unpack[ComponentArgsDict],
    ) -> None:
        super().__init__(**kwargs)
        self._offset = offset

    async def step(self) -> None:
        self.x = self.a + self._offset
```

If a component is a source of new data into the model, it should await `self.io.close()` when it has finished producing values so the `Process` can shut down cleanly.

```python
class Iterator(Component):
    io = IO(outputs=["x"])

    def __init__(self, iters: int, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self._iters = iters

    async def init(self) -> None:
        self._seq = iter(range(self._iters))

    async def step(self) -> None:
        try:
            self.x = next(self._seq)
        except StopIteration:
            self._logger.info("Iterator exhausted", total_iterations=self._iters)
            await self.io.close()
```

## Assembling a process

Connect components and create a runnable process. Unless asked otherwise, prefer `LocalProcess`.

```python
from plugboard.connector import AsyncioConnector
from plugboard.library import FileWriter
from plugboard.process import LocalProcess
from plugboard.schemas import ConnectorSpec

connect = lambda src, tgt: AsyncioConnector(spec=ConnectorSpec(source=src, target=tgt))

process = LocalProcess(
    components=[
        Random(name="random", iters=5, low=0, high=10),
        Offset(name="offset", offset=10),
        Scale(name="scale", scale=2),
        Sum(name="sum"),
        FileWriter(name="save-output", path="results.csv", field_names=["input_value", "output_value"]),
    ],
    connectors=[
        connect("random.x", "save-output.input_value"),
        connect("random.x", "offset.a"),
        connect("random.x", "scale.a"),
        connect("offset.x", "sum.a"),
        connect("scale.x", "sum.b"),
        connect("sum.x", "save-output.output_value"),
    ],
)
```

Check for circular loops when defining connectors. Resolve them with `initial_values` on a component within the loop when needed.

```python
my_component = MyComponent(name="test", initial_values={"x": [False], "y": [False]})
```

## Event-driven models

Plugboard can also model workflows with events. Events are useful for conditional workflows, alerts, state transitions, or any interaction where data connectors are not the best fit.

Events must inherit from `plugboard.events.Event` and define their payload with a Pydantic model.

```python
from pydantic import BaseModel
from plugboard.events import Event

class MyEventData(BaseModel):
    some_value: int
    another_value: str

class MyEvent(Event):
    data: MyEventData
```

Components can emit events with `self.io.queue_event()` or by returning them from an event handler.

```python
from plugboard.component import Component, IOController as IO

class MyEventPublisher(Component):
    io = IO(inputs=["some_input"], output_events=[MyEvent])

    async def step(self) -> None:
        event_data = MyEventData(some_value=42, another_value=f"received {self.some_input}")
        self.io.queue_event(MyEvent(source=self.name, data=event_data))

class MyEventSubscriber(Component):
    io = IO(input_events=[MyEvent], output_events=[MyEvent])

    @MyEvent.handler
    async def handle_my_event(self, event: MyEvent) -> MyEvent:
        output_event_data = MyEventData(
            some_value=event.data.some_value + 1,
            another_value="handled",
        )
        return MyEvent(source=self.name, data=output_event_data)
```

To assemble an event-driven process, combine normal connectors with event connectors built from the component set.

```python
from plugboard.connector import AsyncioConnector
from plugboard.process import LocalProcess
from plugboard.schemas import ConnectorSpec

component_1 = ...
component_2 = ...

connect = lambda src, tgt: AsyncioConnector(spec=ConnectorSpec(source=src, target=tgt))
connectors = [
    connect("component_1.output", "component_2.input"),
]
event_connectors = AsyncioConnector.builder().build_event_connectors([component_1, component_2])

process = LocalProcess(
    components=[component_1, component_2],
    connectors=connectors + event_connectors,
)
```

## Exporting and running models

Save a process configuration for reuse:

```python
process.dump("my-model.yaml")
```

Run the saved model from the CLI:

```sh
plugboard process run my-model.yaml
```

## Resources

- **Library Components**: `plugboard.library`
- **Component Base Class**: `plugboard.component.Component`
- **Process Types**: `plugboard.process`
- **Event System**: `plugboard.events`
- **API Documentation**: https://docs.plugboard.dev
