from collections import deque

from core.framework.common import (MemAccessInfo, eAllocStatus, eRequestType,
                                   eResourceType)
from core.framework.fifo_id import BA_FIFO_ID
from core.modules.parallel_unit import ParallelUnit


class BufferAllocator(ParallelUnit):
    def __init__(self, product_args, _address, unit_fifo_num=1):
        super().__init__(product_args, _address, unit_fifo_num)
        assert self.address == self.address_map.BA

        self.remain_buffer_cnt = [0 for _ in eResourceType]
        self.remain_buffer_cnt[eResourceType.ReadBuffer.value] = self.param.BA_READ_BUFFER_CNT
        self.remain_buffer_cnt[eResourceType.WriteBuffer.value] = self.param.BA_WRITE_BUFFER_CNT

        self.generate_submodule(
            self.allocate_fetch,
            self.feature.BA_ALLOCATE_FETCH)
        self.generate_submodule(
            self.release_fetch,
            self.feature.BA_RELEASE_FETCH)
        self.generate_submodule(
            self.allocate,
            self.feature.BA_ALLOC_PER_SEGMENT)
        self.generate_submodule(
            self.release,
            self.feature.BA_RELEASE_PER_SEGMENT)

        self.allocate_issue_submodule = [None for _ in eResourceType]
        self.free_id_queue = [0 for _ in eResourceType]
        for resource_type in eResourceType:
            if eResourceType.ReadBuffer == resource_type:
                start_address = MemAccessInfo.SRAM_CURRENT_ADDR
                MemAccessInfo.SRAM_CURRENT_ADDR += self.remain_buffer_cnt[resource_type.value]
            else:
                start_address = MemAccessInfo.DRAM_CURRENT_ADDR
                MemAccessInfo.DRAM_CURRENT_ADDR += self.remain_buffer_cnt[resource_type.value]
            self.free_id_queue[resource_type.value] = deque(
                [i + start_address for i in range(self.remain_buffer_cnt[resource_type.value])])
            if self.remain_buffer_cnt[resource_type.value] != 0:
                self.allocate_issue_submodule[resource_type.value] = self.generate_submodule(
                    self.allocate_issue, [self.feature.BA_ALLOC_PER_SEGMENT], s_id=resource_type.value)
                self.address_map.set_memory_start_address(
                    resource_type.value, start_address)

        self.total_alloc_cnt = [0 for _ in eResourceType]
        self.total_release_cnt = [0 for _ in eResourceType]
        self.cur_alloc_cnt = [0 for _ in eResourceType]
        self.buffer_wait_event = [self.env.event() for _ in eResourceType]
        self.buffer_wait_cnt = [0 for _ in eResourceType]

        self.release_req_done_cnt = 0
        self.RELEASE_REQ_DONE_CNT = 8
        self.SEND_FLAG = True

        self.address_map.init_done_memory_map()

    def handle_request(self, packet, fifo_id):

        if packet['request_type'] == eRequestType.Allocate:
            assert fifo_id == BA_FIFO_ID.Allocate.value
            self.wakeup(
                self.address,
                self.allocate_fetch,
                packet,
                src_id=fifo_id,
                description='Allocate Fetch')
        elif packet['request_type'] == eRequestType.Release:
            assert fifo_id == BA_FIFO_ID.Release.value
            self.wakeup(
                self.address,
                self.release_fetch,
                packet,
                src_id=fifo_id,
                description='Release Fetch')

        else:
            assert 0, 'not support'

    def allocate_fetch(self, packet):
        self.wakeup(
            self.allocate_fetch,
            self.allocate,
            packet,
            description='Allocate')

    def allocate(self, packet):
        if packet:
            self.wakeup(
                self.allocate,
                self.allocate_issue,
                packet,
                dst_id=packet['resource_type'].value,
                description='Allocate Issue')

    def gen_alloc_done_packet(self, packet):
        done_packet = dict()
        done_packet['resource_id'] = packet['resource_id']
        done_packet['alloc_status'] = eAllocStatus.Valid
        done_packet['resource_type'] = packet['resource_type']
        done_packet['request_ip'] = packet['request_ip']
        done_packet['request_size'] = packet['request_size']
        done_packet['request_callback_fifo_id'] = packet['request_callback_fifo_id']
        done_packet['unique_key'] = packet['unique_key']
        return done_packet

    def allocate_issue(self, packet, s_id):
        resource_type = packet['resource_type'].value
        dst_address = packet['request_ip']
        dst_fifo_id = packet['request_callback_fifo_id']

        if self.remain_buffer_cnt[resource_type] < packet['request_size']:
            self.buffer_wait_cnt[resource_type] = packet['request_size']
            yield self.buffer_wait_event[resource_type]
            assert self.remain_buffer_cnt[resource_type]
        yield from self.allocate_issue_submodule[s_id].activate_feature(self.feature.BA_ALLOC_PER_SEGMENT)

        self.remain_buffer_cnt[resource_type] -= packet['request_size']
        self.total_alloc_cnt[resource_type] += packet['request_size']
        self.cur_alloc_cnt[resource_type] += packet['request_size']
        packet['resource_id'] = [self.free_id_queue[resource_type].popleft()
                                 for _ in range(packet['request_size'])]
        self.send_sq(
            self.gen_alloc_done_packet(packet),
            self.address,
            dst_address,
            dst_fifo_id,
            src_submodule=self.allocate_issue,
            src_submodule_id=s_id,
            description='AllocateCQ')

    def release_fetch(self, packet):
        self.wakeup(
            self.release_fetch,
            self.release,
            packet,
            description='Release')

    def release(self, packet):
        resource_type = packet['resource_type'].value

        self.remain_buffer_cnt[resource_type] += packet['request_size']
        self.total_release_cnt[resource_type] += packet['request_size']
        self.cur_alloc_cnt[resource_type] -= packet['request_size']
        self.free_id_queue[resource_type].extend(packet['resource_id'])

        if self.buffer_wait_cnt[resource_type] <= self.remain_buffer_cnt[resource_type]:
            self.buffer_wait_event[resource_type].succeed()
            self.buffer_wait_event[resource_type] = self.env.event()
            self.buffer_wait_cnt[resource_type] = 0

        if resource_type == eResourceType.ReadBuffer.value:
            self.release_req_done_cnt += 1
            if self.release_req_done_cnt == self.RELEASE_REQ_DONE_CNT:
                self.release_req_done_cnt = 0
                self.SEND_FLAG = True
