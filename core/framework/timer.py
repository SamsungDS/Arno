from core.framework.singleton import Singleton


class FrameworkTimer(metaclass=Singleton):
    def __init__(self, env):
        self.env = env
        self.timer_func_instance_list = []
        self.expire_waiting_timer_count = 0

    def run_timer(self):
        if self.expire_waiting_timer_count != 0:  # timer enabled by generation
            return

        self.expire_waiting_timer_count += len(self.timer_func_instance_list)
        for timer_func in self.timer_func_instance_list:
            self.env.process(timer_func)

    def generate_infinity_timer(
            self,
            timer_interval_ns,
            wakeup_func,
            func_latency_ns):
        self.expire_waiting_timer_count += 1
        self.timer_func_instance_list.append(
            self.timer(
                self.expire_waiting_timer_count - 1,
                timer_interval_ns,
                wakeup_func,
                func_latency_ns))
        self.env.process(self.timer_func_instance_list[-1])

    def run_func(self, func):
        run_waiting_events_count = len(
            self.env._queue)           # remain simpy event count
        func()                                                    # run registered func
        assert run_waiting_events_count == len(
            self.env._queue), 'this timer does not support an increase in simpy_event'

    def timer(self, timer_id, timer_interval_ns, wakeup_func, func_latency_ns):
        next_timer_expire_interval_ns = timer_interval_ns - func_latency_ns
        assert next_timer_expire_interval_ns != 0
        while True:
            # wait, func_latency
            yield self.env.timeout(func_latency_ns)
            # run registered func
            self.run_func(wakeup_func)
            # wait, timer interval
            yield self.env.timeout(next_timer_expire_interval_ns)

            run_waiting_events_count = len(
                self.env._queue)                 # remain simpy event count
            if run_waiting_events_count == self.expire_waiting_timer_count - 1:
                self.expire_waiting_timer_count -= 1
                return
