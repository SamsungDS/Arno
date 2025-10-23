from enum import Enum

from core.framework.common import MemAccessInfo, ProductArgs, eResourceType


class AddressMap(object):
    def __new__(cls, product_args: ProductArgs = None):
        if not hasattr(cls, 'instance'):
            cls.instance = super(AddressMap, cls).__new__(cls)
            cls.instance.init_address_map()

        if product_args is not None:
            product_args.set_args_to_class_instance(cls.instance)
            cls.instance.init_memory_map(product_args)

        return cls.instance

    def init_memory_map(self, product_args):
        self.param = product_args.param
        self.resource_start_address = [-1 for _ in eResourceType]
        self.sorted_start_address_list = []

        # SRAM

        # DRAM
        dram_start_address = MemAccessInfo.DRAM_START_ADDR
        self.resource_start_address[eResourceType.ReadDMADesc.value], dram_start_address = dram_start_address, dram_start_address + self.param.READ_DMA_CNT
        self.resource_start_address[eResourceType.WriteDMADesc.value], dram_start_address = dram_start_address, dram_start_address + self.param.WRITE_DMA_CNT
        self.resource_start_address[eResourceType.MediaBufferedUnitID.value], dram_start_address = dram_start_address, dram_start_address + \
            self.param.MEDIA_BUFFERED_UNIT_ID_COUNT
        self.resource_start_address[eResourceType.MediaNandJobID.value], dram_start_address = dram_start_address, dram_start_address + \
            self.param.NAND_JOB_BUFFER_COUNT

        # for ba dram start address
        MemAccessInfo.SRAM_CURRENT_ADDR = MemAccessInfo.SRAM_START_ADDR
        MemAccessInfo.DRAM_CURRENT_ADDR = dram_start_address

    def get_memory_start_address(self, resource_type):
        if isinstance(resource_type, Enum):
            resource_type = resource_type.value
        assert self.resource_start_address[resource_type] > 0
        return self.resource_start_address[resource_type]

    def set_memory_start_address(self, resource_type, val):
        if isinstance(resource_type, Enum):
            resource_type = resource_type.value
        assert self.resource_start_address[resource_type] == MemAccessInfo.INVALID_ADDR
        self.resource_start_address[resource_type] = val

    def init_done_memory_map(self):
        self.sorted_start_address_list = [
            (resource_type_idx,
             start_address) for resource_type_idx,
            start_address in enumerate(
                self.resource_start_address) if start_address != MemAccessInfo.INVALID_ADDR]
        self.sorted_start_address_list = sorted(
            self.sorted_start_address_list, key=lambda x: x[1])

    def init_address_map(self):
        self.HOST = 0
        self.PCIe = 1
        self.HDMA = 2
        self.NVMe = 3
        self.MEMC = 4
        self.BM = 5

        self.JG = 6
        self.JS = 7
        self.NFC = 8
        self.ECC = 9
        self.NAND = 10
        self.BA = 11
        self.SRAM = 12

        self.SC = 13
        self.EXAMPLE = 14
        self.HIL = 15
        self.BCM = 16
        self.DCL = 17
        self.AML = 18
        self.TSU = 19
        self.FBM = 20

        self.address_name_dict = {
            value: name for name, value in self.__dict__.items()
            if isinstance(value, int)
        }
        # because bus waiting queue is implemented by list.
        assert self.get_max_address() <= 1000

    def get_max_address(self):
        return max(self.address_name_dict.keys())

    def get_name(self, address):
        return self.address_name_dict[address]
