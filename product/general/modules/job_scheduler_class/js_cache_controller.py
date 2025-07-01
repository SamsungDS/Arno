from collections import deque

from core.framework.media_common import (NANDCMDType, is_din_cmd, is_dout_cmd,
                                         is_read_cmd, is_tprog_cmd, is_tr_cmd)
from product.general.modules.job_scheduler_class.js_nand_config import NANDConfig
from product.general.modules.job_scheduler_class.js_queue import (QCountObserver,
                                                                  SchedulerQ)


class CacheController:
    def __init__(
            self,
            nand_config: NANDConfig,
            queue_count_observer: QCountObserver):
        self.was_cache_program = [[False for _ in range(
            nand_config.way_count)] for _ in range(nand_config.channel_count)]
        self.cache_tr_done_buffered_unit_id = [[deque() for _ in range(
            nand_config.way_count)] for _ in range(nand_config.channel_count)]
        self.queue_count_observer = queue_count_observer

    def ch_way_getter(self, data):
        return data['channel'], data['way']

    def dout_issue_available(self, data):
        if data['cache_read_ctxt'].is_cache_read:
            ch, way = self.ch_way_getter(data)
            buffered_unit_id = data['buffered_unit_id']
            try:
                return buffered_unit_id == self.cache_tr_done_buffered_unit_id[ch][way][0]
            except IndexError:
                return False

    def din_issue_available(self, queue: SchedulerQ, data):
        if data['nand_cmd_type'] != NANDCMDType.Din_LSB:
            return False

        ch, way = self.ch_way_getter(data)
        if data['tfirst']:
            return self.queue_count_observer.get_queue_count_wo_Q(
                queue) == 0 and self.was_cache_program[ch][way]
        else:
            return self.was_cache_program[ch][way]

    def selected(self, data):
        nand_cmd_type = data['nand_cmd_type']
        ch, way = self.ch_way_getter(data)
        if is_din_cmd(nand_cmd_type):
            if data['tfirst'] and self.queue_count_observer.queue_count_wo_normalQ[ch][way] != 0:
                data['cache_program_ctxt'].is_cache_program = False
        elif is_tprog_cmd(nand_cmd_type):
            self.was_cache_program[ch][way] = data['cache_program_ctxt'].is_cache_program

    def done(self, data):
        nand_cmd_type: NANDCMDType = data['nand_cmd_type']
        if is_read_cmd(
                nand_cmd_type) and data['cache_read_ctxt'].is_cache_read:
            ch, way = self.ch_way_getter(data)
            buffered_unit_id = data['buffered_unit_id']
            if is_tr_cmd(nand_cmd_type):
                self.cache_tr_done_buffered_unit_id[ch][way].append(buffered_unit_id)
            elif is_dout_cmd(nand_cmd_type) and data['dlast']:
                assert self.cache_tr_done_buffered_unit_id[ch][way][0] == buffered_unit_id
                self.cache_tr_done_buffered_unit_id[ch][way].popleft()
