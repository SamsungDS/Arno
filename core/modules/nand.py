from abc import ABCMeta, abstractmethod
from collections import deque
from random import seed
from typing import Dict

from core.config.nand_tprog_parser import NANDtProgParser
from core.framework.media_common import *
from core.framework.nand_io_efficiency_recorder import NANDIOEffiRecorder
from core.framework.nand_io_efficiency_table import NANDIOEfficiencyTable
from core.framework.submodule import SubModule
from core.framework.submodule_event import SubmoduleEvent
from core.modules.parallel_unit import ParallelUnit
from product.general.provided_interface import nand_flash_controller_pif


class NANDStats:
    def __init__(self):
        self.nand_program_count = 0
        self.nand_tr_count = 0
        self.nand_erase_count = 0
        self.nand_dout_count = 0
        self.nand_din_count = 0

    def read(self):
        self.nand_tr_count += 1

    def program(self):
        self.nand_program_count += 1

    def erase(self):
        self.nand_erase_count += 1

    def dout(self):
        self.nand_dout_count += 1

    def din(self):
        self.nand_din_count += 1


class NANDIOPin:
    def __init__(self, env, channel_count, way_count):
        self.env = env
        self.channel_count = channel_count
        self.way_count = way_count

        self.job_count = [0 for _ in range(self.channel_count)]
        self.queue = [[deque() for _ in range(way_count)]
                      for _ in range(channel_count)]
        self.event = [SubmoduleEvent(self.env) for _ in range(channel_count)]

    def append(self, ch, data):
        way = data['way']
        self.queue[ch][way].append(data)
        self.job_count[ch] += 1

    def notify(self, ch):
        self.event[ch].trigger()

    def wait(self, ch):
        return self.event[ch].wait()

    def reset(self, ch):
        self.event[ch].reset()

    def job_exist(self, ch):
        return self.job_count[ch]

    @lru_cache
    def get_priority_level(self, nand_cmd_type):
        if is_tr_cmd(nand_cmd_type):
            return 4

        if is_tprog_cmd(nand_cmd_type):
            return 3

        if is_data_cmd(nand_cmd_type):
            return 2

        if is_suspend_cmd(nand_cmd_type):
            return 5

        return 1

    def compare_priority(self, left, right):
        if left is None:
            return True

        left_nand_cmd_type = left['nand_cmd_type']
        right_nand_cmd_type = right['nand_cmd_type']
        if self.get_priority_level(
                left_nand_cmd_type) > self.get_priority_level(right_nand_cmd_type):
            return False
        if self.get_priority_level(
                left_nand_cmd_type) < self.get_priority_level(right_nand_cmd_type):
            return True
        if left['time_stamp'] < right['time_stamp']:
            return False
        return True

    def fetch_job(self, channel):
        target_data = None
        target_way = None
        for way, Q in enumerate(self.queue[channel]):
            try:
                cur_data = Q[0]
            except IndexError:
                continue

            if self.compare_priority(target_data, cur_data):
                target_way, target_data = way, cur_data

        if target_data is not None:
            self.job_count[channel] -= 1
            return self.queue[channel][target_way].popleft()
        return None


class Latch(metaclass=ABCMeta):
    def __init__(self, env, param, vcd_manager):
        self.env = env
        self.param = param
        self.vcd_manager = vcd_manager
        self.wait_event = [[SubmoduleEvent(self.env) for _ in range(
            self.param.WAY)] for _ in range(self.param.CHANNEL)]

    @abstractmethod
    def empty(self, packet):
        pass

    @abstractmethod
    def update_status(self, packet, value):
        pass

    @abstractmethod
    def get_latch_info(self, ch, way):
        pass

    @abstractmethod
    def set_latch_info(self, ch, way, value):
        pass

    @abstractmethod
    def clear_latch_info(self, ch, way):
        pass

    def set_occupied(self, packet):
        self.update_status(packet, True)

    def set_empty(self, packet):
        self.update_status(packet, False)

    def notify_latch_empty(self, ch, way):
        self.wait_event[ch][way].trigger()

    def wait(self, ch, way):
        return self.wait_event[ch][way].wait()

    def reset(self, ch, way):
        self.wait_event[ch][way].reset()


class DataLatch(Latch):
    def __init__(self, env, param, vcd_manager):
        super().__init__(env, param, vcd_manager)
        self.latch_occupied_count = [[False for _ in range(
            self.param.WAY)] for _ in range(self.param.CHANNEL)]

    def empty(self, packet):
        ch, way = packet['channel'], packet['way']

        compare_val = 0
        if is_din_cmd(packet['nand_cmd_type']):
            cell_type: Cell = packet['cell_type']
            compare_val = cell_type.value - 1

        return self.latch_occupied_count[ch][way] <= compare_val

    def update_status(self, packet, value):
        ch, way = packet['channel'], packet['way']
        if value:
            self.latch_occupied_count[ch][way] += 1
        else:
            self.latch_occupied_count[ch][way] = 0

        self.vcd_manager.update_dlatch_state(
            ch, way, self.latch_occupied_count[ch][way])

    def get_latch_info(self, ch: int, way: int) -> bool:
        return self.latch_occupied_count[ch][way]

    def set_latch_info(self, ch: int, way: int, value: int) -> None:
        self.latch_occupied_count[ch][way] = value
        self.vcd_manager.update_dlatch_state(
            ch, way, self.latch_occupied_count[ch][way])

    def clear_latch_info(self, ch: int, way: int) -> None:
        self.latch_occupied_count[ch][way] = 0
        self.vcd_manager.update_dlatch_state(
            ch, way, self.latch_occupied_count[ch][way])


class SLatch(Latch):
    def __init__(self, env, param, vcd_manager):
        super().__init__(env, param, vcd_manager)
        self.latch_occupied = [[[False for _ in range(self.param.PLANE)] for _ in range(
            self.param.WAY)] for _ in range(self.param.CHANNEL)]

    def get_info(self, packet):
        ch, way = packet['channel'], packet['way']
        plane_list = packet['target_plane_id']
        return ch, way, plane_list

    def empty(self, packet):
        ch, way, plane_list = self.get_info(packet)
        for plane in plane_list:
            if self.latch_occupied[ch][way][plane]:
                return False
        return True

    def update_status(self, packet, value):
        ch, way, plane_list = self.get_info(packet)

        nand_cmd_type = packet['nand_cmd_type']
        if is_program_cmd(nand_cmd_type) or is_dout_cmd(nand_cmd_type):
            plane_list = [p for p in range(self.param.PLANE)]

        for plane in plane_list:
            self.latch_occupied[ch][way][plane] = value
            self.vcd_manager.update_slatch_state(ch, way, plane, value)

    def get_latch_info(self, ch: int, way: int) -> list[bool]:
        return self.latch_occupied[ch][way]

    def set_latch_info(
            self,
            ch: int,
            way: int,
            value_list: list[bool]) -> None:
        self.latch_occupied[ch][way][:] = value_list
        for plane in range(self.param.PLANE):
            self.vcd_manager.update_slatch_state(
                ch, way, plane, self.latch_occupied[ch][way][plane])

    def clear_latch_info(self, ch: int, way: int) -> None:
        self.latch_occupied[ch][way][:] = [False] * self.param.PLANE
        for plane in range(self.param.PLANE):
            self.vcd_manager.update_slatch_state(
                ch, way, plane, self.latch_occupied[ch][way][plane])


class WriteTypeInfo:
    def __init__(self) -> None:
        self.cmd_type: NANDCMDType | None = None
        self.expected_end_time: float = 0.0
        self.remain_time: float = 0.0
        self.prev_s_latch_info: list[bool] | None = None
        self.prev_d_latch_info: int | None = None

    def __repr__(self) -> str:
        return f'WriteTypeInfo({self.cmd_type}, end_time={self.expected_end_time}, remain_time={self.remain_time})'

    def set_info(self, cmd: NANDCMDType, end_time: float) -> None:
        self.cmd_type = cmd
        self.expected_end_time = end_time

    def clear_info(self) -> None:
        self.cmd_type = None
        self.expected_end_time = 0.0
        self.remain_time = 0.0

    def set_prev_info(self, packet, s_latch: SLatch | None,
                      d_latch: DataLatch | None) -> None:
        ch, way = packet['channel'], packet['way']
        self.prev_s_latch_info = s_latch.get_latch_info(ch, way)
        self.prev_d_latch_info = d_latch.get_latch_info(ch, way)

    def clear_prev_info(self) -> None:
        self.prev_s_latch_info = None
        self.prev_d_latch_info = None


class NAND(ParallelUnit):
    def __init__(self, product_args, _address=0, unit_fifo_num=1):
        super().__init__(product_args, _address, unit_fifo_num)

        seed(0)
        self.stats = NANDStats()
        assert self.address == self.address_map.NAND
        self.media_perf_record = False
        self.nand_job_id_allocator = self.allocator_mediator.nand_job_id_allocator
        self.nand_io_effi_recorder = None
        # Reference
        # V8 1Tb : 44.5/61/44.5, V8 512Gb : 40/55/40,   61/44.5 = 1.37, 55/40 =
        # 1.375
        self.tlc_page_offset_ratio = [1, 1, 1]  # [1, 1.37, 1]
        self.tR_time: Dict[Cell, int] = {
            Cell.SLC:
                self.param.NAND_PARAM[self.param.NAND_PRODUCT]['SLC_tR'],
            Cell.MLC:
                self.param.NAND_PARAM[self.param.NAND_PRODUCT]['MLC_tR'],
            Cell.TLC: {
                cmd: self.param.NAND_PARAM[self.param.NAND_PRODUCT][f'TLC_{size}_tR']
                for cmd, size in NANDCMDType.get_tr_cmd_size()
                }}
        self.tr_count_per_cell_type = {cell: 0 for cell in Cell}

        self.tSUS_us = self.param.NAND_PARAM[self.param.NAND_PRODUCT]['tSUS']

        self.nand_io_effi_info = NANDIOEfficiencyTable(self.product_args)
        self.tDMA = self.calculate_tDMA()
        self.way_queue, self.way_event = list(), list()
        self.plane_queue, self.plane_event = list(), list()

        self.tprog_parser = NANDtProgParser(self.param.NAND_PRODUCT)
        self.io_pin = NANDIOPin(self.env, self.param.CHANNEL, self.param.WAY)
        self.channel_job_vcd_func_map = {
            ChannelJobType.LatchDumpUp: self.vcd_manager.update_latch_dump_up_state,
            ChannelJobType.LatchDumpDown: self.vcd_manager.update_latch_dump_down_state,
            ChannelJobType.ABC: self.vcd_manager.update_abc_state,
            ChannelJobType.tRCMD: self.vcd_manager.update_tR_cmd_state,
            ChannelJobType.ConfirmCMD: self.vcd_manager.update_confirm_cmd_state,
            ChannelJobType.DoutCMD: self.vcd_manager.update_dout_cmd_state,
            ChannelJobType.DinCMD: self.vcd_manager.update_din_cmd_state,
            ChannelJobType.SuspendCMD: self.vcd_manager.update_suspend_cmd_state}

        self.channel_buffer_submodule_list: List[None | SubModule] = [
            None for _ in range(self.param.CHANNEL)]
        self.channel_dq_pin_submodule_list: List[None | SubModule] = [
            None for _ in range(self.param.CHANNEL)]
        self.channel_submodule_list: List[None | SubModule] = [
            None for _ in range(self.param.CHANNEL)]
        self.plane_submodule_list: List[None | SubModule] = [
            None for _ in range(self.param.CHANNEL * self.param.WAY * self.param.PLANE)]
        self.slatch = SLatch(self.env, self.param, self.vcd_manager)
        self.data_latch = DataLatch(self.env, self.param, self.vcd_manager)
        self.way_operation_submodule: List[None | SubModule] = [
            None for _ in range(self.param.CHANNEL * self.param.WAY)]
        self.latch_dump_submodule_list: List[None | SubModule] = [
            None for _ in range(self.param.CHANNEL * self.param.WAY)]

        self.slatch_checker_submodule_list: List[None | SubModule] = [
            None for _ in range(self.param.CHANNEL * self.param.WAY)]

        if self.param.ENABLE_NAND_SUSPEND:
            self.write_type_info: list[WriteTypeInfo] = [
                WriteTypeInfo() for _ in range(
                    self.param.CHANNEL * self.param.WAY)]

        for channel in range(self.param.CHANNEL):
            self.env.process(self.channel_operation(channel))
            self.channel_submodule_list[channel] = self.generate_submodule_without_process(self.channel_operation,
                                                                                           [self.feature.NAND_CHANNEL_OPERATION,
                                                                                            self.feature.ZERO,
                                                                                            self.feature.NAND_LATCH_DUMP_UP,
                                                                                            self.feature.NAND_TR_CMD,
                                                                                            self.feature.NAND_CONFIRM_CMD,
                                                                                            self.feature.NAND_DOUT_CMD,
                                                                                            self.feature.NAND_DIN_CMD,
                                                                                            self.feature.NAND_OPERATION[NANDCMDType.Dout_4K],
                                                                                            self.feature.NAND_OPERATION[NANDCMDType.Dout_8K],
                                                                                            self.feature.NAND_OPERATION[NANDCMDType.Dout_12K],
                                                                                            self.feature.NAND_OPERATION[NANDCMDType.Dout_16K],
                                                                                            self.feature.NAND_OPERATION[NANDCMDType.Din_LSB],
                                                                                            self.feature.NAND_OPERATION[NANDCMDType.Din_USB],
                                                                                            self.feature.NAND_OPERATION[NANDCMDType.Din_MSB],
                                                                                            self.feature.NAND_OPERATION[NANDCMDType.LatchDumpUp],
                                                                                            self.feature.NAND_OPERATION[NANDCMDType.LatchDumpDown],
                                                                                            self.feature.NAND_OPERATION[NANDCMDType.tNSC]],
                                                                                           s_id=channel)
            for way in range(self.param.WAY):
                chip_id = channel * self.param.WAY + way
                self.way_operation_submodule[chip_id] = self.generate_submodule(
                    self.way_operation, self.feature.NAND_WAY_OPERATION, chip_id)
                self.latch_dump_submodule_list[chip_id] = self.generate_submodule(
                    self.latch_dump, [
                        self.feature.ZERO, self.feature.NAND_LATCH_DUMP, self.feature.NAND_LATCH_DUMP_UP], chip_id)
                self.slatch_checker_submodule_list[chip_id] = self.generate_submodule(
                    self.slatch_checker, [self.feature.ZERO], chip_id)
                for plane in range(self.param.PLANE):
                    plane_id = channel * self.param.WAY * \
                        self.param.PLANE + way * self.param.PLANE + plane
                    feature_list = list()
                    for plane_type in (
                            NANDCMDType.tR_8P,
                            NANDCMDType.tR_6P,
                            NANDCMDType.tR_4P,
                            NANDCMDType.tR_2P,
                            NANDCMDType.tR_1P,
                            NANDCMDType.tR_1P_4K,
                            NANDCMDType.tProg,
                            NANDCMDType.tProg_1P):
                        for cell_type in Cell:
                            feature_list.append(
                                self.feature.NAND_OPERATION[hash((plane_type, cell_type))])
                    feature_list.append(
                        self.feature.NAND_OPERATION[NANDCMDType.tBERS])
                    self.plane_submodule_list[plane_id] = self.generate_submodule(
                        self.plane_operation, feature_list, s_id=plane_id)

    def calculate_tDMA(self):
        tDout = self.nand_io_effi_info.tDout
        tDout_parity = self.nand_io_effi_info.tDout_parity
        tDin = self.nand_io_effi_info.tDin
        tDin_parity = self.nand_io_effi_info.tDin_parity

        tDMA = [[0 for _ in range(len(NANDCMDType))], [0 for _ in range(
            len(NANDCMDType))]]  # [0]:data, [1]:parity
        for nand_cmd_type, time in tDout.items():
            tDMA[0][nand_cmd_type.value] = time

        for nand_cmd_type, time in tDout_parity.items():
            tDMA[1][nand_cmd_type.value] = time

        for nand_cmd_type, time in tDin.items():
            tDMA[0][nand_cmd_type.value] = time

        for nand_cmd_type, time in tDin_parity.items():
            tDMA[1][nand_cmd_type.value] = time

        return tDMA

    def set_nand_io_effi_recorder(self, recorder: NANDIOEffiRecorder):
        self.nand_io_effi_recorder = recorder

    def consume_channel_time(
            self,
            job_type,
            channel_submodule,
            feature_id,
            runtime_latency=-1):
        vcd_func = self.channel_job_vcd_func_map[job_type]

        if self.need_nand_io_effi_record():
            self.nand_io_effi_recorder.add_cmd_time(
                self.env.now, channel_submodule.submodule_info.s_id, job_type, runtime_latency)

        vcd_func(channel_submodule.submodule_info.s_id, 1)
        yield from channel_submodule.activate_feature(feature_id, runtime_latency=runtime_latency)
        vcd_func(channel_submodule.submodule_info.s_id, 0)

    def channel_dqpin_operation(self, packet, channel):
        submodule = self.channel_dq_pin_submodule_list[channel]
        yield from self.channel_data_tranfer_and_send_done(packet, channel, self.channel_dqpin_operation, submodule)

    def need_nand_io_effi_record(self):
        return self.nand_io_effi_recorder is not None

    def channel_data_tranfer_and_send_done(
            self, packet, channel, src_func, submodule):
        nand_cmd = packet['nand_cmd_type']
        plane_id = get_plane_id(packet, self.param.WAY, self.param.PLANE)
        t_data = self.tDMA[0][nand_cmd.value]
        t_parity = self.tDMA[1][nand_cmd.value]

        if self.need_nand_io_effi_record():
            self.nand_io_effi_recorder.add_data_time(
                self.env.now, channel, t_data, t_parity)

        is_dout = is_dout_cmd(nand_cmd)
        self.vcd_manager.nand_dma(plane_id, 1, is_dout)
        yield from submodule.activate_feature(self.feature.NAND_OPERATION[nand_cmd], runtime_latency=t_data + t_parity)
        self.vcd_manager.nand_dma(plane_id, 0, is_dout)

        dbl_info = generate_dbl_info(packet)
        self.send_sq(
            nand_flash_controller_pif.NandJobReleaseDBL(
                dbl_info,
                self.address),
            self.address,
            self.address_map.NFC,
            dst_fifo_id=eMediaFifoID.DonePath.value,
            src_submodule=src_func,
            src_submodule_id=channel,
            description=nand_cmd.name)

        if is_dout_cmd(nand_cmd) and packet['dlast']:
            if not packet['cache_read_ctxt'].is_cache_read:
                latch = self.slatch
            else:
                latch = self.data_latch
            latch.set_empty(packet)
            latch.notify_latch_empty(channel, packet['way'])
        elif is_din_cmd(nand_cmd):
            self.slatch.set_occupied(packet)

    def busy_check(self, packet, channel, channel_submodule):
        nand_cmd = packet['status_nand_cmd_type']
        assert nand_cmd == NANDCMDType.tNSC
        yield from self.consume_channel_time(ChannelJobType.ABC, channel_submodule, self.feature.NAND_OPERATION[nand_cmd], self.nand_io_effi_info.tNSC)
        dbl_info = generate_dbl_info(packet)
        self.send_sq(
            nand_flash_controller_pif.NandJobReleaseDBL(
                dbl_info,
                self.address),
            self.address,
            self.address_map.NFC,
            dst_fifo_id=eMediaFifoID.DonePath.value,
            src_submodule=self.latch_dump,
            src_submodule_id=channel,
            description=packet['nand_cmd_type'].name)

    def start_latch_dump(self, packet, channel, channel_submodule):
        nand_cmd = packet['status_nand_cmd_type']
        if nand_cmd == NANDCMDType.LatchDumpUp:
            latency = self.nand_io_effi_info.latch_dump_up_cmd
            channel_job_type = ChannelJobType.LatchDumpUp
        elif nand_cmd == NANDCMDType.LatchDumpDown:
            latency = self.nand_io_effi_info.latch_dump_down_cmd
            channel_job_type = ChannelJobType.LatchDumpDown
        else:
            assert 0, 'Wrong NANDCMDType'

        chip_id = get_way_id(packet, self.param.WAY)
        yield from self.consume_channel_time(channel_job_type, channel_submodule,
                                             self.feature.NAND_OPERATION[nand_cmd], latency)

        self.wakeup_by_inst(
            self.channel_submodule_list[channel],
            self.latch_dump_submodule_list[chip_id],
            packet,
            description=nand_cmd.name)

    def channel_operation(self, channel):
        channel_submodule = self.channel_submodule_list[channel]
        while True:
            yield self.io_pin.wait(channel)
            self.io_pin.reset(channel)
            while self.io_pin.job_exist(channel):
                packet = self.io_pin.fetch_job(channel)
                if not packet:
                    break

                if is_resume_cmd(packet['nand_cmd_type']):
                    chip_id = get_way_id(packet, self.param.WAY)
                    packet['nand_cmd_type'] = self.write_type_info[chip_id].cmd_type
                    self.restore_latch_info(packet)

                nand_cmd = packet.get(
                    'status_nand_cmd_type',
                    packet['nand_cmd_type'])
                if is_data_cmd(nand_cmd):
                    if is_dout_cmd(nand_cmd):
                        self.stats.dout()
                        yield from self.consume_channel_time(ChannelJobType.DoutCMD, channel_submodule, self.feature.NAND_DOUT_CMD, self.nand_io_effi_info.dout_cmd)
                    elif is_din_cmd(nand_cmd):
                        self.stats.din()
                        yield from self.consume_channel_time(ChannelJobType.DinCMD, channel_submodule, self.feature.NAND_DIN_CMD, self.nand_io_effi_info.din_cmd)
                    yield from self.channel_data_tranfer_and_send_done(packet, channel, self.channel_operation, channel_submodule)
                elif is_busy_cmd(nand_cmd):
                    yield from self.busy_check(packet, channel, channel_submodule)
                elif is_latch_dump_up(nand_cmd) or is_latch_dump_down(nand_cmd):
                    yield from self.start_latch_dump(packet, channel, channel_submodule)
                else:  # tR, tProg, tBERS, tSus
                    chip_id = get_way_id(packet, self.param.WAY)
                    if is_tr_cmd(nand_cmd):
                        yield from self.consume_channel_time(ChannelJobType.tRCMD, channel_submodule, self.feature.NAND_TR_CMD, self.nand_io_effi_info.tR_cmd)
                    elif is_tprog_cmd(nand_cmd):
                        yield from self.consume_channel_time(ChannelJobType.ConfirmCMD, channel_submodule, self.feature.NAND_CONFIRM_CMD, self.nand_io_effi_info.confirm_cmd)
                    elif is_suspend_cmd(nand_cmd):
                        yield from self.consume_channel_time(ChannelJobType.SuspendCMD, channel_submodule,
                                                             self.feature.NAND_SUSPEND_CMD, self.nand_io_effi_info.suspend_cmd)
                    self.wakeup_by_inst(
                        self.channel_submodule_list[channel],
                        self.way_operation_submodule[chip_id],
                        packet,
                        description=nand_cmd.name)

    def slatch_checker(self, packet, chip_id):
        ch = packet['channel']
        while not self.slatch.empty(packet):
            way = packet['way']
            yield self.slatch.wait(ch, way)
            self.slatch.reset(ch, way)

        self.io_pin_append(
            ch,
            packet,
            src_submodule=self.slatch_checker_submodule_list[chip_id])

    def restore_latch_info(self, packet):
        ch, way = packet['channel'], packet['way']
        chip_id = get_way_id(packet, self.param.WAY)
        self.slatch.set_latch_info(
            ch, way, self.write_type_info[chip_id].prev_s_latch_info)
        self.data_latch.set_latch_info(
            ch, way, self.write_type_info[chip_id].prev_d_latch_info)
        self.write_type_info[chip_id].clear_prev_info()

    def clear_latch_info(self, packet):
        ch, way = packet['channel'], packet['way']
        self.slatch.clear_latch_info(ch, way)
        self.data_latch.clear_latch_info(ch, way)

    def prepare_suspend(self, packet, chip_id):
        cmd_type = packet['nand_cmd_type']
        self.write_type_info[chip_id].set_info(
            cmd_type, self.env.now + packet['operation_time'])

    def suspend_operation(self, packet, chip_id):
        cmd_type = packet['nand_cmd_type']
        if busy_cmd := self.write_type_info[chip_id].cmd_type:
            base_plane_id = chip_id * self.param.PLANE
            for plane in range(self.param.PLANE):
                plane_id = base_plane_id + plane
                self.plane_submodule_list[plane_id].interrupt(
                    f'{busy_cmd.name}_suspend')
                self.wakeup_by_inst(
                    self.way_operation_submodule[chip_id],
                    self.plane_submodule_list[plane_id],
                    packet,
                    description=cmd_type.name)
            self.write_type_info[chip_id].remain_time = (self.write_type_info[
                chip_id].expected_end_time - self.env.now + self.param.PGM_OVERHEAD_PER_SUSPEND) / 1e3
            self.write_type_info[chip_id].set_prev_info(
                packet, self.slatch, self.data_latch)
            self.clear_latch_info(packet)
        else:  # already tPROG or tBERS done
            dbl_info = generate_dbl_info(packet)
            self.send_sq(
                nand_flash_controller_pif.NandJobReleaseDBL(
                    dbl_info,
                    self.address),
                src=self.address,
                src_submodule=self.way_operation,
                src_submodule_id=chip_id,
                dst=self.address_map.NFC,
                dst_fifo_id=eMediaFifoID.DonePath.value,
                description=cmd_type.name)

    def way_operation(self, packet, chip_id):
        packet['operation_time'] = self.get_plane_operating_time(packet)
        cmd_type = packet['nand_cmd_type']

        if is_tr_cmd(cmd_type):
            ch, way = packet['channel'], packet['way']
            while not self.slatch.empty(packet):
                yield self.slatch.wait(ch, way)
                self.slatch.reset(ch, way)
            self.stats.read()
        elif is_program_cmd(cmd_type):
            self.stats.program()
        elif is_erase_cmd(cmd_type):
            self.stats.erase()

        if self.param.ENABLE_NAND_SUSPEND:
            if is_tprog_cmd(cmd_type) or is_erase_cmd(cmd_type):
                self.prepare_suspend(packet, chip_id)
            elif is_suspend_cmd(cmd_type):
                self.suspend_operation(packet, chip_id)
                return

        for plane_id in packet['target_plane_id']:
            plane = chip_id * self.param.PLANE + plane_id
            self.wakeup_by_inst(
                self.way_operation_submodule[chip_id],
                self.plane_submodule_list[plane],
                packet,
                description=cmd_type.name)

    def get_tR(self, packet):
        cmd_type = packet['nand_cmd_type']
        cell_type = packet['cell_type']
        self.tr_count_per_cell_type[cell_type] += 1
        if self.param.TR_US != 0:
            return self.param.TR_US
        else:
            if cell_type == Cell.TLC:
                page_offset = packet['page'] % Cell.TLC.value
                return self.tR_time[Cell.TLC][cmd_type] * \
                    self.tlc_page_offset_ratio[page_offset]
            else:
                return self.tR_time[cell_type]

    def get_tProg(self, packet):
        chip_id = get_way_id(packet, self.param.WAY)
        if self.param.ENABLE_NAND_SUSPEND and self.write_type_info[chip_id].remain_time:
            return self.write_type_info[chip_id].remain_time

        cell_type = packet['cell_type']
        page_per_cell = cell_type.value

        if self.param.TPROG_US != 0:
            tprog = self.param.TPROG_US
        else:
            wl = packet.get('wl', 0)
            tprog = self.tprog_parser.get_tprog(cell_type, wl)
        return tprog * page_per_cell

    def get_tBERS(self):
        return self.param.NAND_PARAM[self.param.NAND_PRODUCT]['tBERS']

    def get_plane_operating_time(self, packet):
        cmd_type = packet['nand_cmd_type']
        if is_tr_cmd(cmd_type):
            operating_time = self.get_tR(packet)
        elif is_tprog_cmd(cmd_type):
            operating_time = self.get_tProg(packet)
        elif is_suspend_cmd(cmd_type):
            operating_time = self.tSUS_us
        else:
            operating_time = self.get_tBERS()

        return operating_time * 1e3

    def is_nfc_done_notify_packet(self, plane, cmd_type):
        if is_tr_cmd(cmd_type):
            return (
                is_full_plane_tr(cmd_type) and plane %
                self.param.PLANE == 0 or cmd_type == NANDCMDType.tR_2P and plane %
                (self.param.PLANE //
                 2) == 0 or cmd_type == NANDCMDType.tR_1P or cmd_type == NANDCMDType.tR_1P_4K)
        else:
            return plane % self.param.PLANE == 0 or is_1p_program_cmd(cmd_type)

    def get_vcd_tag(self, packet):

        return 1

    def plane_operation(self, packet, plane):
        cmd_type = packet['nand_cmd_type']

        self.vcd_manager.nand_operation(
            plane, self.get_vcd_tag(packet), cmd_type)
        try:
            cell_type = packet['cell_type']
            busy_done = yield from self.plane_submodule_list[plane].activate_feature(self.feature.NAND_OPERATION[hash((cmd_type, cell_type))], runtime_latency=packet['operation_time'])
        except KeyError:
            busy_done = yield from self.plane_submodule_list[plane].activate_feature(self.feature.NAND_OPERATION[cmd_type], runtime_latency=packet['operation_time'])
        self.vcd_manager.nand_operation(plane, 0, cmd_type)

        if busy_done:
            channel = get_channel_id(packet)
            if self.is_nfc_done_notify_packet(plane, cmd_type):
                dbl_info = generate_dbl_info(packet)
                self.send_sq(
                    nand_flash_controller_pif.NandJobReleaseDBL(
                        dbl_info,
                        self.address),
                    self.address,
                    self.address_map.NFC,
                    dst_fifo_id=eMediaFifoID.DonePath.value,
                    src_submodule=self.plane_operation,
                    src_submodule_id=plane,
                    description=cmd_type.name)

                if is_tr_cmd(cmd_type):
                    self.slatch.set_occupied(packet)
                elif is_tprog_cmd(cmd_type):
                    if need_latch_dump_up(packet):
                        latch = self.data_latch
                    else:
                        latch = self.slatch
                    latch.set_empty(packet)
                    latch.notify_latch_empty(packet['channel'], packet['way'])

                if self.param.ENABLE_NAND_SUSPEND:
                    if is_tprog_cmd(cmd_type) or is_erase_cmd(cmd_type):
                        way = get_way_id(packet, self.param.WAY)
                        self.write_type_info[way].clear_info()

            self.io_pin.notify(channel)

    def latch_dump(self, packet, chip_id):
        ch, way = packet['channel'], packet['way']
        if not self.data_latch.empty(packet):
            yield self.data_latch.wait(ch, way)
            self.data_latch.reset(ch, way)

        assert self.data_latch.empty(packet)

        self.vcd_manager.latch_dump(1, chip_id)
        if packet['status_nand_cmd_type'] == NANDCMDType.LatchDumpDown:
            yield from self.latch_dump_submodule_list[chip_id].activate_feature(self.feature.NAND_LATCH_DUMP,
                                                                                runtime_latency=self.param.tDCBSYR_us * 1e3)
        else:  # LatchDumpUp
            yield from self.latch_dump_submodule_list[chip_id].activate_feature(self.feature.NAND_LATCH_DUMP_UP,
                                                                                runtime_latency=self.param.tDBSY2 * 1e3)
        self.vcd_manager.latch_dump(0, chip_id)

        dbl_info = generate_dbl_info(packet)
        self.send_sq(
            nand_flash_controller_pif.NandJobReleaseDBL(
                dbl_info,
                self.address),
            self.address,
            self.address_map.NFC,
            dst_fifo_id=eMediaFifoID.DonePath.value,
            src_submodule=self.latch_dump,
            src_submodule_id=chip_id,
            description=packet['nand_cmd_type'].name)

        self.slatch.set_empty(packet)
        self.slatch.notify_latch_empty(ch, way)
        self.data_latch.set_occupied(packet)

    def io_pin_append(self, ch, packet, src_name=None, src_submodule=None):
        self.io_pin.append(ch, packet)
        self.io_pin.notify(ch)

        if self.param.GENERATE_SUBMODULE_DIAGRAM:
            if src_submodule is not None:
                self.record_packet_transfer_to_diagram(
                    src_submodule=src_submodule,
                    dst_submodule=self.submodule_mapper.get(
                        ch,
                        self.channel_operation),
                    description='Channel Operation',
                    is_send_packet=True)
                return

            assert src_name is not None
            self.record_packet_transfer_to_diagram(
                src_name=src_name,
                dst_submodule=self.submodule_mapper.get(
                    ch,
                    self.channel_operation),
                description='Channel Operation',
                is_send_packet=True)

    def handle_request(self, dbl_info, fifo_id):
        packet = self.nand_job_id_allocator.read(dbl_info['nand_job_id'])
        channel = get_channel_id(packet)
        self.vcd_manager.received_nand_packet(channel)

        nand_cmd = packet.get('status_nand_cmd_type', packet['nand_cmd_type'])
        if is_tr_cmd(nand_cmd):
            chip_id = get_way_id(packet, self.param.WAY)
            self.wakeup_by_inst(
                self.address,
                self.slatch_checker_submodule_list[chip_id],
                packet,
                src_id=fifo_id,
                description='LatchCheck')
        else:
            self.io_pin_append(
                channel, packet, src_name=self.get_name(
                    self.address, fifo_id))
