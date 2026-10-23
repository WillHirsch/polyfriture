"""Identity and row order for one generation of captured audio.

Physical channel IDs are zero-based PortAudio indices. Labels are one-based;
an array row is identified by channel_ids[row], never by its position alone.
"""

from dataclasses import dataclass
from numbers import Integral


@dataclass(frozen=True)
class ChannelConfiguration:
    device_id: int
    channel_ids: tuple[int, ...]
    device_channel_count: int
    generation: int

    def __post_init__(self):
        for name, minimum in (("device_id", 0), ("device_channel_count", 1), ("generation", 1)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral) or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        try:
            channels = tuple(self.channel_ids)
        except TypeError as error:
            raise ValueError("channel IDs must be a nonempty iterable of integers") from error
        if not channels or any(isinstance(channel, bool) or not isinstance(channel, Integral)
                               or not 0 <= channel < self.device_channel_count for channel in channels):
            raise ValueError("channel IDs must be nonempty and within the device's input range")
        object.__setattr__(self, "channel_ids", tuple(sorted({int(channel) for channel in channels})))

    @property
    def channel_labels(self) -> tuple[str, ...]:
        return tuple(f"Channel {channel + 1}" for channel in self.channel_ids)
