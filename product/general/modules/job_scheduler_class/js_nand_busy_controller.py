from typing import Any

from product.general.modules.job_scheduler_class.js_nand_config import \
    NANDConfig


class PlaneOperationBitmap:
    def __init__(self, nand_config: NANDConfig, vcd_manager):
        self.plane_count = nand_config.plane_count
        self.plane_busy_bitmap: list[list[list[int]]] = [[[0 for _ in range(nand_config.plane_count)]
                                                          for _ in range(nand_config.way_count)]
                                                         for _ in range(nand_config.channel_count)]
        self.latch_busy_bitmap: list[list[list[int]]] = [[[0 for _ in range(nand_config.plane_count)]
                                                          for _ in range(nand_config.way_count)]
                                                         for _ in range(nand_config.channel_count)]
        self.vcd_manager = vcd_manager

    def update(
            self,
            ch: int,
            way: int,
            plane: int,
            value: bool,
            is_latch: bool) -> None:
        busy_bitmap = self.latch_busy_bitmap if is_latch else self.plane_busy_bitmap
        busy_bitmap[ch][way][:] = [value] * self.plane_count
        self.vcd_manager.update_nand_busy_bitmap(
            ch, way, value, is_latch=is_latch)

    def is_busy(self, ch: int, way: int, plane: int, is_latch: bool) -> bool:
        busy_bitmap = self.latch_busy_bitmap if is_latch else self.plane_busy_bitmap
        return any(busy_bitmap[ch][way])


class NANDBusyController:
    def __init__(self, nand_config: NANDConfig, vcd_manager):
        self.plane_op_bitmap = PlaneOperationBitmap(nand_config, vcd_manager)
        self.vcd_manager = vcd_manager

    def get_busy_state(self, data: dict[Any], is_latch: bool = False) -> bool:
        ch, way, plane = data['channel'], data['way'], data['plane']

        return self.plane_op_bitmap.is_busy(ch, way, plane, is_latch)

    def update_plane_busy_status(
            self,
            ch: int,
            way: int,
            plane: int,
            value: int) -> None:
        self.plane_op_bitmap.update(ch, way, plane, value, False)

    def update_nand_status(
            self,
            data: dict[Any],
            value: bool,
            is_latch: bool) -> None:
        ch, way, plane = data['channel'], data['way'], data['plane']

        self.plane_op_bitmap.update(ch, way, plane, value, is_latch)

    def set_nand_busy(self, data: dict[Any], is_latch: bool) -> None:
        self.update_nand_status(data, 1, is_latch)

    def set_nand_ready(self, data: dict[Any], is_latch: bool) -> None:
        self.update_nand_status(data, 0, is_latch)
