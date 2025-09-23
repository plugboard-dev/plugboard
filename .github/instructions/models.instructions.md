---
applyTo: "examples/**/*.py,examples/**/*.ipynb"
---

# Project Overview

Plugboard is an event-driven modelling and orchestration framework in Python for simulating and driving complex processes with many interconnected stateful components.

## Planning a model

Help users to plan their models from a high-level overview to a detailed design. This should include:

* The inputs and outputs of the model;
* The components that will be needed to implement each part of the model, and any inputs, outputs and parameters they will need;
* The data flow between components.

For example, a model of a hot-water tank might have components for the water tank, the heater and the thermostat. Additional components might be needed to load data from a file or database, and similarly to save simulation results.

## Implementing components

Help users set up the components they need to implement their model. Custom components can be implemented by subclassing the [`Component`][plugboard.component.Component]. Common components for tasks like loading data can be imported from [`plugboard.library`][plugboard.library].

An empty component looks  like this:

```python
import typing as _t

from plugboard.component import Component, IOController as IO
from plugboard.schemas import ComponentArgsDict

class Offset(Component):
    """Implements `x = a + offset`."""
    io = IO(inputs=["a"], outputs=["x"])

    def __init__(self, offset: float = 0, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self._offset = offset

    async def step(self) -> None:
        # TODO: Implement business logic here
        # Example `self.x = self.a + self._offset`
        pass
```

## Connecting components into a process

You can help users to connect their components together. For initial development and testing use a [LocalProcess][plugboard.process.LocalProcess] to run the model in a single process.

Example code to connect components together and create a process:

```python
from plugboard.connector import AsyncioConnector
from plugboard.process import LocalProcess
from plugboard.schemas import ConnectorSpec

connect = lambda in_, out_: AsyncioConnector( 
    spec=ConnectorSpec(source=in_, target=out_)
)
process = LocalProcess(
    components=[
        Random(name="random", iters=5, low=0, high=10),
        Offset(name="offset", offset=10),
        Scale(name="scale", scale=2),
        Sum(name="sum"),
        Save(name="save-input", path="input.txt"),
        Save(name="save-output", path="output.txt"),
    ],
    connectors=[
        # Connect x output of the component named "random" to the value_to_save input of the component named "save-input", etc.
        connect("random.x", "save-input.value_to_save"),
        connect("random.x", "offset.a"),
        connect("random.x", "scale.a"),
        connect("offset.x", "sum.a"),
        connect("scale.x", "sum.b"),
        connect("sum.x", "save-output.value_to_save"),
    ],
)
```

If you need a diagram of the process you can import `plugboard.diagram.markdown_diagram` and use it to create a markdown representation of the process:

```python
from plugboard.diagram import markdown_diagram
diagram = markdown_diagram(process)
print(diagram)
```

## Running the model

You can help users to run their model. For example, to run the model defined above:

```python

import asyncio

async with process:
    await process.run()
```

## Event-driven models

You can help users to implement event-driven models using Plugboard's event system. Components can emit and handle events to communicate with each other.

Examples of where you might want to use events include:
* A component that monitors a data stream and emits an event when a threshold is crossed;
* A component that listens for events and triggers actions in response, e.g. sending an alert;
* A trading algorithm that uses events to signal buy/sell decisions.

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

## Exporting models

If the user wants to export their model you use in the CLI, you can do this by calling `process.dump("path/to/file.yaml")`. 
