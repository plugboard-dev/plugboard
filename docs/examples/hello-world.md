Plugboard is built to help you with two things: defining process models, and executing those models. There are two main ways to interact with plugboard: via the Python API; or, via the CLI using model definitions saved in yaml or json format.

### Building models with the Python API
A model is made up of one or more components, though Plugboard really shines when you have many! First we start by defining the `Component`s within our model. Components can have only inputs, only outputs, or both. To keep it simple we just have two components here, showing the most basic functionality.
```python
import typing as _t
import aiofiles
from plugboard.component import Component
from plugboard.io import IOController as IO

class A(Component):
    io = IO(outputs=["out_1"])

    def __init__(self, iters: int, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._iters = iters

    async def init(self) -> None:
        self._seq = range(self._iters)

    async def step(self) -> None:
        self.out_1 = next(self._seq)

class B(Component):
    io = IO(inputs=["in_1"])

    def __init__(self, path: str, *args: _t.Any, **kwargs: _t.Any) -> None:
        super().__init__(*args, **kwargs)
        self._path = path

    async def step(self) -> None:
        out = 2 * self.in_1
        async with aiofiles.open(self._path, "a") as f:
            f.write(f"{out}\n")
```

Now we take these components, connect them up as a `Process`, and fire off the model. Calling `Process.run` triggers all the components to start iterating through all their inputs until a termination condition is reached. Simulations proceed in an event-driven manner: when inputs arrive, the components are triggered to step forward in time. The framework handles the details of the inter-component communication, you just need to specify the logic of your components, and the connections between them.
```python
import asyncio
from plugboard.process import ProcessBuilder
from pluboard.connector import ConnectorSpec

process = ProcessBuilder(
    components=[
        A(name="a", iters=10), B(name="b", path="./b.txt")
    ],
    connector_specs=[
        ConnectorSpec(source="a.out_1", target="b.in_1")
    ]
)

await process.init()
await process.run()
```

### Executing pre-defined models on the CLI
In many cases, we want to define components once, with suitable parameters, and then use them repeatedly in different simulations. Plugboard enables this workflow with model specification files in yaml or json format. Once the components have been defined, the simple model above can be represented with a yaml file like so.
```yaml
# my-model.yaml
plugboard:
  process:
    args:
      components:
      - type: A
        args:
          name: "a"
          iters: 10
      - type: B
        args:
          name: "b"
          path: "./b.txt"
      connectors:
      - source: "a.out_1"
        target: "b.in_1"
```

We can now run this model using the plugboard CLI with the command:
```shell
plugboard process run --yaml-input my-model.yaml
```
