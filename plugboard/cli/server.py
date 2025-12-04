import typer
import uvicorn


app = typer.Typer(help="Manage the Plugboard API server.")


@app.command()
def start(
    host: str = typer.Option("127.0.0.1", help="Host to bind the server to."),
    port: int = typer.Option(8000, help="Port to bind the server to."),
    reload: bool = typer.Option(False, help="Enable auto-reload."),
):
    """Start the Plugboard API server."""
    uvicorn.run("plugboard.server.app:app", host=host, port=port, reload=reload)
