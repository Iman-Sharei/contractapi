"""ASGI entrypoint: `uvicorn contractapi.main:app`."""

from contractapi.interfaces.http.app_factory import create_studio_app

app = create_studio_app()
