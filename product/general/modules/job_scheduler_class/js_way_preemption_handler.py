from enum import Enum, auto
from typing import Any

from core.framework.cell_type import Cell
from core.framework.media_common import (NANDCMDType, is_din_cmd, is_dout_cmd,
                                         is_erase_cmd, is_resume_cmd,
                                         is_tprog_cmd, is_tr_cmd)
from core.framework.vcd_manager import VCDManager
from product.general.modules.job_scheduler_class.js_nand_busy_controller import \
    NANDBusyController
from product.general.modules.job_scheduler_class.js_nand_config import NANDConfig


class WayState(Enum):
    READY = 0
    READ = auto()
    SLC_PROGRAM = auto()
    DIN = auto()
    CONFIRM = auto()
    ERASE = auto()
    SUSPENDED = auto()


class WayInfo:
    def __init__(self, plane_count: int):
        self.plane_count = plane_count
        self.state: list[WayState] = [WayState.READY] * self.plane_count
        self.write_type_nand_job_id: int = -1
        self.suspended_state: WayState | None = None
        self.suspend_start_time: float = 0.0
        self.tRES_ns: float = 0.0
        self.suspended_count: int = 0

    def __repr__(self) -> str:
        return f'WayInfo({self.state}, suspended_state={self.suspended_state}, write_type_nand_job_id={self.write_type_nand_job_id})'

    def set_state(self, way_state: WayState, plane: int = None) -> None:
        if plane is None:
            self.state[:] = [way_state] * self.plane_count
        else:
            self.state[plane] = way_state


class WayPreemptionHandler:
    def __init__(
            self,
            nand_config: NANDConfig,
            vcd_manager: VCDManager,
            busy_handler: NANDBusyController):
        self.PGM_SUSPEND_LIMIT_TIME = 3800000  # 3.8ms (< 4ms)
        self.ERS_SUSPEND_LIMIT_COUNT = 200
        self.nand_config = nand_config
        self.vcd_manager = vcd_manager
        self.busy_handler = busy_handler
        self.way_info: list[list[WayInfo]] = [[WayInfo(nand_config.plane_count) for _ in range(
            nand_config.way_count)] for _ in range(nand_config.channel_count)]

    def is_suspendable(
            self,
            ch: int,
            way: int,
            plane: int,
            now: float) -> bool:
        current_state: WayState = self.way_info[ch][way].state[plane]
        if current_state is WayState.CONFIRM or current_state is WayState.ERASE:
            return not self.is_suspend_limit(ch, way, current_state, now)
        else:
            return False

    def is_suspend_limit(
            self,
            ch: int,
            way: int,
            state: WayState,
            now: float) -> bool:
        if state is WayState.CONFIRM:
            elapsed_time = now - \
                self.way_info[ch][way].suspend_start_time if self.way_info[ch][way].suspend_start_time > 0 else 0.0
            if self.way_info[ch][way].tRES_ns + \
                    elapsed_time > self.PGM_SUSPEND_LIMIT_TIME:
                self.vcd_manager.update_suspend_limit(True, ch, way)
                return True
            return False
        elif state is WayState.ERASE:
            if self.way_info[ch][way].suspended_count > self.ERS_SUSPEND_LIMIT_COUNT:
                self.vcd_manager.update_suspend_limit(True, ch, way)
                return True
            return False

    def is_suspended(self, ch: int, way: int) -> bool:
        return self.way_info[ch][way].suspended_state is not None

    def get_physical_info(self, task_data: dict[Any]) -> tuple[int, int, int]:
        return task_data['channel'], task_data['way'], task_data['plane']

    def get_suspended_nand_job_id(self, ch: int, way: int) -> int:
        return self.way_info[ch][way].write_type_nand_job_id

    def get_next_way_state(self, task_data: dict[Any]) -> WayState:
        ch, way, _ = self.get_physical_info(task_data)
        cmd_type: NANDCMDType = task_data['nand_cmd_type']

        cell_type = task_data.get('cell_type', None)
        if is_tr_cmd(cmd_type) or is_dout_cmd(cmd_type):
            is_suspend_read: bool = task_data.get('suspend_read', False)
            return WayState.SUSPENDED if is_suspend_read else WayState.READ
        elif is_din_cmd(cmd_type):
            return WayState.SLC_PROGRAM if cell_type is Cell.SLC else WayState.DIN
        elif is_tprog_cmd(cmd_type):
            return WayState.SLC_PROGRAM if cell_type is Cell.SLC else WayState.CONFIRM
        elif is_erase_cmd(cmd_type):
            return WayState.ERASE
        elif is_resume_cmd(cmd_type):
            return WayState.CONFIRM if cmd_type == NANDCMDType.PGMResume else WayState.ERASE
        else:
            assert False, 'not yet handle'

    def is_suspend_miss(self, ch: int, way: int) -> bool:
        return self.way_info[ch][way].suspended_state is None

    def is_erase_suspended(self, ch: int, way: int) -> bool:
        return self.way_info[ch][way].suspended_state == WayState.ERASE

    def set_suspended_state(self, ch: int, way: int) -> None:
        self.way_info[ch][way].suspended_state = self.way_info[ch][way].state[0]

    def get_suspended_state(self, ch: int, way: int) -> WayState:
        return self.way_info[ch][way].suspended_state

    def clear_suspended_state(self, ch: int, way: int) -> None:
        self.way_info[ch][way].suspended_state = None

    def set_write_type_nand_job_id(self, ch: int, way: int, nand_job_id: int) -> None:
        self.way_info[ch][way].write_type_nand_job_id = nand_job_id

    def clear_write_type_id(self, ch: int, way: int) -> None:
        self.way_info[ch][way].write_type_nand_job_id = None

    def set_way_state_to_read(
            self,
            task_data: dict[Any],
            is_suspended: bool) -> None:
        ch, way, plane = self.get_physical_info(task_data)

        self.way_info[ch][way].set_state(WayState.READ)
        self.vcd_manager.update_way_state(WayState.READ.value, ch, way)

    def set_way_state(self, task_data: dict[Any]) -> None:
        ch, way, plane = self.get_physical_info(task_data)
        next_way_state: WayState = self.get_next_way_state(task_data)
        self.way_info[ch][way].set_state(next_way_state)
        self.vcd_manager.update_way_state(next_way_state.value, ch, way)

    def clear_way_state(self, task_data: dict[Any]) -> None:
        ch, way, plane = self.get_physical_info(task_data)

        if is_dout_cmd(
                task_data['nand_cmd_type']) and self.busy_handler.get_busy_state(task_data):
            return

        next_way_state: WayState = WayState.READY
        self.way_info[ch][way].set_state(next_way_state)
        self.vcd_manager.update_way_state(next_way_state.value, ch, way)

    def set_suspend_start_time(self, ch: int, way: int, now: float) -> None:
        assert self.way_info[ch][way].suspend_start_time == 0
        self.way_info[ch][way].suspend_start_time = now

    def increase_suspend_count(self, ch: int, way: int) -> None:
        self.way_info[ch][way].suspended_count += 1
        self.vcd_manager.update_suspend_count(
            self.way_info[ch][way].suspended_count, ch, way)

    def set_suspended_time(self, ch: int, way: int, now: float) -> None:
        assert self.way_info[ch][way].suspend_start_time
        self.way_info[ch][way].tRES_ns += now - \
            self.way_info[ch][way].suspend_start_time
        self.way_info[ch][way].suspend_start_time = 0.0
        self.vcd_manager.update_suspended_time(
            self.way_info[ch][way].tRES_ns, ch, way)

    def clear_suspended_info(self, ch: int, way: int) -> None:
        self.way_info[ch][way].tRES_ns = 0.0
        self.way_info[ch][way].suspended_count = 0
        self.vcd_manager.update_suspended_time(
            self.way_info[ch][way].tRES_ns, ch, way)
        self.vcd_manager.update_suspend_count(
            self.way_info[ch][way].suspended_count, ch, way)
        self.vcd_manager.update_suspend_limit(False, ch, way)
