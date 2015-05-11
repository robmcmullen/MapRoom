"""
    point: x, y, z (depth), color, state
    state = selected | flagged | deleted | edited | added | land_polygon | water_polygon | other_polygon
"""
from ..renderer import data_types

STATE_NONE = 0
STATE_SELECTED = 1
STATE_FLAGGED = 2
STATE_DELETED = 4
STATE_EDITED = 8
STATE_ADDED = 16
STATE_LAND_POLYGON = 32
STATE_WATER_POLYGON = 64
STATE_OTHER_POLYGON = 128
