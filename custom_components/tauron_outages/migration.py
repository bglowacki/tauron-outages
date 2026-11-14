from collections.abc import Mapping
from typing import Any

from .const import CONF_LOCALITY

_LEGACY_TYPE_FILTER = "filter_type"
_LEGACY_MESSAGE_FILTER = "filter_message"
_LEGACY_FILTER_KEYS = (_LEGACY_TYPE_FILTER, _LEGACY_MESSAGE_FILTER)


def migrate_v1_to_v2(
    data: Mapping[str, Any], options: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    locality = options.get(_LEGACY_MESSAGE_FILTER) or data.get(_LEGACY_MESSAGE_FILTER) or ""
    new_data = {k: v for k, v in data.items() if k not in _LEGACY_FILTER_KEYS}
    new_options = {k: v for k, v in options.items() if k not in _LEGACY_FILTER_KEYS}
    new_options[CONF_LOCALITY] = locality
    return new_data, new_options
