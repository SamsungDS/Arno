import sys

from product.general.framework.simulation_env import StorageSimulationEnv


class PrintWorkload:
    def __init__(self, env: StorageSimulationEnv):
        self.env = env
        self.param = self.env.param
        self.qd = None
        self.is_file_prefix_set_by_user = False
        self.workload_name = None

    def print_sim_started(self, workload_name):
        print('-' * 100)
        print('-' * 100)
        print(f'\'{workload_name}\' is started, QD: {self.qd}')
        print('-' * 100)
        print('-' * 100)

    def set_qd(self, qd):
        self.qd = qd

    def set_file_prefix(self, file_prefix, by_user=True):
        self.is_file_prefix_set_by_user = by_user
        assert self.qd is not None
        self.env.set_file_prefix(file_prefix, self.qd)

    def start(self, workload_name):
        if not self.is_file_prefix_set_by_user:
            self.set_file_prefix(workload_name, by_user=False)
        self.print_sim_started(workload_name)
        self.workload_name = workload_name

    def result(self, workload_name=None, skip_report=False):
        emphasis = '\033[1m'
        if sys.platform == 'win32':
            emphasis += '\033[7m'
        else:
            emphasis += '\033[5m'

        is_success = self.env.success()
        workload_name = self.workload_name if workload_name is None else workload_name
        self.env.report_output(workload_name, is_success, skip_report)

        if is_success:
            print(f'\n{emphasis}\033[32m[INFO] Simulation Success\033[0m')
        else:
            print(
                f'\n{emphasis}\033[31m[ERROR] Simulation Fail, Something Wrong...\033[0m')
            self.env.vcd_manager.vcd_manager.close_vcd_file()
            breakpoint()
        return is_success
