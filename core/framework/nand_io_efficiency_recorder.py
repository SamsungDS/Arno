from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass

from core.framework.media_common import ChannelJobType


class NANDIOEffiRecorderFactory:
    @classmethod
    def get_instance(cls, channel_count):
        return NANDIOEffiRecorderNormal(channel_count)


class NANDIOEffiRecorder(ABC):
    def __init__(self, channel_count):
        self.channel_count = channel_count
        self.clear()

    def clear(self):
        self.io_time_sum = [0 for _ in range(self.channel_count)]
        self.parity_time_sum = [0 for _ in range(self.channel_count)]
        self.cmd_time_sum = [defaultdict(int)
                             for _ in range(self.channel_count)]

    def add_data_time(self, cur_time, ch, io_time, parity_time):
        self.io_time_sum[ch] += io_time
        self.parity_time_sum[ch] += parity_time

    def get_time_sum(self):
        io_time_sum = sum(self.io_time_sum)
        parity_time_sum = sum(self.parity_time_sum)
        cmd_time_sum = sum(sum(d.values()) for d in self.cmd_time_sum)
        return io_time_sum, parity_time_sum, cmd_time_sum

    def get_channel_job_type_effi(self):
        job_type_effi = defaultdict(float)
        job_type_time_sum = defaultdict(int)
        io_time_sum, parity_time_sum, cmd_time_sum = self.get_time_sum()
        for cur_cmd_time_sum in self.cmd_time_sum:
            for job_type, time_sum in cur_cmd_time_sum.items():
                job_type_time_sum[job_type] += time_sum

        for job_type, time in job_type_time_sum.items():
            job_type_effi[job_type] = time / \
                (io_time_sum + parity_time_sum + cmd_time_sum) * 100
        return job_type_effi

    @abstractmethod
    def add_cmd_time(
            self,
            cur_time,
            ch,
            channel_job_type: ChannelJobType,
            cmd_time):
        pass

    @abstractmethod
    def calculate_effi(self, *args, **kwargs):
        pass


class NANDIOEffiRecorderNormal(NANDIOEffiRecorder):
    def add_cmd_time(
            self,
            cur_time,
            ch,
            channel_job_type: ChannelJobType,
            cmd_time):
        self.cmd_time_sum[ch][channel_job_type] += cmd_time

    def calculate_effi(self, period):
        io_time_sum, parity_time_sum, cmd_time_sum = self.get_time_sum()
        io_time_avg = io_time_sum / len(self.io_time_sum)
        total_effi = io_time_avg / period * 100
        total_sum = (io_time_sum + parity_time_sum + cmd_time_sum)
        channel_only_effi = io_time_sum / total_sum * 100
        parity_only_effi = parity_time_sum / total_sum * 100
        job_type_effi = self.get_channel_job_type_effi()
        return total_effi, channel_only_effi, parity_only_effi, job_type_effi


@dataclass
class TimeInfo:
    start_time: float
    end_time: float
    job_type: ChannelJobType = None
