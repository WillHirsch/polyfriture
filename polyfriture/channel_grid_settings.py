"""The global column preference shared by every channel grid."""

from polyfriture.settings_model import IntSetting


CHANNEL_GRID_COLUMNS = IntSetting(2, minimum=1)
