
from enum import Enum


class FifoIDEnum(str, Enum):
    def __repr__(self):
        return self.name

    def __str__(self):
        return self.name


class BA_FIFO_ID(Enum):
    Allocate = 0
    Release = 1
    FifoCount = 2


class NVMe_FIFO_ID(Enum):
    Up = 0
    Down = 1
    Resource = 2
    FifoCount = 3


class NAND_FIFO_ID(Enum):
    Normal = 0
    Resource = 1
    FifoCount = 2


class NFC_FIFO_ID(Enum):
    IssuePath = 0
    DonePath = 1
    Resource = 2
