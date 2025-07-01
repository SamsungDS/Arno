from collections import deque
from inspect import isgeneratorfunction
from itertools import cycle

import simpy

from core.backbone.bus import BusWaitingQ
from core.backbone.power_manager import PowerManager
from core.framework.analyzer import Analyzer
from core.framework.common import ProductArgs, QFetchType
from core.framework.latency_logger import LatencyLogger
from core.framework.submodule_event import SubmoduleEvent


class SubmoduleQ(deque):
    def __init__(self, _id):
        super().__init__()
        self.id = _id
        self.is_locked = False

    def lock(self):
        self.is_locked = True

    def unlock(self):
        self.is_locked = False


class SubmoduleInfo:
    @classmethod
    def generate_submodule_name(cls, s_id, func):
        if s_id == -1:
            return func.__name__
        else:
            return f'{func.__name__}_{s_id}'

    def __init__(self, env, ip_name, s_id, func, feature_id,
                 q_fetch_type, q_count=1, user_queue=None, is_dummy=False):
        self.ip_name = ip_name
        self.s_id = s_id
        self.func = func
        self.name = SubmoduleInfo.generate_submodule_name(s_id, func)
        self.latency_log = 0
        self.consumed_time = 0
        self.feature_id = feature_id

        if is_dummy:
            return

        self.env = env
        self.queue_fetch_type = q_fetch_type
        self.queue_count = q_count
        if self.queue_fetch_type == QFetchType.FIFO:
            assert q_count == 1, 'if you want to use several Q, change queue fetch type'

        self.queue = None
        if user_queue is not None:
            assert isinstance(user_queue, BusWaitingQ)
            self.queue = user_queue
            self.fetch_queue = self.fetch_queue_from_bus
            self.job_exist = self.job_exist_from_bus
            self.wait = self.wait_from_bus
            self.reset_wait_event = self.reset_wait_event_from_bus
            self.pop_queue = self.pop_queue_from_bus
        else:
            self.wakeup = SubmoduleEvent(self.env)
            if q_fetch_type == QFetchType.FIFO:
                self.fetch_queue = self.fetch_queue_from_submodule_fifo
            elif q_fetch_type == QFetchType.RoundRobin:
                self.fetch_queue = self.fetch_queue_from_submodule_rr
            elif q_fetch_type == QFetchType.Priority:
                self.fetch_queue = self.fetch_queue_from_submodule_priority

            self.job_exist = self.job_exist_from_submodule
            self.wait = self.wait_from_submodule
            self.reset_wait_event = self.reset_wait_event_from_submodule
            self.pop_queue = self.pop_queue_from_submodule

        self.generate()

    def generate(self):
        if self.queue is None:
            self.queue = [SubmoduleQ(i) for i in range(self.queue_count)]
            if self.queue_fetch_type == QFetchType.RoundRobin:
                self.rr_queue = cycle(self.queue)

        self.queue_job_count = 0
        self.is_latency_recorded = 0
        self.submodule_run_count = 0
        self.job_done_success_flag = 1
        self.cancel_flag = 0

    def reset_wait_event_from_bus(self):
        self.queue.dst_event.reset()

    def reset_wait_event_from_submodule(self):
        self.wakeup.reset()

    def wait_from_bus(self):
        return self.queue.dst_event.wait()

    def wait_from_submodule(self):
        return self.wakeup.wait()

    def job_exist_from_bus(self):
        return self.queue.dst_queue

    def job_exist_from_submodule(self):
        return self.queue_job_count

    def fetch_queue_from_bus(self):
        return self.queue.dst_queue[0], 0

    def fetch_queue_from_submodule_fifo(self):
        queue: SubmoduleQ = self.queue[0]
        if queue and not queue.is_locked:
            return queue[0], 0
        return None, None

    def fetch_queue_from_submodule_rr(self):
        for _ in range(self.queue_count):
            current_queue = next(self.rr_queue)
            if current_queue and not current_queue.is_locked:
                return current_queue[0], current_queue.id

        return None, None

    def fetch_queue_from_submodule_priority(self):
        for q_id, queue in enumerate(self.queue):
            if queue and not queue.is_locked:
                return queue[0], q_id
        return None, None

    def pop_queue_from_bus(self, q_id=None):
        self.queue.dst_queue.popleft()

    def pop_queue_from_submodule(self, q_id):
        self.queue[q_id].popleft()
        self.queue_job_count -= 1


class SubModule:
    def __init__(
            self,
            ip_name,
            product_args: ProductArgs,
            s_id,
            func,
            feature_id=0,
            q_fetch_type=QFetchType.FIFO,
            q_count=1,
            user_queue=None,
            is_dummy=False):
        product_args.set_args_to_class_instance(self)
        self.is_interrupt = False
        self.submodule_info = SubmoduleInfo(
            self.env,
            ip_name,
            s_id,
            func,
            feature_id,
            q_fetch_type,
            q_count,
            user_queue,
            is_dummy=is_dummy)
        self.analyzer = Analyzer()
        if any(
            (self.param.ENABLE_POWER,
             self.param.ENABLE_VCD,
             self.param.RECORD_SUBMODULE_UTILIZATION,
             self.param.ENABLE_SUBMODULE_WAKEUP_VCD,
             self.param.ENABLE_LATENCY_LOGGER)):
            self.power_manager = PowerManager()
            self.power_manager.add_sub_module(
                ip_name, self.submodule_info.name, feature_id)
            self.latency_logger = LatencyLogger()
        else:
            self.process = self.process_fast_sim
            self.activate_feature = self.activate_feature_fast_sim
            self.deactivate_feature = self.deactivate_feature_fast_sim

        if not is_dummy:
            self.process_handle = self.env.process(self.process(s_id, func))

    def __repr__(self):
        return self.submodule_info.name

    def record_utilization(self, time_value):
        try:
            self.submodule_info.consumed_time += time_value
        except AttributeError:
            pass

    def reset_utilization(self):
        self.submodule_info.consumed_time = 0

    def record_vcd_log(self):
        self.submodule_info.submodule_run_count += 1
        self.vcd_manager.record_log(
            self.submodule_info.submodule_run_count,
            'subModuleWakeup',
            self.submodule_info.name)

    def activate_feature(
            self,
            feature_id=None,
            runtime_latency=-1,
            runtime_active_power=-1,
            auto_deactivate=True) -> bool:
        if feature_id is None:
            feature_id = self.submodule_info.feature_id
        if runtime_latency == -1:  # No User Input
            runtime_latency = self.feature.get_latency(feature_id)

        if self.param.ENABLE_POWER:
            yield from self.power_manager.activate_feature(self.submodule_info.ip_name, self.submodule_info.name, feature_id, runtime_active_power)

        result = True
        yield self.env.timeout(runtime_latency)
        if self.is_interrupt:
            result = False
            self.is_interrupt = False

        if self.param.ENABLE_POWER:
            if auto_deactivate:
                yield from self.power_manager.deactivate_feature(self.submodule_info.ip_name, self.submodule_info.name, feature_id)

        if self.param.RECORD_SUBMODULE_UTILIZATION and self.analyzer.is_sustained_perf_measure_state:
            self.record_utilization(runtime_latency)
        if self.param.ENABLE_VCD and self.param.ENABLE_SUBMODULE_WAKEUP_VCD:
            self.record_vcd_log()

        return result

    def deactivate_feature(self, feature_id=None):
        if feature_id is None:
            feature_id = self.submodule_info.feature_id
        self.power_manager.deactivate_feature(
            self.submodule_info.ip_name,
            self.submodule_info.name,
            feature_id)

    def process_cancel_available(self, q_id):
        for queue in self.submodule_info.queue:
            if q_id != queue.id and queue and not queue.is_locked:
                return False
        return True

    def wakeup(self, packet, q_id=0, description='SQ'):
        if packet is not None:
            self.submodule_info.queue[q_id].append(packet)
            self.submodule_info.queue_job_count += 1
        self.submodule_info.wakeup.trigger()

    def init_submodule_and_get_packet(self):
        submodule_info: SubmoduleInfo = self.submodule_info
        submodule_info.job_done_success_flag = 1
        submodule_info.cancel_flag = 0
        return submodule_info.fetch_queue()

    def cancel_submodule_process_state(self, q_id):
        if self.submodule_info.job_done_success_flag:
            self.submodule_info.pop_queue(q_id)

        return self.submodule_info.cancel_flag and self.process_cancel_available(
            q_id)

    def interrupt(self, cause: str) -> None:
        self.process_handle.interrupt(cause)

    def process(self, s_id, func):
        is_yield_exist_in_func = isgeneratorfunction(func)
        yield self.env.timeout(0)

        def function_wrapper(func, packet, s_id):
            return func(packet)

        def function_wrapper_with_s_id(func, packet, s_id):
            return func(packet, s_id)

        submodule_info = self.submodule_info
        feature = self.feature
        submodule_feature_id = submodule_info.feature_id
        if s_id != -1:
            my_function_wrapper = function_wrapper_with_s_id
        else:
            my_function_wrapper = function_wrapper

        while True:
            yield submodule_info.wait()
            submodule_info.reset_wait_event()
            while submodule_info.job_exist():
                packet, q_id = self.init_submodule_and_get_packet()
                if packet is None:
                    break

                if not isinstance(submodule_feature_id, list):
                    yield from self.activate_feature()
                    if not submodule_info.is_latency_recorded:
                        submodule_info.latency_log += feature.get_latency(
                            submodule_feature_id)

                if is_yield_exist_in_func:
                    for internal_yield in my_function_wrapper(
                            func, packet, s_id):
                        if isinstance(internal_yield, simpy.events.Timeout):
                            assert isinstance(
                                submodule_feature_id, list), f'{submodule_info.name}, {submodule_feature_id}'
                            if not submodule_info.is_latency_recorded:
                                submodule_info.latency_log += internal_yield._delay
                        try:
                            yield internal_yield
                        except simpy.Interrupt:
                            self.is_interrupt = True
                else:
                    my_function_wrapper(func, packet, s_id)

                self.latency_logger.logging_latency(
                    submodule_info.name, s_id, packet)
                submodule_info.is_latency_recorded = True

                if self.cancel_submodule_process_state(q_id):
                    break

    def activate_feature_fast_sim(
            self,
            feature_id=None,
            runtime_latency=-1,
            runtime_active_power=-1,
            auto_deactivate=True):
        if runtime_latency == -1:
            if feature_id is None:
                feature_id = self.submodule_info.feature_id
            runtime_latency = self.feature.get_latency(feature_id)

        try:
            yield self.env.timeout(runtime_latency)
        except simpy.Interrupt:
            return False
        return True

    def deactivate_feature_fast_sim(self, feature_id=None):
        pass

    def process_fast_sim(self, s_id, func):
        is_yield_exist_in_func = isgeneratorfunction(func)
        yield self.env.timeout(0)

        def function_wrapper(func, packet, s_id):
            return func(packet)

        def function_wrapper_with_s_id(func, packet, s_id):
            return func(packet, s_id)

        submodule_info = self.submodule_info
        submodule_feature_id = submodule_info.feature_id
        if s_id != -1:
            my_function_wrapper = function_wrapper_with_s_id
        else:
            my_function_wrapper = function_wrapper

        if not isinstance(submodule_feature_id, list):
            if is_yield_exist_in_func:
                while True:
                    yield submodule_info.wait()
                    submodule_info.reset_wait_event()
                    while submodule_info.job_exist():
                        packet, q_id = self.init_submodule_and_get_packet()
                        if packet is None:
                            break

                        yield from self.activate_feature()
                        yield from my_function_wrapper(func, packet, s_id)

                        if self.cancel_submodule_process_state(q_id):
                            break
            else:
                while True:
                    yield submodule_info.wait()
                    submodule_info.reset_wait_event()
                    while submodule_info.job_exist():
                        packet, q_id = self.init_submodule_and_get_packet()
                        if packet is None:
                            break

                        yield from self.activate_feature()
                        my_function_wrapper(func, packet, s_id)

                        if self.cancel_submodule_process_state(q_id):
                            break
        else:
            if is_yield_exist_in_func:
                while True:
                    yield submodule_info.wait()
                    submodule_info.reset_wait_event()
                    while submodule_info.job_exist():
                        packet, q_id = self.init_submodule_and_get_packet()
                        if packet is None:
                            break

                        yield from my_function_wrapper(func, packet, s_id)
                        if self.cancel_submodule_process_state(q_id):
                            break
            else:
                while True:
                    yield submodule_info.wait()
                    submodule_info.reset_wait_event()
                    while submodule_info.job_exist():
                        packet, q_id = self.init_submodule_and_get_packet()
                        if packet is None:
                            break

                        my_function_wrapper(func, packet, s_id)
                        if self.cancel_submodule_process_state(q_id):
                            break
