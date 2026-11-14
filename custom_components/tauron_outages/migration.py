from collections.abc import Mapping
from typing import Any

from .const import CONF_LOCALITY

_LEGACY_FILTER_KEYS = ("filter_type", "filter_message")


def migrate_v1_to_v2(
    data: Mapping[str, Any], options: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    locality = options.get("filter_message") or data.get("filter_message") or ""
    new_data = {k: v for k, v in data.items() if k not in _LEGACY_FILTER_KEYS}
    new_options = {k: v for k, v in options.items() if k not in _LEGACY_FILTER_KEYS}
    new_options[CONF_LOCALITY] = locality.strip()
    return new_data, new_options
