from copy import deepcopy

from core.backbone.bus import Bus
from core.modules.parallel_unit import ParallelUnit
from product.general.config.storage_feature import Feature
from product.general.config.storage_parameters import Parameter


class PlainInfo:
    def __init__(self):
        self.param = Parameter()
        self.page_count = self.param.PAGE_PER_BLOCK
        self.block_count = self.param.BLOCK_PER_PLANE
        self.blocks = []
        self.free_block_pool = []
        self.active_block = []
        self.total_page_count = self.page_count * self.block_count
        self.free_page_count = self.page_count * self.block_count
        self.valid_page_count = 0
        self.invalid_page_count = 0
        for i in range(self.block_count):
            block = BlockInfo(i)
            self.blocks.append(block)
            if i < self.param.STREAM_COUNT:
                self.active_block.append(-1)
                self.free_block_pool.append(block)
            else:
                self.free_block_pool.append(block)

    def get_a_free_block(self, stream_id,):
        self.active_block[stream_id] = self.free_block_pool[0]
        del self.free_block_pool[0]

    def get_free_block_pool_size(self, ):
        return len(self.free_block_pool)

    def add_to_free_block_pool(self, block_num):
        block = BlockInfo(block_num)
        self.free_block_pool.append(block)


class BlockInfo:
    def __init__(self, id, ):
        self.param = Parameter()
        self.page_count = self.param.PAGE_PER_BLOCK
        self.block_id = id
        self.current_page_write_id = 0
        self.current_status = ''
        self.Invalid_page_count = self.page_count
        self.erase_count = 0
        self.page_size_of_block = self.page_count
        self.invlaid_page_list = 0
        self.stream_id = 0


class FlashBlockManager(ParallelUnit):
    feature: Feature

    def __init__(self, product_args, _address, unit_fifo_num=1):
        super().__init__(product_args, _address, unit_fifo_num)
        assert self.address == self.address_map.FBM

        self.bus = Bus()
        self.param = Parameter()

        self.generate_submodule(
            self.erase_done_handler,
            self.feature.FBM_ERASE_DONE_HANDLING)
        self.block_alloc_handler_submodule_list = [
            None for _ in range(self.param.CHANNEL * self.param.WAY)]
        self.receive_erase_event = {}
        for channel in range(self.param.CHANNEL):
            for way in range(self.param.WAY):
                chip_id = channel * self.param.WAY + way
                self.block_alloc_handler_submodule_list[chip_id] = self.generate_submodule(
                    self.block_alloc_handler, self.feature.FBM_BLOCK_ALLOC_HANDLING, s_id=chip_id)
                self.receive_erase_event[chip_id] = self.env.event()

        self.block_erase_count = 0
        self.block_erase_done_count = 0
        self.page_allock_count = 0

        self.max_block_erase_count = 0
        self.channel_count = self.param.CHANNEL
        self.way_count = self.param.WAY
        self.plane_count = self.param.PLANE
        self.page_count = self.param.PAGE_PER_BLOCK
        self.block_count = self.param.BLOCK_PER_PLANE
        self.stream_cnt = self.param.STREAM_COUNT

        self.a_plane_info = [[[PlainInfo() for _ in range(self.plane_count)] for _ in range(
            self.way_count)] for _ in range(self.channel_count)]

    def block_alloc_handler(self, packet, dst_id):
        stream_id = packet['nvm_transaction'].stream_id
        address = packet['nvm_transaction_flash'].address
        chip_id = address.channel * self.param.WAY + address.way
        plane = self.a_plane_info[address.channel][address.way][address.plane]
        if plane.active_block[stream_id] == -1:
            erase_packet = deepcopy(packet)
            for i in range(self.plane_count):
                plane = self.a_plane_info[address.channel][address.way][i]
                plane.get_a_free_block(stream_id)
            erase_packet['nvm_transaction_flash'].address.plane = 0
            erase_packet['nvm_transaction'].transaction_type = 'erase'
            erase_packet['nvm_transaction_flash'].address.block = plane.active_block[stream_id].block_id
            self.block_erase_count += 1
            self.send_sq(
                erase_packet,
                self.address,
                self.address_map.TSU,
                src_submodule=self.block_alloc_handler,
                src_submodule_id=chip_id)

            yield self.receive_erase_event[chip_id]

            plane = self.a_plane_info[address.channel][address.way][packet['nvm_transaction_flash'].address.plane]

        if plane.active_block[stream_id].current_page_write_id == plane.active_block[stream_id].page_size_of_block:
            erase_packet = deepcopy(packet)
            for i in range(self.plane_count):
                plane = self.a_plane_info[address.channel][address.way][i]
                plane.get_a_free_block(stream_id)
            plane.get_a_free_block(stream_id)

            erase_packet['nvm_transaction_flash'].address.plane = 0
            erase_packet['nvm_transaction'].transaction_type = 'erase'
            erase_packet['nvm_transaction_flash'].address.block = plane.active_block[stream_id].block_id
            self.block_erase_count += 1
            self.send_sq(
                erase_packet,
                self.address,
                self.address_map.TSU,
                src_submodule=self.block_alloc_handler,
                src_submodule_id=chip_id)
            yield self.receive_erase_event[chip_id]

            plane = self.a_plane_info[address.channel][address.way][packet['nvm_transaction_flash'].address.plane]

        self.page_allock_count += 1
        packet['nvm_transaction_flash'].address.page = plane.active_block[stream_id].current_page_write_id
        packet['nvm_transaction_flash'].address.block = plane.active_block[stream_id].block_id
        plane.active_block[stream_id].current_page_write_id += 1

        self.send_sq(
            packet,
            self.address,
            self.address_map.AML,
            src_submodule=self.block_alloc_handler,
            src_submodule_id=dst_id)

    def erase_done_handler(self, packet):
        address = packet['nvm_transaction_flash'].address
        chip_id = address.channel * self.param.WAY + address.way
        self.receive_erase_event[chip_id].succeed()
        self.receive_erase_event[chip_id] = self.env.event()
        self.block_erase_done_count += 1

    def handle_request(self, packet, fifo_id):
        src = packet['src']
        address = packet['nvm_transaction_flash'].address
        if src == self.address_map.AML:
            chip_id = address.channel * self.param.WAY + address.way
            self.wakeup(
                self.address,
                self.block_alloc_handler,
                packet,
                src_id=fifo_id,
                dst_id=chip_id)
        elif src == self.address_map.TSU:
            self.wakeup(
                self.address,
                self.erase_done_handler,
                packet,
                src_id=fifo_id)

    def print_debug(self):
        pass
