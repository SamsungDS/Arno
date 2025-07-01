from simpy.events import PENDING, EventCallbacks

'''
Refer to simpy.event
'''


class FirenzeEvent:
    def __init__(self, env):
        self.env = env
        self.callbacks: EventCallbacks = []
        self._ok = True
        self._defused = False
        self._value = PENDING


class SubmoduleEvent(FirenzeEvent):
    def __init__(self, env):
        super().__init__(env)
        self.is_pending = False

    def trigger(self):
        if self.is_pending:
            self._ok = True
            self.env.schedule(self)
            self.is_pending = False

    def wait(self):
        self.is_pending = True
        return self

    def reset(self):
        self.callbacks = []
