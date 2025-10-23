import math

from core.backbone.address_map import AddressMap
from core.config.nand_parameters.tlc_example import TLCExample
from core.framework.singleton import Singleton


class PLPParameter:
    def __init__(self):
        self.SKIP_DIGEST_DOUT = False


class CoreParameter(metaclass=Singleton):
    def __init__(self):
        self.address_map = AddressMap()
        self.ENABLE_VCD = 1
        self.ENABLE_SUBMODULE_WAKEUP_VCD = 0
        self.VCD_DUMP_END_TIME_MS = -1
        self.VCD_FILE_NAME = 'simpy.vcd'
        self.PRINT_PROGRESS = 0
        self.ENABLE_COMMAND_RECORD = 0
        self.ENABLE_WAF_RECORD = False  # WAF
        self.ENABLE_POWER = 0
        self.ENABLE_OPTION_PRINT = False
        self.ENABLE_POWER_LATENCY = False
        self.ENABLE_LOGGER = 0
        self.ENABLE_LATENCY_LOGGER = 0
        self.MEDIA_READ_JOB_LOGGING = 0
        self.RECORD_SUBMODULE_UTILIZATION = 0
        self.GENERATE_DIAGRAM = 1
        self.ENABLE_PERFORMANCE_RECORD_TO_TERMINAL = 1
        self.GENERATE_SUBMODULE_DIAGRAM = 1
        self.IN_ORDER_DATA_TRANSFER = 0
        self.DEBUG_MODE = 0
        self.SKIP_BUFFER_CHECK = 0
        self.ENABLE_tHost = 0

        self.IP_TRANSACTION_LATENCY_NS = 1

        self.ENABLE_CLOCK_GATING = False
        self.ENABLE_DYNAMIC_POWERSTATE = False
        self.CLOCKGATING_ENTER_LATENCY = 0
        self.CLOCKGATING_EXIT_LATENCY = 0

        self.SC_PS_TIMER_INTERVAL = 0
        self.SC_BACK_GROUND_TRIGGER_INTERVAL = 0
        self.SC_ACTIVE_IDLE_TRIGGER_INTERVAL = 0
        self.SC_PS3_TRIGGER_INTERVAL = 0
        self.SC_PS4_TRIGGER_INTERVAL = 0
        self.ENABLE_DUMP_POWER_VCD = True
        self.ENABLE_LOGGING_TOTAL_POWER = True
        self.TOTAL_POWER_LOG_FILE_NAME = "power.txt"

        self.KB = 1024
        self.MAPUNIT_SIZE = 4 * self.KB  # Bytes
        self.PAGE_SIZE = 16 * self.KB  # Bytes
        # 32K / 64K / 128K / 256K / 512K / 1MB
        self.LOGICAL_MAP_UNIT_SIZE = 32 * self.KB
        self.FTL_MAP_UNIT_SIZE = 16 * self.KB  # Bytes
        self.MAPUNIT_PER_PLANE = self.PAGE_SIZE // self.MAPUNIT_SIZE
        self.SECTOR_SIZE = 512  # Bytes
        self.SECTOR_PER_LPN = self.MAPUNIT_SIZE // self.SECTOR_SIZE
        self.PlaneAllocationScheme = 'PCW'

        self.STRIPING_WAY = 1  # Number of round striping way
        self.CHANNEL = 4
        self.WAY = 2
        self.PLANE = 4

        self.READ_DMA_CNT = 144
        self.WRITE_DMA_CNT = 1920
        self.BA_READ_BUFFER_CNT = 144
        self.DIGEST_BUFFER_CNT = 100000

        self.READ_BUFFER_MANAGER = self.address_map.BA
        self.WRITE_BUFFER_MANAGER = self.address_map.BA
        self.WRITE_BUFFER_PRE_ALLOCATION_POS = None
        self.WRITE_BUFFER_PRE_ALLOCATION_CALL_BACK_FIFO = None
        self.GC_BUFFER_MANAGER = self.address_map.BA

        self.BA_READ_BUFFER_MIN_CNT = 0
        self.BA_WRITE_BUFFER_MIN_CNT = 0
        self.BA_QLC_PERIODIC_RECLAIM_BUFFER_MIN_CNT = 0

        self.BUFFERED_UNIT_ID_COUNT = 1280
        self.NAND_JOB_BUFFER_COUNT = 12800
        self.READ_BUFFER_PRE_ALLOC_COUNT = 128
        self.WRITE_BUFFER_PRE_ALLOC_COUNT = 32  # 4K * 32 = 128K

        self.WRITE_BUFFERED_UNIT_CNT = 256

        self.ENABLE_NAND_SUSPEND = 0
        self.ENABLE_NAND_CACHE_READ = 0
        self.ENABLE_NAND_CACHE_PROGRAM = 0
        self.RATIO_CHANNEL_TO_ECC = 2

        self.JS_QUEUE_DEPTH = 64

        self.MEMORY_PARAM = {
            'SRAM': {
                'FREQUENCY': 3600 * 4,      # mHz
                'IO_WIDTH': 32,             # bit
                'EFFICIENCY': 0.6,
                'PAYLOAD': 128,             # byte, memory access min payload
                'BANDWIDTH': 0,             # calculate #123 ~ #126
                'BANDWIDTH_B_PER_NS': 0     # calculate #123 ~ #126
            },
            'DRAM': {
                'FREQUENCY': 3600 * 3,      # mHz
                'IO_WIDTH': 32,             # bit
                'EFFICIENCY': 0.6,
                'PAYLOAD': 128,             # byte, memory access min payload
                'BANDWIDTH': 0,             # calculate #123 ~ #126
                'BANDWIDTH_B_PER_NS': 0     # calculate #123 ~ #126
            }
        }

        self.sram_param = self.MEMORY_PARAM['SRAM']
        self.dram_param = self.MEMORY_PARAM['DRAM']
        self.sram_param['BANDWIDTH'] = self.sram_param['FREQUENCY'] * \
            self.sram_param['IO_WIDTH'] / 8 * self.sram_param['EFFICIENCY']
        self.dram_param['BANDWIDTH'] = self.dram_param['FREQUENCY'] * \
            self.dram_param['IO_WIDTH'] / 8 * self.dram_param['EFFICIENCY']
        self.sram_param['BANDWIDTH_B_PER_NS'] = self.sram_param['BANDWIDTH'] * \
            1024 * 1024 / 1e9
        self.dram_param['BANDWIDTH_B_PER_NS'] = self.dram_param['BANDWIDTH'] * \
            1024 * 1024 / 1e9

        self.NAND_PARAM = \
            {
                'TLC_EXAMPLE': TLCExample()
            }
        self._NAND_IO_USER_SETTING = False
        self.NAND_PRODUCT = 'TLC_EXAMPLE'
        self.NAND_IO_Mbps = 0
        self.tDCBSYR_us = 5
        self.tDBSY2 = 10
        self.TR_US = 0
        self.TPROG_US = 0
        # about 100 us
        self.PGM_OVERHEAD_PER_SUSPEND = 100000

        self.tNSC = 400  # nand status check
        self.tR_cmd = 200
        self.confirm_cmd = 200
        self.latch_dump_up_cmd = 200
        self.latch_dump_down_cmd = 200
        self.tDout_cmd = 400
        self.tDin_cmd = 500
        self.tSus_cmd = 200

        self.IO_EFFICIENCY_WITH_tFW = 1

        self.ENABLE_TR_SKIP = 0
        self.USING_PIF = False

        self.product_type = None

        self.plp_param = PLPParameter()
        self.SKIP_DIGEST_DOUT = False

        self.SUPPORT_LARGE_MAPPING = False

        self.ENABLE_PROGRAM_FAIL_TRIGGER = False

    @property
    def NAND_IO_Mbps(self):
        return self._NAND_IO_Mbps

    @NAND_IO_Mbps.setter
    def NAND_IO_Mbps(self, value):
        if value != 0:
            self._NAND_IO_USER_SETTING = True
            self._NAND_IO_Mbps = value
        else:
            self._NAND_IO_Mbps = self.NAND_PARAM[self.NAND_PRODUCT]['NAND_IO_Mbps']

    @property
    def NAND_PRODUCT(self):
        return self._NAND_PRODUCT

    @NAND_PRODUCT.setter
    def NAND_PRODUCT(self, value):
        self._NAND_PRODUCT = value
        self.WORDLINE = self.NAND_PARAM[self.NAND_PRODUCT]['WL_COUNT']
        self.SSL = self.NAND_PARAM[self.NAND_PRODUCT]['SSL_COUNT']
        self.BLOCK = self.NAND_PARAM[self.NAND_PRODUCT]['BLOCK_COUNT']
        self.SPARE_BLOCK = self.NAND_PARAM[self.NAND_PRODUCT]['SPARE_BLOCK_COUNT']
        self.PAGE = self.NAND_PARAM[self.NAND_PRODUCT]['PAGE_COUNT']
        self.ECC_PARITY_RATIO = self.NAND_PARAM[self.NAND_PRODUCT]['ECC_PARITY_RATIO']
        self.TOTAL_USER_PPN_COUNT = math.floor(self.NAND_PARAM[self.NAND_PRODUCT]['CAPACITY_Gb'] * (
            1024 ** 3) * self.CHANNEL * self.WAY) // (self.MAPUNIT_SIZE * 8)
        if not self._NAND_IO_USER_SETTING:
            self._NAND_IO_Mbps = self.NAND_PARAM[self.NAND_PRODUCT]['NAND_IO_Mbps']
        if hasattr(self, '_PLANE'):
            self.TOTAL_SUPER_BLOCK_COUNT = (
                self.BLOCK + self.SPARE_BLOCK) // self.PLANE

    @property
    def CHANNEL(self):
        return self._CHANNEL

    def chip_count_changed(self):
        if hasattr(self, '_WAY'):
            if hasattr(self, '_PLANE'):
                self.TOTAL_PLANE_COUNT = self.CHANNEL * self.WAY * self.PLANE
            self.TOTAL_CHIP_COUNT = self.CHANNEL * self.WAY
            if hasattr(self, '_NAND_PRODUCT'):
                self.TOTAL_USER_PPN_COUNT = math.floor(self.NAND_PARAM[self.NAND_PRODUCT]['CAPACITY_Gb'] * (
                    1024 ** 3) * self.CHANNEL * self.WAY) // (self.MAPUNIT_SIZE * 8)

    @CHANNEL.setter
    def CHANNEL(self, value):
        self._CHANNEL = value
        self.RATIO_CHANNEL_TO_JG = self.CHANNEL
        self.chip_count_changed()

    @property
    def WAY(self):
        return self._WAY

    @WAY.setter
    def WAY(self, value):
        self._WAY = value
        self.chip_count_changed()

    @property
    def PLANE(self):
        return self._PLANE

    @PLANE.setter
    def PLANE(self, value):
        self._PLANE = value
        if hasattr(self, '_CHANNEL') and hasattr(self, '_WAY'):
            self.TOTAL_PLANE_COUNT = self.CHANNEL * self.WAY * self.PLANE

    @property
    def TOTAL_PLANE_COUNT(self):
        return self._TOTAL_PLANE_COUNT

    @TOTAL_PLANE_COUNT.setter
    def TOTAL_PLANE_COUNT(self, value):
        self._TOTAL_PLANE_COUNT = value
