from math import ceil

from core.config.core_parameter import CoreParameter
from core.framework.cell_type import Cell
from core.framework.fifo_id import NVMe_FIFO_ID


class Parameter:
    def __new__(cls, args=None, init_flag=False):
        if not hasattr(cls, 'instance'):
            cls.instance = super(Parameter, cls).__new__(cls)
            cls.instance.init_param(args)
        elif args:
            cls.instance.set_param_from_args(args)

        if init_flag:
            cls.instance.init_param()

        return cls.instance

    def set_param_from_args(self, args):

        self.args = args
        self.NAND_PRODUCT = args.nand_product
        self.core_parameter.NAND_IO_Mbps = self.args.nand_io_mbps
        self.WORKLOAD_TYPE = "basic"
        self.ROUND_VBLOCK = 1
        self.ROUND_VBLOCK_NOT_SPECIFIED = self.ROUND_VBLOCK == -1
        self.VIRTUAL_DOMAIN = 1
        self.VBLOCK_PER_SUPERBLOCK = -1 // self.VIRTUAL_DOMAIN
        self.VBLOCK_PER_SUPERBLOCK_NOT_SPECIFIED = True
        self.STREAM_COUNT = 1
        self.BATCH_NVM_TRANS_NUMBER = 1
        self.BATCH_NVM_TRANS_NUMBER_NOT_SPECIFIED = self.BATCH_NVM_TRANS_NUMBER == -1
        self.WAY = self.args.way
        self.CHANNEL = self.args.channel
        self.PLANE = self.args.plane
        self.BLOCK_PER_PLANE = self.BLOCK // self.PLANE
        self.PAGE_PER_BLOCK = self.core_parameter.PAGE
        self.NAND_CELL_TYPE = Cell.TLC
        self.SIM_CMD_COUNT = -1
        self.ENABLE_QOS = args.enable_qos
        self.ENABLE_COMMAND_RECORD = self.args.enable_command_record
        self.ENABLE_PERFORMANCE_RECORD = self.args.enable_performance_record
        self.USE_FIXED_LATENCY = True if self.WORKLOAD_TYPE in (
            'cdm',
            'atto',
            'anvil',
            'asssd_4major',
            'asssd_copybench',
            'basic',
            'rw') else False

        self.OUTPUT_FOLDER_NAME = args.folder_name
        self.RECORD_SUBMODULE_UTILIZATION = args.enable_utilization

    def __getattr__(self, name):
        return getattr(self.core_parameter, name)

    def init_param(self, args=None):
        self.core_parameter = CoreParameter()

        # Large Size Mapping
        # 32K / 64K / 128K / 256K / 512K / 1MB
        self.LOGICAL_MAP_UNIT_SIZE = 32 * self.KB
        self.FTL_MAP_UNIT_SIZE = 4 * self.KB  # Bytes
        self.FTL_MAP_UNIT_PER_PLANE = self.PAGE_SIZE // self.FTL_MAP_UNIT_SIZE
        self.FTL_MAPUNIT_PER_PLANE = self.PAGE_SIZE // self.FTL_MAP_UNIT_SIZE
        self.SECTOR_PER_4K = self.MAPUNIT_SIZE // self.SECTOR_SIZE
        self.SECTOR_PER_GAUDI_MAP_UNIT = self.FTL_MAP_UNIT_SIZE // self.SECTOR_SIZE

        if args:
            self.set_param_from_args(args)
        elif not hasattr(self, 'args') or self.args is None:
            self.args = None
            self.NAND_PRODUCT = 'TLC_EXAMPLE'
            self.core_parameter.NAND_IO_Mbps = 0
            self.ROUND_VBLOCK_NOT_SPECIFIED = True
            self.VBLOCK_PER_SUPERBLOCK_NOT_SPECIFIED = True
            self.BATCH_NVM_TRANS_NUMBER_NOT_SPECIFIED = True
            self.VIRTUAL_DOMAIN = 1
            self.STREAM_COUNT = 1
            self.WAY = 2
            self.CHANNEL = 16
            self.WORKLOAD_TYPE = ''
            self.ENABLE_VCD = 0
            self.VCD_FILE_NAME = 'simpy.vcd'
            self.ENABLE_COMMAND_RECORD = False
            self.ENABLE_PERFORMANCE_RECORD = False
            self.ENABLE_WAF_RECORD = False   # WAF
            self.SIM_CMD_COUNT = -1
            self.ENABLE_CLOCK_GATING = True
            self.ENABLE_DYNAMIC_POWERSTATE = False
            self.HOST_BLOCK_TYPE = 'tlc'
            self.OUTPUT_FOLDER_NAME = None
            self.RECORD_SUBMODULE_UTILIZATION = True
            self.ENABLE_NAND_CACHE_READ = 0
            self.PLANE = 4
            self.LOGICAL_MAP_UNIT_SIZE = 128 * self.KB
            self.ENABLE_QOS = False

        self.ENABLE_LATENCY_LOGGER = 1
        self.HOST_FIXED_DELAY = 7.8 * 1e3  # 7.8 us
        self.HOST_QD_DEFAULT = 1

        self.QOS_CANDIDATES = [1, 50, 90, 99, 99.9, 99.99, 99.999, 99.9999]

        self.POWER_SNAP_SHOT_INTERVAL = 0
        self.SDC_BACK_GROUND_ENTER_LATENCY = 0
        self.SDC_BACK_GROUND_EXIT_LATENCY = 0
        self.SDC_ACTIVE_IDLE_ENTER_LATENCY = 0
        self.SDC_ACTIVE_IDLE_EXIT_LATENCY = 0
        self.SDC_PS3_ENTER_LATENCY = 0
        self.SDC_PS3_EXIT_LATENCY = 0
        self.SDC_PS4_ENTER_LATENCY = 0
        self.SDC_PS4_EXIT_LATENCY = 0
        self.ENABLE_DUMP_POWER_VCD = False
        self.ENABLE_LOGGING_TOTAL_POWER = False
        self.TOTAL_POWER_LOG_FILE_NAME = None

        self.PERF_MEASURE_INTERVAL_MS = 10

        self.ENABLE_LOGGER = False
        self.PRINT_PROGRESS = 1
        self.PRINT_PREFILL_PROGRESS = 1
        self.SKIP_BUFFER_CHECK = 0
        self.GENERATE_DIAGRAM = 0
        self.GENERATE_SUBMODULE_DIAGRAM = 0

        self.IP_TRANSACTION_LATENCY_NS = 1  # 21e3 // 200
        self.ENABLE_NAND_SUSPEND = 0
        self.ENABLE_NAND_CACHE_PROGRAM = 0

        # Buffer

        self.ENABLE_LOGICAL_CACHE = 1

        self.BUFFERED_UNIT_SHARED_1P_SEQ_CNT = 2
        self.BUFFERED_UNIT_SHARED_RAN_CNT = 1

        # Resource
        self.READ_DMA_CNT = 144 * 100
        self.WRITE_DMA_CNT = 1408

        self.set_buffer_count()

        self.READ_BUFFER_MANAGER = self.core_parameter.address_map.BA
        self.WRITE_BUFFER_MANAGER = self.core_parameter.address_map.BA
        self.WRITE_BUFFER_PRE_ALLOCATION_POS = self.core_parameter.address_map.NVMe
        self.WRITE_BUFFER_PRE_ALLOCATION_CALL_BACK_FIFO = NVMe_FIFO_ID.Resource.value
        # debuging
        self.MEDIA_READ_JOB_LOGGING = 0

        self.product_type = 'general'

    def set_buffer_count(self):
        self.BA_READ_BUFFER_CNT = 144 * 1000
        self.BA_READ_BUFFER_MIN_CNT = 64
        if not hasattr(self, 'NVM_TRANS_COUNT_PER_FULL_PLANE'):
            return

        self.BA_WRITE_BUFFER_MIN_CNT = int(
            self.CHANNEL *
            self.WAY *
            Cell.TLC.value *
            self.NVM_TRANS_COUNT_PER_FULL_PLANE *
            4)
        self.NAND_PROGRAM_CNT_PER_LPAGE = int(
            self.CHANNEL *
            self.WAY *
            Cell.TLC.value *
            self.NVM_TRANS_COUNT_PER_FULL_PLANE)
        self.LOGICAL_CACHE_ENTRY_CNT = self.NAND_PROGRAM_CNT_PER_LPAGE * 4
        self.BA_WRITE_BUFFER_MIN_CNT += self.WRITE_DMA_CNT + 5
        self.BA_WRITE_BUFFER_CNT = self.BA_WRITE_BUFFER_MIN_CNT * 5
        self.WRITE_BUFFERED_UNIT_CNT = self.CHANNEL * self.WAY * 3

    def chip_count_changed(self):
        self.MEDIA_BUFFERED_UNIT_ID_COUNT = self.CHANNEL * self.WAY * 512
        if hasattr(self, 'PPN_COUNT_PER_L2P_UNIT'):
            self.TOTAL_L2P_UNIT_COUNT = ceil(
                self.TOTAL_USER_PPN_COUNT /
                self.PPN_COUNT_PER_L2P_UNIT)
        if hasattr(self, 'L2P_UNIT_COUNT_PER_DIR_UNIT'):
            self.TOTAL_DIR_UNIT_COUNT = ceil(
                self.TOTAL_L2P_UNIT_COUNT /
                self.L2P_UNIT_COUNT_PER_DIR_UNIT)
        if hasattr(self, 'NVM_TRANS_COUNT_PER_FULL_PLANE'):
            self.set_buffer_count()

        if self.VBLOCK_PER_SUPERBLOCK_NOT_SPECIFIED:
            self.VBLOCK_PER_SUPERBLOCK = self.CHANNEL * self.WAY // self.VIRTUAL_DOMAIN

        if self.ROUND_VBLOCK_NOT_SPECIFIED:
            self.ROUND_VBLOCK = self.VBLOCK_PER_SUPERBLOCK

        self.STREAM_COUNT = self.CHANNEL * self.WAY // self.VBLOCK_PER_SUPERBLOCK
        self.WRITE_ZERO_STREAM_COUNT = 1
        self.WRITE_ZERO_STREAM_START_ID = self.STREAM_COUNT

    @property
    def CHANNEL(self):
        return self._CHANNEL

    @CHANNEL.setter
    def CHANNEL(self, value):
        self._CHANNEL = value
        self.core_parameter.CHANNEL = value
        self.RATIO_CHANNEL_TO_JG = self.CHANNEL
        self.chip_count_changed()

    @property
    def WAY(self):
        return self._WAY

    @WAY.setter
    def WAY(self, value):
        self._WAY = value
        self.core_parameter.WAY = value
        self.chip_count_changed()

    @property
    def PLANE(self):
        return self._PLANE

    @PLANE.setter
    def PLANE(self, value):
        self._PLANE = value
        self.core_parameter.PLANE = value
        self.MULTI_PLANE_READ = self.PLANE
        self.NVM_TRANS_COUNT_PER_FULL_PLANE = self.PLANE * self.FTL_MAP_UNIT_PER_PLANE
        if self.BATCH_NVM_TRANS_NUMBER_NOT_SPECIFIED:
            self.BATCH_NVM_TRANS_NUMBER = self.NVM_TRANS_COUNT_PER_FULL_PLANE
        if hasattr(self, 'NAND_PRODUCT'):
            self.NAND_PRODUCT = self.core_parameter.NAND_PRODUCT

    @property
    def LOGICAL_MAP_UNIT_SIZE(self):
        return self._LOGICAL_MAP_UNIT_SIZE

    @LOGICAL_MAP_UNIT_SIZE.setter
    def LOGICAL_MAP_UNIT_SIZE(self, value):
        self._LOGICAL_MAP_UNIT_SIZE = value
        self.STORAGE_MAP_UNIT_COUNT_PER_LOGICAL_MAPPING_UNIT = self._LOGICAL_MAP_UNIT_SIZE // self.FTL_MAP_UNIT_SIZE
        self.SECTOR_PER_LOGICAL_MAP_UNIT = self._LOGICAL_MAP_UNIT_SIZE // self.SECTOR_SIZE

    @property
    def NAND_PRODUCT(self):
        return self.core_parameter.NAND_PRODUCT

    @NAND_PRODUCT.setter
    def NAND_PRODUCT(self, value):
        self.core_parameter.NAND_PRODUCT = value
        self.META_SUPER_BLOCK_COUNT = 0
        self.BLOCK_COUNT_PER_PLANE = self.BLOCK // self.PLANE
        self.SPARE_BLOCK_COUNT_PER_PLANE = self.SPARE_BLOCK // self.PLANE
        self.TOTAL_SUPER_BLOCK_COUNT_PER_STREAM = self.BLOCK_COUNT_PER_PLANE + \
            self.SPARE_BLOCK_COUNT_PER_PLANE - self.META_SUPER_BLOCK_COUNT
        self.OVER_PROVISIONING_SB_COUNT = 12
        self.LOGICAL_WORDLINE = self.WORDLINE * self.SSL

        self.set_buffer_count()
