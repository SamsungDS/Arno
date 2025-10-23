from collections import deque
from math import ceil

import simpy
from core.config.basic_workload_generator import BasicWorkloadGenerator
from core.config.basic_workload_types import BasicWorkload
from core.framework.cmd_generator import CommandClassifier, CommandGenerator
from core.framework.common import eCMDType
from core.modules.parallel_unit import ParallelUnit
from core.script.workload_reader import WorkloadColumn


class Host(ParallelUnit):
    def __init__(self, product_args, _address, unit_fifo_num=1):
        super().__init__(product_args, _address, unit_fifo_num)

        self.cmd_id = 0
        self.cmd_outstanding_count = 0

        self.thost_offset_time = self.param.HOST_FIXED_DELAY

        self.thost_submodule = self.generate_submodule(
            self.thost, [self.feature.ZERO])
        self.generate_submodule(self.sender, self.feature.ZERO)

        self.debug_queue = deque()
        self.cmd_generator = CommandGenerator(self.env, self.param)

    def set_qd(self, qd):
        self.host_qd = simpy.Resource(self.env, capacity=qd)
        self.host_qd_queue = deque()

    def thost(self, info):
        issue_time, packet = info
        thost_offset_time = 0

        yield self.env.timeout(int(thost_offset_time))
        self.wakeup(self.thost, self.sender, packet)

    def sender(self, cmd):
        if not self.debug_queue:
            print('Host submodule sender is not implemented!!')

        self.debug_queue.append((self.env.now, cmd))

    def run(self, workload, cmd_count=-1):
        if workload is None:
            return

        if isinstance(workload, BasicWorkload):
            self.env.process(self.basic_start(workload))
        else:
            self.env.process(self.benchmark_start(workload, cmd_count))

    def reset_analyzer_with_workload_size(self, df):

        workload_io_cmd = df.loc[(df[WorkloadColumn.io_type] == 'Write') | (df[WorkloadColumn.io_type] == 'Read') | (df[WorkloadColumn.io_type] == 'Flush'), [WorkloadColumn.min_offset, WorkloadColumn.size]]

        def calculate_aligned_size(min_offset, size):
            return (ceil((min_offset + size) / self.param.FTL_MAP_UNIT_SIZE) - (
                        min_offset // self.param.FTL_MAP_UNIT_SIZE)) * self.param.FTL_MAP_UNIT_SIZE

        workload_size_total = workload_io_cmd.apply(lambda x: calculate_aligned_size(x[WorkloadColumn.min_offset], x[WorkloadColumn.size]),
                                                    axis=1).sum()
        self.analyzer.reset_analyzer(len(workload_io_cmd), workload_size_total)

    def check_host_qd(self):
        host_qd_available = self.host_qd.request()
        yield host_qd_available
        self.host_qd_queue.append(host_qd_available)
        self.vcd_manager.set_host_qd_count(len(self.host_qd_queue))

    def handle_cmd(self, delay, cmd):
        yield from self.check_host_qd()

        yield self.env.timeout(delay)
        cmd['init_time'] = self.env.now
        self.wakeup(self.address, self.thost, (self.env.now, cmd), src_id=0)

    def increase_cmd_id(self):
        self.cmd_id += 1
        if self.cmd_id == 1:
            self.analyzer.set_sim_start_time()

    def generate_cmd(self, io_type, size, min_offset, base_lba=0, deac=0):
        return self.cmd_generator.generate_cmd(self.cmd_id, io_type, size, min_offset, base_lba)

    def benchmark_start(self, workload, cmd_count):
        self.cmd_id = 0
        base_lba = 0
        df = workload.df

        if cmd_count != -1:
            self.analyzer.reset_analyzer(cmd_count)
        else:
            self.reset_analyzer_with_workload_size(df)

        delay_info = deque(df[WorkloadColumn.init_time].iloc[1:].values - df[WorkloadColumn.init_time].iloc[:-1].values)
        delay_info.appendleft(0)
        for io_type, size, init_time, min_offset, delay in zip(df[WorkloadColumn.io_type],
                                                               df[WorkloadColumn.size],
                                                               df[WorkloadColumn.init_time],
                                                               df[WorkloadColumn.min_offset],
                                                               delay_info):

            if io_type not in CommandClassifier.workload_type_dict.keys():
                continue
            cmd = self.generate_cmd(io_type, size, min_offset, base_lba)
            yield from self.handle_cmd(delay, cmd)

            self.increase_cmd_id()
            if cmd_count != -1 and cmd_count <= self.cmd_id:
                break

    def basic_start(self, workload: BasicWorkload):
        self.cmd_id = 0
        workload_generator = BasicWorkloadGenerator(self.env, workload)
        self.analyzer.reset_analyzer(workload_generator.total_cmd_count)

        for command in workload_generator.create_command():

            delay = command['init_time'] - self.env.now
            if delay < 0:
                delay = 0
            yield from self.handle_cmd(delay, command)

            self.increase_cmd_id()

    def release_host_qd(self):
        self.host_qd.release(self.host_qd_queue.popleft())
        self.vcd_manager.set_host_qd_count(len(self.host_qd_queue))

    def is_release_qd_packet(self, packet):
        if packet['cmd_type'] == eCMDType.Write and packet['src'] == self.address_map.PCIe:
            return True
        elif packet['src'] == self.address_map.NVMe:
            return True
        else:
            return False

    def handle_request(self, packet, fifo_id):
        if self.is_release_qd_packet(packet):
            self.cmd_outstanding_count -= 1
            self.release_host_qd()
