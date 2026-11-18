"""How specs are shown to Studio clients (secrets masked)."""

from __future__ import annotations

from typing import Any

from contractapi.domain.models.spec import ApiSpec, dump_spec


def _spec_json(spec: ApiSpec) -> dict[str, Any]:
    """Spec as returned to clients: literal passwords/secrets masked."""
    from contractapi.infrastructure.secrets import mask_spec_dict

    return mask_spec_dict(spec.model_dump(by_alias=True, mode="json"))


def _spec_yaml(spec: ApiSpec) -> str:
    return dump_spec(ApiSpec.model_validate(_spec_json(spec)))
