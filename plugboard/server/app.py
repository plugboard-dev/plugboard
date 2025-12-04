from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from plugboard.server.routers import configs, types


app = FastAPI(
    title="Plugboard API",
    description="API for building and observing Plugboard models.",
    version="0.1.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(types.router, tags=["Types"])
app.include_router(configs.router, tags=["Configs"])


@app.get("/health")
async def health_check():
    return {"status": "ok"}
