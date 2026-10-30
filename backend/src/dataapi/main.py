"""ASGI entrypoint: `uvicorn dataapi.main:app`."""

from dataapi.interfaces.http.app_factory import create_studio_app

app = create_studio_app()
