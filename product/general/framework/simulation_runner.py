import sys
from math import ceil

from product.general.framework.print_workload import PrintWorkload
from product.general.framework.simulation_env import StorageSimulationEnv


class SimulationRunner:
    def __init__(
            self,
            env: StorageSimulationEnv,
            pcmark_workload=False,
            snappiness_workload=False):
        self.env = env
        self.param = self.env.param
        self.qd = None
        self.print_workload = PrintWorkload(self.env)

    def print_nand_option(self) -> None:
        emphasis = '\033[1m' + \
            ('\033[7m' if sys.platform == 'win32' else '\033[5m')
        print(
            f'\n{emphasis}\033[32m[INFO] '
            f'{self.param.NAND_PRODUCT} '
            f'Cache Read {"Enable" if self.param.ENABLE_NAND_CACHE_READ else "Disable"}, '
            f'Logical Cache {"Enable" if self.param.ENABLE_LOGICAL_CACHE else "Disable"} \033[0m')

    def set_qd(self, qd):
        if qd is None:
            qd = self.param.HOST_QD_DEFAULT
        self.qd = qd
        self.env.set_qd(qd)
        self.print_workload.set_qd(qd)

    def set_mapping_table(self, test_size, sustained=False):
        self.env.set_mapping_table(test_size, sustained)

    def get_range_bytes(self, workload_type, workload):
        if workload_type == 'basic':
            range_bytes = workload.pattern.range_bytes
        else:
            df = workload.df
            workload_io_cmd = df.loc[(df['IO Type'] == 'Write') | (df['IO Type'] == 'Read'), ['Min Offset', 'Size (B)']]

            def calculate_aligned_size(min_offset, size):
                return int(ceil((min_offset + size) / self.param.FTL_MAP_UNIT_SIZE) - (
                            min_offset // self.param.FTL_MAP_UNIT_SIZE)) * self.param.FTL_MAP_UNIT_SIZE
            range_bytes = workload_io_cmd.apply(lambda x: calculate_aligned_size(x['Min Offset'], x['Size (B)']), axis=1).sum()
        return range_bytes

    def get_max_mapping_table(self, workload_list):
        max_map_size = 0
        for workload in workload_list:
            range_bytes = self.get_range_bytes(self.param.WORKLOAD_TYPE, workload)
            if range_bytes // self.param.FTL_MAP_UNIT_SIZE > max_map_size:
                max_map_size = range_bytes // self.param.FTL_MAP_UNIT_SIZE
        return max_map_size

    def set_file_prefix(self, workload_name):
        assert self.qd is not None
        self.print_workload.set_file_prefix(workload_name)

    def start_sim(self, workload, skip_perf_measure):
        cmd_count = self.param.SIM_CMD_COUNT

        self.print_workload.start(workload.name)
        self.env.start(workload, cmd_count, skip_perf_measure)

    def debug(self):
        self.env.print_debug_info()

    def run_workload(
            self,
            workload,
            skip_report=False,
            reset_log=True,
            skip_perf_measure=False):
        self.env.start_power_snapshot(workload, self.qd)
        assert self.qd is not None

        if reset_log:
            self.env.reset_log()

        self.start_sim(workload, skip_perf_measure)
        self.print_workload.result(skip_report=skip_report)
