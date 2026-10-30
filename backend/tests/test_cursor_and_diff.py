from dataapi.application.cursor_paging import decode_cursor, encode_cursor
from dataapi.application.openapi_diff import diff_openapi


def test_cursor_roundtrip():
    cursor = encode_cursor(42)
    assert decode_cursor(cursor) == 42


def test_openapi_diff_detects_breaking_and_new():
    before = {
        "paths": {
            "/customers": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "properties": {
                                            "id": {"type": "integer"},
                                            "name": {"type": "string"},
                                            "email": {"type": "string"},
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    after = {
        "paths": {
            "/customers": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "properties": {
                                            "id": {"type": "integer"},
                                            "name": {"type": "string"},
                                            "phone": {"type": "string"},
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/orders": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"properties": {"id": {"type": "integer"}}}
                                }
                            }
                        }
                    }
                }
            },
        }
    }
    result = diff_openapi(before, after)
    assert result["breaking"] is True
    assert any(c["type"] == "NEW" and c["path"] == "/orders" for c in result["changes"])
    update = next(c for c in result["changes"] if c["type"] == "UPDATE")
    assert "phone" in update["added_fields"]
    assert "email" in update["removed_fields"]
