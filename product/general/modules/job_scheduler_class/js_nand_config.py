from dataclasses import dataclass


@dataclass
class NANDConfig:
    channel_count: int
    way_count: int
    plane_count: int
