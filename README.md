<div align="center">
  <picture align="center">
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/plugboard-dev/plugboard/refs/heads/main/docs/assets/plugboard-logo-dark.svg" width="65%" height="auto">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/plugboard-dev/plugboard/refs/heads/main/docs/assets/plugboard-logo-light.svg" width="65%" height="auto">
    <img alt="Plugboard" src="docs/assets/plugboard-logo.jpeg" width="80%" height="auto">
  </picture>
</div>

<div align="center" class="badge-section">
  <br>
  <a href="https://pypi.org/project/plugboard/", alt="PyPI version">
    <img alt="PyPI" src="https://img.shields.io/pypi/v/plugboard?labelColor=075D7A&color=CC9C4A"></a>
  <a href="https://www.python.org/", alt="Python versions">
    <img alt="Python" src="https://img.shields.io/pypi/pyversions/plugboard?labelColor=075D7A&color=CC9C4A"></a>
  <a href="https://github.com/plugboard-dev/plugboard?tab=Apache-2.0-1-ov-file#readme", alt="License">
    <img alt="License" src="https://img.shields.io/github/license/plugboard-dev/plugboard?labelColor=075D7A&color=CC9C4A"></a>
  <a href="https://github.com/plugboard-dev/plugboard", alt="Typed">
    <img alt="Typed" src="https://img.shields.io/pypi/types/plugboard?labelColor=075D7A&color=CC9C4A"></a>
  <br>
  <a href="https://github.com/plugboard-dev/plugboard/actions/workflows/lint-test.yaml", alt="Lint and test">
    <img alt="Lint and Test" src="https://github.com/plugboard-dev/plugboard/actions/workflows/lint-test.yaml/badge.svg"></a>
  <a href="https://github.com/plugboard-dev/plugboard/actions/workflows/docs.yaml", alt="Documentation">
    <img alt="Docs" src="https://github.com/plugboard-dev/plugboard/actions/workflows/docs.yaml/badge.svg"></a>
  <a href="https://codecov.io/gh/plugboard-dev/plugboard" >
    <img src="https://codecov.io/gh/plugboard-dev/plugboard/graph/badge.svg?token=4LU4K6TOLQ"/></a>
</div>

<hr>

Plugboard is an **event-driven modelling and orchestration framework** in Python for simulating and driving complex processes with many interconnected stateful components.

You can use it to **define models** in Python and **connect them together easily** so that data automatically moves between them. After running your model on a laptop, you can then scale out on multiple processors, or go to a compute cluster in the cloud.

Some examples of what you can build with Plugboard include:

- Digital twin models of complex processes:
    - It can easily handle common problems in industrial process simulation like material recirculation;
    - Models can be composed from different underlying components, e.g. physics-based simulations, machine-learning, AI models;
- AI integrations:
    - You can feed data to/from different LLMs using Plugboard components;
    - Easily reconfigure and swap model providers for optimal performance.

## 🖋️ Key Features

- **Reusable classes** containing the core framework, which you can extend to define your own model logic;
- Support for different simulation paradigms: **discrete time** and **event based**.
- **YAML model specification** format for saving model definitions, allowing you to run the same model locally or in cloud infrastructure;
- A **command line interface** for executing models;
- Built to handle the **data intensive simulation** requirements of industrial process applications;
- Modern implementation with **Python 3.12 and above** based around **asyncio** with complete type annotation coverage;
- Built-in integrations for **loading/saving data** from cloud storage and SQL databases;
- **Detailed logging** of component inputs, outputs and state for monitoring and process mining or surrogate modelling use-cases.

## 🔌 Installation

Plugboard requires Python >= 3.12. Install the package with pip inside a virtual env as below.
```shell
python -m pip install plugboard
```

Optional integrations for different cloud providers can be installed using `plugboard[aws]`, `plugboard[azure]` or `plugboard[gcp]`.

Support for parallelisation can be installed using `plugboard[ray]`.

## 🚀 Usage

Plugboard is built to help you with two things: defining process models, and executing those models. There are two main ways to interact with plugboard: via the Python API; or, via the CLI using model definitions saved in yaml format.

### Building models with the Python API

A model is made up of one or more components, though Plugboard really shines when you have many! First we start by defining the `Component`s within our model. Components can have only inputs, only outputs, or both. To keep it simple we just have two components here, showing the most basic functionality. Each component has several methods which are called at different stages during model execution: `init` for optional initialisation actions; `step` to take a single step forward through time; `run` to execute all steps; and `destroy` for optional teardown actions.
```python
import typing as _t
from plugboard.component import Component, IOController as IO
from plugboard.schemas import ComponentArgsDict

class A(Component):
    io = IO(outputs=["out_1"])

    def __init__(self, iters: int, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self._iters = iters

    async def init(self) -> None:
        self._seq = iter(range(self._iters))

    async def step(self) -> None:
        try:
            self.out_1 = next(self._seq)
        except StopIteration:
            await self.io.close()


class B(Component):
    io = IO(inputs=["in_1"])

    def __init__(self, path: str, **kwargs: _t.Unpack[ComponentArgsDict]) -> None:
        super().__init__(**kwargs)
        self._path = path

    async def init(self) -> None:
        self._f = open(self._path, "w")

    async def step(self) -> None:
        out = 2 * self.in_1
        self._f.write(f"{out}\n")

    async def destroy(self) -> None:
        self._f.close()
```

There is also a `@component` decorator which simplifies creating `Component`s for small stateless transform type functions. A component instance can be created by calling the `.component` method of the object returned by the decorator. The wrapped function can be sync or async and will be called as the step method with the named inputs being passed in. Inputs must be specified matching function args. Outputs must be specified and the function must return a dictionary where the keys match the outputs.
```python
@component(inputs=["in_1"], outputs=["out_1"])
def pow2(in_1: int) -> int:
  return {"out_1": in_1 ** 2}

result = pow2(2)  # Preserves original function call -> result = {"out_1": 4}
comp_pow2 = pow2.component(name="component-pow2")
```

Now we take these components, connect them up as a `Process`, and fire off the model. Using the `Process` context handler takes care of calling `init` at the beginning and `destroy` at the end for all `Component`s. Calling `Process.run` triggers all the components to start iterating through all their inputs until a termination condition is reached. Simulations proceed in an event-driven manner: when inputs arrive, the components are triggered to step forward in time. The framework handles the details of the inter-component communication, you just need to specify the logic of your components, and the connections between them.
```python
from plugboard.connector import AsyncioConnector
from plugboard.process import LocalProcess
from plugboard.schemas import ConnectorSpec

process = LocalProcess(
    components=[A(name="component-a", iters=5), B(name="component-b", path="b.txt"), comp_pow2],
    connectors=[
        AsyncioConnector(
            spec=ConnectorSpec(source="component-a.out_1", target="component-b.in_1"),
        ),
        AsyncioConnector(
            spec=ConnectorSpec(source="component-a.out_1", target=f"{comp_pow2.name}.in_1"),
        )
    ],
)
async with process:
    await process.run()
```

Visually, we've created the model below, with Plugboard automatically handling the flow of data between the components.
```mermaid
flowchart LR
  subgraph Process
    direction LR
    comp_a(A<br>**component-a**)
    comp_b(B<br>**component-b**)
    comp_pow2(pow2<br>**component-pow2**)
  end
  comp_a -- out_1 --> comp_b
  comp_a -- out_1 --> comp_pow2
```

### Executing pre-defined models on the CLI

In many cases, we want to define components once, with suitable parameters, and then use them repeatedly in different simulations. Plugboard enables this workflow with model specification files in yaml format. Once the components have been defined, the simple model above can be represented as follows. Components auto-generated with the `@component` decorator can be referenced by the name of the wrapped function.
```yaml
# my-model.yaml
plugboard:
  process:
    args:
      components:
      - type: hello_world.A
        args:
          name: "component-a"
          iters: 10
      - type: hello_world.B
        args:
          name: "component-b"
          path: "./b.txt"
      - type: hello_world.pow2
        args:
          name: "component-pow2"
      connectors:
      - source: "component-a.out_1"
        target: "component-b.in_1"
      - source: "component-a.out_1"
        target: "component-pow2.in_1"
```

We can now run this model using the plugboard CLI with the command:
```shell
plugboard process run my-model.yaml
```

## 📖 Documentation

For more information including a detailed API reference and step-by-step usage examples, refer to the [documentation site](https://docs.plugboard.dev). We recommend diving into the [tutorials](https://docs.plugboard.dev/latest/examples/tutorials/hello-world/) for a step-by-step to getting started.

## 🐾 Roadmap

Plugboard is under active development, with new features in the works:

- Support for strongly typed data messages and validation based on pydantic.
- Support for different parallelisation patterns such as: single-threaded with coroutines, single-host multi process, or distributed with Ray in Kubernetes.
- Data exchange between components with popular messaging technologies like RabbitMQ and Google Pub/Sub.
- Support for different message exchange patterns such as: one-to-one, one-to-many, many-to-one etc via a broker; or peer-to-peer with http requests.

## 👋 Contributions

Contributions are welcomed and warmly received! For bug fixes and smaller feature requests feel free to open an issue on this repo. For any larger changes please get in touch with us to discuss first. More information for developers can be found in [the contributing section](https://docs.plugboard.dev/latest/contributing/) of the docs.

## ⚖️ Licence

Plugboard is offered under the [Apache 2.0 Licence](https://www.apache.org/licenses/LICENSE-2.0) so it's free for personal or commercial use within those terms.
