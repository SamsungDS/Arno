from collections import defaultdict


class SFR:
    def __new__(cls):
        if not hasattr(cls, 'instance'):
            cls.instance = super(SFR, cls).__new__(cls)
            cls.instance.init_sfr()
        return cls.instance

    def init_sfr(self):
        self.sfr_dict = dict()
        self.add_sfr('host_cmd_cnt')
        self.add_sfr('host_qd_empty')
        self.add_sfr('cmd_idle_timer_expire')
        self.add_sfr('setfeature_cmd_issued')
        self.add_sfr('reset_cmd_idle_timer')
        self.add_sfr('bg_job_start')
        self.add_sfr('bg_wakeup')
        self.add_sfr(
            'shared_qos_info', {
                'target_h2d_perf': 0, 'current_waf': 0})
        self.add_sfr('read_dma_target_perf')
        self.add_sfr('write_dma_target_perf')

        self.sfr_func_dict = dict()
        self.sfr_func_dict = defaultdict(list)

    def add_sfr(self, key, value=0):
        self.sfr_dict[key] = value

    def __sfr_notify(self, name, val):
        if name in self.sfr_func_dict:
            for func in self.sfr_func_dict[name]:
                func(val)

    def read_sfr(self, name):
        return self.sfr_dict[name]

    def write_sfr(self, name, val):
        self.sfr_dict[name] = val
        self.__sfr_notify(name, val)

    def register_func(self, name, func):
        if name not in self.sfr_dict:
            self.add_sfr(name)
        self.sfr_func_dict[name].append(func)
