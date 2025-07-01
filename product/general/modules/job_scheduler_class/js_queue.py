from collections import deque

from core.framework.media_common import (is_dout_cmd, is_read_cmd,
                                         is_resume_cmd, is_tr_cmd)
from product.general.config.storage_parameters import Parameter


class SchedulerQ:
    _hash_counter = 0

    def __init__(self, ch, way):
        self.deq = deque()
        self.ch = ch
        self.way = way
        self.hash = SchedulerQ._hash_counter
        SchedulerQ._hash_counter += 1

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(len={len(self.deq)})'

    def __hash__(self):
        return self.hash

    def __len__(self):
        return len(self.deq)

    def get_front(self):
        return self.deq[0]

    def popleft(self):
        data = self.deq.popleft()
        return data

    def append(self, data):
        self.deq.append(data)

    def insert(self, idx, data):
        self.deq.insert(idx, data)

    def remove(self, data):
        self.deq.remove(data)

    def clear(self):
        self.deq.clear()


class StarvationQ(SchedulerQ):
    def __init__(self, ch, way, starvation_threshold):
        super().__init__(ch, way)
        self.starvation_count = 0
        self.starvation_threshold = starvation_threshold

    def starvation_state(self):
        return self.starvation_count >= self.starvation_threshold

    def increase_starvation(self):
        self.starvation_count += 1

    def clear_starvation(self):
        self.starvation_count = 0


class ResumeQ(SchedulerQ):
    def __init__(self, ch, way):
        super().__init__(ch, way)

    def append(self, data):
        assert not self.deq, 'only one resume allowed in way'
        self.deq.append(data)


class UrgentQ(StarvationQ):
    pass


class MetaWriteQ(StarvationQ):
    pass


class NormalQ(StarvationQ):
    pass


class QCountObserver:
    def __init__(self, param: Parameter, vcd_manager):
        self.param = param
        self.vcd_manager = vcd_manager
        self.queue_count_wo_normalQ = [
            [0 for _ in range(param.WAY)] for _ in range(param.CHANNEL)]
        self.queue_count_wo_urgentQ = [
            [0 for _ in range(param.WAY)] for _ in range(param.CHANNEL)]
        self.queue_count_in_all_urgentQ = [
            [0 for _ in range(param.WAY)] for _ in range(param.CHANNEL)]
        self.queue_count = None

    def update_wo_queue_count(self, queue: SchedulerQ, value):
        ch, way = queue.ch, queue.way
        if not isinstance(queue, UrgentQ):
            self.queue_count_wo_urgentQ[ch][way] += value
        if not isinstance(queue, NormalQ):
            self.queue_count_wo_normalQ[ch][way] += value

    def update_urgent_q_count(self, queue: SchedulerQ, value: int) -> None:
        ch, way = queue.ch, queue.way
        if isinstance(queue, UrgentQ):
            self.queue_count_in_all_urgentQ[ch][way] += value

    def update_vcd(self, queue):
        ch, way = queue.ch, queue.way
        self.vcd_manager.update_media_scheduling_queue(
            self.queue_count[ch][way][queue.hash], ch, way, queue.__class__.__name__)

    def appended(self, queue: SchedulerQ):
        if self.queue_count is None:
            self.queue_count = [[[0 for _ in range(SchedulerQ._hash_counter)] for _ in range(
                self.param.WAY)] for _ in range(self.param.CHANNEL)]

        ch, way = queue.ch, queue.way
        self.queue_count[ch][way][queue.hash] += 1
        self.update_vcd(queue)
        self.update_wo_queue_count(queue, +1)
        self.update_urgent_q_count(queue, 1)

    def popped(self, queue: SchedulerQ):
        ch, way = queue.ch, queue.way
        self.queue_count[ch][way][queue.hash] -= 1
        self.update_vcd(queue)
        self.update_wo_queue_count(queue, -1)
        self.update_urgent_q_count(queue, -1)

    def get_queue_count_wo_Q(self, queue: SchedulerQ):
        ch, way = queue.ch, queue.way
        if isinstance(queue, UrgentQ):
            return self.queue_count_wo_urgentQ[ch][way]
        else:
            return self.queue_count_wo_normalQ[ch][way]

    def get_all_urgent_queue_count(self, ch: int, way: int) -> int:
        return self.queue_count_in_all_urgentQ[ch][way]


class CacheTRController:
    def __init__(self, ch, way, queue_count_observer: QCountObserver):
        self.queue_count_observer = queue_count_observer
        self.latest_tr_data = [[deque() for _ in range(way)]
                               for _ in range(ch)]

    def ch_way_getter(self, data):
        return data['channel'], data['way']

    def update(self, data):
        if is_tr_cmd(data['nand_cmd_type']):
            ch, way = self.ch_way_getter(data)
            self.latest_tr_data[ch][way].append(data)

    def popped(self, data):
        if is_dout_cmd(data['nand_cmd_type']) and data['dfirst']:
            ch, way = self.ch_way_getter(data)
            self.latest_tr_data[ch][way].popleft()

    def need_to_try_reschedule(self, queue: UrgentQ, data):
        return queue and is_tr_cmd(data['nand_cmd_type'])

    def is_cache_tr_available(self, queue: SchedulerQ, data):
        ch, way = self.ch_way_getter(data)
        if (not self.latest_tr_data[ch][way] or self.queue_count_observer.get_queue_count_wo_Q(
                queue) != 0 or not data['urgent']):
            return False

        latest_tr_data = self.latest_tr_data[ch][way][-1]
        nand_cmd_type = data['nand_cmd_type']
        cache_tr_available = True
        cache_tr_available &= latest_tr_data['nand_cmd_type'] == nand_cmd_type
        cache_tr_available &= latest_tr_data['cell_type'] == data['cell_type']
        cache_tr_available &= latest_tr_data['plane'] == data['plane']
        return cache_tr_available

    def tr_rescheduling_available(self, data):
        ch, way = self.ch_way_getter(data)
        return self.latest_tr_data[ch][way][-1]['cache_read_ctxt'].is_cache_read

    def reschedule(self, queue: UrgentQ, data):
        scheduling_queue_len = len(queue)
        deq = queue.deq
        last_buffered_unit_id = deq[-1]['buffered_unit_id']

        for i in range(scheduling_queue_len - 1, -1, -1):
            cur_data = deq[i]
            if is_tr_cmd(cur_data['nand_cmd_type']
                         ) or cur_data['buffered_unit_id'] != last_buffered_unit_id:
                queue.insert(i + 1, data)
                return

        queue.insert(0, data)


class QFacade:
    def __init__(self, param, vcd_manager):
        self.param = param
        self.queue_count_observer = QCountObserver(param, vcd_manager)

        STARVATION_THRESHOLD = 8
        self.urgent_queue = [[UrgentQ(ch, way, STARVATION_THRESHOLD) for way in range(
            self.param.WAY)] for ch in range(self.param.CHANNEL)]
        self.meta_write_queue = [[MetaWriteQ(ch, way, STARVATION_THRESHOLD) for way in range(
            self.param.WAY)] for ch in range(self.param.CHANNEL)]
        self.normal_queue = [[NormalQ(ch, way, STARVATION_THRESHOLD) for way in range(
            self.param.WAY)] for ch in range(self.param.CHANNEL)]
        self.resume_queue: list[list[ResumeQ]] = [[ResumeQ(ch, way) for way in range(
            self.param.WAY)] for ch in range(self.param.CHANNEL)]
        self.cls_to_instance_map = {UrgentQ: self.urgent_queue,
                                    MetaWriteQ: self.meta_write_queue,
                                    NormalQ: self.normal_queue,
                                    ResumeQ: self.resume_queue}

        self.cache_tr_controller = CacheTRController(
            self.param.CHANNEL, self.param.WAY, self.queue_count_observer)
        self.ch_task_count = [0 for _ in range(self.param.CHANNEL)]
        self.chip_task_count = [
            [0 for _ in range(self.param.WAY)] for _ in range(self.param.CHANNEL)]

    def get_insert_target_queue(self, data):
        nand_cmd_type = data['nand_cmd_type']
        user = data['user']
        ch = data['channel']
        way = data['way']
        if is_read_cmd(nand_cmd_type):
            is_urgent = data['urgent']
            if is_urgent:
                return self.urgent_queue[ch][way]
            else:
                return self.normal_queue[ch][way]
        elif is_resume_cmd(nand_cmd_type):
            return self.resume_queue[ch][way]
        elif user == 'ma':
            return self.meta_write_queue[ch][way]
        else:
            return self.normal_queue[ch][way]

    def is_urgent_type_queue(self, queue: SchedulerQ):
        return isinstance(queue, UrgentQ)

    def update_task_count(self, queue, value):
        ch, way = queue.ch, queue.way
        self.ch_task_count[ch] += value
        self.chip_task_count[ch][way] += value

    def add_task(self, queue: SchedulerQ, data):
        queue.append(data)

    def add_tr_task(self, queue: SchedulerQ, data):
        if (not self.param.ENABLE_NAND_CACHE_READ or not self.cache_tr_controller.need_to_try_reschedule(
                queue, data) or not self.cache_tr_controller.is_cache_tr_available(queue, data)):
            queue.append(data)
            self.cache_tr_controller.update(data)
            return

        data['cache_read_ctxt'].is_cache_read = True
        if not self.cache_tr_controller.tr_rescheduling_available(data):
            queue.append(data)
        else:
            self.cache_tr_controller.reschedule(queue, data)
        self.cache_tr_controller.update(data)

    def add(self, data):
        queue: SchedulerQ = self.get_insert_target_queue(data)

        if is_tr_cmd(data['nand_cmd_type']):
            self.add_tr_task(queue, data)
        else:
            self.add_task(queue, data)
        self.queue_count_observer.appended(queue)
        self.update_task_count(queue, 1)

    def popleft(self, queue: SchedulerQ):
        data = queue.popleft()
        self.cache_tr_controller.popped(data)
        self.queue_count_observer.popped(queue)
        self.update_task_count(queue, -1)
        return data

    def get_all_urgent_count(self, ch: int, way: int) -> int:
        return self.queue_count_observer.get_all_urgent_queue_count(ch, way)

    def cancel_cache_read(self, data):
        queue: UrgentQ = self.get_insert_target_queue(data)
        assert isinstance(queue, UrgentQ) and data is queue.deq[0]

        next_data = queue.deq[1]
        if is_tr_cmd(
                data['nand_cmd_type']) and is_tr_cmd(
                next_data['nand_cmd_type']):
            cache_read_cancel_buffered_unit_id = next_data['buffered_unit_id']
            for idx in range(2, len(queue)):
                if is_tr_cmd(
                        queue.deq[idx]['nand_cmd_type']) or queue.deq[idx]['buffered_unit_id'] == cache_read_cancel_buffered_unit_id:
                    queue.insert(idx, next_data)
                    break
            queue.remove(next_data)
