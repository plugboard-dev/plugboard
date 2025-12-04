from typing import Dict, List
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from plugboard.server.models import ProcessConfig, ProcessConfigSummary


router = APIRouter()

# In-memory storage for demonstration
_configs: Dict[str, ProcessConfig] = {}


@router.get("/process-configs", response_model=List[ProcessConfigSummary])
async def list_process_configs():
    return [
        ProcessConfigSummary(id=c.id, name=c.cli_config.args.name)
        for c in _configs.values()
        if c.id
    ]


@router.post("/process-configs", response_model=ProcessConfig, status_code=201)
async def create_process_config(config: ProcessConfig):
    new_id = str(uuid4())
    config.id = new_id
    _configs[new_id] = config
    return config


@router.get("/process-configs/{id}", response_model=ProcessConfig)
async def get_process_config(id: str):
    if id not in _configs:
        raise HTTPException(status_code=404, detail="Process config not found")
    return _configs[id]
