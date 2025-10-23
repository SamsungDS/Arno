import bisect
import logging
import sys
from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from itertools import cycle


def custom_excepthook(type, value, traceback):
    if type == AssertionError:
        logger = logging.getLogger("ExceptionLogger")
        logger.error(
            "Unexpected exception.",
            exc_info=(type, value, traceback)
        )
        print("AssertionError occurred. Calling breakpoint()")
        breakpoint()
    else:
        sys.__excepthook__(type, value, traceback)


def is_qlc_nand(nand_product):
    return 'QLC' in nand_product


class RequestResourceInfo(dict):
    def __init__(
            self,
            resourceType,
            requestType,
            requestIPAddr,
            unique_key,
            requestSize=1,
            resourceID=-1,
            requestCallbackFifoID=-1):
        self['resource_type'] = resourceType
        self['request_type'] = requestType
        self['request_ip'] = requestIPAddr
        self['request_size'] = requestSize
        self['unique_key'] = unique_key
        # -1 means don't need callback
        self['request_callback_fifo_id'] = requestCallbackFifoID
        self['resource_id'] = resourceID


class SortedList:
    def __init__(self):
        self.li = list()

    def append(self, data, key=None):
        bisect.insort(self.li, data, key=key)

    def search_index(self, data, key=None):
        index = bisect.bisect_right(self.li, data, key=key)
        return index

    def clear(self):
        self.li.clear()

    def __getitem__(self, index: int):
        return self.li[index]

    def __len__(self):
        return len(self.li)

    def __delitem__(self, index):
        del self.li[index]


class QFetchType(Enum):
    FIFO = auto()
    RoundRobin = auto()
    Priority = auto()  # Lower Queue Index is higher priority. 0 is higher than 1


class eCMDType(Enum):
    Read = 0
    ReadDone = auto()
    ReadDoneSQ = auto()
    ReadDoneCQ = auto()
    NANDReadDone = auto()
    CacheReadDone = auto()
    Write = auto()
    WriteDone = auto()
    CacheWriteDone = auto()
    Erase = auto()
    EraseDone = auto()
    Flush = auto()
    FlushDone = auto()
    MetaRead = auto()
    MetaWrite = auto()
    MetaWriteDone = auto()
    Update = auto()
    UpdateDone = auto()
    MetaReadDone = auto()
    BufferReleaseReq = auto()
    ReadBufferAlloc = auto()


class TransactionSourceType(Enum):
    UserIO = 0
    GCIO = auto()
    GCDone = auto()


class eMemoryType(Enum):
    SRAM = 0
    DRAM = auto()


class eResourceType(Enum):
    ReadBuffer = 0
    WriteBuffer = auto()
    ReadDMADesc = auto()
    WriteDMADesc = auto()
    MediaBufferedUnitID = auto()
    MediaNandJobID = auto()
    GCBuffer = auto()


class BufferedUnitType(Enum):
    SeqReadBufferedUnit = 0
    RanReadBufferedUnit = 1
    WriteBufferedUnit = 2


class StatusType(Enum):
    CANCEL = auto()


class MemAccessInfo:
    INVALID_ADDR = -1
    SRAM_START_ADDR = 0
    SRAM_SIZE = 0x2000_0000
    DRAM_START_ADDR = SRAM_START_ADDR + SRAM_SIZE   # 0x2000_0000
    DRAM_SIZE = 0x4000_0000

    @classmethod
    def get_memory_type(cls, addr):
        if addr >= cls.DRAM_START_ADDR:
            return eMemoryType.DRAM
        else:
            return eMemoryType.SRAM

    @classmethod
    def get_memory_type_and_start_addr(cls):
        return {name: value for name, value in vars(
            cls).items() if isinstance(value, int)}

    def __init__(self, _resource_id, _resource_type, _request_size_B=4096):
        self.resource_id = _resource_id
        self.request_size = _request_size_B
        self.event = None
        self._is_read = True
        self.resource_type = _resource_type

    def set_type_write(self):
        self._is_read = False

    def is_read(self):
        return self._is_read


class eRequestType(Enum):
    Allocate = 0,
    Release = 1,


class eAllocStatus(Enum):
    Valid = 0,
    NoRemain = 1
    Retry = 2


class CMD_PATH_FIFO_ID(Enum):
    eUp = 0
    eDown = 1
    FifoCount = 2


class eCacheResultType(Enum):
    miss = auto()
    miss_slc = auto()
    miss_mlc = auto()
    miss_tlc = auto()
    logical_temporal = auto()
    logical_spatial = auto()
    logical_mix = auto()
    physical = auto()
    logical_physical_mix = auto()

    @staticmethod
    def get_dict():
        return {key: 0 for key in eCacheResultType}


class ProductArgs:
    def __init__(self, *args, **kwargs):
        self.init_args(*args, **kwargs)

    def init_args(self, *args, **kwargs):
        self.env = kwargs['env']
        self.param = kwargs['param']
        self.feature = kwargs['feature']
        self.vcd_manager = None

    def set_vcd_variables(self, vcd_variables):
        self.vcd_manager = vcd_variables

    def set_args_to_class_instance(self, cls_instance):
        if self.env:
            cls_instance.env = self.env
        if self.feature:
            cls_instance.feature = self.feature
        if self.param:
            cls_instance.param = self.param
        if self.vcd_manager:
            cls_instance.vcd_manager = self.vcd_manager
        cls_instance.product_args = self


class VPBGenerationContext:
    @dataclass
    class DirectoryInfo:
        idx: int = -1
        loading: bool = False

        def set_loading(self):
            self.idx = -1
            self.loading = True

        def load_done(self, idx):
            self.idx = idx
            self.loading = False

        def clear(self):
            self.idx = -1
            self.loading = False

    def __init__(self):
        self.clear()

    def clear(self):
        self.sbn = None
        self.directory_info = self.DirectoryInfo()
        self.archive_load_waiting_count = 0
        self.working_sb_meta_info = None
        self.working_job_type = None
        self.archive_load_issued_count = 0


class RoundRobinQueues:
    def __init__(self, num_queues):
        self.num_queues = num_queues
        self.queues = [deque() for _ in range(num_queues)]
        self.round_robin_queues = cycle(self.queues)

    def any_remaining_jobs(self):
        return any(self.queues)

    def push(self, value, queue_index):
        try:
            self.queues[queue_index].append(value)
        except KeyError:
            assert 0, 'invalid queue index'

    def pop_round_robin(self):
        current_queue = next(self.round_robin_queues)
        value = None

        while value is None:
            if current_queue:
                value = current_queue.popleft()
                break
            current_queue = next(self.round_robin_queues)

        return value


class QueueDepthChecker:
    def __init__(self, env, qd=1):
        self.env = env
        self.qd_event = self.env.event()
        self.total_queue_depth = qd
        self.current_queue_depth = 0
        self.blocked_qd = False

    def set_total_queue_depth(self, qd):
        self.total_queue_depth = qd

    def wait_qd(self):
        if self.current_queue_depth >= self.total_queue_depth:
            self.blocked_qd = True
            yield self.qd_event
        self.increase_current_qd()
        yield self.env.timeout(0)

    def increase_current_qd(self):
        self.current_queue_depth += 1

    def release_qd(self):
        self.current_queue_depth -= 1
        if self.blocked_qd:
            self.blocked_qd = False
            self.qd_event.succeed()
            self.qd_event = self.env.event()
