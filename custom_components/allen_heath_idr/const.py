"""Constants for the Allen & Heath iDR integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "allen_heath_idr"
MANUFACTURER: Final = "Allen & Heath"

DEFAULT_PORT: Final = 23

CONF_INPUTS: Final = "inputs"
CONF_OUTPUTS: Final = "outputs"
CONF_GROUPS: Final = "expose_groups"
CONF_CROSSPOINTS: Final = "expose_crosspoints"
CONF_SCAN_INTERVAL: Final = "scan_interval"

DEFAULT_INPUTS: Final = 8
DEFAULT_OUTPUTS: Final = 8
DEFAULT_SCAN_INTERVAL: Final = 10  # seconds
MIN_SCAN_INTERVAL: Final = 2
MAX_SCAN_INTERVAL: Final = 300
