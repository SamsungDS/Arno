import os
from dataclasses import dataclass
from typing import Optional

from core.framework.common import eCMDType


@dataclass
class CommandItem:
    process_name: Optional[str] = 'None'
    command_type: Optional[eCMDType] = None
    command_size_in_bytes: Optional[int] = None
    start_lpn: Optional[int] = None
    issue_time_ns: Optional[int] = None
    completion_time_ns: Optional[int] = None
    latency_ns: Optional[int] = None
    cache_hit_result: Optional[str] = None
    queue_depth: Optional[int] = None
    unique_id: Optional[int] = None

    def get_size(self):
        return self.command_size_in_bytes

    def get_latency(self):
        return self.latency_ns

    def get_type(self):
        return self.command_type


class CommandRecorder:
    def __init__(self, tc_count):
        self.command_log = [None for _ in range(tc_count)]
        self.command_queue_depth = 0

    def set_command_process_name(self, cmd_id, name):
        assert self.command_log[cmd_id] is not None
        self.command_log[cmd_id].process_name = name

    def make_command_log(self, cmd_id, process_name):
        self.command_log[cmd_id] = CommandItem(process_name)

    def update_issued_command_log(
            self,
            cmd_id,
            cmd_type,
            cmd_size,
            start_lpn,
            issue_time):
        if self.command_log[cmd_id] is None:
            self.command_log[cmd_id] = CommandItem()

        self.command_log[cmd_id].command_type = cmd_type
        self.command_log[cmd_id].command_size_in_bytes = cmd_size
        self.command_log[cmd_id].start_lpn = start_lpn
        self.command_log[cmd_id].issue_time_ns = int(issue_time)
        self.command_log[cmd_id].queue_depth = self.command_queue_depth
        self.command_queue_depth += 1

    def update_done_command_log(
            self,
            cmd_id,
            completion_time,
            cache_hit_result):
        assert self.command_log[cmd_id] is not None, f'CMD ID[{cmd_id:d}] not issued but done happened'
        completion_time = int(completion_time)
        self.command_queue_depth -= 1
        self.command_log[cmd_id].completion_time_ns = completion_time
        self.command_log[cmd_id].latency_ns = completion_time - \
            self.command_log[cmd_id].issue_time_ns
        self.command_log[cmd_id].cache_hit_result = cache_hit_result
        self.command_log[cmd_id].unique_id = cmd_id

    def get_command_item(self, cmd_id):
        return self.command_log[cmd_id]

    def delete(self, cmd_id):
        self.command_log[cmd_id] = None


class QoSRecorder:
    def __init__(self):
        qos_cmd = ['Write', 'Read']
        self.qos_log = {key: [] for key in qos_cmd}
        self.qos_candidates = None

    def set_qos_candidates(self, qos_list):
        self.qos_candidates = qos_list

    def is_qos_candidates_set(self):
        return self.qos_candidates is not None

    def record_qos(self, cmd_type, latency_ns):
        latency = latency_ns / 1e3
        if cmd_type == eCMDType.Write:
            self.qos_log['Write'].append(latency)
        elif cmd_type == eCMDType.Read:
            self.qos_log['Read'].append(latency)

    def get_qos(self, cmd_type):
        qos_list = list()
        self.qos_log[cmd_type] = sorted(self.qos_log[cmd_type])
        for qos_idx in self.qos_candidates:
            if isinstance(qos_idx, float):
                qos_idx = int(str(qos_idx).replace('.', ''))
                qos_digit = 10**len(str(qos_idx))
            else:
                qos_digit = 10**2
            if qos_idx <= len(self.qos_log[cmd_type]):
                qos_idx = int((qos_idx / qos_digit) *
                              len(self.qos_log[cmd_type]))
                qos_list.append(self.qos_log[cmd_type][qos_idx - 1])
            else:
                qos_list.append('-')
        return qos_list

    def get_latency_report(self, cmd_type):
        if self.qos_log[cmd_type]:
            return f'{min(self.qos_log[cmd_type]):.2f}/{sum(self.qos_log[cmd_type])/len(self.qos_log[cmd_type]):.2f}/{max(self.qos_log[cmd_type]):.2f}'
        else:
            return '-'

    def print_qos(self):
        print('-' * 20 + 'QoS' + '-' * 20)
        print(f" ** QoS Candidates: {self.qos_candidates}")
        print(f" ** Read QoS(us): {self.get_qos('Read')}")
        print(f" ** Write QoS(us): {self.get_qos('Write')}")
        print(
            f" ** Read Latency(us)(Min/Avg/Max): {self.get_latency_report('Read')}")
        print(
            f" ** Write Latency(us)(Min/Avg/Max): {self.get_latency_report('Write')}")


class CommandRecordFileGenerator:
    def __init__(self, output_prefix):
        self.cmd_record_file_name = self.generate_file_name(output_prefix)
        self.file = None

    def generate_file_name(self, prefix):
        return os.path.join('.', f'{prefix}_command_record.csv')

    def open_file(self):
        self.file = open(self.cmd_record_file_name, 'w')
        self.write_count = 0
        self.file_flush_line_threshold = 1000  # to reduce file open/close overhead
        self.generate_file_header()

    def generate_file_header(self):
        line = ''
        for header_name in CommandItem().__dict__.keys():
            line += f'{header_name},'

        self.write(line[:-1])

    def write(self, line):
        if self.file is None:
            self.open_file()

        self.file.write(line + '\n')
        self.write_count += 1
        if self.write_count == self.file_flush_line_threshold:
            self.file.close()
            self.file = open(self.cmd_record_file_name, 'a')
            self.write_count = 0

    def close_file(self):
        if self.file is not None:
            self.file.close()

    def record(self, cmd_item: CommandItem):
        line = ''
        for value in cmd_item.__dict__.values():
            try:
                line += f'{value.name},'
            except AttributeError:
                line += f'{value},'

        self.write(line[:-1])
