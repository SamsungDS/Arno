from core.framework.submodule_event import FirenzeEvent

'''
Refer to simpy.timeout
'''


class SubmoduleTimeout(FirenzeEvent):
    def __init__(self, env):
        super().__init__(env)
        self._delay = 0

    def wait(self, delay):
        self._delay = delay
        self.callbacks = []
        self.env.schedule(self, delay=self._delay)
        return self
