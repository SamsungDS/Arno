import inspect
from enum import Enum

import simpy
from core.framework.analyzer import Analyzer
from core.framework.common import ProductArgs
from core.framework.file_path_generator import FilePathGenerator, LogOutputType
from core.framework.timer import FrameworkTimer


class ePowerState(Enum):
    Active = 0
    Idle = 1
    Idle1 = 2
    BackGround = 3
    ActiveIdle = 4
    Leakage = 5
    Off = 6
    Timer = 7


class ePowerManagerState(Enum):
    PS0 = 0
    PS0BackGround = 3
    PS0ActiveIdle = 4
    PS3 = 5
    PS4 = 6


class Timer:
    def __init__(
            self,
            env,
            ip_name,
            module_name,
            feature_id,
            timer_expire_time,
            power_manager):
        self.env = env
        self.ip_name = ip_name
        self.module_name = module_name
        self.timer_expire_time = timer_expire_time
        self.triggered = False
        self.wait_trigger = self.env.event()
        self.timer_process = self.env.process(self.process())
        self.feature_id = feature_id
        self.power_manager: PowerManager = power_manager

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
                # change power state from idle to idle1
                self.power_manager.activate_clock_gating(
                    self.ip_name, self.module_name, self.feature_id)

    def is_running(self):
        return self.triggered

    def reset(self, cause=None):
        if self.triggered:
            self.timer_process.interrupt(cause)
        yield self.env.timeout(0)

    def start(self):
        assert self.triggered is False, 'Timer Triggered Again'
        if self.timer_expire_time != 0:
            self.wait_trigger.succeed()
            self.wait_trigger = self.env.event()
        yield self.env.timeout(0)


class PowerContext:
    def __init__(self, PowerManager, product_args: ProductArgs, name):
        product_args.set_args_to_class_instance(self)
        self.parent = PowerManager
        self.cur_state = ePowerState.Idle
        self.name = name
        self.reset_power_context()
        self.subModule_power = dict()
        self.vcd_manager.add_vcd_dump_var('PM', str('total_power'), 'int')

        self.submodule_power = dict()
        self.submodule_last_snapshot_time = dict()
        self.submodule_accumulated_power = dict()
        self.submodule_accumulated_active_count = dict()
        self.submodule_accumulated_active_time = dict()
        self.submodule_accumulated_idle_count = dict()
        self.submodule_accumulated_idle_time = dict()
        self.submodule_last_snapshot_power = dict()
        self.submodule_accumulated_sustain_power = dict()
        self.is_submodule_activated = dict()
        self.is_submodule_sustain_activated = dict()

        self.analyzer = Analyzer()
        self.submodule_power_sum = 0
        self.submodule_sustain_power_sum = 0
        self.submodule_nfcp_din_power_sum = 0
        self.submodule_nfcp_din_sustain_power_sum = 0
        self.submodule_nfcp_dout_power_sum = 0
        self.submodule_nfcp_dout_sustain_power_sum = 0
        self.submodule_nfc_din_power_sum = 0
        self.submodule_nfc_din_sustain_power_sum = 0
        self.submodule_nfc_dout_power_sum = 0
        self.submodule_nfc_dout_sustain_power_sum = 0

        self.submodule_pciephy_power_sum = 0
        self.submodule_pciephy_sustain_power_sum = 0

        self.submodule_dramc_power_sum = 0
        self.submodule_dramc_sustain_power_sum = 0
        self.submodule_dram_power_sum = 0
        self.submodule_dram_sustain_power_sum = 0

        self.idle1_enter_latency = dict()
        self.idle1_exit_latency = dict()
        self.power_state_enter_latency = {
            ePowerState.Idle: 0,
            ePowerState.Idle1: 0,
            ePowerState.BackGround: self.param.SDC_BACK_GROUND_ENTER_LATENCY,
            ePowerState.ActiveIdle: self.param.SDC_ACTIVE_IDLE_ENTER_LATENCY,
            ePowerState.Leakage: self.param.SDC_PS3_ENTER_LATENCY,
            ePowerState.Off: self.param.SDC_PS4_ENTER_LATENCY}
        self.power_state_exit_latency = {
            ePowerState.Idle: 0,
            ePowerState.Idle1: 0,
            ePowerState.BackGround: self.param.SDC_BACK_GROUND_EXIT_LATENCY,
            ePowerState.ActiveIdle: self.param.SDC_ACTIVE_IDLE_EXIT_LATENCY,
            ePowerState.Leakage: self.param.SDC_PS3_EXIT_LATENCY,
            ePowerState.Off: self.param.SDC_PS4_EXIT_LATENCY}

    def reset_power_context(self):
        self.ip_power = 0
        self.ip_power_snapShot_rms_list = dict()
        self.submodule_power_sum = 0
        self.submodule_sustain_power_sum = 0
        self.submodule_nfcp_din_power_sum = 0
        self.submodule_nfcp_din_sustain_power_sum = 0
        self.submodule_nfcp_dout_power_sum = 0
        self.submodule_nfcp_dout_sustain_power_sum = 0
        self.submodule_nfc_din_power_sum = 0
        self.submodule_nfc_din_sustain_power_sum = 0
        self.submodule_nfc_dout_power_sum = 0
        self.submodule_nfc_dout_sustain_power_sum = 0
        self.submodule_pciephy_power_sum = 0
        self.submodule_pciephy_sustain_power_sum = 0
        self.submodule_dramc_power_sum = 0
        self.submodule_dramc_sustain_power_sum = 0
        self.submodule_dram_power_sum = 0
        self.submodule_dram_sustain_power_sum = 0

        if self.env.now != 0:
            for module_name in self.subModule_power.keys():
                self.submodule_last_snapshot_time[module_name] = self.env.now

    def get_state_power(self, state):
        state_power_sum = 0
        for module_name in self.subModule_power.keys():
            state_power_sum += self.subModule_power[module_name][state]

        if state == ePowerState.Idle:
            self.ip_power = state_power_sum

        return state_power_sum

    def get_phy_state_power(self, state):
        state_power_sum = 0
        for module_name in self.subModule_power.keys():
            if 'PCIePHY' in module_name or 'BACKBONE' in module_name:
                state_power_sum += self.subModule_power[module_name][state]

        return state_power_sum

    def reset_context(self):
        for module_name in self.subModule_power.keys():
            self.submodule_power[module_name] = 0
            self.submodule_accumulated_power[module_name] = 0
            self.submodule_accumulated_active_count[module_name] = 0
            self.submodule_accumulated_active_time[module_name] = 0
            self.submodule_accumulated_idle_count[module_name] = 0
            self.submodule_accumulated_idle_time[module_name] = 0
            self.submodule_accumulated_sustain_power[module_name] = 0
            self.is_submodule_activated[module_name] = False
            self.is_submodule_sustain_activated[module_name] = False
            self.submodule_last_snapshot_time[module_name] = self.env.now

    def add_sub_module_power(self, ip_name, submodule_name, power_value):
        self.submodule_power[submodule_name] += power_value

    def del_sub_module_power(self, ip_name, submodule_name, power_value):
        self.submodule_power[submodule_name] -= power_value

    def get_ip_power(self, ip_name):
        return self.ip_power

    def get_nand_sub_module_power(self, submodule_name):
        power_sum = 0
        str = ''
        if 'channel_operation' in submodule_name:
            str = 'channel_operation'
        elif 'plane_operation' in submodule_name:
            str = 'plane_operation'

        for module_name in self.submodule_power.keys():
            if str in module_name:
                power_sum += self.submodule_power[module_name]

        return power_sum

    def get_sub_module_power(self, submodule_name):
        return self.submodule_power[submodule_name]

    def add_sub_module(self, ip_name, modulename, feature_id):
        module_name = modulename
        module_name += f'_{feature_id}'
        assert module_name not in self.subModule_power, f'{module_name}, already '

        self.subModule_power[module_name] = dict()
        if ip_name == 'non_implementation':
            self.subModule_power[module_name]['cur_state'] = ePowerState.Active
        else:
            self.subModule_power[module_name]['cur_state'] = ePowerState.Idle

        idle_power = self.feature.get_idle(feature_id)

        self.subModule_power[module_name]['feature_id'] = feature_id
        self.subModule_power[module_name][ePowerState.Active] = self.feature.get_active(
            feature_id)
        self.subModule_power[module_name][ePowerState.Idle] = idle_power
        self.subModule_power[module_name][ePowerState.Idle1] = self.feature.get_idle1_power(
            feature_id)
        self.subModule_power[module_name][ePowerState.BackGround] = self.feature.get_background_power(
            feature_id)
        self.subModule_power[module_name][ePowerState.ActiveIdle] = self.feature.get_active_idle_power(
            feature_id)
        self.subModule_power[module_name][ePowerState.Leakage] = self.feature.get_leakage_power(
            feature_id)
        self.subModule_power[module_name][ePowerState.Off] = self.feature.get_off_power(
            feature_id)
        if self.feature.get_idle1_enter_latency(
                feature_id) != 0 and self.param.ENABLE_CLOCK_GATING:
            self.subModule_power[module_name][ePowerState.Timer] = Timer(
                self.env, ip_name, modulename, feature_id, self.feature.get_idle1_enter_latency(feature_id), self.parent)
        else:
            self.subModule_power[module_name][ePowerState.Timer] = 0

        self.submodule_power[module_name] = 0
        self.submodule_last_snapshot_time[module_name] = 0
        self.submodule_last_snapshot_power[module_name] = 0
        self.submodule_accumulated_power[module_name] = 0
        self.submodule_accumulated_active_count[module_name] = 0
        self.submodule_accumulated_active_time[module_name] = 0
        self.submodule_accumulated_idle_count[module_name] = 0
        self.submodule_accumulated_idle_time[module_name] = 0
        self.submodule_accumulated_sustain_power[module_name] = 0
        self.submodule_power_sum = 0
        self.submodule_sustain_power_sum = 0
        self.submodule_nfcp_din_power_sum = 0
        self.submodule_nfcp_din_sustain_power_sum = 0
        self.submodule_nfcp_dout_power_sum = 0
        self.submodule_nfcp_dout_sustain_power_sum = 0
        self.submodule_nfc_din_power_sum = 0
        self.submodule_nfc_din_sustain_power_sum = 0
        self.submodule_nfc_dout_power_sum = 0
        self.submodule_nfc_dout_sustain_power_sum = 0
        self.submodule_pciephy_sustain_power_sum = 0
        self.is_submodule_activated[module_name] = False
        self.is_submodule_sustain_activated[module_name] = False

        if self.param.ENABLE_CLOCK_GATING:
            self.idle1_enter_latency[module_name] = self.feature.get_idle1_enter_latency(
                feature_id)
            self.idle1_exit_latency[module_name] = self.feature.get_idle1_exit_latency(
                feature_id)
        else:
            self.idle1_enter_latency[module_name] = 0
            self.idle1_exit_latency[module_name] = 0

        self.vcd_manager.add_vcd_dump_var('PM', f'{module_name}', 'int')
        power = idle_power
        return power

    def set_state(self, state): self.cur_state = state
    def get_state(self): return self.cur_state

    def check_feature_id(self, name, feature_id):
        name += f'_{feature_id}'
        assert name in self.subModule_power, f'feature_id not in sub_module, {name}, {feature_id}'

    def is_sub_module_active(self, name, feature_id):
        name += f'_{feature_id}'
        return self.subModule_power[name]['cur_state'] == ePowerState.Active

    def get_cur_power(self): return self.ip_power

    def activate_sub_module(
            self,
            ip_name,
            module_name,
            feature_id,
            runtime_power=0):
        module_name += f'_{feature_id}'
        diff = 0
        if self.subModule_power[module_name]['cur_state'] == ePowerState.Idle:
            diff = self.subModule_power[module_name][ePowerState.Active] - self.subModule_power[module_name][ePowerState.Idle]
        elif self.subModule_power[module_name]['cur_state'] == ePowerState.Leakage:
            diff = self.subModule_power[module_name][ePowerState.Active] - self.subModule_power[module_name][ePowerState.Leakage]
        elif self.subModule_power[module_name]['cur_state'] == ePowerState.Off:
            diff = self.subModule_power[module_name][ePowerState.Active] - self.subModule_power[module_name][ePowerState.Off]
        elif self.subModule_power[module_name]['cur_state'] == ePowerState.Idle1:
            diff = self.subModule_power[module_name][ePowerState.Active] - self.subModule_power[module_name][ePowerState.Idle1]
        self.ip_power += diff

        power = 0
        duration = 0
        if self.subModule_power[module_name]['cur_state'] == ePowerState.Idle:
            if self.env.now > self.submodule_last_snapshot_time[module_name]:
                power = (self.env.now - self.submodule_last_snapshot_time[module_name]) * self.subModule_power[module_name][ePowerState.Idle]
                duration = (self.env.now - self.submodule_last_snapshot_time[module_name])
            else:
                power = (self.submodule_last_snapshot_time[module_name] - self.env.now) * self.subModule_power[module_name][ePowerState.Idle]
                self.submodule_accumulated_sustain_power[module_name] -= power
                power = 0
            self.submodule_last_snapshot_time[module_name] = self.env.now
        elif self.subModule_power[module_name]['cur_state'] == ePowerState.Idle1:
            if self.env.now > self.submodule_last_snapshot_time[module_name]:
                power = (self.env.now - self.submodule_last_snapshot_time[module_name] +
                         self.idle1_exit_latency[module_name]) * self.subModule_power[module_name][ePowerState.Idle1]
                duration = (
                    self.env.now -
                    self.submodule_last_snapshot_time[module_name])
            else:
                power = (self.submodule_last_snapshot_time[module_name] - self.env.now) \
                    * self.subModule_power[module_name][self.subModule_power[module_name]['cur_state']]
                self.submodule_accumulated_sustain_power[module_name] -= power
                power = (self.idle1_exit_latency[module_name] *
                         self.subModule_power[module_name][ePowerState.Idle1])

            self.submodule_last_snapshot_time[module_name] = self.env.now + \
                self.idle1_exit_latency[module_name]

        self.subModule_power[module_name]['cur_state'] = ePowerState.Active

        if self.analyzer.is_sim_measure_state:
            if self.analyzer.is_sustained_perf_measure_state:
                self.submodule_accumulated_sustain_power[module_name] += power
                self.submodule_sustain_power_sum += power
                if ip_name == 'NFC' and 'nfcp_channel_operation' in module_name and self.feature.NFCP_DIN == feature_id:
                    self.submodule_nfcp_din_sustain_power_sum += power
                elif ip_name == 'NFC' and 'nfcp_channel_operation' in module_name and self.feature.NFCP_DOUT == feature_id:
                    self.submodule_nfcp_dout_sustain_power_sum += power
                elif ip_name == 'NFC' and 'nfc_channel_operation' in module_name and self.feature.NFC_DIN == feature_id:
                    self.submodule_nfc_din_sustain_power_sum += power
                elif ip_name == 'NFC' and 'nfc_channel_operation' in module_name and self.feature.NFC_DOUT == feature_id:
                    self.submodule_nfc_dout_sustain_power_sum += power
                elif ip_name == 'MEMC' and 'mem_access_submodule' in module_name and self.feature.DRAM_MEM_ACCESS == feature_id:
                    self.submodule_dramc_sustain_power_sum += power
                elif ip_name == 'MEMC' and 'memory_submodule' in module_name and self.feature.DRAM:
                    self.submodule_dram_sustain_power_sum += power

            self.submodule_accumulated_power[module_name] += power
            self.submodule_power_sum += power
            self.submodule_accumulated_idle_count[module_name] += 1
            self.submodule_accumulated_idle_time[module_name] += duration
            if ip_name == 'NFC' and 'nfcp_channel_operation' in module_name and self.feature.NFCP_DIN == feature_id:
                self.submodule_nfcp_din_power_sum += power
            elif ip_name == 'NFC' and 'nfcp_channel_operation' in module_name and self.feature.NFCP_DOUT == feature_id:
                self.submodule_nfcp_dout_power_sum += power
            elif ip_name == 'NFC' and 'nfc_channel_operation' in module_name and self.feature.NFC_DIN == feature_id:
                self.submodule_nfc_din_power_sum += power
            elif ip_name == 'NFC' and 'nfc_channel_operation' in module_name and self.feature.NFC_DOUT == feature_id:
                self.submodule_nfc_dout_power_sum += power
            elif ip_name == 'MEMC' and 'mem_access_submodule' in module_name and self.feature.DRAM_MEM_ACCESS == feature_id:
                self.submodule_dramc_power_sum += power
            elif ip_name == 'MEMC' and 'memory_submodule' in module_name and self.feature.DRAM == feature_id:
                self.submodule_dram_power_sum += power

        if self.param.ENABLE_DUMP_POWER_VCD:
            self.vcd_manager.record_log(
                self.subModule_power[module_name]['cur_state'].value + 1, 'PM', module_name)

        if self.subModule_power[module_name][ePowerState.Timer] != 0:
            yield from self.subModule_power[module_name][ePowerState.Timer].reset()

        self.is_submodule_activated[module_name] = True
        if self.analyzer.is_sustained_perf_measure_state:
            self.is_submodule_sustain_activated[module_name] = True

        return diff

    def deactivate_sub_module(self, ip_name, module_name, feature_id):
        module_name += f'_{feature_id}'
        diff = abs(self.subModule_power[module_name][ePowerState.Idle] - self.subModule_power[module_name][ePowerState.Active])
        self.ip_power -= diff

        duration = 0
        if self.env.now > self.submodule_last_snapshot_time[module_name]:
            power = (self.env.now - self.submodule_last_snapshot_time[module_name]) * self.subModule_power[module_name][ePowerState.Active]
            duration = (self.env.now - self.submodule_last_snapshot_time[module_name])
        else:
            power = (self.submodule_last_snapshot_time[module_name] - self.env.now) * \
                self.subModule_power[module_name][ePowerState.Active]
            self.submodule_accumulated_sustain_power[module_name] -= power
            power = 0

        if self.analyzer.is_sim_measure_state:
            if self.analyzer.is_sustained_perf_measure_state:
                self.submodule_accumulated_sustain_power[module_name] += power
                self.submodule_sustain_power_sum += power
                if ip_name == 'NFC' and 'nfcp_channel_operation' in module_name and self.feature.NFCP_DIN == feature_id:
                    self.submodule_nfcp_din_sustain_power_sum += power
                elif ip_name == 'NFC' and 'nfcp_channel_operation' in module_name and self.feature.NFCP_DOUT == feature_id:
                    self.submodule_nfcp_dout_sustain_power_sum += power
                elif ip_name == 'NFC' and 'nfc_channel_operation' in module_name and self.feature.NFC_DIN == feature_id:
                    self.submodule_nfc_din_sustain_power_sum += power
                elif ip_name == 'NFC' and 'nfc_channel_operation' in module_name and self.feature.NFC_DOUT == feature_id:
                    self.submodule_nfc_dout_sustain_power_sum += power
                elif ip_name == 'MEMC' and 'mem_access_submodule' in module_name and self.feature.DRAM_MEM_ACCESS == feature_id:
                    self.submodule_dramc_sustain_power_sum += power
                elif ip_name == 'MEMC' and 'memory_submodule' in module_name and self.feature.DRAM == feature_id:
                    self.submodule_dram_sustain_power_sum += power

            self.submodule_accumulated_power[module_name] += power
            self.submodule_power_sum += power
            self.submodule_accumulated_active_count[module_name] += 1
            self.submodule_accumulated_active_time[module_name] += duration
            if ip_name == 'NFC' and 'nfcp_channel_operation' in module_name and self.feature.NFCP_DIN == feature_id:
                self.submodule_nfcp_din_power_sum += power
            elif ip_name == 'NFC' and 'nfcp_channel_operation' in module_name and self.feature.NFCP_DOUT == feature_id:
                self.submodule_nfcp_dout_power_sum += power
            elif ip_name == 'NFC' and 'nfc_channel_operation' in module_name and self.feature.NFC_DIN == feature_id:
                self.submodule_nfc_din_power_sum += power
            elif ip_name == 'NFC' and 'nfc_channel_operation' in module_name and self.feature.NFC_DOUT == feature_id:
                self.submodule_nfc_dout_power_sum += power
            elif ip_name == 'MEMC' and 'mem_access_submodule' in module_name and self.feature.DRAM_MEM_ACCESS == feature_id:
                self.submodule_dramc_power_sum += power
            elif ip_name == 'MEMC' and 'memory_submodule' in module_name and self.feature.DRAM == feature_id:
                self.submodule_dram_power_sum += power

        self.subModule_power[module_name]['cur_state'] = ePowerState.Idle
        self.submodule_last_snapshot_time[module_name] = self.env.now
        self.is_submodule_activated[module_name] = True
        if self.analyzer.is_sustained_perf_measure_state:
            self.is_submodule_sustain_activated[module_name] = True

        if self.param.ENABLE_DUMP_POWER_VCD:
            self.vcd_manager.record_log(
                self.subModule_power[module_name]['cur_state'].value + 1, 'PM', module_name)

        if self.subModule_power[module_name][ePowerState.Timer] != 0:
            yield from self.subModule_power[module_name][ePowerState.Timer].start()
        yield self.env.timeout(0)
        return diff

    def deactivate_non_implementation_sub_module(
            self, module_name, feature_id):
        module_name += f'_{feature_id}'
        power = (self.analyzer.sim_end_time - self.analyzer.sim_start_time) * \
            self.subModule_power[module_name][ePowerState.Active]
        sustain_power = (self.analyzer.sustained_perf_measure_end_time -
                         self.analyzer.sustained_perf_measure_start_time) * self.subModule_power[module_name][ePowerState.Active]

        self.submodule_sustain_power_sum += sustain_power
        self.submodule_power_sum += power

        yield self.env.timeout(0)

    # clock gating timer is expired, and module will be clock gating
    def activate_clock_gating_sub_module(
            self, ip_name, module_name, feature_id):
        module_name += f'_{feature_id}'
        power = (self.env.now - self.submodule_last_snapshot_time[module_name]
                 ) * self.subModule_power[module_name][ePowerState.Idle]

        if self.analyzer.is_sim_measure_state:
            if self.analyzer.is_sustained_perf_measure_state:
                self.submodule_accumulated_sustain_power[module_name] += power
                self.submodule_sustain_power_sum += power
                if ip_name == 'NFC' and 'nfcp_channel_operation' in module_name and self.feature.NFCP_DIN == feature_id:
                    self.submodule_nfcp_din_sustain_power_sum += power
                elif ip_name == 'NFC' and 'nfcp_channel_operation' in module_name and self.feature.NFCP_DOUT == feature_id:
                    self.submodule_nfcp_dout_sustain_power_sum += power
                elif ip_name == 'NFC' and 'nfc_channel_operation' in module_name and self.feature.NFC_DIN == feature_id:
                    self.submodule_nfc_din_sustain_power_sum += power
                elif ip_name == 'NFC' and 'nfc_channel_operation' in module_name and self.feature.NFC_DOUT == feature_id:
                    self.submodule_nfc_dout_sustain_power_sum += power
                elif ip_name == 'MEMC' and 'mem_access_submodule' in module_name and self.feature.DRAM_MEM_ACCESS == feature_id:
                    self.submodule_dramc_sustain_power_sum += power
                elif ip_name == 'MEMC' and 'memory_submodule' in module_name and self.feature.DRAM == feature_id:
                    self.submodule_dram_sustain_power_sum += power

            self.submodule_accumulated_power[module_name] += power
            self.submodule_power_sum += power
            if ip_name == 'NFC' and 'nfcp_channel_operation' in module_name:
                self.submodule_nfcp_din_power_sum += power
                self.submodule_nfcp_dout_power_sum += power
            elif ip_name == 'NFC' and 'nfc_channel_operation' in module_name and self.feature.NFC_DIN == feature_id:
                self.submodule_nfc_din_power_sum += power
            elif ip_name == 'NFC' and 'nfc_channel_operation' in module_name and self.feature.NFC_DOUT == feature_id:
                self.submodule_nfc_dout_power_sum += power
            elif ip_name == 'MEMC' and 'mem_access_submodule' in module_name and self.feature.DRAM_MEM_ACCESS == feature_id:
                self.submodule_dramc_power_sum += power
            elif ip_name == 'MEMC' and 'memory_submodule' in module_name and self.feature.DRAM == feature_id:
                self.submodule_dram_power_sum += power

        self.subModule_power[module_name]['cur_state'] = ePowerState.Idle1
        self.submodule_last_snapshot_time[module_name] = self.env.now
        self.is_submodule_activated[module_name] = True
        if self.analyzer.is_sustained_perf_measure_state:
            self.is_submodule_sustain_activated[module_name] = True

        if self.param.ENABLE_DUMP_POWER_VCD:
            self.vcd_manager.record_log(
                self.subModule_power[module_name]['cur_state'].value + 1, 'PM', module_name)

    def change_sub_module_power_state(
            self, module_name, before_state, after_state):
        diff = abs(
            self.subModule_power[module_name][before_state] -
            self.subModule_power[module_name][after_state])
        curState = self.subModule_power[module_name]['cur_state']
        if curState != before_state:
            diff = abs(
                self.subModule_power[module_name][curState] -
                self.subModule_power[module_name][before_state])
            diff += abs(
                self.subModule_power[module_name][before_state] -
                self.subModule_power[module_name][after_state])
        if (after_state.value - before_state.value) > 0:
            self.ip_power -= diff
        else:
            self.ip_power += diff
        self.subModule_power[module_name]['cur_state'] = after_state
        return diff

    def change_all_sub_module_power_state(
            self, ip_name, before_state, after_state):
        power = 0
        for module_name in self.subModule_power:
            if self.param.ENABLE_DYNAMIC_POWERSTATE:
                if before_state.value <= after_state.value:
                    if self.env.now > self.submodule_last_snapshot_time[module_name]:
                        power = (self.env.now - self.submodule_last_snapshot_time[module_name] +
                                 self.power_state_enter_latency[before_state]) * \
                            self.subModule_power[module_name][before_state]
                        if before_state.value < after_state.value:
                            self.submodule_last_snapshot_time[module_name] = self.env.now + \
                                self.power_state_enter_latency[before_state]
                        else:
                            self.submodule_last_snapshot_time[module_name] = self.env.now
                    else:
                        if before_state != ePowerState.Idle:
                            power = (self.submodule_last_snapshot_time[module_name] - self.env.now) * \
                                self.subModule_power[module_name][before_state]
                            self.submodule_accumulated_power[module_name] -= power

                        power = self.power_state_enter_latency[before_state] * \
                            self.subModule_power[module_name][before_state]
                        self.submodule_last_snapshot_time[module_name] = self.env.now + \
                            self.power_state_enter_latency[before_state]
                else:
                    if self.env.now > self.submodule_last_snapshot_time[module_name]:
                        power = (self.env.now - self.submodule_last_snapshot_time[module_name] +
                                 self.power_state_exit_latency[before_state]) * \
                            self.subModule_power[module_name][before_state]
                        self.submodule_last_snapshot_time[module_name] = self.env.now + \
                            self.power_state_exit_latency[before_state]
                    else:
                        power = (self.submodule_last_snapshot_time[module_name] - self.env.now) * \
                            self.subModule_power[module_name][before_state]
                        self.submodule_accumulated_power[module_name] -= power
                        power = 0
                        power = self.power_state_exit_latency[before_state] * \
                            self.subModule_power[module_name][before_state]
                        self.submodule_last_snapshot_time[module_name] = self.env.now + \
                            self.power_state_exit_latency[before_state]
            else:
                power = (
                    self.env.now - self.submodule_last_snapshot_time[module_name]) * self.subModule_power[module_name][before_state]
                self.submodule_last_snapshot_time[module_name] = self.env.now

            if self.analyzer.is_sim_measure_state:
                self.submodule_accumulated_power[module_name] += power
                self.submodule_power_sum += power
                if ip_name == 'non_implementation' and 'PCIePHY' in module_name:
                    self.submodule_pciephy_power_sum += power
                elif ip_name == 'NFC' and 'nfcp_channel_operation' in module_name:
                    self.submodule_nfcp_din_power_sum += power
                    self.submodule_nfcp_dout_power_sum += power
                elif ip_name == 'NFC' and 'nfc_channel_operation' in module_name:
                    self.submodule_nfc_din_power_sum += power
                    self.submodule_nfc_dout_power_sum += power
                elif ip_name == 'MEMC' and 'mem_access_submodule' in module_name:
                    self.submodule_dramc_power_sum += power
                elif ip_name == 'MEMC' and 'memory_submodule' in module_name:
                    self.submodule_dram_power_sum += power

                if self.analyzer.is_sustained_perf_measure_state:
                    self.is_submodule_sustain_activated[module_name] = True
                    self.submodule_accumulated_sustain_power[module_name] += power
                    self.submodule_sustain_power_sum += power
                    if ip_name == 'non_implementation' and 'PCIePHY' in module_name:
                        self.submodule_pciephy_sustain_power_sum += power
                    elif ip_name == 'NFC' and 'nfcp_channel_operation' in module_name:
                        self.submodule_nfcp_din_sustain_power_sum += power
                        self.submodule_nfcp_dout_sustain_power_sum += power
                    elif ip_name == 'NFC' and 'nfc_channel_operation' in module_name:
                        self.submodule_nfc_din_sustain_power_sum += power
                        self.submodule_nfc_dout_sustain_power_sum += power
                    elif ip_name == 'MEMC' and 'mem_access_submodule' in module_name:
                        self.submodule_dramc_sustain_power_sum += power
                    elif ip_name == 'MEMC' and 'memory_submodule' in module_name:
                        self.submodule_dram_sustain_power_sum += power

            self.subModule_power[module_name]['cur_state'] = after_state
            self.is_submodule_activated[module_name] = True

        return power

    def snapshot_sub_module_power(self, ip_name):
        power_sum = 0
        for module_name in self.submodule_power.keys():
            power = 0
            if not self.is_submodule_activated[module_name]:
                power = (self.analyzer.sim_end_time - self.analyzer.sim_start_time) * \
                    self.subModule_power[module_name][self.subModule_power[module_name]['cur_state']]
                power_sum += power
                if ip_name == 'non_implementation' and 'PCIePHY' in module_name:
                    self.submodule_pciephy_power_sum += power
            else:
                if self.analyzer.sim_end_time > self.submodule_last_snapshot_time[module_name]:
                    power = (self.analyzer.sim_end_time - self.submodule_last_snapshot_time[module_name]) * \
                        self.subModule_power[module_name][self.subModule_power[module_name]['cur_state']]
                    power_sum += power
                    if ip_name == 'non_implementation' and 'PCIePHY' in module_name:
                        self.submodule_pciephy_power_sum += power

        self.submodule_power_sum += power_sum

        return self.submodule_power_sum

    def snapshot_sub_module_sustain_power(self, ip_name):
        power_sum = 0
        for module_name in self.submodule_power.keys():
            power = 0
            if not self.is_submodule_sustain_activated[module_name]:
                power = (self.analyzer.sustained_perf_measure_end_time - self.analyzer.sustained_perf_measure_start_time) * \
                    self.subModule_power[module_name][self.subModule_power[module_name]['cur_state']]
                power_sum += power
                if ip_name == 'non_implementation' and 'PCIePHY' in module_name:
                    self.submodule_pciephy_sustain_power_sum += power
            else:
                if self.analyzer.sustained_perf_measure_end_time > self.submodule_last_snapshot_time[
                        module_name]:
                    power = (self.analyzer.sustained_perf_measure_end_time -
                             self.submodule_last_snapshot_time[module_name]) * self.subModule_power[module_name][self.subModule_power[module_name]['cur_state']]
                    power_sum += power
                    if ip_name == 'non_implementation' and 'PCIePHY' in module_name:
                        self.submodule_pciephy_sustain_power_sum += power

        self.submodule_sustain_power_sum += power_sum
        return self.submodule_sustain_power_sum

    def get_sustain_avg_sub_module_power(self, ip_name):
        return self.submodule_sustain_power_sum / (self.analyzer.sustained_perf_measure_end_time - self.analyzer.sustained_perf_measure_start_time)

    def get_sustain_avg_nfcp_power(self):

        return (self.submodule_nfcp_din_sustain_power_sum + self.submodule_nfcp_dout_sustain_power_sum) / \
            (self.analyzer.sustained_perf_measure_end_time - self.analyzer.sustained_perf_measure_start_time)

    def get_sustain_avg_nfcp_din_power(self):
        return self.submodule_nfcp_din_sustain_power_sum / \
            (self.analyzer.sustained_perf_measure_end_time - self.analyzer.sustained_perf_measure_start_time)

    def get_sustain_avg_nfcp_dout_power(self):
        return self.submodule_nfcp_dout_sustain_power_sum / \
            (self.analyzer.sustained_perf_measure_end_time - self.analyzer.sustained_perf_measure_start_time)

    def get_sustain_avg_nfc_power(self):
        return (self.submodule_nfc_din_sustain_power_sum + self.submodule_nfc_dout_sustain_power_sum) / \
            (self.analyzer.sustained_perf_measure_end_time - self.analyzer.sustained_perf_measure_start_time)

    def get_sustain_avg_nfc_din_power(self):
        return self.submodule_nfc_din_sustain_power_sum / \
            (self.analyzer.sustained_perf_measure_end_time - self.analyzer.sustained_perf_measure_start_time)

    def get_sustain_avg_nfc_dout_power(self):
        return self.submodule_nfc_dout_sustain_power_sum / \
            (self.analyzer.sustained_perf_measure_end_time - self.analyzer.sustained_perf_measure_start_time)

    def get_sustain_avg_backbone_power(self):
        return (self.submodule_sustain_power_sum - self.submodule_pciephy_sustain_power_sum) / \
            (self.analyzer.sustained_perf_measure_end_time - self.analyzer.sustained_perf_measure_start_time)

    def get_sustain_avg_pciephy_power(self):
        return (self.submodule_pciephy_sustain_power_sum) / \
            (self.analyzer.sustained_perf_measure_end_time - self.analyzer.sustained_perf_measure_start_time)

    def get_sustain_avg_dramc_power(self):
        return (self.submodule_dramc_sustain_power_sum) / \
            (self.analyzer.sustained_perf_measure_end_time - self.analyzer.sustained_perf_measure_start_time)

    def get_sustain_avg_dram_power(self):
        return (self.submodule_dram_sustain_power_sum) / \
            (self.analyzer.sustained_perf_measure_end_time - self.analyzer.sustained_perf_measure_start_time)

    def get_full_avg_backbone_power(self):
        return (self.submodule_power_sum - self.submodule_pciephy_power_sum) / \
            (self.analyzer.sim_end_time - self.analyzer.sim_start_time)

    def get_full_avg_pciephy_power(self):
        return (self.submodule_pciephy_power_sum) / \
            (self.analyzer.sim_end_time - self.analyzer.sim_start_time)

    def get_full_avg_nfcp_power(self):
        return (self.submodule_nfcp_din_power_sum + self.submodule_nfcp_dout_power_sum) / \
            (self.analyzer.sim_end_time - self.analyzer.sim_start_time)

    def get_full_avg_nfcp_din_power(self):
        return self.submodule_nfcp_din_power_sum / \
            (self.analyzer.sim_end_time - self.analyzer.sim_start_time)

    def get_full_avg_nfcp_dout_power(self):
        return self.submodule_nfcp_dout_power_sum / \
            (self.analyzer.sim_end_time - self.analyzer.sim_start_time)

    def get_full_avg_nfc_power(self):
        return (self.submodule_nfc_din_power_sum + self.submodule_nfc_dout_power_sum) / \
            (self.analyzer.sim_end_time - self.analyzer.sim_start_time)

    def get_full_avg_nfc_din_power(self):
        return self.submodule_nfc_din_power_sum / \
            (self.analyzer.sim_end_time - self.analyzer.sim_start_time)

    def get_full_avg_nfc_dout_power(self):
        return self.submodule_nfc_dout_power_sum / \
            (self.analyzer.sim_end_time - self.analyzer.sim_start_time)

    def get_full_avg_dramc_power(self):
        return (self.submodule_dramc_power_sum) / \
            (self.analyzer.sim_end_time - self.analyzer.sim_start_time)

    def get_full_avg_dram_power(self):
        return (self.submodule_dram_power_sum) / \
            (self.analyzer.sim_end_time - self.analyzer.sim_start_time)

    def get_avg_sub_module_power(self, ip_name):
        return self.submodule_power_sum / (
            self.analyzer.sim_end_time - self.analyzer.sim_start_time)

    def update_non_implementation_sub_module_power(self):
        for module_name in self.submodule_power.keys():
            self.submodule_accumulated_power[module_name] = (
                self.analyzer.sim_end_time - self.analyzer.sim_start_time) * self.subModule_power[module_name][ePowerState.Active]
            self.submodule_power_sum += self.submodule_accumulated_power[module_name]
            self.is_submodule_activated[module_name] = True

    def update_non_implementation_sub_module_sustain_power(self):
        for module_name in self.submodule_power.keys():
            self.submodule_accumulated_sustain_power[module_name] = (
                self.analyzer.sustained_perf_measure_end_time - self.analyzer.sustained_perf_measure_start_time) * self.subModule_power[module_name][ePowerState.Active]
            self.submodule_sustain_power_sum += self.submodule_accumulated_sustain_power[module_name]

    def get_accumulate_power(self):
        submodule_power = 0
        for module_name in self.submodule_power.keys():
            submodule_power += self.submodule_accumulated_power[module_name]
        return submodule_power

    def get_cur_submodule_power(self, ip_name):
        snapshot_submodule_power = 0

        if self.analyzer.is_sim_measure_state:
            for module_name in self.submodule_power.keys():
                if (self.env.now -
                        self.submodule_last_snapshot_time[module_name]) >= self.param.POWER_SNAP_SHOT_INTERVAL:
                    power = self.subModule_power[module_name][self.subModule_power[module_name]
                                                              ['cur_state']] * self.param.POWER_SNAP_SHOT_INTERVAL
                    self.submodule_accumulated_power[module_name] += power
                    if ip_name == 'non_implementation' and 'PCIePHY' in module_name:
                        self.submodule_pciephy_power_sum += power
                    if self.analyzer.is_sustained_perf_measure_state:
                        self.submodule_accumulated_sustain_power[module_name] += power
                        if ip_name == 'non_implementation' and 'PCIePHY' in module_name:
                            self.submodule_pciephy_sustain_power_sum += power
                else:
                    if self.env.now > self.submodule_last_snapshot_time[module_name]:
                        power = (self.env.now - self.submodule_last_snapshot_time[module_name]) * \
                            self.subModule_power[module_name][self.subModule_power[module_name]['cur_state']]
                    else:
                        power = 0

                    self.submodule_accumulated_power[module_name] += power
                    if ip_name == 'non_implementation' and 'PCIePHY' in module_name:
                        self.submodule_pciephy_power_sum += power
                    if self.analyzer.is_sustained_perf_measure_state:
                        self.submodule_accumulated_sustain_power[module_name] += power
                        if ip_name == 'non_implementation' and 'PCIePHY' in module_name:
                            self.submodule_pciephy_sustain_power_sum += power
                        elif ip_name == 'NFC' and 'nfcp_channel_operation' in module_name:
                            self.submodule_nfcp_din_sustain_power_sum += power
                            self.submodule_nfcp_dout_sustain_power_sum += power
                        elif ip_name == 'NFC' and 'nfc_channel_operation' in module_name:
                            self.submodule_nfc_din_sustain_power_sum += power
                            self.submodule_nfc_dout_sustain_power_sum += power
                        elif ip_name == 'MEMC' and 'mem_access_submodule' in module_name:
                            self.submodule_dramc_sustain_power_sum += power
                        elif ip_name == 'MEMC' and 'memory_submodule' in module_name:
                            self.submodule_dram_sustain_power_sum += power

                self.submodule_last_snapshot_power[module_name] = self.submodule_accumulated_power[module_name]
                self.submodule_last_snapshot_time[module_name] = self.env.now
                snapshot_submodule_power += power
                if ip_name == 'NFC' and 'nfcp_channel_operation' in module_name:
                    self.submodule_nfcp_din_power_sum += power
                    self.submodule_nfcp_dout_power_sum += power
                elif ip_name == 'NFC' and 'nfc_channel_operation' in module_name:
                    self.submodule_nfc_dout_power_sum += power
                    self.submodule_nfc_din_power_sum += power
                elif ip_name == 'MEMC' and 'mem_access_submodule' in module_name:
                    self.submodule_dramc_power_sum += power
                elif ip_name == 'MEMC' and 'memory_submodule' in module_name:
                    self.submodule_dram_power_sum += power

                self.is_submodule_activated[module_name] = True
                if self.analyzer.is_sustained_perf_measure_state:
                    self.is_submodule_sustain_activated[module_name] = True

            self.submodule_power_sum += snapshot_submodule_power
            if self.analyzer.is_sustained_perf_measure_state:
                self.submodule_sustain_power_sum += snapshot_submodule_power

        return snapshot_submodule_power

    def get_snapshot_power(self, ip_name):
        snapshot_submodule_power = 0

        for module_name in self.submodule_power.keys():
            snapshot_submodule_power += self.subModule_power[module_name][self.subModule_power[module_name]['cur_state']]

        return snapshot_submodule_power


def PowerManagerFuncDecorator(func):
    def check_enable_power(self, *args, **kwargs):
        if self.param.ENABLE_POWER:
            return func(self, *args, **kwargs)
        else:
            return
    return check_enable_power


def PowerManagerClassDecorator(cls):
    for name, function in inspect.getmembers(cls, inspect.isfunction):
        if '__new__' not in name:
            setattr(cls, name, PowerManagerFuncDecorator(function))
    return cls


@PowerManagerClassDecorator
class PowerManager:
    def __new__(cls, product_args: ProductArgs = None):
        if not hasattr(cls, 'instance'):
            cls.instance = super(PowerManager, cls).__new__(cls)
        if product_args is not None:
            product_args.set_args_to_class_instance(cls.instance)
            cls.instance.init_power_manager()
        return cls.instance

    def init_power_manager(self):
        self.implementation_module = dict()
        self.analyzer = Analyzer()
        self.file_path_generator = FilePathGenerator()

        self.total_power = 0
        self.total_power_rms = 0
        self.total_power_sustain = 0
        self.total_power_snapshot = 0
        self.max_total_power = 0

        self.max_hosttop_power = 0
        self.max_coretop_power = 0
        self.max_mediatop_power = 0
        self.max_nand_power = 0
        self.max_pci_power = 0
        self.max_total_power = 0
        self.snapshot_max_power = dict()

        self.last_total_power_rms = 0
        self.last_snapshot_submodule_power = 0

        self.total_power_filename = open(
            self.param.TOTAL_POWER_LOG_FILE_NAME, 'w')
        self.power_snap_shot_interval = self.param.POWER_SNAP_SHOT_INTERVAL
        self.product_type = self.param.product_type

        self.finish = False
        self.power_manager_cur_state = ePowerManagerState.PS0

        self.non_implementation_module = None
        self.non_implementation_ip_name = 'non_implementation'
        self.add_non_implementation_module()
        self.vcd_manager.add_vcd_dump_var('PM', 'power_state', 'int')

        self.power_state_exit_latency = {
            ePowerManagerState.PS0: 0,
            ePowerManagerState.PS0BackGround: self.param.SDC_BACK_GROUND_EXIT_LATENCY,
            ePowerManagerState.PS0ActiveIdle: self.param.SDC_ACTIVE_IDLE_EXIT_LATENCY,
            ePowerManagerState.PS3: self.param.SDC_PS3_EXIT_LATENCY,
            ePowerManagerState.PS4: self.param.SDC_PS4_EXIT_LATENCY}

        self.framework_timer = FrameworkTimer(self.env)

    def get_snapshot_max_power(self, *module_name_list):
        power_sum = 0
        for module_name in module_name_list:
            try:
                power_sum += self.snapshot_max_power[module_name]
            except KeyError:
                pass
        return power_sum

    def update_total_power(self):
        snapshot_submodule_power = 0
        snapshot_power_sum = 0
        self.snapshot_max_power = dict()

        for ip_name in self.implementation_module.keys():
            snapshot_submodule_power += self.implementation_module[ip_name].get_cur_submodule_power(
                ip_name)
            power = self.implementation_module[ip_name].get_snapshot_power(
                ip_name)
            snapshot_power_sum += power
            self.snapshot_max_power[ip_name] = power

        hosttop_power_sum = self.get_snapshot_max_power("PCIe")
        coretop_power_sum = self.get_snapshot_max_power("BA")
        mediatop_power_sum = self.get_snapshot_max_power("JG", "JS", "NFC")
        nand_power_sum = self.get_snapshot_max_power("NAND")
        pci_power_sum = self.get_snapshot_max_power(
            "BACKBONE", "PCIEPHY", "NFCP")

        self.max_hosttop_power = max(self.max_hosttop_power, hosttop_power_sum)
        self.max_coretop_power = max(self.max_coretop_power, coretop_power_sum)
        self.max_mediatop_power = max(
            self.max_mediatop_power, mediatop_power_sum)
        self.max_nand_power = max(self.max_nand_power, nand_power_sum)
        self.max_pci_power = max(self.max_pci_power, pci_power_sum)
        self.max_total_power = max(self.max_total_power, snapshot_power_sum)

        self.last_snapshot_submodule_power = snapshot_submodule_power
        if self.param.ENABLE_LOGGING_TOTAL_POWER and self.power_snap_shot_interval != 0:
            logstr = f'#{self.env.now}, {snapshot_power_sum}\n'
            self.total_power_filename.write(logstr)

    def start_power_snapshot(self, workload, qd):
        if self.param.ENABLE_LOGGING_TOTAL_POWER:
            self.file_path_generator.set_file_prefix(workload.name, qd)
            self.power_trace_log_file_prefix = self.file_path_generator.get_file_prefix(LogOutputType.Power.value)
            self.power_trace_log_filename = open(f'{self.power_trace_log_file_prefix}_power_trace.csv', 'w')
            self.make_log_title_header()
        self.framework_timer.generate_infinity_timer(self.power_snap_shot_interval, self.power_snapShot, 0)

    def make_log_title_header(self):
        if self.param.ENABLE_LOGGING_TOTAL_POWER and self.power_snap_shot_interval != 0:
            if self.product_type == 'client_value' or self.product_type == 'mobile':
                logstr = f'#Index, TotalPower, HostPower, CoretopPower, MediatopPower, Backbone, PCIePhy, NANDIO, NandPower,MEMPower\n'
            else:
                logstr = f'#Index, TotalPower, HostPower, CoretopPower, MediatopPower, BufferTop, Backbone, PCIePhy, NANDIO, NandPower,MEMPower\n'
            self.power_trace_log_filename.write(logstr)

    def power_manager_reset(self):
        self.total_power = 0
        self.total_power_snapshot = 0
        if self.param.ENABLE_DUMP_POWER_VCD:
            self.vcd_manager.record_log(
                int(self.total_power), 'PM', 'total_power')
        self.finish = False
        self.total_power_rms = 0
        self.total_power_sustain = 0

        # Initialize Idle Power
        for ip_name in self.implementation_module.keys():
            self.implementation_module[ip_name].reset_power_context()
            diff = self.implementation_module[ip_name].get_state_power(
                ePowerState.Idle)
            self.total_power += diff

        idle_power_sum = 0
        idle1_power_sum = 0
        idle1_phy_power_sum = 0
        active_idle_power_sum = 0
        background_power_sum = 0
        leakage_power_sum = 0
        off_power_sum = 0
        self.power_manager_cur_state = ePowerManagerState.PS0

        for ip_name in self.implementation_module.keys():
            idle_power_sum += self.implementation_module[ip_name].get_state_power(
                ePowerState.Idle)
            idle1_power_sum += self.implementation_module[ip_name].get_state_power(
                ePowerState.Idle1)
            idle1_phy_power_sum += self.implementation_module[ip_name].get_phy_state_power(
                ePowerState.Idle1)
            background_power_sum += self.implementation_module[ip_name].get_state_power(
                ePowerState.BackGround)
            active_idle_power_sum += self.implementation_module[ip_name].get_state_power(
                ePowerState.ActiveIdle)
            leakage_power_sum += self.implementation_module[ip_name].get_state_power(
                ePowerState.Leakage)
            off_power_sum += self.implementation_module[ip_name].get_state_power(
                ePowerState.Off)

        print('-' * 28 + 'Power Option Information' + '-' * 28)
        print(
            f'Clock Gating {self.param.ENABLE_CLOCK_GATING}, Power Latency {self.param.ENABLE_POWER_LATENCY}, CG Enter Latency {self.param.CLOCKGATING_ENTER_LATENCY}, '
            f'CG Exit Latency {self.param.CLOCKGATING_EXIT_LATENCY}, DYNAMIC POWERSTATE {self.param.ENABLE_DYNAMIC_POWERSTATE}, \n'
            f'Background Trigger Interval {self.param.SC_BACK_GROUND_TRIGGER_INTERVAL}, Active Idle Trigger Interval {self.param.SC_ACTIVE_IDLE_TRIGGER_INTERVAL}, '
            f'PS3 Trigger Interval {self.param.SC_PS3_TRIGGER_INTERVAL}, PS4 Trigger Interval {self.param.SC_PS4_TRIGGER_INTERVAL} \n')
        print(f'Idle total power : {idle_power_sum:.4f}')
        print(f'Idle1 total power : {idle1_power_sum:.4f}')
        print(f'- Idle1 phy/backbon total power : {idle1_phy_power_sum:.4f}')
        print(f'Background Power : {background_power_sum:.4f}')
        print(f'Active Idle Power : {active_idle_power_sum:.4f}')
        print(f'Leakage Power : {leakage_power_sum:.4f}')
        print(f'Off Power : {off_power_sum:.4f}')

    def add_non_implementation_module(self):
        self.implementation_module[self.non_implementation_ip_name] = PowerContext(
            self, self.product_args, self.non_implementation_ip_name)
        module_list = self.feature.get_non_implementation_module_list()
        for module_id, module_name in module_list.items():
            self.total_power += self.implementation_module[self.non_implementation_ip_name].add_sub_module(
                self.non_implementation_ip_name, module_name, module_id)
            self.vcd_manager.add_vcd_dump_var(
                'PM', f'{module_name}_{module_id}', 'int')
            self.activate_non_implementation_module(module_name, module_id)

    def activate_non_implementation_module(self, module_name, module_id):
        self.total_power += yield from self.implementation_module[self.non_implementation_ip_name].activate_sub_module(module_name, module_id)
        if self.param.ENABLE_DUMP_POWER_VCD:
            self.vcd_manager.record_log(
                int(self.total_power * 1000), 'PM', 'total_power')

    def all_off_non_implementation_module(self):
        module_list = self.feature.get_non_implementation_module_list()
        for module_id, module_name in module_list.items():
            yield from self.implementation_module[self.non_implementation_ip_name].deactivate_non_implementation_sub_module(module_name, module_id, ePowerState.Off)

    def add_sub_module(self, ip_name, sub_module_name, feature_id):
        if ip_name not in self.implementation_module:
            self.implementation_module[ip_name] = PowerContext(
                self, self.product_args, ip_name)
        if not isinstance(feature_id, type(list())):
            self.total_power += self.implementation_module[ip_name].add_sub_module(
                ip_name, sub_module_name, feature_id)
        else:
            for id in feature_id:
                self.total_power += self.implementation_module[ip_name].add_sub_module(
                    ip_name, sub_module_name, id)

    def activate_feature(
            self,
            ip_name,
            sub_module_name,
            feature_id,
            runtime_active_power):
        self.implementation_module[ip_name].check_feature_id(
            sub_module_name, feature_id)
        yield self.env.timeout(0)

        if not self.implementation_module[ip_name].is_sub_module_active(sub_module_name, feature_id):

            diff = yield from self.implementation_module[ip_name].activate_sub_module(ip_name, sub_module_name, feature_id, runtime_active_power)
            sub_name = sub_module_name + f'_{feature_id}'
            self.implementation_module[ip_name].add_sub_module_power(
                ip_name, sub_name, diff)
            self.total_power += diff
            if self.param.ENABLE_DUMP_POWER_VCD:
                self.vcd_manager.record_log(
                    int(self.total_power * 1000), 'PM', 'total_power')

    def deactivate_feature(self, ip_name, sub_module_name, feature_id):
        self.implementation_module[ip_name].check_feature_id(
            sub_module_name, feature_id)
        yield self.env.timeout(0)
        if self.implementation_module[ip_name].is_sub_module_active(
                sub_module_name, feature_id):
            diff = yield from self.implementation_module[ip_name].deactivate_sub_module(ip_name, sub_module_name, feature_id)
            sub_name = sub_module_name + f'_{feature_id}'
            self.implementation_module[ip_name].del_sub_module_power(
                ip_name, sub_name, diff)

            self.total_power -= diff
            if self.param.ENABLE_DUMP_POWER_VCD:
                self.vcd_manager.record_log(
                    int(self.total_power * 1000), 'PM', 'total_power')

    def activate_clock_gating(self, ip_name, sub_module_name, feature_id):
        self.implementation_module[ip_name].activate_clock_gating_sub_module(
            ip_name, sub_module_name, feature_id)

    def is_ps0(self):
        return self.power_manager_cur_state == ePowerManagerState.PS0 or \
            self.power_manager_cur_state == ePowerManagerState.PS0ActiveIdle or \
            self.power_manager_cur_state == ePowerManagerState.PS0BackGround

    def is_ps3(self):
        return self.power_manager_cur_state == ePowerManagerState.PS3

    def change_power_state_to_idle(self):
        power_manager_before_state = self.power_manager_cur_state
        if self.power_manager_cur_state != ePowerManagerState.PS0:
            for ip_name in self.implementation_module.keys():
                if self.power_manager_cur_state == ePowerManagerState.PS0BackGround:
                    diff = self.implementation_module[ip_name].change_all_sub_module_power_state(
                        ip_name, ePowerState.BackGround, ePowerState.Idle)
                    self.total_power += diff
                    if self.param.ENABLE_DUMP_POWER_VCD:
                        self.vcd_manager.record_log(
                            int(self.total_power * 1000), 'PM', 'total_power')
                elif self.power_manager_cur_state == ePowerManagerState.PS0ActiveIdle:
                    diff = self.implementation_module[ip_name].change_all_sub_module_power_state(
                        ip_name, ePowerState.ActiveIdle, ePowerState.Idle)
                    self.total_power += diff
                    if self.param.ENABLE_DUMP_POWER_VCD:
                        self.vcd_manager.record_log(
                            int(self.total_power * 1000), 'PM', 'total_power')
                elif self.power_manager_cur_state == ePowerManagerState.PS3:
                    diff = self.implementation_module[ip_name].change_all_sub_module_power_state(
                        ip_name, ePowerState.Leakage, ePowerState.Idle)
                    self.total_power += diff
                    if self.param.ENABLE_DUMP_POWER_VCD:
                        self.vcd_manager.record_log(
                            int(self.total_power * 1000), 'PM', 'total_power')
                elif self.power_manager_cur_state == ePowerManagerState.PS4:
                    diff = self.implementation_module[ip_name].change_all_sub_module_power_state(
                        ip_name, ePowerState.Off, ePowerState.Idle)
                    self.total_power += diff
                    if self.param.ENABLE_DUMP_POWER_VCD:
                        self.vcd_manager.record_log(
                            int(self.total_power * 1000), 'PM', 'total_power')

            self.power_manager_cur_state = ePowerManagerState.PS0
            if self.param.ENABLE_DUMP_POWER_VCD:
                self.vcd_manager.record_log(
                    self.power_manager_cur_state.value, 'PM', 'power_state')
        else:
            # Idle or Idle1 -> Idle
            for ip_name in self.implementation_module.keys():
                diff = self.implementation_module[ip_name].change_all_sub_module_power_state(
                    ip_name, ePowerState.Idle, ePowerState.Idle)
                self.total_power += diff

        return self.power_state_exit_latency[power_manager_before_state]

    def change_power_state_idle_to_leakage(self):
        if self.power_manager_cur_state == ePowerManagerState.PS0:
            for ip_name in self.implementation_module.keys():
                diff = self.implementation_module[ip_name].change_all_sub_module_power_state(
                    ip_name, ePowerState.Idle, ePowerState.Leakage)
                self.total_power -= diff
                if self.param.ENABLE_DUMP_POWER_VCD:
                    self.vcd_manager.record_log(
                        int(self.total_power * 1000), 'PM', 'total_power')
        elif self.power_manager_cur_state == ePowerManagerState.PS0BackGround:
            for ip_name in self.implementation_module.keys():
                diff = self.implementation_module[ip_name].change_all_sub_module_power_state(
                    ip_name, ePowerState.BackGround, ePowerState.Leakage)
                self.total_power -= diff
                if self.param.ENABLE_DUMP_POWER_VCD:
                    self.vcd_manager.record_log(
                        int(self.total_power * 1000), 'PM', 'total_power')
        elif self.power_manager_cur_state == ePowerManagerState.PS0ActiveIdle:
            for ip_name in self.implementation_module.keys():
                diff = self.implementation_module[ip_name].change_all_sub_module_power_state(
                    ip_name, ePowerState.ActiveIdle, ePowerState.Leakage)
                self.total_power -= diff
                if self.param.ENABLE_DUMP_POWER_VCD:
                    self.vcd_manager.record_log(
                        int(self.total_power * 1000), 'PM', 'total_power')

        self.power_manager_cur_state = ePowerManagerState.PS3
        if self.param.ENABLE_DUMP_POWER_VCD:
            self.vcd_manager.record_log(
                self.power_manager_cur_state.value, 'PM', 'power_state')

    def change_power_state_idle_to_background_idle(self):
        if self.power_manager_cur_state == ePowerManagerState.PS0:
            for ip_name in self.implementation_module.keys():
                diff = self.implementation_module[ip_name].change_all_sub_module_power_state(
                    ip_name, ePowerState.Idle, ePowerState.BackGround)
                self.total_power -= diff
                if self.param.ENABLE_DUMP_POWER_VCD:
                    self.vcd_manager.record_log(
                        int(self.total_power * 1000), 'PM', 'total_power')

            self.power_manager_cur_state = ePowerManagerState.PS0BackGround
            if self.param.ENABLE_DUMP_POWER_VCD:
                self.vcd_manager.record_log(
                    self.power_manager_cur_state.value, 'PM', 'power_state')

    def change_power_state_background_to_active_idle(self):
        if self.power_manager_cur_state == ePowerManagerState.PS0BackGround:
            for ip_name in self.implementation_module.keys():
                diff = self.implementation_module[ip_name].change_all_sub_module_power_state(
                    ip_name, ePowerState.BackGround, ePowerState.ActiveIdle)
                self.total_power -= diff
                if self.param.ENABLE_DUMP_POWER_VCD:
                    self.vcd_manager.record_log(
                        int(self.total_power * 1000), 'PM', 'total_power')
            self.power_manager_cur_state = ePowerManagerState.PS0ActiveIdle
            if self.param.ENABLE_DUMP_POWER_VCD:
                self.vcd_manager.record_log(
                    self.power_manager_cur_state.value, 'PM', 'power_state')

    def change_power_state_active_idle_to_leakage(self):
        if self.power_manager_cur_state == ePowerManagerState.PS0ActiveIdle:
            for ip_name in self.implementation_module.keys():
                diff = self.implementation_module[ip_name].change_all_sub_module_power_state(
                    ip_name, ePowerState.ActiveIdle, ePowerState.Leakage)
                self.total_power -= diff
                if self.param.ENABLE_DUMP_POWER_VCD:
                    self.vcd_manager.record_log(
                        int(self.total_power * 1000), 'PM', 'total_power')
            self.power_manager_cur_state = ePowerManagerState.PS3
            if self.param.ENABLE_DUMP_POWER_VCD:
                self.vcd_manager.record_log(
                    self.power_manager_cur_state.value, 'PM', 'power_state')

    def change_power_state_leakage_to_off(self):
        if self.power_manager_cur_state == ePowerManagerState.PS3:
            for ip_name in self.implementation_module.keys():
                diff = self.implementation_module[ip_name].change_all_sub_module_power_state(
                    ip_name, ePowerState.Leakage, ePowerState.Off)
                self.total_power -= diff
                self.vcd_manager.record_log(
                    int(self.total_power * 1000), 'PM', 'total_power')
            if self.param.ENABLE_DUMP_POWER_VCD:
                self.vcd_manager.record_log(
                    self.power_manager_cur_state.value, 'PM', 'power_state')

            self.total_power -= diff
            self.power_manager_cur_state = ePowerManagerState.PS4

            if self.param.ENABLE_DUMP_POWER_VCD:
                self.vcd_manager.record_log(
                    int(self.total_power * 1000), 'PM', 'total_power')
                self.vcd_manager.record_log(
                    self.power_manager_cur_state.value, 'PM', 'power_state')

    def change_power_state_idle_to_off(self):
        if self.power_manager_cur_state == ePowerManagerState.PS0:
            for ip_name in self.implementation_module.keys():
                diff = self.implementation_module[ip_name].change_all_sub_module_power_state(
                    ip_name, ePowerState.Idle, ePowerState.Off)
                self.total_power -= diff
            if self.param.ENABLE_DUMP_POWER_VCD:
                self.vcd_manager.record_log(
                    int(self.total_power * 1000), 'PM', 'total_power')
                self.vcd_manager.record_log(
                    self.power_manager_cur_state.value, 'PM', 'power_state')
        elif self.power_manager_cur_state == ePowerManagerState.PS3:
            for ip_name in self.implementation_module.keys():
                diff = self.implementation_module[ip_name].change_all_sub_module_power_state(
                    ip_name, ePowerState.Idle, ePowerState.Off)
        self.power_manager_cur_state = ePowerManagerState.PS4

    def power_snapShot(self):
        self.update_total_power()

    def calculate_total_power(self):
        for ip_name in self.implementation_module.keys():
            self.total_power_rms += self.implementation_module[ip_name].snapshot_sub_module_power(
                ip_name)
            self.total_power_sustain += self.implementation_module[ip_name].snapshot_sub_module_sustain_power(
                ip_name)

    def get_backbone_power(self, is_sustain_range):
        power = 0
        if is_sustain_range:
            power = self.ip_sustain_power_summary['BACKBONE']
        else:
            power = self.ip_full_range_power_summary['BACKBONE']
        return power

    def get_dram_power(self, is_sustain_range):
        power = 0
        if is_sustain_range:
            power = self.ip_sustain_power_summary['DRAM']
        else:
            power = self.ip_full_range_power_summary['DRAM']
        return power

    def get_pciephy_power(self, is_sustain_range):
        if is_sustain_range:
            power = self.ip_sustain_power_summary['PCIEPHY']
        else:
            power = self.ip_full_range_power_summary['PCIEPHY']
        return power

    def get_ip_sustain_power(self, *module_name_list):
        power_sum = 0
        for module_name in module_name_list:
            try:
                power_sum += self.ip_sustain_power_summary[module_name]
            except KeyError:
                power_sum += 0

        return power_sum

    def get_ip_full_range_power(self, *module_name_list):
        power_sum = 0
        for module_name in module_name_list:
            try:
                power_sum += self.ip_full_range_power_summary[module_name]
            except KeyError:
                power_sum = 0
        return power_sum

    def get_coretop_power(self, is_sustain_range):
        if is_sustain_range:
            power = self.get_ip_sustain_power("BA")
        else:
            power = self.get_ip_full_range_power("BA")
        return power

    def get_mediatop_power(self, is_sustain_range):
        if is_sustain_range:
            power = self.get_ip_sustain_power("JG", "JS", "NFC")
        else:
            power = self.get_ip_full_range_power("JG", "JS", "NFC")
        return power

    def get_buffertop_power(self, is_sustain_range):
        if is_sustain_range:
            power = self.get_ip_sustain_power("DRAMC")
        else:
            power = self.get_ip_full_range_power("DRAMC")
        return power

    def get_total_power(self, is_sustain_range):
        power = self.get_coretop_power(is_sustain_range)
        power += self.get_mediatop_power(is_sustain_range)
        power += self.get_buffertop_power(is_sustain_range)
        power += self.get_backbone_power(is_sustain_range)
        power += self.get_pciephy_power(is_sustain_range)
        if is_sustain_range:
            power += self.get_ip_sustain_power("NFCP")
            power += self.get_ip_sustain_power("NAND")
            if self.product_type == 'general':
                power += self.get_ip_sustain_power("DRAM")
        else:
            power += self.get_ip_full_range_power("NFCP")
            power += self.get_ip_full_range_power("NFCP")
            if self.product_type == 'general':
                power += self.get_ip_full_range_power("DRAM")

        return power

    def print_power(self, workload_name=''):
        sustain_interval = self.analyzer.sustained_perf_measure_end_time - \
            self.analyzer.sustained_perf_measure_start_time

        self.ip_sustain_power_summary = dict()
        self.ip_full_range_power_summary = dict()

        # 마지막 짜투리 계산
        self.calculate_total_power()

        if self.param.ENABLE_POWER:
            file_prefix = self.file_path_generator.get_file_prefix(
                LogOutputType.Power.value)
            with open(f'{file_prefix}.log', 'w') as f:
                line = (
                    '-' *
                    28 +
                    'Power Option Information' +
                    '-' *
                    28 +
                    '\n')
                line += (
                    f'Clock Gating {self.param.ENABLE_CLOCK_GATING}, Power Latency {self.param.ENABLE_POWER_LATENCY}, CG Enter Latency {self.param.CLOCKGATING_ENTER_LATENCY}, '
                    f'CG Exit Latency {self.param.CLOCKGATING_EXIT_LATENCY},  DYNAMIC POWERSTATE {self.param.ENABLE_DYNAMIC_POWERSTATE},'
                    f'Background Trigger Interval {self.param.SC_BACK_GROUND_TRIGGER_INTERVAL}, Active Idle Trigger Interval {self.param.SC_ACTIVE_IDLE_TRIGGER_INTERVAL}, '
                    f'PS3 Trigger Interval {self.param.SC_PS3_TRIGGER_INTERVAL}, PS4 Trigger Interval {self.param.SC_PS4_TRIGGER_INTERVAL} \n')
                line += ('-' *
                         24 +
                         ' Submodule Sustain Average Power' +
                         '-' *
                         24 +
                         '\n')
                line += ('-' * 80 + '\n')
                if sustain_interval != 0:
                    sustainPower_W = self.total_power_sustain / sustain_interval
                    line += f'Sustain power : {sustainPower_W:.7f} W, End : {self.analyzer.sustained_perf_measure_end_time:.1f}, Start : {self.analyzer.sustained_perf_measure_start_time:.1f}' + '\n'
                    line += f'Total Set Sustain power : {(sustainPower_W / 0.85):.7f} W\n'
                    line += ('-' * 80 + '\n')

                    for ip_name in self.implementation_module.keys():
                        sub_avg = self.implementation_module[ip_name].get_sustain_avg_sub_module_power(
                            ip_name)
                        if ip_name == 'NFC':
                            self.ip_sustain_power_summary['NFC'] = self.implementation_module[ip_name].get_sustain_avg_nfc_power()
                            self.ip_sustain_power_summary['NFC_DIN'] = self.implementation_module[ip_name].get_sustain_avg_nfc_din_power()
                            self.ip_sustain_power_summary['NFC_DOUT'] = self.implementation_module[ip_name].get_sustain_avg_nfc_dout_power()
                            self.ip_sustain_power_summary['NFCP'] = self.implementation_module[ip_name].get_sustain_avg_nfcp_power()
                            self.ip_sustain_power_summary['NFCP_DIN'] = self.implementation_module[ip_name].get_sustain_avg_nfcp_din_power()
                            self.ip_sustain_power_summary['NFCP_DOUT'] = self.implementation_module[ip_name].get_sustain_avg_nfcp_dout_power()

                        elif ip_name == 'non_implementation':
                            self.ip_sustain_power_summary['BACKBONE'] = self.implementation_module[ip_name].get_sustain_avg_backbone_power(
                            )
                            self.ip_sustain_power_summary['PCIEPHY'] = self.implementation_module[ip_name].get_sustain_avg_pciephy_power(
                            )
                        elif ip_name == 'MEMC':
                            self.ip_sustain_power_summary['DRAMC'] = self.implementation_module[ip_name].get_sustain_avg_dramc_power(
                            )
                            self.ip_sustain_power_summary['DRAM'] = self.implementation_module[ip_name].get_sustain_avg_dram_power(
                            )
                        else:
                            self.ip_sustain_power_summary[ip_name] = sub_avg

                    line += (f'* Host : {self.get_ip_sustain_power("PCIe"):.7f}\n')
                    line += (f'* Core : {self.get_coretop_power(True):.7f}\n')
                    line += (f' - BA : {self.get_ip_sustain_power("BA"):.7f}\n')
                    line += (f'* Media : {self.get_mediatop_power(True):.7f}\n')
                    if self.product_type != 'general':
                        line += (f' - JG : {self.get_ip_sustain_power("JG"):.7f}\n')
                        line += (f' - JS : {self.get_ip_sustain_power("JS"):.7f}\n')
                    line += (f' - NFC : {self.get_ip_sustain_power("NFC"):.7f}\n')
                    line += (f'  - DIN : {self.get_ip_sustain_power("NFC_DIN"):.7f}\n')
                    line += (f'  - DOUT : {self.get_ip_sustain_power("NFC_DOUT"):.7f}\n')
                    if self.product_type == 'general':
                        line += (f'* Buffer: {self.get_buffertop_power(True):.7f}\n')
                        line += (f' - DRAMC : {self.get_ip_sustain_power("DRAMC"):.7f}\n')
                    line += (f'* BACK BONE : {self.get_backbone_power(True):.7f}\n')
                    line += (f'* PCIe Phy : {self.get_pciephy_power(True):.7f}\n')
                    line += (f'* NFCP/NAND IO : {self.get_ip_sustain_power("NFCP"):.7f}\n')
                    line += (f' - NFCP DIN : {self.get_ip_sustain_power("NFCP_DIN"):.7f}\n')
                    line += (f' - NFCP DOUT : {self.get_ip_sustain_power("NFCP_DOUT"):.7f}\n')
                    line += (f'* NAND : {self.get_ip_sustain_power("NAND"):.7f}\n')
                    if self.product_type == 'general':
                        line += (f'* DRAM : {self.get_ip_sustain_power("DRAM"):.7f}\n')
                    line += (f'* ETC : {(sustainPower_W/0.85 - sustainPower_W):.7f}\n')
                    line += (f'\n')
                    line += f'Total Set power : {(sustainPower_W / 0.85):.7f} W \n'
                    f.write(line + '\n')
                    print(line)

                full_interval = self.analyzer.sim_end_time - self.analyzer.sim_start_time
                if full_interval != 0:
                    line = (
                        '-' *
                        22 +
                        ' Submodule Full Range Average Power ' +
                        '-' *
                        22 +
                        '\n')
                    total_power_W = self.total_power_rms / full_interval
                    line += f'Total power : {total_power_W:.7f} W, End : {self.analyzer.sim_end_time:.1f}, Start : {self.analyzer.sim_start_time:.1f}' + '\n'
                    line += f'Total Set power : {(total_power_W / 0.85):.7f} W\n'
                    line += ('-' * 80 + '\n')

                    for ip_name in self.implementation_module.keys():
                        sub_avg = self.implementation_module[ip_name].get_avg_sub_module_power(
                            ip_name)
                        if ip_name == 'NFC':
                            self.ip_full_range_power_summary['NFC'] = self.implementation_module[ip_name].get_full_avg_nfc_power()
                            self.ip_full_range_power_summary['NFC_DIN'] = self.implementation_module[ip_name].get_full_avg_nfc_din_power()
                            self.ip_full_range_power_summary['NFC_DOUT'] = self.implementation_module[ip_name].get_full_avg_nfc_dout_power()
                            self.ip_full_range_power_summary['NFCP'] = self.implementation_module[ip_name].get_full_avg_nfcp_power()
                            self.ip_full_range_power_summary['NFCP_DIN'] = self.implementation_module[ip_name].get_full_avg_nfcp_din_power()
                            self.ip_full_range_power_summary['NFCP_DOUT'] = self.implementation_module[ip_name].get_full_avg_nfcp_dout_power()
                        elif ip_name == 'non_implementation':
                            self.ip_full_range_power_summary['BACKBONE'] = self.implementation_module[ip_name].get_full_avg_backbone_power(
                            )
                            self.ip_full_range_power_summary['PCIEPHY'] = self.implementation_module[ip_name].get_full_avg_pciephy_power(
                            )
                        elif ip_name == 'MEMC':
                            self.ip_full_range_power_summary['DRAMC'] = self.implementation_module[ip_name].get_full_avg_dramc_power(
                            )
                            self.ip_full_range_power_summary['DRAM'] = self.implementation_module[ip_name].get_full_avg_dram_power(
                            )
                        else:
                            self.ip_full_range_power_summary[ip_name] = sub_avg

                    line += (
                        f'* Host : {self.get_ip_full_range_power("PCIe"):.7f}, {self.max_hosttop_power:.7f}\n')
                    line += (
                        f'* Core : {self.get_coretop_power(False):.7f}, {self.max_coretop_power:.7f}\n')
                    line += (f' - BA : {self.get_ip_full_range_power("BA"):.7f}\n')
                    line += (
                        f'* Media : {self.get_mediatop_power(False):.7f}, {self.max_mediatop_power:.7f}\n')
                    if self.product_type != 'general':
                        line += (f' - JG : {self.get_ip_full_range_power("JG"):.7f}\n')
                        line += (f' - JS : {self.get_ip_full_range_power("JS"):.7f}\n')
                    line += (f' - NFC : {self.get_ip_full_range_power("NFC"):.7f}\n')
                    line += (f' - NFC DIN : {self.get_ip_full_range_power("NFC_DIN"):.7f}\n')
                    line += (
                        f' - NFC DOUT : {self.get_ip_full_range_power("NFC_DOUT"):.7f}\n')
                    if self.product_type == 'general':
                        line += (f'* Buffer : {self.get_buffertop_power(False):.7f}\n')
                        line += (f' - DRAMC : {self.get_ip_full_range_power("DRAMC"):.7f}\n')
                    line += (f'* BACK BONE : {self.get_backbone_power(False):.7f}\n')
                    line += (f'* PCIe Phy : {self.get_pciephy_power(False):.7f}\n')
                    line += (f'* NFCP/NAND IO : {self.get_ip_full_range_power("NFCP"):.7f}\n')
                    line += (f' - NFCP DIN : {self.get_ip_full_range_power("NFCP_DIN"):.7f}\n')
                    line += (f' - NFCP DOUT : {self.get_ip_full_range_power("NFCP_DOUT"):.7f}\n')
                    line += (f'* NAND : {self.get_ip_full_range_power("NAND"):.7f}, {self.max_nand_power:.7f}\n')
                    if self.product_type == 'general':
                        line += (f'* DRAM : {self.get_ip_full_range_power("DRAM"):.7f}\n')
                    line += (f'* ETC : {(total_power_W/0.85 - total_power_W):.7f}\n')
                    line += ('\n')
                    line += (
                        f'Total power : {total_power_W:.7f} W, Max Total Power : {self.max_total_power:.7f} W\n')
                    line += (f'Total Set power : {(total_power_W/0.85):.7f} W\n')

                    f.write(line + '\n')
                    print(line)

        for ip_name in self.implementation_module.keys():
            self.implementation_module[ip_name].reset_context()
