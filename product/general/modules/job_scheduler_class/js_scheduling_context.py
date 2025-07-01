from typing import Any, List

from core.framework.media_common import (NANDCMDType, is_data_cmd, is_din_cmd,
                                         is_dout_cmd, is_erase_cmd,
                                         is_read_cmd, is_resume_cmd,
                                         is_suspend_cmd, is_tprog_cmd,
                                         is_tr_cmd)
from product.general.modules.job_scheduler_class.js_cache_controller import \
    CacheController
from product.general.modules.job_scheduler_class.js_channel_arbiter import ChannelArbiter
from product.general.modules.job_scheduler_class.js_nand_busy_controller import \
    NANDBusyController
from product.general.modules.job_scheduler_class.js_nand_config import NANDConfig
from product.general.modules.job_scheduler_class.js_queue import QFacade, SchedulerQ
from product.general.modules.job_scheduler_class.js_queue_selecter import QueueSelecter
from product.general.modules.job_scheduler_class.js_starvation_manager import \
    StarvationManager
from product.general.modules.job_scheduler_class.js_way_preemption_handler import \
    WayPreemptionHandler


class tRRCManager:
    def __init__(self, nand_config: NANDConfig):
        self.trrc_bitmap = [[[False for _ in range(nand_config.plane_count)]
                             for _ in range(nand_config.way_count)]
                            for _ in range(nand_config.channel_count)]

    def update_bitmap(self, ch, way, plane, value):
        self.trrc_bitmap[ch][way][plane] = value

    def is_busy(self, data):
        ch, way = data['channel'], data['way']
        start_plane = data['target_plane_id'][0]
        end_plane = data['target_plane_id'][-1]

        return sum(self.trrc_bitmap[ch][way][start_plane:end_plane + 1]) != 0


class JSSchedulingContext:
    def __init__(self, env, param, vcd_manager, q_facade: QFacade):
        self.env = env
        self.param = param
        self.vcd_manager = vcd_manager
        nand_config = NANDConfig(
            channel_count=self.param.CHANNEL,
            way_count=self.param.WAY,
            plane_count=self.param.PLANE)
        self.support_cache_read_suspended_way: bool = False if 'QLC' in self.param.NAND_PRODUCT else True
        self.q_facade = q_facade
        self.queue_selecter = QueueSelecter(nand_config, q_facade)
        self.busy_checker = NANDBusyController(nand_config, vcd_manager)
        self.cache_controller = CacheController(
            nand_config, q_facade.queue_count_observer)
        self.channel_arbiter = ChannelArbiter(nand_config.channel_count)
        self.starvation_manager = StarvationManager(q_facade, vcd_manager)
        self.trrc_manager = tRRCManager(nand_config)
        self.way_preemption_handler = WayPreemptionHandler(
            nand_config, vcd_manager, self.busy_checker)
        self.scheduling_event = [self.env.event()
                                 for _ in range(self.param.CHANNEL)]
        if self.param.ENABLE_NAND_SUSPEND:
            self.tr_cmd_ready: callable = self.tr_cmd_ready_with_suspend
            self.din_cmd_ready: callable = self.din_cmd_ready_with_suspend
            self.erase_cmd_ready: callable = self.erase_cmd_ready_with_suspend
        else:
            self.tr_cmd_ready: callable = self.tr_cmd_ready_wo_suspend
            self.din_cmd_ready: callable = self.din_cmd_ready_wo_suspend
            self.erase_cmd_ready: callable = self.erase_cmd_ready_wo_suspend

    def start_tRRC(self, ch, way, plane):
        self.trrc_manager.update_bitmap(ch, way, plane, True)

    def end_tRRC(self, ch, way, plane):
        self.trrc_manager.update_bitmap(ch, way, plane, False)

    def wakeup(self, channel):
        self.scheduling_event[channel].succeed()
        self.scheduling_event[channel] = self.env.event()

    def tr_issue_available(self, data: dict[Any]) -> bool:
        ch, way, plane = data['channel'], data['way'], data['plane']
        is_urgent = data.get('urgent', False)

        is_suspendable = is_urgent and self.way_preemption_handler.is_suspendable(
            ch, way, plane, self.env.now)
        data['suspend_read'] = is_suspendable

        return is_suspendable

    def tr_cmd_ready_with_suspend(self, nand_busy_state, data):
        if self.trrc_manager.is_busy(data):
            return False

        ch, way = data['channel'], data['way']
        if self.way_preemption_handler.is_suspended(ch, way):
            is_urgent = data.get('urgent', False)
            suspended_state = self.way_preemption_handler.get_suspended_state(
                ch, way)
            is_suspend_limit = self.way_preemption_handler.is_suspend_limit(
                ch, way, suspended_state, self.env.now)
            if is_suspend_limit:
                self.queue_selecter.set_suspend_limit(ch, way)
            return not nand_busy_state and not is_suspend_limit and is_urgent
        else:
            return not nand_busy_state or self.tr_issue_available(data)

    def tr_cmd_ready_wo_suspend(self, nand_busy_state, data):
        return not (nand_busy_state or self.trrc_manager.is_busy(data))

    def dout_cmd_ready(self, nand_busy_state, latch_busy_state, data):
        return not latch_busy_state and (
            not nand_busy_state or self.cache_controller.dout_issue_available(data))

    def din_cmd_ready_with_suspend(
            self,
            nand_busy_state,
            latch_busy_state,
            data,
            queue: SchedulerQ):
        if self.way_preemption_handler.is_suspended(
                data['channel'], data['way']):
            return False
        return not latch_busy_state and (
            not nand_busy_state or self.cache_controller.din_issue_available(
                queue, data))

    def din_cmd_ready_wo_suspend(
            self,
            nand_busy_state,
            latch_busy_state,
            data,
            queue: SchedulerQ):
        return not latch_busy_state and (
            not nand_busy_state or self.cache_controller.din_issue_available(
                queue, data))

    def erase_cmd_ready_with_suspend(
            self,
            nand_busy_state,
            latch_busy_state,
            data) -> bool:
        if self.way_preemption_handler.is_suspended(
                data['channel'], data['way']):
            return False
        return not nand_busy_state and not latch_busy_state

    def erase_cmd_ready_wo_suspend(
            self,
            nand_busy_state,
            latch_busy_state,
            data) -> bool:
        return not nand_busy_state and not latch_busy_state

    def is_nand_ready(
            self,
            data,
            nand_busy_state,
            latch_busy_state,
            queue: SchedulerQ):
        nand_cmd_type = data['nand_cmd_type']
        if is_tr_cmd(nand_cmd_type):
            return self.tr_cmd_ready(nand_busy_state, data)
        elif is_dout_cmd(nand_cmd_type):
            return self.dout_cmd_ready(nand_busy_state, latch_busy_state, data)
        elif is_din_cmd(nand_cmd_type):
            return self.din_cmd_ready(
                nand_busy_state, latch_busy_state, data, queue)
        elif is_erase_cmd(nand_cmd_type):
            return self.erase_cmd_ready(
                nand_busy_state, latch_busy_state, data)

        return not nand_busy_state and not latch_busy_state

    def select_nand_ready_task(self, ch):
        candidate_list = []
        for way in range(self.param.WAY):
            curQ_list: List[SchedulerQ] = self.queue_selecter.select_queue(
                ch, way)
            if not curQ_list:
                continue

            for curQ in curQ_list:
                try:
                    data = curQ.get_front()
                except IndexError:
                    continue

                nand_busy_state = self.busy_checker.get_busy_state(data)
                latch_busy_state = self.busy_checker.get_busy_state(data, True)

                if self.is_nand_ready(
                        data, nand_busy_state, latch_busy_state, curQ):
                    candidate_list.append(data)

        return candidate_list

    def ask_channel_arbiter(self, prev_candidate_list):
        candidate_list = []
        for candidate in prev_candidate_list:
            nand_cmd_type = candidate['nand_cmd_type']
            ch = candidate['channel']
            if is_data_cmd(nand_cmd_type) and not self.channel_arbiter.ask_available(
                    ch, candidate['buffered_unit_id']):
                continue

            candidate_list.append(candidate)
        return candidate_list

    def select_old_task(self, candidate_list):
        data = candidate_list[0]
        for candidate in candidate_list[1:]:
            if candidate['time_stamp'] < data['time_stamp']:
                data = candidate
        return data

    def delete_duplicated_suspend(self,
                                  data: dict[Any],
                                  candidate_list: list[dict[Any]]) -> None:
        way = data['way']
        if sum(d.get('suspend_read', False)
               for d in candidate_list if d['way'] == way) > 1:
            for candidate in candidate_list:
                if candidate is not data and candidate['way'] == way:
                    del candidate['suspend_read']

    def is_cache_read(self, data):
        return is_read_cmd(
            data['nand_cmd_type']) and data['cache_read_ctxt'].is_cache_read

    def select_task(self, ch):
        candidate_list = self.select_nand_ready_task(ch)
        if not candidate_list:
            return None

        candidate_list = self.ask_channel_arbiter(candidate_list)
        if not candidate_list:
            return None

        data = self.select_old_task(candidate_list)
        nand_cmd_type: NANDCMDType = data['nand_cmd_type']

        skip_starvation_update = False
        if self.param.ENABLE_NAND_SUSPEND:
            way = data['way']
            is_suspended_way = self.way_preemption_handler.is_suspended(
                ch, way)
            skip_starvation_update = is_suspended_way
            if data.get('suspend_read', False):
                self.delete_duplicated_suspend(data, candidate_list)
                self.way_preemption_handler.set_suspended_state(ch, way)
                skip_starvation_update = True
            if is_tprog_cmd(nand_cmd_type) or is_erase_cmd(nand_cmd_type):
                self.way_preemption_handler.set_write_type_nand_job_id(
                    ch, way, data['nand_job_id'])
            elif is_resume_cmd(nand_cmd_type):
                self.way_preemption_handler.clear_suspended_state(ch, way)
                self.way_preemption_handler.set_suspended_time(
                    ch, way, self.env.now)
                data['tfirst'] = True
            elif self.is_cache_read(data) and is_suspended_way:
                if not self.support_cache_read_suspended_way or self.way_preemption_handler.is_erase_suspended(
                        ch, way):
                    self.q_facade.cancel_cache_read(data)
                    data['cache_read_ctxt'].is_cache_read = False

        self.way_preemption_handler.set_way_state(data)
        self.channel_arbiter.update(data)
        self.cache_controller.selected(data)
        self.queue_selecter.selected(data)
        self.busy_checker.set_nand_busy(data, is_data_cmd(nand_cmd_type))
        self.starvation_manager.update_starvation_state(
            data, skip_starvation_update)
        return data

    def done(self, data):
        ch, way = data['channel'], data['way']
        nand_cmd_type: NANDCMDType = data['nand_cmd_type']
        assert not is_suspend_cmd(nand_cmd_type)

        set_ready: bool = True
        if data['tlast']:
            if is_tprog_cmd(nand_cmd_type) or is_erase_cmd(nand_cmd_type):
                if self.way_preemption_handler.is_suspended(ch, way):
                    self.way_preemption_handler.clear_suspended_state(ch, way)
                    set_ready = False
                else:
                    self.way_preemption_handler.clear_way_state(data)
                self.way_preemption_handler.clear_write_type_id(ch, way)
                self.way_preemption_handler.clear_suspended_info(ch, way)
                self.queue_selecter.clear_suspend_limit(ch, way)
            else:
                self.way_preemption_handler.clear_way_state(data)

        if set_ready:
            self.busy_checker.set_nand_ready(data, is_data_cmd(nand_cmd_type))

        self.cache_controller.done(data)
        self.wakeup(data['channel'])

    def handle_suspend_done(self, data: dict[Any], nand_job_id_allocator) -> bool:
        ch, way = data['channel'], data['way']
        if self.way_preemption_handler.is_suspend_miss(ch, way):
            self.way_preemption_handler.set_way_state_to_read(data, False)
            return None
        else:
            self.way_preemption_handler.set_way_state_to_read(data, True)
            resume_nand_job_id = self.way_preemption_handler.get_suspended_nand_job_id(ch, way)
            resume_data = nand_job_id_allocator.read(resume_nand_job_id)
            resume_data['nand_cmd_type'] = (
                NANDCMDType.PGMResume if is_tprog_cmd(
                    resume_data['nand_cmd_type']) else NANDCMDType.ERSResume)
            return resume_data

    def set_suspend_start_info(self, data: dict[Any]) -> None:
        ch, way = data['channel'], data['way']
        self.way_preemption_handler.set_suspend_start_time(
            ch, way, self.env.now)
        self.way_preemption_handler.increase_suspend_count(ch, way)
