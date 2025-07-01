import math

import simpy

from core.backbone.address_map import AddressMap
from core.backbone.bus import Bus
from core.backbone.power_manager import PowerManager
from core.framework.allocator import Allocator
from core.framework.analyzer import Analyzer
from core.framework.latency_logger import LatencyLogger
from core.framework.performance_measure import PerformanceMeasure
from core.framework.singleton import Singleton
from core.framework.timer import FrameworkTimer
from product.general.config.storage_feature import Feature
from product.general.config.storage_parameters import Parameter
from product.general.framework.common import StorageProductArgs
from product.general.framework.storage_vcd_variables import VCDVariables
from product.general.framework.user_data_lba_count_calculator import (
    LBACalculator, UserDataLBACountMediator)


def set_max_user_ppn(param):
    calculator = UserDataLBACountMediator()
    NAND_PRODUCT = param.NAND_PRODUCT
    NAND_CAPACITY = param.NAND_PARAM[NAND_PRODUCT]['CAPACITY_Gb']
    DEVICE_CAPACITY_TB = NAND_CAPACITY * param.TOTAL_CHIP_COUNT / 1024 / 8
    param.TOTAL_USER_PPN_COUNT = math.ceil(
        calculator.calculate_lba_count(DEVICE_CAPACITY_TB) *
        LBACalculator.lba_size /
        param.FTL_MAP_UNIT_SIZE)
    SLPN_PER_LPN = param.STORAGE_MAP_UNIT_COUNT_PER_LOGICAL_MAPPING_UNIT
    SUSTAIN_WRITE_SB_COUNT = (
        (param.TOTAL_SUPER_BLOCK_COUNT_PER_STREAM -
         param.OVER_PROVISIONING_SB_COUNT) *
        param.STREAM_COUNT)
    coef = SLPN_PER_LPN * SUSTAIN_WRITE_SB_COUNT

    # Prevent unaligned LPN and unaligned sustain write prefill
    param.TOTAL_USER_PPN_COUNT = (param.TOTAL_USER_PPN_COUNT // coef) * coef


def initialize_environment(cls_instance, param=None):
    Allocator.reset()
    env = simpy.Environment()
    timer = FrameworkTimer(env)
    timer.__init__(env)
    if param is None:
        param = Parameter(init_flag=True)
    set_max_user_ppn(param)
    feature = Feature()
    Singleton.clear()
    cls_instance.product_args = StorageProductArgs(
        env=env, param=param, feature=feature)
    cls_instance.product_args.set_args_to_class_instance(cls_instance)
    cls_instance.client_value_vcd_vars = VCDVariables(
        product_args=cls_instance.product_args)
    cls_instance.product_args.set_vcd_variables(
        cls_instance.client_value_vcd_vars)
    cls_instance.product_args.set_args_to_class_instance(cls_instance)

    cls_instance.address_map = AddressMap(cls_instance.product_args)
    cls_instance.bus = Bus(cls_instance.product_args)
    cls_instance.analyzer = Analyzer(cls_instance.product_args)

    cls_instance.power_manager = PowerManager(cls_instance.product_args)
    cls_instance.latency_logger = LatencyLogger(cls_instance.product_args)
    cls_instance.performance_measure = PerformanceMeasure(
        cls_instance.product_args)
