from product.general.modules.job_scheduler_class.js_queue import (MetaWriteQ,
                                                                  QFacade,
                                                                  StarvationQ,
                                                                  UrgentQ)


class StarvationManager:
    def __init__(self, q_facade: QFacade, vcd_manager):
        self.q_facade = q_facade
        self.vcd_manager = vcd_manager

    def update_vcd(self, queue: StarvationQ):
        ch, way = queue.ch, queue.way
        if isinstance(queue, UrgentQ):
            self.vcd_manager.update_urgentQ_starvation_count(
                ch, way, queue.starvation_count)
        elif isinstance(queue, MetaWriteQ):
            self.vcd_manager.update_metawriteQ_starvation_count(
                ch, way, queue.starvation_count)
        else:
            self.vcd_manager.update_normalQ_starvation_count(
                ch, way, queue.starvation_count)

    def clear_starvation(self, queue: StarvationQ):
        queue.clear_starvation()
        self.update_vcd(queue)

    def increase_starvation(self, queue: StarvationQ):
        queue.increase_starvation()
        self.update_vcd(queue)

    def update_starvation_state(self, data, skip_starvation_update: bool):
        if not data['tfirst']:
            return

        ch, way = data['channel'], data['way']
        targetQ = self.q_facade.get_insert_target_queue(data)

        clear_target = None
        increase_target = list()
        for cls, instance in self.q_facade.cls_to_instance_map.items():
            if isinstance(targetQ, cls):
                if isinstance(targetQ, StarvationQ):
                    assert clear_target is None
                    clear_target = instance[ch][way]
            elif not skip_starvation_update and isinstance(instance[ch][way], StarvationQ) and instance[ch][way]:
                # TODO: Urgent Q
                increase_target.append(instance[ch][way])

        if clear_target is not None:
            self.clear_starvation(clear_target)
        for target in increase_target:
            self.increase_starvation(target)
