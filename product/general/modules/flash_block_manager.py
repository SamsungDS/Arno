from core.backbone.bus import Bus
from core.framework.common import (BufferedUnitType, MemAccessInfo,
                                   QueueDepthChecker, StatusType,
                                   TransactionSourceType, eCMDType,
                                   eResourceType)
from core.modules.parallel_unit import ParallelUnit
from product.general.config.storage_feature import Feature
from product.general.config.storage_parameters import Parameter
from product.general.provided_interface.fbm_pif import FBMPIF


class PlainInfo:
    def __init__(self, stream_id):
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
        self.chip_id = 0
        self.stream_id = stream_id
        for i in range(self.block_count):
            block = BlockInfo(i)
            self.blocks.append(block)
            if i < self.param.STREAM_COUNT:
                self.active_block.append(-1)
                self.free_block_pool.append(block)
            else:
                self.free_block_pool.append(block)

    def get_a_free_block(self, stream_id):
        if self.active_block[stream_id] != -1:
            self.active_block[stream_id].current_status = 'data'
        self.active_block[stream_id] = self.free_block_pool[0]
        del self.free_block_pool[0]

    def get_free_block_pool_size(self, ):
        return len(self.free_block_pool)

    def add_to_free_block_pool(self, block_id):
        self.free_block_pool.append(self.blocks[block_id])
        self.blocks[block_id].current_status = 'free'


class BlockInfo:
    def __init__(self, id):
        self.param = Parameter()
        self.page_count = self.param.PAGE_PER_BLOCK
        self.block_id = id
        self.current_page_write_id = 0
        self.current_status = 'free'
        self.valid_page_count = 0
        self.erase_count = 0
        self.page_size_of_block = self.page_count
        self.valid_page_list = {}
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
        self.generate_submodule(
            self.gc_handler,
            self.feature.FBM_GC_HANDLING)
        self.generate_submodule(
            self.page_release_handler,
            self.feature.FBM_RELEASE_HANDLING)
        self.generate_submodule(
            self.gc_done_handler,
            self.feature.FBM_GC_DONE_HANDLING)
        self.page_alloc_handler_submodule_list = [
            None for _ in range(self.param.CHANNEL * self.param.WAY)]
        self.receive_erase_event = {}
        self.wait_free_block_event = {}
        for channel in range(self.param.CHANNEL):
            for way in range(self.param.WAY):
                chip_id = channel * self.param.WAY + way
                self.page_alloc_handler_submodule_list[chip_id] = self.generate_submodule(
                    self.page_alloc_handler, self.feature.FBM_ALLOC_HANDLING, s_id=chip_id)
                self.receive_erase_event[chip_id] = self.env.event()
                self.wait_free_block_event[chip_id] = self.env.event()
        self.block_erase_count = 0
        self.block_erase_done_count = 0
        self.page_allock_count = 0
        self.max_erase_count = 1000
        self.max_block_erase_count = 0
        self.channel_count = self.param.CHANNEL
        self.way_count = self.param.WAY
        self.plane_count = self.param.PLANE
        self.page_count = self.param.PAGE_PER_BLOCK
        self.block_count = self.param.BLOCK_PER_PLANE
        self.stream_cnt = self.param.STREAM_COUNT
        self.gc_threshold = self.param.GC_THRESHOLD
        self.urgent_gc_threshold = self.param.URGENT_GC_THRESHOLD
        self.check_gc_active = False
        self.check_gc_active_2 = False
        self.urgent_gc_check = False
        self.urgent_gc_count = 0
        self.a_plane_info = [[[PlainInfo(0) for _ in range(self.plane_count)] for _ in range(
            self.way_count)] for _ in range(self.channel_count)]
        self.remain_free_block = [0] * 32

    def set_init_block(self, address):
        plane = self.a_plane_info[address.channel][address.way][address.plane]
        block_id = address.block
        page = address.page
        if block_id == plane.free_block_pool[0].block_id:
            plane.free_block_pool[0].current_status = 'data'
            del plane.free_block_pool[0]
        if page not in plane.blocks[block_id].valid_page_list:
            plane.blocks[block_id].valid_page_list[page] = 0b1111
            plane.blocks[block_id].valid_page_count += 1

    def page_release_handler(self, packet):
        address = packet['nvm_transaction_flash'].address
        plane = self.a_plane_info[address.channel][address.way][address.plane]
        bit = 2 ** address.lpo
        if address.page in plane.blocks[address.block].valid_page_list:
            plane.blocks[address.block].valid_page_list[address.page] -= bit
            if plane.blocks[address.block].valid_page_list[address.page] == 0b0000:
                del plane.blocks[address.block].valid_page_list[address.page]
                plane.blocks[address.block].valid_page_count -= 1
        self.send_sq(
            packet,
            self.address,
            self.address_map.AML,
            src_submodule=self.page_release_handler)

    def ensure_active_block(self, stream_id, packet):
        for ch in range(self.channel_count):
            for way in range(self.way_count):
                chip_id = ch * self.way_count + way
                for pl in range(self.plane_count):
                    plane = self.a_plane_info[ch][way][pl]
                    if len(plane.free_block_pool) == 0:
                        yield self.wait_free_block_event[chip_id]
                    plane.get_a_free_block(stream_id)
                    plane.active_block[stream_id].current_status = 'active'
                    plane.active_block[stream_id].erase_count += 1
                    plane.active_block[stream_id].current_page_write_id = 0
                    plane.active_block[stream_id].valid_page_count = 0
                    plane.active_block[stream_id].valid_page_list.clear()
                erase_packet = FBMPIF.create_erase_packet(
                    channel=ch,
                    way=way,
                    plane=0,
                    block=plane.active_block[stream_id].block_id,  # 임시, 아래에서 업데이트
                    stream_id=stream_id,
                )
                self.remain_free_block[chip_id] = len(self.a_plane_info[ch][way][0].free_block_pool)
                self.block_erase_count += 1
                self.send_sq(
                    erase_packet,
                    self.address,
                    self.address_map.TSU,
                    src_submodule=self.page_alloc_handler,
                    src_submodule_id=chip_id)
                yield self.receive_erase_event[chip_id]

    def alloc_page(self, packet):
        address = packet['nvm_transaction_flash'].address
        plane = self.a_plane_info[address.channel][address.way][address.plane]
        stream = packet['nvm_transaction'].stream_id
        self.page_allock_count += 1
        packet['nvm_transaction_flash'].address.page = plane.active_block[stream].current_page_write_id
        packet['nvm_transaction_flash'].address.block = plane.active_block[stream].block_id
        plane.active_block[stream].current_page_write_id += 1
        plane.active_block[stream].valid_page_count += 1
        plane.active_block[stream].valid_page_list[packet['nvm_transaction_flash'].address.page] = 0b1111

    def check_gc_required(self, packet):
        if not self.check_gc_active:
            if self.get_total_free_block_size() / self.block_count / self.plane_count / self.way_count / self.channel_count <= self.gc_threshold:
                if packet['nvm_transaction'].transaction_source_type == TransactionSourceType.UserIO or self.urgent_gc_check:
                    gc_packet = FBMPIF.create_gc_trigger_packet(packet, src_num=1)
                    self.check_gc_active = True
                    self.wakeup(
                        self.page_alloc_handler,
                        self.gc_handler,
                        gc_packet)

        elif self.check_gc_active_2 == False:
            if self.get_total_free_block_size() / self.block_count / self.plane_count / self.way_count / self.channel_count <= self.gc_threshold:
                if packet['nvm_transaction'].transaction_source_type == TransactionSourceType.UserIO or self.urgent_gc_check:
                    gc_packet = FBMPIF.create_gc_trigger_packet(packet, src_num=2)
                    self.check_gc_active_2 = True
                    self.wakeup(
                        self.page_alloc_handler,
                        self.gc_handler,
                        gc_packet)

    def page_alloc_handler(self, packet, dst_id):
        for ch in range(self.channel_count):
            for way in range(self.way_count):
                chip_id = ch * self.way_count + way
                for pl in range(self.plane_count):
                    self.remain_free_block[chip_id] = len(self.a_plane_info[ch][way][0].free_block_pool)

        stream_id = packet['nvm_transaction'].stream_id
        address = packet['nvm_transaction_flash'].address
        plane = self.a_plane_info[address.channel][address.way][address.plane]
        chip_id = address.channel * self.way_count + address.way
        if plane.active_block[stream_id] == -1:
            yield from self.ensure_active_block(stream_id, packet)
        if plane.active_block[stream_id].current_page_write_id == plane.active_block[stream_id].page_size_of_block:
            yield from self.ensure_active_block(stream_id, packet)

        self.alloc_page(packet)

        self.send_sq(
            packet,
            self.address,
            self.address_map.AML,
            src_submodule=self.page_alloc_handler,
            src_submodule_id=dst_id)

        if chip_id == 0:
            self.check_gc_required(packet)

    def get_total_free_block_size(self):
        total = 0
        for ch in range(self.channel_count):
            for way in range(self.way_count):
                for plane in self.a_plane_info[ch][way]:
                    total += plane.get_free_block_pool_size()
        return total

    def get_src_block(self, stream_id):

        min_erase_cnt = self.max_erase_count * self.plane_count * 2
        min_valid_page = self.page_count ** 3
        src_block_id = None
        for block_id in range(self.block_count):
            total_valid = 0
            total_erase = 0
            for ch in range(self.channel_count):
                for way in range(self.way_count):
                    for plane in self.a_plane_info[ch][way]:
                        if plane.blocks[block_id].current_status != 'data':
                            total_valid += self.page_count ** 3
                        total_valid += plane.blocks[block_id].valid_page_count
                        total_erase += plane.blocks[block_id].erase_count

            if total_valid <= min_valid_page and total_erase <= min_erase_cnt:
                min_valid_page = total_valid
                min_erase_cnt = total_erase
                src_block_id = block_id
        return src_block_id, min_valid_page

    def check_urgent_gc_required(self, src_block):
        check_urgent = False
        for ch in range(self.channel_count):
            for way in range(self.way_count):
                for plane in self.a_plane_info[ch][way]:
                    plane.blocks[src_block].current_status = 'gc'
                    if self.get_total_free_block_size() / self.block_count / self.plane_count / self.way_count / self.channel_count <= self.urgent_gc_threshold:
                        check_urgent = True
        if check_urgent:
            self.urgent_gc_check = True
            self.urgent_gc_count += 1
            call_urgent = FBMPIF.create_urgent_signal(True)
            self.send_sq(
                call_urgent,
                self.address,
                self.address_map.AML,
                src_submodule=self.gc_handler)

    def gc_handler(self, packet):
        stream_id = packet['nvm_transaction'].stream_id
        src_block, valid_page_count = self.get_src_block(stream_id)
        assert src_block is not None, " block full"

        gc_packet = FBMPIF.create_gc_trigger_packet(packet, src_num=packet["src_num"])
        gc_packet['nvm_transaction_flash'].address.block = src_block
        gc_packet['nvm_transaction_flash_list'] = []
        for ch in range(self.channel_count):
            for way in range(self.way_count):
                for plane in self.a_plane_info[ch][way]:
                    gc_packet['nvm_transaction_flash_list'].append(plane.blocks[src_block])

        if valid_page_count == 0:
            for ch in range(self.channel_count):
                for way in range(self.way_count):
                    for plane in self.a_plane_info[ch][way]:
                        plane.add_to_free_block_pool(src_block)

        else:
            self.check_urgent_gc_required(src_block)

            self.send_sq(
                gc_packet,
                self.address,
                self.address_map.BCM,
                src_submodule=self.gc_handler)

    def end_urgent_gc(self):
        self.urgent_gc_check = False
        call_urgent = FBMPIF.create_urgent_signal(False)

        self.send_sq(
            call_urgent,
            self.address,
            self.address_map.AML,
            src_submodule=self.gc_handler)

    def gc_done_handler(self, packet):
        if packet['nvm_transaction'].transaction_source_type == TransactionSourceType.GCDone:
            ppn = packet['nvm_transaction_flash'].old_ppn
            block = ppn // self.page_count % self.block_count
            way_id = ppn // self.page_count // self.block_count // self.plane_count % self.way_count
            ch_id = ppn // self.page_count // self.block_count // self.plane_count // self.way_count
            chip_id = ch_id * self.param.WAY + way_id

            if packet['src_num'] == 1:
                self.check_gc_active = False
            elif packet['src_num'] == 2:
                self.check_gc_active_2 = False

            for ch in range(self.channel_count):
                for way in range(self.way_count):
                    for plane in self.a_plane_info[ch][way]:
                        plane.add_to_free_block_pool(block)

            self.wait_free_block_event[chip_id].succeed()
            self.wait_free_block_event[chip_id] = self.env.event()

            if self.urgent_gc_check:
                self.end_urgent_gc()

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
            if packet['nvm_transaction'].transaction_type == eCMDType.Write:
                chip_id = address.channel * self.param.WAY + address.way
                self.wakeup(
                    self.address,
                    self.page_alloc_handler,
                    packet,
                    src_id=fifo_id,
                    dst_id=chip_id)
            else:
                self.wakeup(
                    self.address,
                    self.page_release_handler,
                    packet,
                    src_id=fifo_id,)
        elif src == self.address_map.TSU:
            self.wakeup(
                self.address,
                self.erase_done_handler,
                packet,
                src_id=fifo_id)
        elif src == self.address_map.BCM and (packet['nvm_transaction'].transaction_source_type == TransactionSourceType.GCDone or packet['nvm_transaction'].transaction_source_type == 'return_block'):
            self.wakeup(
                self.address,
                self.gc_done_handler,
                packet,
                src_id=fifo_id)

    def print_debug(self):
        pass
