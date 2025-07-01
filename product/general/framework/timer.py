import simpy


class Timer:
    def __init__(self, env, timer_expire_time, timer_id):
        self.env = env
        self.timer_expire_time = timer_expire_time
        self.triggered = False
        self.wait_trigger = self.env.event()
        self.timer_process = self.env.process(self.process())
        self.timer_id = timer_id
        self.dbl = self.env.event()

    def process(self):
        while True:
            self.triggered = False
            yield self.wait_trigger
            self.triggered = True
            try:
                yield self.env.timeout(self.timer_expire_time)
            except simpy.Interrupt:
                pass
            else:
                self.dbl.succeed()
                self.dbl = self.env.event()

    def is_running(self):
        return self.triggered

    def reset(self, cause=None):
        if self.triggered:
            self.timer_process.interrupt(cause)
        yield self.env.timeout(0)

    def start(self):
        assert self.triggered is False, 'Timer Triggered Again'
        self.wait_trigger.succeed()
        self.wait_trigger = self.env.event()
        yield self.env.timeout(0)

    def doorbell(self):
        return self.dbl
