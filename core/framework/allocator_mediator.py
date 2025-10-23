from core.backbone.address_map import AddressMap
from core.framework.allocator import (ModuleTransactionAllocator,
                                      SimpyResourceAllocator)
from core.framework.common import ProductArgs, eResourceType
from core.framework.fifo_id import BA_FIFO_ID
from core.framework.singleton import Singleton


class AllocatorMediator(metaclass=Singleton):
    def __init__(self, product_args: ProductArgs):
        self.param = product_args.param
        self.feature = product_args.feature
        self.address_map = AddressMap()

        # DRAM
        self.read_dma_desc_allocator = SimpyResourceAllocator(
            product_args,
            eResourceType.ReadDMADesc,
            self.param.READ_DMA_CNT,
            start_addr=self.address_map.get_memory_start_address(
                eResourceType.ReadDMADesc))
        self.write_dma_desc_allocator = SimpyResourceAllocator(
            product_args,
            eResourceType.WriteDMADesc,
            self.param.WRITE_DMA_CNT,
            start_addr=self.address_map.get_memory_start_address(
                eResourceType.WriteDMADesc))

        self.buffered_unit_id_allocator = SimpyResourceAllocator(
            product_args,
            eResourceType.MediaBufferedUnitID,
            self.param.MEDIA_BUFFERED_UNIT_ID_COUNT,
            start_addr=self.address_map.get_memory_start_address(
                eResourceType.MediaBufferedUnitID))
        self.nand_job_id_allocator = SimpyResourceAllocator(
            product_args,
            eResourceType.MediaNandJobID,
            self.param.NAND_JOB_BUFFER_COUNT,
            start_addr=self.address_map.get_memory_start_address(
                eResourceType.MediaNandJobID))

        self.buffer_allocator = ModuleTransactionAllocator(product_args)
        self.buffer_allocator.set_resource_producer_address(
            eResourceType.ReadBuffer.value,
            self.param.READ_BUFFER_MANAGER,
            BA_FIFO_ID.Allocate.value,
            BA_FIFO_ID.Release.value)
        self.buffer_allocator.set_feature_id(
            eResourceType.ReadBuffer.value,
            self.feature.BUFFER_REQUEST_4K_UNIT,
            self.feature.BUFFER_RELEASE_4K_UNIT)
        self.buffer_allocator.set_resource_producer_address(
            eResourceType.WriteBuffer.value,
            self.param.WRITE_BUFFER_MANAGER,
            BA_FIFO_ID.Allocate.value,
            BA_FIFO_ID.Release.value)
        self.buffer_allocator.set_feature_id(
            eResourceType.WriteBuffer.value,
            self.feature.BUFFER_REQUEST_4K_UNIT,
            self.feature.BUFFER_RELEASE_4K_UNIT)
        self.buffer_allocator.set_resource_producer_address(eResourceType.GCBuffer.value, self.param.GC_BUFFER_MANAGER,
                                                            BA_FIFO_ID.Allocate.value, BA_FIFO_ID.Release.value)
        self.buffer_allocator.set_feature_id(eResourceType.GCBuffer.value, self.feature.BUFFER_REQUEST_4K_UNIT,
                                             self.feature.BUFFER_RELEASE_4K_UNIT)
        self.allocator_list = [None for _ in range(len(eResourceType))]

        self.allocator_list[eResourceType.ReadDMADesc.value] = self.read_dma_desc_allocator
        self.allocator_list[eResourceType.WriteDMADesc.value] = self.write_dma_desc_allocator
        self.allocator_list[eResourceType.ReadBuffer.value] = self.buffer_allocator
        self.allocator_list[eResourceType.WriteBuffer.value] = self.buffer_allocator
        self.allocator_list[eResourceType.MediaBufferedUnitID.value] = self.buffered_unit_id_allocator
        self.allocator_list[eResourceType.MediaNandJobID.value] = self.nand_job_id_allocator
        self.allocator_list[eResourceType.GCBuffer.value] = self.buffer_allocator

    def read(self, resource_type, resource_id):
        allocator = self.allocator_list[resource_type.value]
        return allocator.read(resource_id)

    def get_destination_info(self, resource_type):
        allocator = self.allocator_list[resource_type.value]
        if isinstance(allocator, ModuleTransactionAllocator):
            dst = allocator.resource_producer_address[resource_type.value]
            dst_fifo_id = allocator.resource_producer_allocation_fifo[resource_type.value]
        else:
            dst, dst_fifo_id = None, None
        return dst, dst_fifo_id

    def allocate(
            self,
            resource_type,
            request_size,
            packet,
            address,
            allocation_callback_fifo_id=0):
        allocator = self.allocator_list[resource_type.value]
        if isinstance(allocator, ModuleTransactionAllocator):
            if self.param.SKIP_BUFFER_CHECK:
                return None
            yield from allocator.allocate(resource_type, request_size, address, packet, allocation_callback_fifo_id)
            return None
        else:
            assert isinstance(allocator, SimpyResourceAllocator)
            return_list = yield from allocator.allocate(packet, request_size)
            return return_list

    def release(self, resource_type, src_addr, return_id=-1):
        allocator = self.allocator_list[resource_type.value]
        if isinstance(allocator, ModuleTransactionAllocator):
            if self.param.SKIP_BUFFER_CHECK:
                return None

            dst = allocator.resource_producer_address[resource_type.value]
            dst_fifo_id = allocator.resource_producer_release_fifo[resource_type.value]
            allocator.release(resource_type, return_id)
        else:
            assert isinstance(allocator, SimpyResourceAllocator)
            allocator.release(return_id)
            dst, dst_fifo_id = None, None

        return dst, dst_fifo_id

    def allocate_callback(self, packet):
        resource_type = packet['resource_type']
        allocator = self.allocator_list[resource_type.value]
        return allocator.allocate_call_back(packet)
