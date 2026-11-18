"""Backward-compatible import path; the implementation lives in application/data_api/."""

from contractapi.application.data_api.app import create_data_app
from contractapi.application.data_api.common import (
    _invalidate_endpoint_cache,
)
from contractapi.application.data_api.write_support import (
    _do_insert,
)

__all__ = ["create_data_app", "_invalidate_endpoint_cache", "_do_insert"]
