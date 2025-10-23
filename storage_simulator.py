import os

from core.config.basic_workload_types import BasicWorkload, PreDefinedWorkload
from core.script.workload_reader import *
from product.general.config.argument import args
from product.general.config.storage_parameters import Parameter
from product.general.framework.simulation_env import StorageSimulationEnv
from product.general.framework.simulation_runner import SimulationRunner


def get_basic_workload():
    pre_defined_workload = PreDefinedWorkload(param)
    param.ENABLE_tHost = 1

    workload_name = param.args.pre_defined_workload

    if workload_name:
        try:
            workload_patterns: tuple[BasicWorkload] = eval(
                f'pre_defined_workload.{workload_name}')
        except SyntaxError:
            assert 0, f'not defined workload: {workload_name}'
    else:
        # Assign pre-defined workload or make custom workload
        workload_patterns: tuple[BasicWorkload] = pre_defined_workload.performance

    if workload_name is None:
        if range_bytes_str := param.args.range_bytes:
            for workload in workload_patterns:
                workload.set_range_bytes(range_bytes_str)

    workload_list = [workload for workload in workload_patterns]
    return workload_list


def get_benchmark_workload():
    if param.WORKLOAD_TYPE == 'pcmark10':
        workload_reader = PCMARK10(param)
    else:
        assert False, f'invalid workload: {param.WORKLOAD_TYPE}'
    workload_list = workload_reader.workload_list
    max_lpn = int(math.ceil(workload_reader.workload_max_offset / param.MAPUNIT_SIZE))
    map_file = workload_reader.meta_map_file

    return workload_list, max_lpn, map_file


def start_sim():
    simulation_env = StorageSimulationEnv()
    runner = SimulationRunner(simulation_env)
    runner.print_nand_option()

    if param.WORKLOAD_TYPE == 'basic':
        workload_list = get_basic_workload()
    else:
        workload_list, max_lpn, map_file = get_benchmark_workload()

    runner.set_mapping_table(runner.get_max_mapping_table(workload_list), param.SUSTAINED)

    for workload in workload_list:
        runner.set_qd(workload.qd)
        runner.run_workload(workload)


if __name__ == "__main__":
    # Activate ANSI escape character for Windows; cf) os.name == 'nt' or
    # sys.platform == 'win32'
    os.system("")
    param = Parameter(args)
    start_sim()
