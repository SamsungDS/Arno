from copy import deepcopy

from core.framework.common import (eCMDType, eResourceType)
from core.modules.parallel_unit import ParallelUnit


class DataCacheLayer(ParallelUnit):
    def __init__(self, product_args, _address, unit_fifo_num=1):
        super().__init__(product_args, _address, unit_fifo_num)
        assert self.address == self.address_map.DCL

        self.issue_count = [0] * len(eCMDType)
        self.request_idx = 0
        self.host_read_issue_count = 0
        self.host_write_issue_count = 0
        self.host_write_done_count = 0
        self.host_read_done_count = 0
        self.host_read_done_cq_count = 0
        self.read_buffer_release_done_count = 0
        self.cache_miss_count = 0
        self.read_cache_hit_count = 0
        self.write_cache_hit_count = 0
        self.cache_evict_count = 0
        self.send_aml_count = 0
        self.nand_write_done_count = 0
        self.wait_cache_write_count = 0

        self.generate_submodule(
            self.read_handler,
            self.feature.DCL_READ_HANDLING)
        self.generate_submodule(
            self.read_done_handler,
            self.feature.DCL_READ_DONE_HANDLING)
        self.generate_submodule(
            self.write_handler,
            self.feature.DCL_WRITE_HANDLING)
        self.generate_submodule(
            self.done_handler,
            self.feature.DCL_DONE_HANDLING)
        self.generate_submodule(self.release_buffer, self.feature.ZERO)
        self.generate_submodule(self.check_write_wait_need, self.feature.ZERO)

        self.data_cache_use_count = {}
        self.data_cache_list = {}
        self.wait_read_done_packet = {}

        self.wait_lpn = None
        self.use_lpn = []

        self.data_cache_slot_count = self.param.LOGICAL_CACHE_ENTRY_CNT
        self.data_cache_empty_count = self.data_cache_slot_count
        self.receive_write_done_event = self.env.event()
        self.wait_lpn_use_done = self.env.event()

    class CacheInfo:
        def __init__(self, packet, clean):
            self.cache_packet = packet
            self.is_clean = clean

    def check_cache_hit(self, lpn):
        if lpn in self.data_cache_list:
            return True
        else:
            return False

    def read_handler(self, packet):
        lpn = packet['nvm_transaction'].lpn
        if self.check_cache_hit(lpn):
            cache_info = self.data_cache_list[lpn].cache_packet['nvm_transaction']
            self.data_cache_use_count[lpn] += 1
            if cache_info.valid_sector_bitmap == packet['nvm_transaction'].valid_sector_bitmap:
                packet['nvm_transaction'].buffer_ptr = cache_info.buffer_ptr
                self.read_cache_hit_count += 1
                self.wakeup(self.read_handler, self.done_handler, packet)
            else:
                self.cache_miss_count += 1
                packet['nvm_transaction'].valid_sector_bitmap = ~ cache_info.valid_sector_bitmap & packet['nvm_transaction'].valid_sector_bitmap
                self.send_aml_count += 1
                self.send_sq(
                    packet,
                    self.address,
                    self.address_map.AML,
                    src_submodule=self.read_handler)
        else:

            self.cache_miss_count += 1
            self.send_aml_count += 1
            self.send_sq(
                packet,
                self.address,
                self.address_map.AML,
                src_submodule=self.read_handler)

        if lpn == self.wait_lpn:
            self.wait_lpn_use_done.succeed()
            self.wait_lpn_use_done = self.env.event()
            self.wait_lpn = None
        self.use_lpn.remove(lpn)

    def read_done_handler(self, packet):
        lpn = packet['nvm_transaction'].lpn
        assert packet['nvm_transaction'].transaction_type == 'read_done_sq'
        if lpn in self.data_cache_use_count:
            if self.data_cache_use_count[lpn] > 0:
                self.data_cache_use_count[lpn] -= 1
        if lpn in self.data_cache_use_count:
            if self.data_cache_use_count[lpn] == 0 and lpn in self.wait_read_done_packet:
                self.wakeup(
                    self.read_done_handler,
                    self.done_handler,
                    self.wait_read_done_packet[lpn])
        if 'nvm_transaction_flash' in packet:
            self.wakeup(self.read_done_handler, self.release_buffer, packet)
            self.read_buffer_release_done_count += 1
            self.vcd_manager.set_read_buffer_release_done_count(
                self.read_buffer_release_done_count)
        if packet['remain_dma_count'] == 0:  # 하나의 Command 완료를 위해 수행해야 하는 잔여 MapUnit 수
            packet['nvm_transaction'].transaction_type = 'read_done_cq'
            self.host_read_done_cq_count += 1
            self.send_sq(
                packet,
                self.address,
                self.address_map.NVMe,
                src_submodule=self.read_done_handler)

    def write_handler(self, packet):
        lpn = packet['nvm_transaction'].lpn
        if self.check_cache_hit(lpn):
            packet['nvm_transaction'].valid_sector_bitmap = self.data_cache_list[lpn].cache_packet[
                'nvm_transaction'].valid_sector_bitmap | packet['nvm_transaction'].valid_sector_bitmap
            self.write_cache_hit_count += 1
            cache_packet = deepcopy(packet)
            self.data_cache_list[lpn].cache_packet = cache_packet
            self.data_cache_list[lpn].is_clean = False
            done_packet = deepcopy(packet)
            self.wakeup(self.write_handler, self.done_handler, done_packet)
            self.send_sq(
                packet,
                self.address,
                self.address_map.AML,
                src_submodule=self.write_handler)
        else:
            if len(self.data_cache_list) == self.data_cache_slot_count:
                yield self.receive_write_done_event
                self.wait_cache_write_count += 1
            cache_packet = deepcopy(packet)
            cache = self.CacheInfo(packet=cache_packet, clean=False)
            self.data_cache_empty_count -= 1
            self.data_cache_list[lpn] = cache
            self.data_cache_use_count[lpn] = 0
            self.wakeup(self.write_handler, self.done_handler, packet)
            self.send_sq(
                cache_packet,
                self.address,
                self.address_map.AML,
                src_submodule=self.write_handler)
        if lpn == self.wait_lpn:
            self.wait_lpn_use_done.succeed()
            self.wait_lpn_use_done = self.env.event()
            self.wait_lpn = None
        self.use_lpn.remove(lpn)

    def release_buffer(self, packet):
        buffer_type = eResourceType.WriteBuffer
        buffer_ptr = packet['nvm_transaction'].buffer_ptr
        if packet['nvm_transaction'].transaction_type == 'read_done_sq' or packet['nvm_transaction'].transaction_type == 'read_done_cq':
            buffer_type = eResourceType.ReadBuffer
            buffer_ptr = packet['nvm_transaction'].buffer_ptr
        self.release_resource(buffer_type, [buffer_ptr])
        description = 'release' + buffer_type.name
        if self.param.GENERATE_DIAGRAM:
            self.analyzer.packet_transfer(
                self.address, self.address_map.BA, 0, 0, 0, 0, description)

    def done_handler(self, packet):
        lpn = packet['nvm_transaction'].lpn
        if packet['nvm_transaction'].transaction_type == 'read':
            self.host_read_issue_count += 1
            packet['nvm_transaction'].transaction_type = 'cache_read_done'
            self.send_sq(
                packet,
                self.address,
                self.address_map.NVMe,
                src_submodule=self.done_handler)
        elif packet['nvm_transaction'].transaction_type == 'nand_read_done':
            self.host_read_issue_count += 1
            self.send_sq(
                packet,
                self.address,
                self.address_map.NVMe,
                src_submodule=self.done_handler)
        elif packet['nvm_transaction'].transaction_type == 'write_done':
            self.nand_write_done_count += 1
            if lpn in self.data_cache_list:
                if packet['nvm_transaction'].buffer_ptr == self.data_cache_list[lpn].cache_packet['nvm_transaction'].buffer_ptr:
                    if self.data_cache_use_count[lpn] != 0:
                        self.wait_read_done_packet[lpn] = packet
                    else:
                        del self.data_cache_list[lpn]
                        del self.data_cache_use_count[lpn]
                        self.receive_write_done_event.succeed()
                        self.receive_write_done_event = self.env.event()
                        self.wakeup(
                            self.done_handler, self.release_buffer, packet)
                else:
                    self.wakeup(self.done_handler, self.release_buffer, packet)

        elif packet['nvm_transaction'].transaction_type == 'write':
            packet['nvm_transaction'].transaction_type = 'cache_write_done'
            self.host_write_done_count += 1
            self.send_sq(
                packet,
                self.address,
                self.address_map.NVMe,
                src_submodule=self.done_handler)

    def check_write_wait_need(self, packet):
        lpn = packet['nvm_transaction'].lpn
        if lpn in self.use_lpn:
            self.wait_lpn = lpn
            yield self.wait_lpn_use_done

        self.use_lpn.append(lpn)
        if packet['nvm_transaction'].transaction_type == 'write':
            self.wakeup(self.address, self.write_handler, packet)
        elif packet['nvm_transaction'].transaction_type == 'read':
            self.wakeup(self.address, self.read_handler, packet)

    def handle_request(self, request, fifo_id):
        if request['src'] == self.address_map.NVMe:
            if request['nvm_transaction'].transaction_type == 'read':
                self.wakeup(
                    self.address,
                    self.check_write_wait_need,
                    request,
                    src_id=fifo_id)
            elif request['nvm_transaction'].transaction_type == 'write':
                self.wakeup(
                    self.address,
                    self.check_write_wait_need,
                    request,
                    src_id=fifo_id)
                self.host_write_issue_count += 1

            elif request['nvm_transaction'].transaction_type == 'read_done_sq':
                self.host_read_done_count += 1
                self.wakeup(
                    self.address,
                    self.read_done_handler,
                    request,
                    src_id=fifo_id)
        elif request['src'] == self.address_map.AML:
            self.wakeup(
                self.address,
                self.done_handler,
                request,
                src_id=fifo_id)

    def print_debug(self):
        pass
