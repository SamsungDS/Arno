from collections import deque

from core.backbone.address_map import AddressMap
from core.framework.command_latency_logger import CommandLatencyLogger
from core.framework.command_record import (CommandItem, CommandRecorder,
                                           CommandRecordFileGenerator,
                                           QoSRecorder)
from core.framework.common import ProductArgs, eCacheResultType, eCMDType
from core.framework.data_printer import DataPrinter
from core.framework.diagram_generator import DiagramGenerator
from core.framework.file_path_generator import FilePathGenerator, LogOutputType
from core.framework.progress_printer import ProgressPrinter


class Analyzer:
    def __new__(cls, product_args: ProductArgs = None):
        if not hasattr(cls, 'instance'):
            cls.instance = super().__new__(cls)
        if product_args is not None:
            product_args.set_args_to_class_instance(cls.instance)
            cls.instance.init_analyzer()
        return cls.instance

    def init_analyzer(self, tc_count=1, tc_size=1):
        self.address_map = AddressMap()
        self.file_path_generator = FilePathGenerator(self.param)
        self.module_list = list()
        self.file_name_prefix = ''
        self.reset_analyzer(tc_count, tc_size)

    def register_module(self, module):
        self.module_list.append(module)

    def initialize_analyzer_dict(self):
        cur_dict = dict()
        cur_dict[eCMDType.Read] = 0
        cur_dict[eCMDType.Write] = 0
        cur_dict[eCMDType.Flush] = 0

        return cur_dict

    def reset_analyzer(self, tc_count=1, tc_size=1):
        self.printer = ProgressPrinter(self.param, tc_count, tc_size, 1000)
        self.expected_total_command_issue_count = 0
        self.total_command_issue_count = 0
        self.total_command_done_count = 0
        self.total_command_done_size = 0

        self.command_issue_count = self.initialize_analyzer_dict()
        self.command_done_count = self.initialize_analyzer_dict()
        self.sustained_command_done_count = self.initialize_analyzer_dict()
        self.data_transfer_mapunit_count = self.initialize_analyzer_dict()
        self.sustained_data_transfer_mapunit_count = self.initialize_analyzer_dict()

        self.is_sustained_perf_measure_state = False
        self.sustained_perf_measure_start_time = -1
        self.sustained_perf_measure_end_time = -1
        self.is_sim_measure_state = False
        self.sim_start_time = -1
        self.sim_end_time = -1

        self.command_latency_logger = CommandLatencyLogger()
        self.cmd_cache_hit_log = eCacheResultType.get_dict()

        self.command_record = CommandRecorder(tc_count)
        self.command_record_file_generator = None
        if self.param.ENABLE_QOS:
            self.qos_record = QoSRecorder()
            self.qos_record.set_qos_candidates(self.param.QOS_CANDIDATES)
        if self.param.ENABLE_COMMAND_RECORD:
            self.command_record_file_generator = CommandRecordFileGenerator(
                self.file_path_generator.get_file_prefix(LogOutputType.Command_Record.value))

        if tc_count != 0:
            self.set_expected_cmd_count(tc_count)

        self.total_nand_program_count = 0
        self.total_host_nand_program_count = 0

        self.diagram_generator = DiagramGenerator(
            self.param, self.file_path_generator.get_file_prefix(
                LogOutputType.Diagram.value))

    def calculate_waf(self):
        try:
            return self.total_nand_program_count / self.total_host_nand_program_count
        except ZeroDivisionError:
            return 1

    def register_packet_transfer(
            self,
            src,
            dst,
            src_fifo_id,
            src_domain_id,
            dst_fifo_id,
            dst_domain_id,
            description='SQ'):
        self.diagram_generator.increase_packet_transfer(
            src, dst, src_fifo_id, src_domain_id, dst_fifo_id, dst_domain_id, description)

    def register_packet_transfer_with_submodule(
            self,
            module_name,
            src,
            dst,
            submodule_latency,
            description,
            is_send_packet=True):
        self.diagram_generator.increase_packet_transfer_with_submodule(
            module_name, src, dst, submodule_latency, description, is_send_packet)

    def generate_diagram(self):
        self.diagram_generator.generate_diagram()

    def set_expected_cmd_count(self, value):
        self.expected_total_command_issue_count = value

    def set_sim_start_time(self):
        self.sim_start_time = self.env.now
        self.is_sim_measure_state = True

    def set_sim_end_time(self):
        self.sim_end_time = self.env.now
        self.is_sim_measure_state = False

    def increase_cmd_issue(self, packet):
        cmd_type = packet['cmd_type']
        lpn_size = packet['remain_lpn_cnt'] if 'remain_lpn_cnt' in packet else packet['remain_g_lpn_count']
        start_lpn = packet['start_lpn'] if 'start_lpn' in packet else packet['start_lpn']
        init_time = packet['init_time']
        cmd_id = packet['cmd_id']

        self.total_command_issue_count += 1
        self.command_issue_count[cmd_type] += 1
        if cmd_id != -1:
            self.command_record.update_issued_command_log(
                cmd_id, cmd_type, lpn_size * self.param.FTL_MAP_UNIT_SIZE, start_lpn, init_time)

    def get_cmd_cache_hit_result(self, total_lpn_cnt, cache_result):
        assert sum(cache_result.values()) == total_lpn_cnt
        if cache_result[eCacheResultType.logical_temporal] == total_lpn_cnt:
            return eCacheResultType.logical_temporal
        elif cache_result[eCacheResultType.logical_spatial] == total_lpn_cnt:
            return eCacheResultType.logical_spatial
        elif (cache_result[eCacheResultType.logical_temporal] +
                cache_result[eCacheResultType.logical_spatial]) == total_lpn_cnt:
            return eCacheResultType.logical_mix
        elif cache_result[eCacheResultType.physical] == total_lpn_cnt:
            return eCacheResultType.physical
        elif (cache_result[eCacheResultType.logical_temporal] +
              cache_result[eCacheResultType.logical_spatial] +
              cache_result[eCacheResultType.physical]) == total_lpn_cnt:
            return eCacheResultType.logical_physical_mix
        else:
            if cache_result[eCacheResultType.miss_tlc] != 0:
                return eCacheResultType.miss_tlc
            elif cache_result[eCacheResultType.miss_mlc] != 0:
                return eCacheResultType.miss_mlc
            elif cache_result[eCacheResultType.miss_slc] != 0:
                return eCacheResultType.miss_slc
            return eCacheResultType.miss

    def set_perf_measure_time(self):
        if self.total_command_done_count == self.expected_total_command_issue_count // 4:
            self.sustained_perf_measure_start_time = self.env.now
            self.is_sustained_perf_measure_state = True

        if self.total_command_done_count == self.expected_total_command_issue_count * 3 // 4:
            self.sustained_perf_measure_end_time = self.env.now
            self.is_sustained_perf_measure_state = False

        if self.total_command_done_count == self.expected_total_command_issue_count:
            self.sim_end_time = self.env.now
            self.is_sim_measure_state = False

    def record_command_latency_log(self, cmd_id, cache_hit_result):
        if cmd_id == -1:
            return

        if cache_hit_result is not None:
            self.cmd_cache_hit_log[cache_hit_result] += 1
        self.command_record.update_done_command_log(
            cmd_id, self.env.now, cache_hit_result)
        cmd_item: CommandItem = self.command_record.get_command_item(cmd_id)
        self.command_latency_logger.record_latency(
            cmd_item.get_type(), cmd_item.get_size(), cmd_item.get_latency())

        if self.param.ENABLE_QOS:
            self.qos_record.record_qos(
                cmd_item.get_type(), cmd_item.get_latency())

        if self.command_record_file_generator is not None:
            self.command_record_file_generator.record(cmd_item)

        self.command_record.delete(cmd_id)

    def increase_cmd_done(self, cmd_type, cmd_id=-1, cache_hit_result=None):
        if cmd_type == eCMDType.Erase:
            return

        self.total_command_done_count += 1
        self.command_done_count[cmd_type] += 1
        if self.is_sustained_perf_measure_state:
            self.sustained_command_done_count[cmd_type] += 1

        if self.printer.is_tqdm_printer:
            self.printer.print_sim_progress(True)
        else:
            if cmd_id != -1 and cmd_type in (eCMDType.Write, eCMDType.Read):
                self.total_command_done_size += self.command_record.get_command_item(
                    cmd_id).get_size()

            self.printer.print_sim_progress(
                self.total_command_done_count,
                self.total_command_done_size)

        try:
            self.record_command_latency_log(cmd_id, cache_hit_result)
        except BaseException:
            print(f'CMD Latency Record Failed. {cmd_type}, {cmd_id:d}')
        self.set_perf_measure_time()

    def increase_data_transfer_done_count(self, cmd_type, mapunit_count=1):
        self.data_transfer_mapunit_count[cmd_type] += mapunit_count
        if self.is_sustained_perf_measure_state:
            self.sustained_data_transfer_mapunit_count[cmd_type] += mapunit_count

    def calculate_performance(self, cmd_type, sustain_perf_flag=False):
        if sustain_perf_flag:
            perf_measure_time_s = (
                self.sustained_perf_measure_end_time - self.sustained_perf_measure_start_time) / 1e9
            data_transfer_mapunit_count = self.sustained_data_transfer_mapunit_count[cmd_type]
            cmd_done_count = self.sustained_command_done_count[cmd_type]
        else:
            perf_measure_time_s = (
                self.sim_end_time - self.sim_start_time) / 1e9
            data_transfer_mapunit_count = self.data_transfer_mapunit_count[cmd_type]
            cmd_done_count = self.command_done_count[cmd_type]

        perf_data = (
            data_transfer_mapunit_count *
            self.param.MAPUNIT_SIZE /
            perf_measure_time_s)
        perf_cmd = (cmd_done_count / perf_measure_time_s)

        perf_MBs = perf_data / 1e6
        perf_MiBs = perf_data / (1024 ** 2)
        perf_KIOPs = perf_cmd / 1e3
        return perf_MBs, perf_MiBs, perf_KIOPs

    def print_perf(self, workload_type):
        self.print_debug_info()
        file_prefix = self.file_path_generator.get_file_prefix(
            LogOutputType.Performance.value)
        with open(f'{file_prefix}.log', 'w') as f:
            read_tag = ['SR', 'RR', 'Read', 'R', 'read', 'rr', 'sr']
            write_tag = ['SW', 'RW', 'Write', 'W', 'write', 'sw', 'rw']

            cmd_type_list = deque()
            if workload_type in read_tag:
                cmd_type_list.append(eCMDType.Read)
            elif workload_type in write_tag:
                cmd_type_list.append(eCMDType.Write)
            else:
                cmd_type_list.append(eCMDType.Read)
                cmd_type_list.append(eCMDType.Write)

            data = [
                ["Description", "MB/s", "KIOPs", "MiB/s"],
            ]
            for cmd_type in cmd_type_list:
                perf_MBs, perf_MiBs, perf_KIOPs = self.calculate_performance(
                    cmd_type, sustain_perf_flag=False)
                data.append([f'{cmd_type.name}, All',
                             f'{perf_MBs:.2f} MB/s',
                             f'{perf_KIOPs:.2f} KIOPs',
                             f'{perf_MiBs:.2f} MiB/s'])
                try:
                    sustain_perf_MBs, sustain_perf_MiBs, sustain_perf_KIOPs = self.calculate_performance(
                        cmd_type, sustain_perf_flag=True)
                    data.append([f'{cmd_type.name}, Interquartile (IQR)',
                                 f'{sustain_perf_MBs:.2f} MB/s',
                                 f'{sustain_perf_KIOPs:.2f} KIOPs',
                                 f'{sustain_perf_MiBs:.2f} MiB/s'])
                except BaseException:
                    pass

            DataPrinter.print_performance(data, workload_type, f)

            if self.param.ENABLE_WAF_RECORD:
                line = f'** WAF : {self.calculate_waf():.2f}'
                f.write(line + '\n')
                print(line)

    def print_elapsed_time(self):
        print(f'* {self.printer.get_elapsed_time_format_line()} Elapsed')
        self.printer.close()

    def print_performance(self, workload_type=None):
        if workload_type is None:
            self.print_perf('Read')
            self.print_perf('Write')
        else:
            self.print_perf(workload_type)

    def print_latency(self):
        self.command_latency_logger.print_latency()

    def print_module_utilization(self, utilization_file, module):
        sustain_perf_time = self.sustained_perf_measure_end_time - \
            self.sustained_perf_measure_start_time
        if sustain_perf_time == 0:
            return

        for submodule in module.submodule_mapper.map.values():
            ip_name = submodule.submodule_info.ip_name
            submodule_name = submodule.submodule_info.name
            consumed_time = submodule.submodule_info.consumed_time

            utilization_line = f'{ip_name}_{submodule_name},{consumed_time * 100 / sustain_perf_time:.2f}\n'
            utilization_file.write(utilization_line)
            submodule.reset_utilization()

    def print_allocator_utilization(self, utilization_file, allocator):
        from core.framework.allocator import SimpyResourceAllocator
        if not isinstance(allocator, SimpyResourceAllocator):
            return

        allocator_analyzer = allocator.resource_analyzer
        lifetime_sum = allocator_analyzer.total_resource_lifetime
        utilization = (lifetime_sum *
                       100 /
                       (((self.sim_end_time -
                          self.sim_start_time) *
                         allocator.resource_count)))
        utilization_line = f'{allocator.resource_type.name},{utilization:.2f}\n'
        utilization_file.write(utilization_line)
        allocator_analyzer.reset_utilization()

    def print_utilization(self, workload_type=''):
        if not self.param.RECORD_SUBMODULE_UTILIZATION:
            return

        file_prefix = self.file_path_generator.get_file_prefix(
            LogOutputType.Utilization.value)
        with open(f'{file_prefix}_utilization.csv', 'w') as utilization_file:
            utilization_file.write('Module Name,Utilization(%)\n')
            for module in self.module_list:
                self.print_module_utilization(utilization_file, module)

            from core.framework.allocator_mediator import AllocatorMediator
            allocator_mediator = AllocatorMediator()
            for allocator in allocator_mediator.allocator_list:
                self.print_allocator_utilization(utilization_file, allocator)

    def print_cache_hit_result(self):
        data = [
            ['Cache Result Type', 'Count', '%']
        ]
        total_read_cmd_count = sum(self.cmd_cache_hit_log.values())
        for cache_hit_type, count in self.cmd_cache_hit_log.items():
            try:
                ratio = (count / total_read_cmd_count) * 100
                data.append([f'{cache_hit_type.name}',
                            f'{count:d}', f'{ratio:.2f} %'])
            except ZeroDivisionError:
                data.append([f'{cache_hit_type.name}', f'{count:d}', 'None'])
        DataPrinter.print_cache_hit_result(total_read_cmd_count, data)

    def check_all_cmd_done(self):
        if self.command_record_file_generator is not None:
            self.command_record_file_generator.file_close()
        print('* Check all commands done :', end='')
        if self.expected_total_command_issue_count == self.total_command_done_count:
            print(' Success')
            return True
        else:
            print(
                ' Fail, Expected CMD %d but %d received' %
                (self.expected_total_command_issue_count,
                 self.total_command_done_count))
            return False

    def print_debug_info(self):
        for module in self.module_list:
            module.hanging_job_info.print_hanging_job_info()
            for submodule in module.submodule_mapper.map.values():
                try:
                    if submodule.submodule_info.queue_job_count != 0:
                        print(
                            submodule.submodule_info.ip_name,
                            submodule.submodule_info.name,
                            end=',')
                        for queue in submodule.submodule_info.queue:
                            print(len(queue), end=' ')
                        print()
                except AttributeError:
                    pass
