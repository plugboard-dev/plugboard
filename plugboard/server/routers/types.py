from typing import List

from fastapi import APIRouter, HTTPException

from plugboard.server.models import (
    ComponentType,
    ConnectorType,
    EventType,
    ProcessType,
)


router = APIRouter()


@router.get("/component-types", response_model=List[ComponentType])
async def list_component_types():
    # TODO: Implement discovery of component types
    return []


@router.get("/component-types/{id}", response_model=ComponentType)
async def get_component_type(id: str):
    # TODO: Implement retrieval of component type details
    raise HTTPException(status_code=404, detail="Component type not found")


@router.get("/connector-types", response_model=List[ConnectorType])
async def list_connector_types():
    # TODO: Implement discovery of connector types
    return []


@router.get("/connector-types/{id}", response_model=ConnectorType)
async def get_connector_type(id: str):
    # TODO: Implement retrieval of connector type details
    raise HTTPException(status_code=404, detail="Connector type not found")


@router.get("/event-types", response_model=List[EventType])
async def list_event_types():
    # TODO: Implement discovery of event types
    return []


@router.get("/event-types/{id}", response_model=EventType)
async def get_event_type(id: str):
    # TODO: Implement retrieval of event type details
    raise HTTPException(status_code=404, detail="Event type not found")


@router.get("/process-types/{id}", response_model=ProcessType)
async def get_process_type(id: str):
    # TODO: Implement retrieval of process type details
    raise HTTPException(status_code=404, detail="Process type not found")
