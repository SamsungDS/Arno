from random import choices, randrange, seed

from core.config.basic_workload_types import (BasicPatternType, BasicWorkload,
                                              MixedPattern)
from core.config.core_parameter import CoreParameter
from core.framework.cmd_generator import CommandClassifier, CommandGenerator
from core.framework.common import eCMDType

seed(0)


class BasicWorkloadGenerator:
    def __init__(self, env, workload: BasicWorkload):
        self.env = env
        self.param = CoreParameter()
        self.sector_size = self.param.SECTOR_SIZE
        self._cmd_id = 0
        self.pattern = workload.pattern
        self.total_cmd_count = workload.cmd_count
        self.qd = workload.qd
        self.idle_time_ms = workload.idle_time_ms

        self.calc_start_lba: dict[BasicPatternType, callable] = {
            BasicPatternType.Dummy: self.dummy_lba,
            BasicPatternType.Seq: self.sequential_lba,
            BasicPatternType.Ran: self.random_lba,
            BasicPatternType.Mixed: self.random_lba
        }
        self.get_start_lba = self.calc_start_lba[self.pattern.pattern_type]
        self.cmd_generator = CommandGenerator(self.env, self.param)

    def get_basic_cmd_type(self, weight) -> eCMDType:
        while True:
            yield self.pattern.cmd_type

    def get_mixed_cmd_type(self, weight):
        while True:
            command = choices(tuple(self.pattern.cmd_type), weights=weight)
            yield command[0]

    def sequential_lba(self):
        return self._cmd_id * \
            self.pattern.chunk_size_bytes % self.pattern.range_bytes // self.sector_size

    def random_lba(self):
        max_offset = int(
            self.pattern.range_bytes //
            self.pattern.chunk_size_bytes)
        return randrange(0, max_offset) * \
            self.pattern.chunk_size_bytes // self.sector_size

    def dummy_lba(self):
        return 0xFFFFFFFFFFFFFFFF

    def custom_seq_lba(self):
        return_lba = self.pattern.start_lba
        self.pattern.start_lba += (self.pattern.chunk_size_bytes //
                                   self.sector_size)
        return return_lba

    def custom_ran_lba(self):
        max_offset = int(
            self.pattern.range_bytes //
            self.pattern.chunk_size_bytes)
        return self.pattern.start_lba + \
            (randrange(0, max_offset) * self.pattern.chunk_size_bytes // self.sector_size)

    def create_command(self):
        chunk_size = self.pattern.chunk_size_bytes

        weight = []
        if isinstance(self.pattern, MixedPattern):
            for cmd_type in self.pattern.cmd_type:
                if cmd_type == eCMDType.Read:
                    weight.append(self.pattern.read_percent)
                elif cmd_type == eCMDType.Write:
                    weight.append(self.pattern.write_percent)
                elif cmd_type == eCMDType.Trim:
                    weight.append(self.pattern.trim_percent)
            get_cmd_type = self.get_mixed_cmd_type
        else:
            get_cmd_type = self.get_basic_cmd_type

        cur_time = self.env.now
        time_offset = 0
        for idx in range(self.total_cmd_count):
            cmd_type = next(get_cmd_type(weight))
            min_offset = self.get_start_lba() * self.param.SECTOR_SIZE
            if CommandClassifier.is_write_cmd(cmd_type):
                command = self.cmd_generator.generate_write_cmd(
                    self._cmd_id,
                    chunk_size,
                    min_offset,
                    init_time=cur_time +
                    time_offset,
                    host_stream_id=0)
            else:
                command = self.cmd_generator.generate_cmd(
                    self._cmd_id,
                    cmd_type,
                    chunk_size,
                    min_offset,
                    init_time=cur_time +
                    time_offset)
            if idx != 0 and idx % self.qd == 0:
                time_offset += int(self.idle_time_ms * 1e6)

            yield command
            self._cmd_id += 1
