import math
from abc import ABC, abstractmethod
from functools import lru_cache


class LBACalculator(ABC):
    lba_size = 512

    def __init__(self, UNIT_SIZE):
        self.user_device_capacity_per_1tb = 960  # GB, not GiB
        self.unit_size = UNIT_SIZE
        self.lba_size = LBACalculator.lba_size

    def calculate_user_capacity_B(self, device_capacity_in_TB):
        return (device_capacity_in_TB *
                self.user_device_capacity_per_1tb) * (1000**3)

    def ceil(self, a, b):
        return math.ceil(a / b) * b

    def floor(self, a, b):
        return math.floor(a / b) * b

    @abstractmethod
    def calculate_lba_count(self, device_capacity_in_TB):
        pass


class SFF8447Calculator(LBACalculator):
    def __init__(self, UNIT_SIZE):
        super().__init__(UNIT_SIZE)
        self.meta_size = 8
        self.logical_block_size = self.lba_size + self.meta_size

    @lru_cache
    def get_fit_adjustment_factor(self):
        if self.meta_size > 0:
            return 0.995
        else:
            return 1

    @lru_cache
    def get_granularity(self):
        if self.lba_size < self.unit_size:
            return 2**21
        else:
            return 2**18

    def calculate_lba_count(self, device_capacity_in_TB=1):
        user_capacity_B = self.calculate_user_capacity_B(device_capacity_in_TB)
        fit_adjustment_factor = self.get_fit_adjustment_factor()
        granularity = self.get_granularity()

        return self.floor(
            self.ceil(
                user_capacity_B /
                self.unit_size,
                2**18) *
            self.unit_size /
            self.logical_block_size *
            fit_adjustment_factor,
            granularity)


class IDEMACalculator(LBACalculator):
    def __init__(self, UNIT_SIZE):
        super().__init__(UNIT_SIZE)
        self.celing_unit = 8

    def calculate_lba_count(self, device_capacity_in_TB=1):
        user_capacity_B = self.calculate_user_capacity_B(device_capacity_in_TB)
        return self.ceil(
            ((1.000194048 * user_capacity_B) + 10838016) / self.lba_size,
            self.celing_unit)


class UserDataLBACountMediator:
    def __init__(self, UNIT_SIZE=4096):
        self.sff8447_calculator = SFF8447Calculator(UNIT_SIZE)
        self.idema_calculator = IDEMACalculator(UNIT_SIZE)

    def select_calculator(self, device_capacity_in_TB):
        if device_capacity_in_TB >= 8:
            return self.sff8447_calculator
        else:
            return self.idema_calculator

    def calculate_lba_count(self, device_capacity_in_TB=1):
        calculator = self.select_calculator(device_capacity_in_TB)
        return calculator.calculate_lba_count(device_capacity_in_TB)
