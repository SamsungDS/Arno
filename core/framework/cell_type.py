from enum import Enum


class Cell(Enum):
    SLC = 1
    MLC = 2
    TLC = 3

    def __add__(self, other: int) -> 'Cell':
        return self.__class__(self.value + other)
