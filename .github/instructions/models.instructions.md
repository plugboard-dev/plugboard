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
from plugboard.component import Component
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