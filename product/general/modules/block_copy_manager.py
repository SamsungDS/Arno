from core.backbone.bus import Bus
from core.framework.common import (BufferedUnitType, MemAccessInfo,
                                   QueueDepthChecker, StatusType,
                                   TransactionSourceType, eCMDType,
                                   eResourceType)
from core.modules.parallel_unit import ParallelUnit
from product.general.config.storage_feature import Feature
from product.general.config.storage_parameters import Parameter
from product.general.modules.nvm_transaction_class.nvm_transaction import (
    AddressID, NvmTransactionFlash)
from product.general.provided_interface.bcm_pif import BCMPIF


class BlockCopyManager(ParallelUnit):
    feature: Feature

    def __init__(self, product_args, _address, unit_fifo_num=1):
        super().__init__(product_args, _address, unit_fifo_num)
        assert self.address == self.address_map.BCM

        self.bus = Bus()
        self.param = Parameter()
        self.gc_read_handler_submodule_list = [
            None for _ in range(self.param.CHANNEL * self.param.WAY)]

        self.receive_alloc_done_event = [
            None for _ in range(self.param.CHANNEL * self.param.WAY)]
        self.generate_submodule(self.gc_write_handler, self.feature.GC_WRITE_HANDLING)
        self.generate_submodule(self.gc_done_handler, self.feature.GC_DONE_DONE_HANDLING)
        self.generate_submodule(self.buffer_alloc_done_handler, self.feature.GC_ALLOC_DONE_HANDLING)
        self.generate_submodule(
            self.gc_read_handler, self.feature.GC_READ_HANDLING)

        self.receive_alloc_done_event = self.env.event()
        self.use_buffer_list = []
        self.buffer_list = []
        self.gc_page_buffer_ids = {}
        self.gc_page_buffer_ids_2 = {}
        self.wait_buffer_alloc = {}
        self.channel_count = self.param.CHANNEL
        self.way_count = self.param.WAY
        self.plane_count = self.param.PLANE
        self.page_count = self.param.PAGE_PER_BLOCK
        self.block_count = self.param.BLOCK_PER_PLANE
        self.stream_cnt = self.param.STREAM_COUNT
        self.gc_start_count = 0
        self.gc_done_count = 0
        self.write_done_page = 0
        self.done_page = 0
        self.gc_size = [0] * self.channel_count * self.way_count

    def get_ppn(self, ch: int, way: int, plane: int, block: int, page: int) -> int:
        return ((((ch * self.way_count + way) * self.plane_count + plane) * self.block_count + block) * self.page_count + page)

    def calculate_buffer_request(self, packet, stream):
        buffer_request_size = 0
        for plane in packet['nvm_transaction_flash_list']:
            for page in plane.valid_page_list:
                valid_sector = plane.valid_page_list[page]
                bit_list = [(valid_sector >> i) & 1 for i in reversed(range(4))]
                for lpo in range(4):
                    if bit_list[lpo] == 1:
                        buffer_request_size += 1
        self.wait_buffer_alloc[stream] = buffer_request_size

    def send_gc_read_packets(self, packet, stream):
        for plane in range(self.plane_count):
            for ch in range(self.channel_count):
                for way in range(self.way_count):
                    index = ch * (self.way_count * self.plane_count) + way * self.plane_count + plane
                    # 해당 인덱스에 valid_page_list가 존재하는지 확인
                    block_info = packet['nvm_transaction_flash_list'][index]
                    if not hasattr(block_info, 'valid_page_list'):
                        continue

                    for page in block_info.valid_page_list:
                        valid_sector = block_info.valid_page_list[page]
                        bit_list = [(valid_sector >> i) & 1 for i in reversed(range(4))]

                        for lpo in range(4):
                            if bit_list[lpo] == 1:

                                try:
                                    buffer_ptr = self.buffer_list.pop()
                                except IndexError:
                                    print("Warning: No available buffer in buffer_list")
                                    continue
                                block_id = packet['nvm_transaction_flash_list'][0].block_id
                                # AddressID 구성
                                address = AddressID()
                                address.channel = ch
                                address.way = way
                                address.plane = plane
                                address.block = block_id
                                address.page = page
                                address.lpo = lpo

                                # PPN 계산
                                old_ppn = self.get_ppn(ch, way, plane, block_id, page)

                                # ✅ BCMPIF Read 패킷 생성
                                read_packet = BCMPIF.create_read_packet(
                                    channel=ch,
                                    way=way,
                                    plane=plane,
                                    block=block_id,
                                    page=page,
                                    lpo=lpo,
                                    stream_id=stream,
                                    buffer_ptr=buffer_ptr,
                                    old_ppn=old_ppn,
                                    user='gc',
                                    src_num=packet["src_num"]
                                )
                                read_packet["src_num"] = packet["src_num"]

                                self.use_buffer_list.append(read_packet['nvm_transaction'].buffer_ptr)
                                self.gc_size[ch * self.way_count + way] += 1

                                # 패킷 전송
                                self.send_sq(
                                    read_packet,
                                    self.address,
                                    self.address_map.AML,
                                    src_submodule=self.gc_read_handler
                                )

                                # 버퍼 기록
                                if packet["src_num"] == 1:
                                    self.gc_page_buffer_ids[stream].append(read_packet['nvm_transaction'].buffer_ptr)
                                elif packet["src_num"] == 2:
                                    self.gc_page_buffer_ids_2[stream].append(read_packet['nvm_transaction'].buffer_ptr)

    def gc_read_handler(self, packet):
        self.gc_start_count += 1
        stream = 1

        self.calculate_buffer_request(packet, stream)

        yield from self.allocate_resource(-1, eResourceType.GCBuffer, request_size=self.wait_buffer_alloc[stream] - len(self.buffer_list))
        yield self.receive_alloc_done_event

        if packet["src_num"] == 1:
            self.gc_page_buffer_ids[stream] = []
        elif packet["src_num"] == 2:
            self.gc_page_buffer_ids_2[stream] = []

        self.send_gc_read_packets(packet, stream)

    def change_transaction_type(self, packet):
        packet['slot_id'] = -1
        packet['nvm_transaction'].transaction_type = eCMDType.Write
        packet['nvm_transaction_flash'].transaction_type = eCMDType.Write

    def gc_write_handler(self, packet):
        self.done_page += 1

        self.change_transaction_type(packet)

        self.send_sq(
            packet,
            self.address,
            self.address_map.AML,
            src_submodule=self.gc_write_handler)

    def remove_buffer_id(self, packet):
        stream = packet['nvm_transaction'].stream_id
        if packet['src_num'] == 1:
            self.gc_page_buffer_ids[stream].remove(packet['nvm_transaction'].buffer_ptr)
            self.use_buffer_list.remove(packet['nvm_transaction'].buffer_ptr)
            self.write_done_page += 1
        elif packet['src_num'] == 2:
            self.gc_page_buffer_ids_2[stream].remove(packet['nvm_transaction'].buffer_ptr)
            self.use_buffer_list.remove(packet['nvm_transaction'].buffer_ptr)
            self.write_done_page += 1
        else:
            assert False

    def check_gc_done(self, packet):
        stream = packet['nvm_transaction'].stream_id

        if stream in self.gc_page_buffer_ids:
            if len(self.gc_page_buffer_ids[stream]) == 0:
                self.gc_done_count += 1
                del self.gc_page_buffer_ids[stream]
                packet['nvm_transaction'].transaction_source_type = TransactionSourceType.GCDone
                return True
        if stream in self.gc_page_buffer_ids_2:
            if len(self.gc_page_buffer_ids_2[stream]) == 0:
                self.gc_done_count += 1
                del self.gc_page_buffer_ids_2[stream]
                packet['nvm_transaction'].transaction_source_type = TransactionSourceType.GCDone
                return True

    def gc_done_handler(self, packet):

        self.remove_buffer_id(packet)

        self.release_resource(eResourceType.GCBuffer, [packet['nvm_transaction'].buffer_ptr])

        if self.check_gc_done(packet):
            self.send_sq(
                packet,
                self.address,
                self.address_map.FBM,
                src_submodule=self.gc_done_handler)

    def buffer_alloc_done_handler(self, packet):
        self.buffer_list.extend(packet['resource_id'])
        self.receive_alloc_done_event.succeed()
        self.receive_alloc_done_event = self.env.event()

    def handle_request(self, packet, fifo_id):
        src = packet['src']
        if src == self.address_map.FBM:
            address = packet['nvm_transaction_flash'].address
            chip_id = address.channel * self.param.WAY + address.way
            self.wakeup(
                self.address,
                self.gc_read_handler,
                packet,
                src_id=fifo_id)
        elif src == self.address_map.AML:
            if packet['nvm_transaction'].transaction_type == eCMDType.NANDReadDone:
                self.wakeup(
                    self.address,
                    self.gc_write_handler,
                    packet,
                    src_id=fifo_id)
            elif packet['nvm_transaction'].transaction_type == eCMDType.WriteDone:
                self.wakeup(
                    self.address,
                    self.gc_done_handler,
                    packet,
                    src_id=fifo_id)
        elif src == self.address_map.BA:

            self.resource_allocate_callback(packet)
            self.wakeup(
                self.address,
                self.buffer_alloc_done_handler,
                packet,
                src_id=fifo_id)

    def print_debug(self):
        pass
