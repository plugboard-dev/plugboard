Plugboard is built to help you with two things: defining process models, and executing those models. There are two main ways to interact with plugboard: via the Python API; or, via the CLI using model definitions saved in yaml or json format.

### Building models with the Python API
A model is made up of one or more components, though Plugboard really shines when you have many! First we start by defining the `Component`s within our model. Components can have only inputs, only outputs, or both. To keep it simple we just have two components here, showing the most basic functionality. Each component has several methods which are called at different stages during model execution: `init` for optional initialisation actions; `step` to take a single step forward through time; `run` to execute all steps; and `destroy` for optional teardown actions.
```python
--8<-- "examples/tutorials/001_hello_world/hello_world.py:components"
```

Now we take these components, connect them up as a `Process`, and fire off the model. Using the `Process` context handler takes care of calling `init` at the beginning and `destroy` at the end for all `Component`s. Calling `Process.run` triggers all the components to start iterating through all their inputs until a termination condition is reached. Simulations proceed in an event-driven manner: when inputs arrive, the components are triggered to step forward in time. The framework handles the details of the inter-component communication, you just need to specify the logic of your components, and the connections between them.
```python
--8<-- "examples/tutorials/001_hello_world/hello_world.py:main"
```

### Executing pre-defined models on the CLI
In many cases, we want to define components once, with suitable parameters, and then use them repeatedly in different simulations. Plugboard enables this workflow with model specification files in yaml or json format. Once the components have been defined, the simple model above can be represented with a yaml file like so.
```yaml
--8<-- "examples/tutorials/001_hello_world/model.yaml"
```

We can now run this model using the plugboard CLI with the command:
```shell
plugboard process run model.yaml
```
