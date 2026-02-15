# AI Agent Instructions for Plugboard Examples

This document provides guidelines for AI agents working with Plugboard example code, demonstrations, and tutorials.

## Purpose

These examples demonstrate how to use Plugboard to model and simulate complex processes. Help users build intuitive, well-documented examples that showcase Plugboard's capabilities.

## Example Categories

### Tutorials (`tutorials/`)

Step-by-step learning materials for new users. Focus on:
- Clear explanations of concepts.
- Progressive complexity.
- Runnable code with expected outputs.
- Markdown documentation alongside code. You can delegate to the `docs` agent to make these updates.

### Demos (`demos/`)

Practical applications are organized by domain into folders.

## Creating a Plugboard model

Always using the following sequence of steps to help users plan, implement and run their models.

### Planning a Model

Help users to plan their models from a high-level overview to a detailed design. This should include:

* The inputs and outputs of the model;
* The components that will be needed to implement each part of the model, and any inputs, outputs and parameters they will need;
* The data flow between components, either via connectors or events. Identify any feedback loops and resolve if necessary.

Ask questions if anything is not clear about the business logic or you require additional domain expertise from the user.

### Implementing Components

Always check whether the functionality you need is already available in the library components in `plugboard.library`. For example, try to use:
- `FileReader` and `FileWriter` for reading/writing data from CSV or parquet files.
- `SQLReader` and `SQLReader` for reading/writing data from SQL databases.
- `LLMChat` for interacting with standard LLMs, e.g. OpenAI, Gemini, etc.

**Using Built-in Components**

```python
from plugboard.library import FileReader

data_loader = FileReader(name="input_data", path="input.csv", field_names=["x", "y", "value"])
```

**Creating Custom Components**

```python
import typing as _t
from plugboard.component import Component, IOController as IO
from plugboard.schemas import ComponentArgsDict

class Offset(Component):
    """Adds a constant offset to input value."""
    io = IO(inputs=["a"], outputs=["x"])

    def __init__(
        self, 
        offset: float = 0, 
        **kwargs: _t.Unpack[ComponentArgsDict]
    ) -> None:
        super().__init__(**kwargs)
        self._offset = offset

    async def step(self) -> None:
        # Implement business logic here
        self.x = self.a + self._offset
```

If a component is intended to be a source of new data into the model, then it should await `self.io.close()` when it has finished all the iterations it needs to do. This sends a signal into the `Process` so that other components know when the model has completed. For example, this component runs for a fixed number of iterations:

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
            await self.io.close()
```

### Assembling a Process

Connect components and create a runnable process. Unless asked otherwise, use a `LocalProcess`.

```python
from plugboard.connector import AsyncioConnector
from plugboard.library import FileWriter
from plugboard.process import LocalProcess
from plugboard.schemas import ConnectorSpec

# Helper for creating connectors
connect = lambda src, tgt: AsyncioConnector(
    spec=ConnectorSpec(source=src, target=tgt)
)

# Create process with components and connectors
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

Check for circular loops when defining connectors in the `Process`. These will need to be resolved using the `initial_values` argument to a component somewhere within the loop, e.g.

```python
my_component = MyComponent(name="test", initial_values={"x": [False], "y": [False]})
```

### Visualizing Process Flow

You can create a mermaid diagram to help users understand their models visually.

```python
from plugboard.diagram import markdown_diagram

diagram = markdown_diagram(process)
print(diagram)
```

### Running the Model

You can help users to run their model. For example, to run the model defined above:

```python
async with process:
    await process.run()
```

## Event-Driven Models

You can help users to implement event-driven models using Plugboard's event system. Components can emit and handle events to communicate with each other.

Examples of where you might want to use events include:
* A component that monitors a data stream and emits an event when a threshold is crossed.
* A component that listens for events and triggers actions in response, e.g. sending an alert.
* A trading algorithm that uses events to signal buy/sell decisions.
* Where a model has conditional workflows, e.g. process data differently in the model depending on a specific condition.

Events must be defined by inheriting from the `plugboard.events.Event` class. Each event class should define the data it carries using a Pydantic `BaseModel`. For example:

```python
from pydantic import BaseModel
from plugboard.events import Event

class MyEventData(BaseModel):
    some_value: int
    another_value: str

class MyEvent(Event):
    data: MyEventData
```

Components can emit events using the `self.io.queue_event()` method or by returning them from an event handler. Event handlers are defined using methods decorated with `@EventClass.handler`. For example:

```python
from plugboard.component import Component, IOController as IO

class MyEventPublisher(Component):
    io = IO(inputs=["some_input"], output_events=[MyEvent])

    async def step(self) -> None:
        # Emit an event
        event_data = MyEventData(some_value=42, another_value=f"received {self.some_input}")
        self.io.queue_event(MyEvent(source=self.name, data=event_data))

class MyEventSubscriber(Component):
    io = IO(input_events=[MyEvent], output_events=[MyEvent])

    @MyEvent.handler
    async def handle_my_event(self, event: MyEvent) -> MyEvent:
        # Handle the event
        print(f"Received event: {event.data}")
        output_event_data = MyEventData(some_value=event.data.some_value + 1, another_value="handled")
        return MyEvent(source=self.name, data=output_event_data)
```

To assemble a process with event-driven components, you can use the same approach as for non-event-driven components. You will need to create connectors for event-driven components using `plugboard.events.event_connector_builder.EventConnectorBuilder`. For example:

```python
from plugboard.connector import AsyncioConnector, ConnectorBuilder
from plugboard.events.event_connector_builder import EventConnectorBuilder
from plugboard.process import LocalProcess

# Define components....
component_1 = ...
component_2 = ...

# Define connectors for non-event components as before
connect = lambda in_, out_: AsyncioConnector(spec=ConnectorSpec(source=in_, target=out_))
connectors = [
    connect("component_1.output", "component_2.input"),
    ...
]

connector_builder = ConnectorBuilder(connector_cls=AsyncioConnector)
event_connector_builder = EventConnectorBuilder(connector_builder=connector_builder)
event_connectors = list(event_connector_builder.build(components).values())

process = LocalProcess(
    components=[
        component_1, component_2, ...
    ],
    connectors=connectors + event_connectors,
)
```

## Exporting Models

Save a process configuration for reuse:

```python
process.dump("my-model.yaml")

Later, load and run via CLI
```sh
plugboard process run my-model.yaml
```

## Jupyter Notebooks

For interactive demonstrations:

1. **Structure**
   - Title markdown cell in the same format as the other notebooks, including badges to run on Github/Colab
   - Clear markdown sections
   - Code cells with explanations
   - Visualizations of results
   - Summary of findings

2. **Best Practices**
   - Keep cells focused and small
   - Add docstrings to helper functions
   - Show intermediate results
   - Include error handling
   - Clean up resources properly

3. **Output**
   - Clear cell output before committing
   - Generate plots where helpful
   - Provide interpretation of results

## Resources

- **Library Components**: `plugboard.library`
- **Component Base Class**: `plugboard.component.Component`
- **Process Types**: `plugboard.process`
- **Event System**: `plugboard.events`
- **API Documentation**: https://docs.plugboard.dev
