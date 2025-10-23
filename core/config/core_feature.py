from dataclasses import dataclass

from core.backbone.address_map import AddressMap
from core.config.core_parameter import CoreParameter
from core.framework.cell_type import Cell
from core.framework.media_common import NANDCMDType
from core.framework.singleton import Singleton

sc_background = 3
sc_active_idle = 3.5
sc_ps3 = 13


class OperationFrequency:
    def __init__(self):
        self.address_map = AddressMap()
        self.param = CoreParameter()
        self.HCLK = 250
        self.FCLK = 300

        self.frequency_map = {
            self.address_map.NVMe: self.HCLK,
            self.address_map.JG: self.FCLK,
            self.address_map.JS: self.FCLK,
            self.address_map.NFC: self.FCLK,
            self.address_map.ECC: self.param.NAND_IO_Mbps // 4,
            self.address_map.NAND: self.param.NAND_IO_Mbps // 4,
            self.address_map.BA: self.FCLK,
            self.address_map.SRAM: self.HCLK}

    def get_operating_frequency(self, address):
        return self.frequency_map[address]


@dataclass
class FeatureInfo:
    latency: float
    idle1_trigger_interval: float
    idle1_enter_latency: float
    idle1_exit_latency: float
    active: float
    idle: float
    idle1: float
    background: float
    active_idle: float
    leakage: float
    off: float


class CoreFeature(metaclass=Singleton):
    def calculate_latency(self, address, cycle):
        return int(
            cycle *
            1e3 //
            self.operating_freq.get_operating_frequency(address))

    def gen_feature_id(self):
        self.feature_id += 1
        return self.feature_id

    def check_feature_id_exist(self, f_id):
        return self.feature_list[f_id] is not None

    def get_latency(self, f_id):
        return self.feature_list[f_id].latency

    def get_idle1_trigger_interval(self, f_id):
        return self.feature_list[f_id].idle1_trigger_interval

    def get_idle1_enter_latency(self, f_id):
        return self.feature_list[f_id].idle1_enter_latency

    def get_idle1_exit_latency(self, f_id):
        return self.feature_list[f_id].idle1_exit_latency

    def get_active(self, f_id):
        return self.feature_list[f_id].active

    def get_idle(self, f_id):
        return self.feature_list[f_id].idle

    def get_idle1_power(self, f_id):
        return self.feature_list[f_id].idle1

    def get_active_idle_power(self, f_id):
        return self.feature_list[f_id].active_idle

    def get_background_power(self, f_id):
        return self.feature_list[f_id].background

    def get_leakage_power(self, f_id):
        return self.feature_list[f_id].leakage

    def get_off_power(self, f_id):
        return self.feature_list[f_id].off

    def get_non_implementation_module_list(self):
        return self.non_implementation_module_list

    def combine_feature(self, feature_id, *args):
        assert feature_id <= self.feature_id
        if self.feature_list[feature_id] is None:
            self.feature_list[feature_id] = FeatureInfo(
                0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        for src_id in args:
            self.feature_list[feature_id].latency += self.feature_list[src_id].latency
            self.feature_list[feature_id].active += self.feature_list[src_id].active
            self.feature_list[feature_id].idle += self.feature_list[src_id].idle
            self.feature_list[feature_id].idle1 += self.feature_list[src_id].idle1
            self.feature_list[feature_id].active_idle += self.feature_list[src_id].active_idle
            self.feature_list[feature_id].background += self.feature_list[src_id].background
            self.feature_list[feature_id].leakage += self.feature_list[src_id].leakage
            self.feature_list[feature_id].off += self.feature_list[src_id].off

    def __init__(self):
        self.operating_freq = OperationFrequency()
        self.address_map = AddressMap()

        self.non_implementation_module_list = {}

        self.feature_id = -1
        self.DEFAULT_LATENCY = 850

        self.ZERO = self.gen_feature_id()

        self.MIN_NS = self.gen_feature_id()
        self.MIN_PS = self.gen_feature_id()

        self.BUFFER_REQUEST_4K_UNIT = self.gen_feature_id()
        self.BUFFER_RELEASE_4K_UNIT = self.gen_feature_id()

        self.MEM_ACCESS = self.gen_feature_id()         # default, only use unit_test
        self.SRAM_MEM_ACCESS = self.gen_feature_id()
        self.DRAM_MEM_ACCESS = self.gen_feature_id()
        self.SRAM = self.gen_feature_id()
        self.DRAM = self.gen_feature_id()

        # mBA
        self.BA_ALLOCATE_FETCH = self.gen_feature_id()
        self.BA_RELEASE_FETCH = self.gen_feature_id()
        self.BA_ALLOC_PER_SEGMENT = self.gen_feature_id()
        self.BA_RELEASE_PER_SEGMENT = self.gen_feature_id()

        # NAND
        self.NAND_CH_BUFFER_TO_ECC = self.gen_feature_id()
        self.NAND_CHANNEL_OPERATION = self.gen_feature_id()
        self.NAND_WAY_OPERATION = self.gen_feature_id()
        self.NAND_TRRC_OPERATION = self.gen_feature_id()
        self.NAND_LATCH_DUMP = self.gen_feature_id()
        self.NAND_LATCH_DUMP_UP = self.gen_feature_id()
        self.NAND_TR_CMD = self.gen_feature_id()
        self.NAND_DOUT_CMD = self.gen_feature_id()
        self.NAND_DIN_CMD = self.gen_feature_id()
        self.NAND_CONFIRM_CMD = self.gen_feature_id()
        self.NAND_SUSPEND_CMD = self.gen_feature_id()
        self.DIGEST_COOKING_CMD = self.gen_feature_id()
        self.NAND_OPERATION = dict()

        for cell in Cell:
            self.NAND_OPERATION[hash(
                (NANDCMDType.tR_4P, cell))] = self.gen_feature_id()
            self.NAND_OPERATION[hash(
                (NANDCMDType.tR_2P, cell))] = self.gen_feature_id()
            self.NAND_OPERATION[hash(
                (NANDCMDType.tR_1P, cell))] = self.gen_feature_id()
            self.NAND_OPERATION[hash(
                (NANDCMDType.tR_1P_4K, cell))] = self.gen_feature_id()
            self.NAND_OPERATION[hash(
                (NANDCMDType.tProg, cell))] = self.gen_feature_id()
            self.NAND_OPERATION[hash(
                (NANDCMDType.tProg_1P, cell))] = self.gen_feature_id()
            self.NAND_OPERATION[hash(
                (NANDCMDType.tR_8P, cell))] = self.gen_feature_id()
            self.NAND_OPERATION[hash(
                (NANDCMDType.tR_6P, cell))] = self.gen_feature_id()

        self.NAND_OPERATION[NANDCMDType.Dout_4K] = self.gen_feature_id()
        self.NAND_OPERATION[NANDCMDType.Dout_8K] = self.gen_feature_id()
        self.NAND_OPERATION[NANDCMDType.Dout_12K] = self.gen_feature_id()
        self.NAND_OPERATION[NANDCMDType.Dout_16K] = self.gen_feature_id()
        self.NAND_OPERATION[NANDCMDType.Din_LSB] = self.gen_feature_id()
        self.NAND_OPERATION[NANDCMDType.Din_USB] = self.gen_feature_id()
        self.NAND_OPERATION[NANDCMDType.Din_MSB] = self.gen_feature_id()
        self.NAND_OPERATION[NANDCMDType.tBERS] = self.gen_feature_id()
        self.NAND_OPERATION[NANDCMDType.tNSC] = self.gen_feature_id()
        self.NAND_OPERATION[NANDCMDType.LatchDumpDown] = self.gen_feature_id()
        self.NAND_OPERATION[NANDCMDType.LatchDumpUp] = self.gen_feature_id()
        self.NAND_OPERATION[NANDCMDType.FDMADone] = self.gen_feature_id()
        self.NAND_OPERATION[NANDCMDType.Suspend] = self.gen_feature_id()

        # ECC
        self.ecc_iteration_count = 2
        self.ECC_DECODING = self.gen_feature_id()
        self.ECC_TO_SRAM = self.gen_feature_id()

        self.param = CoreParameter()
        clock_gating_enter_latency = self.param.CLOCKGATING_ENTER_LATENCY
        clock_gating_exit_latency = self.param.CLOCKGATING_EXIT_LATENCY

        self.core_feature_max_id = self.feature_id

        self.feature_list = [None for _ in range(self.core_feature_max_id + 1)]

        self.feature_list[self.ZERO] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.MIN_NS] = FeatureInfo(
            1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.MIN_PS] = FeatureInfo(
            0.001, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        self.feature_list[self.MEM_ACCESS] = FeatureInfo(
            1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.SRAM_MEM_ACCESS] = FeatureInfo(
            1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.DRAM_MEM_ACCESS] = FeatureInfo(
            1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.SRAM] = FeatureInfo(
            1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.DRAM] = FeatureInfo(
            1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        self.feature_list[self.BA_ALLOCATE_FETCH] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.BA_RELEASE_FETCH] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.BA_ALLOC_PER_SEGMENT] = FeatureInfo(self.calculate_latency(
            self.address_map.BA, cycle=25), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.BA_RELEASE_PER_SEGMENT] = FeatureInfo(self.calculate_latency(
            self.address_map.BA, cycle=7), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        self.feature_list[self.NAND_CH_BUFFER_TO_ECC] = FeatureInfo(self.calculate_latency(
            self.address_map.NAND, cycle=576), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_WAY_OPERATION] = FeatureInfo(
            1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_CHANNEL_OPERATION] = FeatureInfo(
            1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_TRRC_OPERATION] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_LATCH_DUMP] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_LATCH_DUMP_UP] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_TR_CMD] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_DOUT_CMD] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_DIN_CMD] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_CONFIRM_CMD] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_SUSPEND_CMD] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        self.feature_list[self.NAND_OPERATION[hash((NANDCMDType.tR_1P, Cell.SLC))]] = FeatureInfo(
            0, 0, 0, 0, 3.51e-2, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[hash((NANDCMDType.tR_2P, Cell.SLC))]] = FeatureInfo(
            0, 0, 0, 0, 3.51e-2, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[hash((NANDCMDType.tR_4P, Cell.SLC))]] = FeatureInfo(
            0, 0, 0, 0, 3.51e-2, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[hash((NANDCMDType.tR_6P, Cell.SLC))]] = FeatureInfo(
            0, 0, 0, 0, 3.51e-2, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[hash((NANDCMDType.tR_8P, Cell.SLC))]] = FeatureInfo(
            0, 0, 0, 0, 3.51e-2, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[hash((NANDCMDType.tR_1P_4K, Cell.SLC))]] = FeatureInfo(
            0, 0, 0, 0, 3.51e-2, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[hash((NANDCMDType.tR_1P, Cell.MLC))]] = FeatureInfo(
            0, 0, 0, 0, 3.51e-2, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[hash((NANDCMDType.tR_2P, Cell.MLC))]] = FeatureInfo(
            0, 0, 0, 0, 3.51e-2, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[hash((NANDCMDType.tR_4P, Cell.MLC))]] = FeatureInfo(
            0, 0, 0, 0, 3.51e-2, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[hash((NANDCMDType.tR_1P_4K, Cell.MLC))]] = FeatureInfo(
            0, 0, 0, 0, 3.51e-2, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[hash((NANDCMDType.tR_6P, Cell.MLC))]] = FeatureInfo(
            0, 0, 0, 0, 3.51e-2, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[hash((NANDCMDType.tR_8P, Cell.MLC))]] = FeatureInfo(
            0, 0, 0, 0, 3.51e-2, 0, 0, 0, 0, 0, 0)

        self.feature_list[self.NAND_OPERATION[hash((NANDCMDType.tR_1P, Cell.TLC))]] = FeatureInfo(
            0, 0, 0, 0, 3.51e-2, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[hash((NANDCMDType.tR_2P, Cell.TLC))]] = FeatureInfo(
            0, 0, 0, 0, 3.51e-2, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[hash((NANDCMDType.tR_4P, Cell.TLC))]] = FeatureInfo(
            0, 0, 0, 0, 3.51e-2, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[hash((NANDCMDType.tR_6P, Cell.TLC))]] = FeatureInfo(
            0, 0, 0, 0, 3.51e-2, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[hash((NANDCMDType.tR_8P, Cell.TLC))]] = FeatureInfo(
            0, 0, 0, 0, 3.51e-2, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[hash((NANDCMDType.tR_1P_4K, Cell.TLC))]] = FeatureInfo(
            0, 0, 0, 0, 3.51e-2, 0, 0, 0, 0, 0, 0)

        self.feature_list[self.NAND_OPERATION[NANDCMDType.Dout_4K]] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[NANDCMDType.Dout_8K]] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[NANDCMDType.Dout_12K]] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[NANDCMDType.Dout_16K]] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        self.feature_list[self.NAND_OPERATION[NANDCMDType.Din_LSB]] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[NANDCMDType.Din_USB]] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[NANDCMDType.Din_MSB]] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        self.feature_list[self.NAND_OPERATION[hash((NANDCMDType.tProg, Cell.SLC))]] = FeatureInfo(
            0, 0, 0, 0, 3.12e-2, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[hash((NANDCMDType.tProg_1P, Cell.SLC))]] = FeatureInfo(
            0, 0, 0, 0, 3.12e-2, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[hash((NANDCMDType.tProg, Cell.MLC))]] = FeatureInfo(
            0, 0, 0, 0, 3.12e-2, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[hash((NANDCMDType.tProg_1P, Cell.MLC))]] = FeatureInfo(
            0, 0, 0, 0, 3.12e-2, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[hash((NANDCMDType.tProg, Cell.TLC))]] = FeatureInfo(
            0, 0, 0, 0, 3.12e-2, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[hash((NANDCMDType.tProg_1P, Cell.TLC))]] = FeatureInfo(
            0, 0, 0, 0, 3.12e-2, 0, 0, 0, 0, 0, 0)

        self.feature_list[self.NAND_OPERATION[NANDCMDType.tBERS]
                          ] = FeatureInfo(0, 0, 0, 0, 1.56e-2, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[NANDCMDType.tNSC]
                          ] = FeatureInfo(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[NANDCMDType.LatchDumpDown]] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[NANDCMDType.LatchDumpUp]] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NAND_OPERATION[NANDCMDType.Suspend]] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        self.feature_list[self.ECC_DECODING] = FeatureInfo(self.calculate_latency(
            self.address_map.ECC, cycle=144 * self.ecc_iteration_count), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.ECC_TO_SRAM] = FeatureInfo(self.calculate_latency(
            self.address_map.ECC, cycle=320), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
