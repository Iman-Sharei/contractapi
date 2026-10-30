"""Unit tests for filter parsing (no database)."""

from __future__ import annotations

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table

from contractapi.application.query_filters import parse_filters
from contractapi.core.errors import AppError
from contractapi.domain.models.spec import EndpointSpec


def _table():
    md = MetaData()
    return Table(
        "t",
        md,
        Column("id", Integer, primary_key=True),
        Column("name", String),
        Column("email", String),
    )


def _endpoint():
    return EndpointSpec(
        name="customers",
        path="/customers",
        table="t",
        fields=["id", "name", "email"],
        filters=["name", "email"],
        filter_operators=["eq", "ne", "contains", "in"],
    )


def test_parse_eq_and_contains():
    clauses = parse_filters(
        [("name", "Ada"), ("email__contains", "@ex")],
        table=_table(),
        endpoint=_endpoint(),
        reserved={"limit"},
    )
    assert len(clauses) == 2


def test_parse_in_and_reject_unknown():
    clauses = parse_filters(
        [("name__in", "a,b,c")],
        table=_table(),
        endpoint=_endpoint(),
        reserved=set(),
    )
    assert len(clauses) == 1
    with pytest.raises(AppError) as ei:
        parse_filters(
            [("password", "x")],
            table=_table(),
            endpoint=_endpoint(),
            reserved=set(),
        )
    assert ei.value.status == 400
