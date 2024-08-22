# plugboard
Plugboard is an event-driven modelling and orchestration framework in Python for simulating complex processes with many interconnected components.

The code was originally developed to create digital twins of complex heavy industrial processes involving material recirculation, enabling scenario analysis, yield optimisation, and operational improvements. At its heart, plugboard is an abstract and general purpose modelling and orchestration tool for distributed simulations which can be applied to problems in many domains.

## Key Features
These are the key features of the core library for building and executing process models:
- Classes containing core framework logic which can be extended to define domain specific model component logic.
- YAML model specification format for defining process models.
- CLI commands for executing models locally or in cloud infrastructure.
- Support for different simulation paradigms: realtime, discrete time, and discrete event.
- Detailed logging of component inputs, outputs and state for monitoring and process mining or surrogate modelling use-cases.
- Modern implementation with Python >= 3.12 based around asyncio with complete type annotation coverage.
- Support for strongly typed data messages and validation based on pydantic.
- Support for different parallelisation patterns such as: single-threaded with coroutines, single-host multi process, or distributed with Ray in Kubernetes.
- Data exchange between components with popular messaging technologies like RabbitMQ and Google Pub/Sub.
- Support for different message exchange patterns such as: one-to-one, one-to-many, many-to-one etc via a broker; or peer-to-peer with http requests.
- Load and store data to/from models using various infrastructures such as blob stores and databases via provided integrations.

## Installation
Plugboard requires Python >= 3.12. Install the package with pip inside a virtual env as below.
```shell
python -m pip install plugboard
```

## Usage
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

## Documentation
For more information including a detailed API reference and step-by-step usage examples, refer to the [documentation site]().

## Contributions
Contributions are welcomed and warmly received! For bug fixes and smaller feature requests feel free to open an issue on this repo. For any larger changes please get in touch with us to discuss first. More information for developers can be found in [the contributors section]() of the docs.

## Licence
Plugboard is offered under the [Apache 2.0 Licence](https://www.apache.org/licenses/LICENSE-2.0) so it's free for personal or commercial use within those terms.
