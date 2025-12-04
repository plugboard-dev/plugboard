from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from plugboard.schemas.process import ProcessSpec


class ComponentType(BaseModel):
    id: str = Field(
        ..., description="Unique identifier for the component type (e.g. python class path)"
    )
    name: str = Field(..., description="Human readable name")
    description: Optional[str] = None
    args_schema: Dict[str, Any] = Field(
        ..., description="JSON Schema describing the arguments this component accepts"
    )


class ConnectorType(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    parameters_schema: Optional[Dict[str, Any]] = None


class EventType(BaseModel):
    type: str = Field(..., description="The event type string (e.g. system.stop)")
    description: Optional[str] = None
    schema_: Dict[str, Any] = Field(
        ..., alias="schema", description="JSON Schema describing the event data"
    )


class ProcessType(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    args_schema: Optional[Dict[str, Any]] = None


class UIConfig(BaseModel):
    layout: Optional[Dict[str, Any]] = Field(None, description="Layout configuration for the UI")
    styles: Optional[Dict[str, Any]] = Field(None, description="Style configuration for the UI")


class ProcessConfig(BaseModel):
    id: Optional[str] = None
    cli_config: ProcessSpec
    ui_config: UIConfig


class ProcessConfigSummary(BaseModel):
    id: str
    name: Optional[str] = None
