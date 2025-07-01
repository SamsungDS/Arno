from enum import Enum

from core.framework.common import (MemAccessInfo, RoundRobinQueues,
                                   eMemoryType, eResourceType)
from core.framework.data_printer import DataPrinter
from core.modules.parallel_unit import ParallelUnit


class MemoryC(ParallelUnit):
    class MemAccessType(Enum):
        Read = 0
        Write = 1

    def __init__(self, product_args, _address, unit_fifo_num=1):
        super().__init__(product_args, _address, unit_fifo_num)
        assert self.address == self.address_map.MEMC

        self.write_done_event_memory_map = dict()
        self.write_processing_memory_set = set()
        self.readable_memory_set = set()

        # must be appended in the order of eMemoryType
        self.memory_bandwidth = []
        self.memory_access_payload = []
        self.memory_access_feature_id, self.memory_feature_id = [], []
        self.memory_payload_latency = []
        self.memory_bandwidth.append(
            self.param.sram_param['BANDWIDTH_B_PER_NS'])
        self.memory_bandwidth.append(
            self.param.dram_param['BANDWIDTH_B_PER_NS'])
        self.memory_access_payload.append(self.param.sram_param['PAYLOAD'])
        self.memory_access_payload.append(self.param.dram_param['PAYLOAD'])
        self.memory_access_feature_id.append(self.feature.SRAM_MEM_ACCESS)
        self.memory_access_feature_id.append(self.feature.DRAM_MEM_ACCESS)
        self.memory_feature_id.append(self.feature.SRAM)
        self.memory_feature_id.append(self.feature.DRAM)
        self.memory_payload_latency.append(
            self.memory_access_payload[0] /
            self.memory_bandwidth[0])
        self.memory_payload_latency.append(
            self.memory_access_payload[1] /
            self.memory_bandwidth[1])

        self.mem_access_submodule_list = [None for _ in eMemoryType]
        self.memory_submodule_list = [None for _ in eMemoryType]
        self.memory_rr_queues = [None for _ in eMemoryType]
        for mem_type in eMemoryType:
            self.mem_access_submodule_list[mem_type.value] = self.generate_submodule(
                self.mem_access_submodule, [self.feature.SRAM_MEM_ACCESS, self.feature.DRAM_MEM_ACCESS], mem_type.value)
            self.memory_submodule_list[mem_type.value] = self.generate_submodule(
                self.memory_submodule, [self.feature.SRAM, self.feature.DRAM], mem_type.value)
            self.memory_rr_queues[mem_type.value] = RoundRobinQueues(
                len(MemoryC.MemAccessType))

        self.generate_submodule(
            self.handle_hmb_access_done,
            self.feature.MEM_ACCESS)
        self.generate_submodule(self.notify_done, self.feature.ZERO)

        self.init_memc_log()

    def init_memc_log(self):
        self.total_memory_write_time = 0
        self.total_memory_read_time = 0
        self.total_memory_access_time = 0
        self.each_resource_type_access_time = [
            [0, 0] for _ in eResourceType]   # 0: read, 1: write

    def notify_done(self, mem_access_info):
        mem_access_info.event.succeed()
        mem_access_info.event = self.env.event()

    def pay_load_rounding(self, mem_access_info):
        mem_type = MemAccessInfo.get_memory_type(mem_access_info.resource_id)
        remainder = mem_access_info.request_size % self.memory_access_payload[mem_type.value]
        if remainder != 0:
            mem_access_info.request_size += self.memory_access_payload[mem_type.value] - remainder

        return int(mem_access_info.request_size //
                   self.memory_access_payload[mem_type.value])

    def send_hmb_access_sq(self, mem_access_info, mem_type_value):
        mem_access_info.event = self.env.event()
        hmd_access_packet = dict()
        hmd_access_packet['mem_access_info'] = mem_access_info
        self.send_sq(
            hmd_access_packet,
            self.address,
            self.address_map.NVMe,
            description="access HMB")

    def read_memory(self, mem_access_info: MemAccessInfo):
        mem_type = MemAccessInfo.get_memory_type(mem_access_info.resource_id)

        resource_id = mem_access_info.resource_id
        if resource_id not in self.readable_memory_set:
            if resource_id in self.write_processing_memory_set:
                yield from self.wait_memory_write_done(resource_id)
            else:
                assert 0, f'{resource_id} access(read) empty memory, write first'

        pay_load_count = self.pay_load_rounding(mem_access_info)
        if pay_load_count:
            mem_access_info.event = self.env.event()
            for pay_load_idx in range(pay_load_count):
                self.memory_rr_queues[mem_type.value].push(
                    mem_access_info, MemoryC.MemAccessType.Read.value)

            if self.memory_rr_queues[mem_type.value].any_remaining_jobs():
                packet = self.memory_rr_queues[mem_type.value].pop_round_robin(
                )
                self.wakeup(
                    self.address,
                    self.mem_access_submodule,
                    packet,
                    src_id=0,
                    dst_id=mem_type.value)

            yield mem_access_info.event

    def write_memory(self, mem_access_info: MemAccessInfo):
        mem_access_info.set_type_write()
        mem_type = MemAccessInfo.get_memory_type(mem_access_info.resource_id)
        resource_id = mem_access_info.resource_id

        if resource_id in self.readable_memory_set:
            self.readable_memory_set.remove(resource_id)

        if resource_id in self.write_processing_memory_set:
            yield from self.wait_memory_write_done(resource_id)
        self.write_processing_memory_set.add(resource_id)

        pay_load_count = self.pay_load_rounding(mem_access_info)
        if pay_load_count:
            mem_access_info.event = self.env.event()
            for pay_load_idx in range(pay_load_count):
                self.memory_rr_queues[mem_type.value].push(
                    mem_access_info, MemoryC.MemAccessType.Write.value)

            if self.memory_rr_queues[mem_type.value].any_remaining_jobs():
                packet = self.memory_rr_queues[mem_type.value].pop_round_robin(
                )
                self.wakeup(
                    self.address,
                    self.mem_access_submodule,
                    packet,
                    src_id=0,
                    dst_id=mem_type.value)
            yield mem_access_info.event

        self.readable_memory_set.add(resource_id)
        self.write_processing_memory_set.remove(resource_id)

    def write_memory_directly(self, resource_id):
        ''' This function is for read that assuming that it is already written in a specific memory address '''
        self.readable_memory_set.add(resource_id)

    def wait_memory_write_done(self, resource_id):
        self.write_done_event_memory_map[resource_id] = self.env.event()
        yield self.write_done_event_memory_map[resource_id]

    def mem_access_submodule(self, mem_access_info, mem_type_value):
        latency = self.memory_payload_latency[mem_type_value]
        mem_access_info.request_size -= self.memory_access_payload[mem_type_value]
        self.wakeup(self.mem_access_submodule, self.memory_submodule, {
                    'latency': latency}, src_id=mem_type_value, dst_id=mem_type_value)
        yield from self.mem_access_submodule_list[mem_type_value].activate_feature(feature_id=self.memory_access_feature_id[mem_type_value], runtime_latency=latency)

        if not mem_access_info.is_read():
            self.total_memory_write_time += latency
            self.each_resource_type_access_time[mem_access_info.resource_type.value][
                MemoryC.MemAccessType.Write.value] += latency
        else:
            self.total_memory_read_time += latency
            self.each_resource_type_access_time[mem_access_info.resource_type.value][
                MemoryC.MemAccessType.Read.value] += latency

        if mem_access_info.request_size == 0:
            mem_access_info.event.succeed()
            mem_access_info.event = self.env.event()

        if self.memory_rr_queues[mem_type_value].any_remaining_jobs():
            packet = self.memory_rr_queues[mem_type_value].pop_round_robin()
            self.wakeup(
                self.mem_access_submodule,
                self.mem_access_submodule,
                packet,
                src_id=mem_type_value,
                dst_id=mem_type_value)

    def memory_submodule(self, mem_access_info, mem_type_value):
        yield from self.memory_submodule_list[mem_type_value].activate_feature(feature_id=self.memory_feature_id[mem_type_value], runtime_latency=mem_access_info['latency'])

    def handle_hmb_access_done(self, mem_access_info):
        if mem_access_info.is_read():
            self.wakeup(self.address, self.notify_done, mem_access_info)
        else:
            resource_id = mem_access_info.resource_id
            if resource_id in self.write_done_event_memory_map:
                self.write_done_event_memory_map[resource_id].succeed()
                del self.write_done_event_memory_map[resource_id]

            assert resource_id not in self.readable_memory_set
            self.readable_memory_set.add(resource_id)
            self.write_processing_memory_set.remove(resource_id)
            self.wakeup(self.address, self.notify_done, mem_access_info)

    def handle_request(self, packet, fifo_id):
        if packet['src'] == self.address_map.NVMe:
            self.wakeup(
                self.address,
                self.handle_hmb_access_done,
                packet['mem_access_info'],
                src_id=fifo_id,
                description='HMB Access Done')
        else:
            assert 0, 'not support interface'

    def print_memc_log(self):
        self.total_memory_access_time = self.total_memory_read_time + \
            self.total_memory_write_time
        if self.total_memory_access_time == 0:
            return

        data = [['Resource Type', 'Read Time', 'Write Time',
                 'Read / Total (%)', 'Write / Total (%)']]

        for resource_type in eResourceType:
            read_time = int(
                self.each_resource_type_access_time[resource_type.value][0])
            write_time = int(
                self.each_resource_type_access_time[resource_type.value][1])
            if read_time + write_time == 0:
                continue
            read_percent = read_time / self.total_memory_access_time * 100
            write_percent = write_time / self.total_memory_access_time * 100
            data.append([f'{resource_type.name}',
                         f'{read_time:d} ns',
                         f'{write_time:d} ns',
                         f'{read_percent:.2f} %',
                         f'{write_percent:.2f} %'])
        DataPrinter.print_memc_log(
            self.total_memory_access_time,
            self.total_memory_read_time,
            self.total_memory_write_time,
            data)
        self.init_memc_log()
