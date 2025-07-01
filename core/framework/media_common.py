from enum import Enum, auto
from functools import lru_cache
from typing import List, Tuple

from core.framework.cell_type import Cell


class ChannelJobType(Enum):
    LatchDumpUp = 1
    ABC = 2
    tRCMD = 3
    ConfirmCMD = 4
    DoutCMD = 5
    DinCMD = 6
    LatchDumpDown = 7
    SuspendCMD = 8


class eMediaFifoID(Enum):
    IssuePath = 0
    DonePath = 1


class NANDCMDType(Enum):
    tR_8P = 0
    tR_6P = auto()
    tR_4P = auto()
    tR_2P = auto()
    tR_1P = auto()
    tR_1P_4K = auto()
    Dout_4K = auto()
    Dout_8K = auto()
    Dout_12K = auto()
    Dout_16K = auto()

    Din_LSB = auto()
    Din_USB = auto()
    Din_MSB = auto()
    tProg = auto()
    tProg_1P = auto()
    tBERS = auto()

    tNSC = auto()
    LatchDumpDown = auto()
    LatchDumpUp = auto()
    FDMADone = auto()
    Suspend = auto()
    PGMResume = auto()
    ERSResume = auto()

    @classmethod
    def get_tr_cmd_size(cls) -> List[Tuple['NANDCMDType', str]]:
        return [(v, v.name.split('_')[-1] if len(v.name.split('_')) > 2 else '16K')
                for v in NANDCMDType.__dict__.values() if isinstance(v, NANDCMDType) and v.name.startswith('tR')]

    def __add__(self, other: int) -> 'NANDCMDType':
        return self.__class__(self.value + other)


def search_target_string(str, cmd_type):
    return str == cmd_type.name[:len(str)]


@lru_cache
def is_dout_cmd(cmd_type):
    return search_target_string('Dout_', cmd_type)


@lru_cache
def is_din_cmd(cmd_type):
    return search_target_string('Din', cmd_type)


@lru_cache
def is_data_cmd(cmd_type):
    return is_dout_cmd(cmd_type) or is_din_cmd(cmd_type)


@lru_cache
def is_dq_releated_cmd(cmd_type):
    return is_dout_cmd(cmd_type) or is_din_cmd(
        cmd_type) or is_tprog_cmd(cmd_type) or is_erase_cmd(cmd_type)


@lru_cache
def is_dout_done_cmd(cmd_type):
    return NANDCMDType.FDMADone == cmd_type


@lru_cache
def is_tr_cmd(cmd_type):
    return search_target_string('tR', cmd_type)


@lru_cache
def is_1p_tr_cmd(cmd_type):
    return search_target_string('tR_1P', cmd_type)


@lru_cache
def is_tprog_cmd(cmd_type):
    return search_target_string('tProg', cmd_type)


@lru_cache
def is_1p_program_cmd(cmd_type):
    return cmd_type == NANDCMDType.tProg_1P


@lru_cache
def is_multi_plane_read(cmd_type):
    return cmd_type in (
        NANDCMDType.tR_8P,
        NANDCMDType.tR_6P,
        NANDCMDType.tR_4P,
        NANDCMDType.tR_2P)


@lru_cache
def is_full_plane_tr(cmd_type):
    return cmd_type in (
        NANDCMDType.tR_8P,
        NANDCMDType.tR_6P,
        NANDCMDType.tR_4P)


@lru_cache
def is_read_cmd(cmd_type):
    return cmd_type.value < NANDCMDType.Din_LSB.value


@lru_cache
def is_program_cmd(cmd_type):
    return NANDCMDType.Din_LSB.value <= cmd_type.value < NANDCMDType.tBERS.value


@lru_cache
def is_erase_cmd(cmd_type):
    return cmd_type == NANDCMDType.tBERS


@lru_cache
def is_busy_cmd(cmd_type):
    return cmd_type == NANDCMDType.tNSC


@lru_cache
def is_latch_dump(cmd_type):
    return 'LatchDump' in cmd_type.name


@lru_cache
def is_latch_dump_up(cmd_type):
    return cmd_type == NANDCMDType.LatchDumpUp


@lru_cache
def is_latch_dump_down(cmd_type):
    return cmd_type == NANDCMDType.LatchDumpDown


@lru_cache
def is_suspend_cmd(cmd_type):
    return cmd_type == NANDCMDType.Suspend


@lru_cache
def is_resume_cmd(cmd_type):
    return cmd_type in (NANDCMDType.PGMResume, NANDCMDType.ERSResume)


def need_latch_dump_up(packet):
    return packet['cache_program_ctxt'].is_cache_program or packet['cell_type'] != Cell.SLC


def get_channel_id(packet):
    return packet['channel']


def get_way_id(packet, way_count):
    return get_channel_id(packet) * way_count + packet['way']


def get_plane_id(packet, way_count, plane_count):
    return get_way_id(packet, way_count) * plane_count + packet['plane']


def generate_dbl_info(queue_data, **kwargs):
    dbl_info = {'buffered_unit_id': queue_data['buffered_unit_id'], 'nand_job_id': queue_data['nand_job_id']}
    dbl_info.update(kwargs)
    return dbl_info
