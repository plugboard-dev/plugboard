# AI Agent Instructions for Plugboard Examples

This document provides guidelines for AI agents working with Plugboard example code, demonstrations, and tutorials.

## Purpose

These examples demonstrate how to use Plugboard to model and simulate complex processes. Help users build intuitive, well-documented examples that showcase Plugboard's capabilities.

## Example Categories

### Tutorials (`tutorials/`)
Step-by-step learning materials for new users. Focus on:
- Clear explanations of concepts
- Progressive complexity
- Runnable code with expected outputs
- Markdown documentation alongside code

### Demos (`demos/`)
Practical applications organized by domain:
- `fundamentals/`: Core Plugboard concepts
- `llm/`: LLM and AI integrations  
- `physics-models/`: Physics-based simulations
- `finance/`: Financial modeling examples

## Creating Examples

### Planning a Model

Help users structure their model from concept to implementation:

1. **Define Scope**
   - Clear problem statement
   - Expected inputs and outputs
   - Success criteria

2. **Component Design**
   - Break problem into logical components
   - Define each component's inputs, outputs, and parameters
   - Identify data dependencies and flow

3. **Data Flow**
   - Map connections between components
   - Identify feedback loops
   - Plan event-driven interactions if needed

Example breakdown for a hot-water tank model:
- **Components**: WaterTank, Heater, Thermostat, DataLoader, ResultSaver
- **Flow**: Temperature sensor → Thermostat → Heater → Tank → Temperature sensor
- **Data**: Load initial conditions, save temperature over time

### Implementing Components

Use appropriate components from the library or create custom ones:

**Using Built-in Components**
```python
from plugboard.library import Load, Save, Random

# Load data from file
data_loader = Load(name="load_data", path="input.csv")

# Save results
results_saver = Save(name="save_results", path="output.csv")
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
        self.x = self.a + self._offset
```

### Assembling a Process

Connect components and create a runnable process:

```python
from plugboard.connector import AsyncioConnector
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
        Save(name="save-input", path="input.txt"),
        Save(name="save-output", path="output.txt"),
    ],
    connectors=[
        connect("random.x", "save-input.value_to_save"),
        connect("random.x", "offset.a"),
        connect("random.x", "scale.a"),
        connect("offset.x", "sum.a"),
        connect("scale.x", "sum.b"),
        connect("sum.x", "save-output.value_to_save"),
    ],
)
```

### Visualizing Process Flow

Generate diagrams to help understand the model:

```python
from plugboard.diagram import markdown_diagram

diagram = markdown_diagram(process)
print(diagram)
```

### Running the Model

Execute the process asynchronously:

```python
import asyncio

async def main():
    async with process:
        await process.run()

if __name__ == "__main__":
    asyncio.run(main())
```

## Event-Driven Models

For models requiring dynamic interactions and responses:

### When to Use Events
- Monitoring thresholds and triggering alerts
- Conditional workflows (if X happens, do Y)
- Multi-agent systems with communication
- Real-time data processing with decision points

### Defining Events

```python
from pydantic import BaseModel
from plugboard.events import Event

class ThresholdCrossedData(BaseModel):
    component: str
    value: float
    threshold: float
    timestamp: float

class ThresholdCrossed(Event):
    data: ThresholdCrossedData
```

### Publishing Events

```python
from plugboard.component import Component, IOController as IO

class Monitor(Component):
    io = IO(
        inputs=["value"],
        outputs=[],
        output_events=[ThresholdCrossed]
    )
    
    def __init__(self, threshold: float, **kwargs) -> None:
        super().__init__(**kwargs)
        self._threshold = threshold
    
    async def step(self) -> None:
        if self.value > self._threshold:
            event_data = ThresholdCrossedData(
                component=self.name,
                value=self.value,
                threshold=self._threshold,
                timestamp=time.time()
            )
            self.io.queue_event(
                ThresholdCrossed(source=self.name, data=event_data)
            )
```

### Subscribing to Events

```python
class AlertHandler(Component):
    io = IO(
        inputs=[],
        outputs=[],
        input_events=[ThresholdCrossed],
        output_events=[AlertSent]
    )
    
    @ThresholdCrossed.handler
    async def handle_threshold(self, event: ThresholdCrossed) -> AlertSent:
        print(f"ALERT: {event.data.component} exceeded threshold!")
        
        # Return new event
        alert_data = AlertSentData(
            original_event=event.data,
            alert_method="console"
        )
        return AlertSent(source=self.name, data=alert_data)
```

### Wiring Event-Driven Components

```python
from plugboard.connector import ConnectorBuilder
from plugboard.events.event_connector_builder import EventConnectorBuilder

# Regular connectors
connect = lambda src, tgt: AsyncioConnector(
    spec=ConnectorSpec(source=src, target=tgt)
)
connectors = [
    connect("data_source.value", "monitor.value"),
    # ... other data connectors
]

# Event connectors (automatically wired)
connector_builder = ConnectorBuilder(connector_cls=AsyncioConnector)
event_connector_builder = EventConnectorBuilder(
    connector_builder=connector_builder
)
components = [monitor, alert_handler, ...]
event_connectors = list(
    event_connector_builder.build(components).values()
)

# Create process with both types
process = LocalProcess(
    components=components,
    connectors=connectors + event_connectors,
)
```

## Exporting Models

Save process configuration for reuse:

```python
# Export to YAML
process.dump("my_model.yaml")

# Later, load and run via CLI
# $ plugboard process run my_model.yaml
```

## Jupyter Notebooks

For interactive demonstrations:

1. **Structure**
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
   - Include sample outputs in notebook
   - Generate plots where helpful
   - Provide interpretation of results

## Documentation Standards

### Code Comments
- Explain *why*, not *what*
- Document assumptions
- Note limitations or edge cases

### Docstrings
- Use Google-style docstrings
- Document all parameters and return values
- Include usage examples for complex functions

### Markdown Files
- Clear headings and structure
- Code blocks with syntax highlighting
- Link to relevant API documentation
- Include expected outputs

## Testing Examples

While examples are primarily educational:
- Ensure all code actually runs
- Verify outputs are as expected
- Check for common error cases
- Test with different parameter values

## Common Patterns

### Data Processing Pipeline
```python
components = [
    Load(name="load", path="data.csv"),
    Transform(name="transform", ...),
    Filter(name="filter", ...),
    Save(name="save", path="output.csv"),
]
```

### Simulation Loop
```python
components = [
    Clock(name="clock", steps=100),
    Model(name="model", ...),
    Observer(name="observer", ...),
    Save(name="save", ...),
]
```

### Multi-Agent System
```python
components = [
    Agent(name="agent_1", ...),
    Agent(name="agent_2", ...),
    Environment(name="env", ...),
    Coordinator(name="coord", ...),
]
# Use events for agent communication
```

## Resources

- **Library Components**: `plugboard.library`
- **Component Base Class**: `plugboard.component.Component`
- **Process Types**: `plugboard.process`
- **Event System**: `plugboard.events`
- **API Documentation**: https://docs.plugboard.dev
