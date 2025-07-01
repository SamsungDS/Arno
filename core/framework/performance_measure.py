from core.framework.analyzer import Analyzer
from core.framework.common import ProductArgs, eCMDType
from core.framework.file_path_generator import FilePathGenerator, LogOutputType


class PerformanceMeasure:
    def __new__(cls, product_args: ProductArgs = None):
        if not hasattr(cls, 'instance'):
            cls.instance = super().__new__(cls)
        if product_args is not None:
            product_args.set_args_to_class_instance(cls.instance)
            cls.instance.init_performance_measure()
        return cls.instance

    def init_performance_measure(self):
        self.analyzer = Analyzer()
        self.file_path_generator = FilePathGenerator()
        self.output_dir_name = self.file_path_generator.output_dir_name

    def init_record(self):
        self.prev_data_transfer_mapunit_count = dict()
        self.prev_done_cmd_count = dict()

        self.read_perf_record = dict()
        self.write_perf_record = dict()

        self.file_prefix = self.file_path_generator.get_file_prefix(
            LogOutputType.Performance.value)
        self.base_time = self.env.now

    def record_perf(self, cmd_type):
        if cmd_type not in self.prev_data_transfer_mapunit_count:
            self.prev_data_transfer_mapunit_count[cmd_type] = 0
            self.prev_done_cmd_count[cmd_type] = 0

        perf_MB_s = ((self.analyzer.data_transfer_mapunit_count[cmd_type] - self.prev_data_transfer_mapunit_count[cmd_type])
                     * self.param.MAPUNIT_SIZE) // self.param.PERF_MEASURE_INTERVAL_MS // 1e3  # MB/s
        perf_KIOPs = (self.analyzer.command_done_count[cmd_type] -
                      self.prev_done_cmd_count[cmd_type]) // self.param.PERF_MEASURE_INTERVAL_MS  # KIOPs/s

        self.prev_data_transfer_mapunit_count[cmd_type] = self.analyzer.data_transfer_mapunit_count[cmd_type]
        self.prev_done_cmd_count[cmd_type] = self.analyzer.command_done_count[cmd_type]

        return perf_MB_s, perf_KIOPs

    def start_perf_measure(self):
        self.init_record()
        self.env.process(self.measure_perf())

    def measure_perf(self):
        interval = self.param.PERF_MEASURE_INTERVAL_MS * 1e6

        if self.param.ENABLE_PERFORMANCE_RECORD:
            log_file = open(
                f'{self.file_prefix}_{self.param.PERF_MEASURE_INTERVAL_MS}ms.log', 'w')
            print(
                'Time(ns),Read(MB/s),Read(KIOPs),Write(MB/s),Write(KIOPs)',
                file=log_file)

        while True:
            yield self.env.timeout(interval)

            read_perf_MB_s, read_perf_KIOPs = self.record_perf(eCMDType.Read)
            write_perf_MB_s, write_perf_KIOPs = self.record_perf(
                eCMDType.Write)

            if read_perf_MB_s == 0 and write_perf_MB_s == 0:
                break

            if self.param.ENABLE_PERFORMANCE_RECORD_TO_TERMINAL:
                print(
                    f'\n[{int(self.env.now - interval):,d} ns ~ {int(self.env.now):,f} ns]',
                    end='')
                print(
                    f'\tRead : {read_perf_MB_s:.2f} MB/s, {read_perf_KIOPs:f} KIOPs',
                    end='')
                print(
                    f'\tWrite : {write_perf_MB_s:.2f} MB/s, {write_perf_KIOPs:f} KIOPs')
                if self.param.ENABLE_WAF_RECORD:
                    print(
                        f'WAF : {(self.analyzer.calculate_waf()):.2f}', end='')

            if self.param.ENABLE_PERFORMANCE_RECORD:
                print(
                    f'{int(self.env.now - self.base_time)},{read_perf_MB_s:.2f},{read_perf_KIOPs:d},{write_perf_MB_s:.2f},{write_perf_KIOPs:d}',
                    file=log_file)

        if self.param.ENABLE_PERFORMANCE_RECORD:
            log_file.close()
