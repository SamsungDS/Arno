from product.general.modules.job_scheduler_class.js_nand_config import \
    NANDConfig
from product.general.modules.job_scheduler_class.js_queue import (QFacade,
                                                                  ResumeQ,
                                                                  SchedulerQ,
                                                                  StarvationQ)


class SelectedQContext(set):
    def __init__(self):
        super().__init__()
        assert SchedulerQ._hash_counter != 0, 'init QFacade Before initiating SelectedQContext !!'
        self.added_count = [0 for _ in range(SchedulerQ._hash_counter)]

    def add(self, queue: SchedulerQ):
        super().add(queue)
        self.added_count[queue.hash] += 1

    def remove(self, queue: SchedulerQ):
        assert self.added_count[queue.hash] > 0
        self.added_count[queue.hash] -= 1
        if self.added_count[queue.hash] == 0:
            super().remove(queue)


class QueueSelecter:
    def __init__(self, nand_config: NANDConfig, q_facade: QFacade):
        self.q_facade = q_facade
        self.plane_count = nand_config.plane_count
        self.selected_q = [[SelectedQContext() for _ in range(
            nand_config.way_count)] for _ in range(nand_config.channel_count)]
        self.suspend_limit: list[list[bool]] = [[False for _ in range(
            nand_config.way_count)] for _ in range(nand_config.channel_count)]

    def is_starvation_state(self, ch, way):
        return self.is_urgentQ_starvation(
            ch,
            way) or self.is_meta_writeQ_starvation(
            ch,
            way) or self.is_normalQ_starvation(
            ch,
            way)

    def is_urgentQ_starvation(self, ch, way):
        return self.q_facade.urgent_queue[ch][way].starvation_state()

    def is_meta_writeQ_starvation(self, ch, way):
        return self.q_facade.meta_write_queue[ch][way].starvation_state()

    def is_normalQ_starvation(self, ch, way):
        return self.q_facade.normal_queue[ch][way].starvation_state()

    def select_resume_queue(self, ch: int, way: int) -> ResumeQ | None:
        if self.q_facade.get_all_urgent_count(
                ch, way) == 0 or self.suspend_limit[ch][way]:
            return self.q_facade.resume_queue[ch][way]

    def selected(self, data):
        targetQ = self.q_facade.get_insert_target_queue(data)
        self.q_facade.popleft(targetQ)

        if data['tfirst'] and data['tlast']:  # Erase or Resume
            return

        ch, way = data['channel'], data['way']
        if data['tfirst']:
            self.selected_q[ch][way].add(targetQ)
        elif data['tlast']:
            self.selected_q[ch][way].remove(targetQ)

    def select_queue(self, ch, way):
        if self.q_facade.chip_task_count[ch][way] == 0:
            return None

        if self.selected_q[ch][way]:
            return list(self.selected_q[ch][way])

        for instance in self.q_facade.cls_to_instance_map.values():
            if isinstance(
                    instance[ch][way],
                    StarvationQ) and instance[ch][way].starvation_state():
                return [instance[ch][way]]

        if resumeQ := self.select_resume_queue(ch, way):
            return [resumeQ]

        for instance in list(self.q_facade.cls_to_instance_map.values())[0:]:
            if instance[ch][way]:
                return [instance[ch][way]]

    def set_suspend_limit(self, ch: int, way: int) -> None:
        self.suspend_limit[ch][way] = True

    def clear_suspend_limit(self, ch: int, way: int) -> None:
        self.suspend_limit[ch][way] = False
