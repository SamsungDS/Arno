import os
import sys

from core.framework.common import CMD_PATH_FIFO_ID, eCMDType, eResourceType
from core.framework.fifo_id import *
from core.framework.file_path_generator import FilePathGenerator
from core.framework.latency_logger import LoggingSection
from core.framework.media_common import eMediaFifoID
from core.framework.memory_c import MemoryC
from core.framework.timer import FrameworkTimer
from core.modules.buffer_allocator import BufferAllocator
from core.modules.ecc import ECC
from core.modules.nand import NAND
from product.general.config.storage_parameters import Parameter
from product.general.framework.environment import initialize_environment
from product.general.modules.address_mapping_layer import AddressMappingLayer
from product.general.modules.block_copy_manager import BlockCopyManager
from product.general.modules.data_cache_layer import DataCacheLayer
from product.general.modules.flash_block_manager import FlashBlockManager
from product.general.modules.HDMA import HDMA
from product.general.modules.host import StorageHost
from product.general.modules.job_generator import JobGenerator
from product.general.modules.job_scheduler import JobScheduler
from product.general.modules.nand_flash_controller import NandFlashController
from product.general.modules.nvme import NVMe
from product.general.modules.PCIe import PCIe
from product.general.modules.transaction_scheduler import TransactionScheduler

sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))


class StorageSimulationEnv:
    param: Parameter

    def __init__(self, param=None):
        if param is not None:
            initialize_environment(self, param)
        else:
            initialize_environment(self)

        self.aml = AddressMappingLayer(
            self.product_args,
            self.address_map.AML,
            len(CMD_PATH_FIFO_ID))
        self.dcl = DataCacheLayer(
            self.product_args,
            self.address_map.DCL,
            len(CMD_PATH_FIFO_ID))
        self.fbm = FlashBlockManager(
            self.product_args,
            self.address_map.FBM,
            len(CMD_PATH_FIFO_ID))
        self.tsu = TransactionScheduler(
            self.product_args,
            self.address_map.TSU,
            len(CMD_PATH_FIFO_ID))
        self.gc = BlockCopyManager(self.product_args,
                                   self.address_map.BCM,
                                   len(CMD_PATH_FIFO_ID))

        self.memc = MemoryC(self.product_args, self.address_map.MEMC)
        self.framework_timer = FrameworkTimer(self.env)

        self.host = StorageHost(self.product_args, self.address_map.HOST)
        self.host.set_qd(64)

        self.nvme = NVMe(
            self.product_args,
            self.address_map.NVMe,
            len(CMD_PATH_FIFO_ID))
        self.nvme.set_qd(64)

        self.nvme.set_pre_allocation_info(
            eResourceType.WriteBuffer,
            self.param.WRITE_BUFFER_PRE_ALLOC_COUNT,
            self.feature.BUFFER_REQUEST_4K_UNIT,
            NVMe_FIFO_ID.Resource.value)

        self.pcie = PCIe(
            self.product_args,
            self.address_map.PCIe,
            len(CMD_PATH_FIFO_ID))
        self.hdma = HDMA(self.product_args, self.address_map.HDMA)
        self.hdma.connect_memc(self.memc)

        self.ba = BufferAllocator(
            self.product_args,
            self.address_map.BA,
            BA_FIFO_ID.FifoCount.value)

        media_fifo_count = len(eMediaFifoID)
        self.jg = JobGenerator(
            self.product_args,
            self.address_map.JG,
            unit_fifo_num=media_fifo_count)

        self.js = JobScheduler(
            self.product_args,
            self.address_map.JS,
            unit_fifo_num=media_fifo_count,
            unit_domain_num=self.param.CHANNEL)  # 1Ch / 1TS
        self.nfc = NandFlashController(
            self.product_args,
            self.address_map.NFC,
            unit_fifo_num=len(NFC_FIFO_ID))
        self.nfc.connect_memc(self.memc)
        self.ecc = ECC(
            self.product_args,
            self.address_map.ECC,
            unit_domain_num=self.param.CHANNEL //
            self.param.RATIO_CHANNEL_TO_ECC)  # 2Ch / 1ECC
        self.ecc.connect_memc(self.memc)
        self.nand = NAND(
            self.product_args,
            self.address_map.NAND,
            unit_fifo_num=NAND_FIFO_ID.FifoCount.value)

        self.latency_logger.set_logging_position(
            "CMDReceiveLogic", -1, LoggingSection.eHostCMDRecv_4KSplit, isStart=True)
        self.latency_logger.set_logging_position(
            "writeTaskGenerator", -1, LoggingSection.eHostCMDRecv_4KSplit, isStart=False)

        self.file_path_generator = FilePathGenerator(self.param)
        self.vcd_manager.add_vcd_module_done()

    def start_power_snapshot(self, workload, qd):
        self.power_manager.power_manager_reset()
        self.power_manager.start_power_snapshot(workload, qd)

    def reset_log(self):
        self.nvme.reset_nvme()
        self.pcie.reset_test()
        self.hdma.reset_test()
        self.memc.init_memc_log()

    def set_qd(self, qd):
        self.nvme.set_qd(qd)
        self.host.set_qd(qd)

    def set_mapping_table(self, test_size, sustained):
        if sustained:
            for i in self.aml.set_sustained_mapping_table(self.param.SUSTAINED_SIZE, self.param.SUSTAINED_BLOCK_RATE, test_size):
                self.fbm.set_init_block(i)
        else:  # normal
            for i in self.aml.set_mapping_table(test_size):
                self.fbm.set_init_block(i)

    def set_file_prefix(self, prefix_name, qd):
        self.file_path_generator.set_file_prefix(prefix_name, qd)

    def start(
            self,
            workload,
            cmd_count,
            skip_perf_measure=False,
            print_workload=None):

        self.host.run(workload, cmd_count)

        self.performance_measure.start_perf_measure()
        self.env.run()

    def check_all_cmd_done(self):
        return self.analyzer.check_all_cmd_done()

    def check_all_dma_done(self):
        return self.nvme.check_DMA(self.analyzer.data_transfer_mapunit_count[eCMDType.Read],
                                   self.analyzer.data_transfer_mapunit_count[eCMDType.Write])

    def success(self):
        success = 1
        success &= self.check_all_cmd_done()

        if self.param.ENABLE_LOGICAL_CACHE:
            return success

        success &= self.check_all_dma_done()
        return success

    def report_output(self, workload_name, is_success, skip_report=False):
        if is_success:
            self.analyzer.print_elapsed_time()
            if not skip_report:
                self.analyzer.print_performance(workload_name)
                self.analyzer.print_latency()
                self.analyzer.print_utilization(workload_name)
                if hasattr(
                        self.analyzer,
                        'qos_record') and self.analyzer.qos_record.is_qos_candidates_set():
                    self.analyzer.qos_record.print_qos()
                self.analyzer.print_cache_hit_result()
                self.memc.print_memc_log()
        else:
            self.print_debug_info()
            self.analyzer.print_debug_info()
            self.nvme.printDebug(self.analyzer.data_transfer_mapunit_count[eCMDType.Read],
                                 self.analyzer.data_transfer_mapunit_count[eCMDType.Write])
            self.nvme.allocator_mediator.buffer_allocator.print_debug()

        self.power_manager.print_power()
        self.analyzer.generate_diagram()

    def print_debug_info(self):
        print()
        print("-" * 50)
        print("-" * 50)
        print('Read Operation')
        print("-" * 50)
        print("-" * 50)
        print('Write Operation')
        print("-" * 50)
        print("-" * 50)
        print("-" * 50)
