

class DataPrinter:
    COLOR_CODE = {'red': '\033[31m',
                  'green': '\033[32m',
                  'yellow': '\033[33m',
                  'blue': '\033[34m',
                  'purple': '\033[35m',
                  'turquoise': '\033[36m',
                  'white': '\033[37m',
                  }
    BOLD_CODE = '\033[1m'
    RESET_CODE = '\033[0m'

    @staticmethod
    def print(line, indent=2, f=None):
        print(' ' * indent + line)
        if f is not None:
            f.write(' ' * indent + line + '\n')

    @staticmethod
    def print_bold(line, color='blue', f=None):
        code = DataPrinter.COLOR_CODE[color]
        print_line = f'{DataPrinter.BOLD_CODE}{code}{line}{DataPrinter.RESET_CODE}{DataPrinter.RESET_CODE}'
        print(print_line)
        if f is not None:
            f.write(line + '\n')

    @staticmethod
    def find_max_colwidth(data):
        col_widths = [max(len(str(item)) for item in col)
                      for col in zip(*data)]
        max_col_width = max(col_widths)
        return max_col_width

    @staticmethod
    def generate_header(data):
        max_col_width = DataPrinter.find_max_colwidth(data)
        header = " | ".join([str(data[0][i]).center(max_col_width)
                            for i in range(len(data[0]))])
        return header

    @staticmethod
    def print_header(header, f=None):
        DataPrinter.print(f'|{header}|', f=f)
        DataPrinter.print("-" * (len(header) + 2), f=f)

    @staticmethod
    def print_items(data, f=None):
        max_col_width = DataPrinter.find_max_colwidth(data)
        header = DataPrinter.generate_header(data)
        for row in data[1:]:
            row_line = " | ".join(
                [str(row[i]).center(max_col_width) for i in range(len(row))])
            DataPrinter.print(f'|{row_line}|', f=f)
        DataPrinter.print("-" * (len(header) + 2), f=f)

    @staticmethod
    def print_performance(data, workload_type, output_file):
        DataPrinter.print_bold('* Print Performance', f=output_file)
        header = DataPrinter.generate_header(data)
        center_pos = len(header) // 2
        workload_type_len = len(workload_type) // 2
        DataPrinter.print('-' *
                          (center_pos -
                           workload_type_len +
                           1) +
                          workload_type +
                          '-' *
                          (center_pos -
                           workload_type_len +
                           1), f=output_file)
        DataPrinter.print_header(header, f=output_file)
        DataPrinter.print_items(data, f=output_file)

    @staticmethod
    def print_table(data):
        header = DataPrinter.generate_header(data)
        DataPrinter.print('-' * (len(header) + 2))
        DataPrinter.print_header(header)
        DataPrinter.print_items(data)

    @staticmethod
    def print_latency(data):
        DataPrinter.print_bold(' * Print Latency')
        DataPrinter.print_table(data)

    @staticmethod
    def print_cache_hit_result(total_read_cmd_count, data):
        DataPrinter.print_bold('* Print Read CMD Cache Hit Result')
        DataPrinter.print(f'- Total Read Cmd Count : {total_read_cmd_count}')
        DataPrinter.print_table(data)

    @staticmethod
    def print_memc_log(TAT, TRT, TWT, data):
        DataPrinter.print_bold('* Print Memory Access Log')
        TAT, TRT, TWT = int(TAT), int(TRT), int(TWT)
        DataPrinter.print(f'- Total Memory Access Time: {TAT:d} ns')
        DataPrinter.print(f'- Total Memory Read Time: {TRT:d} ns')
        DataPrinter.print(f'- Total Memory Write Time: {TWT:d} ns')
        DataPrinter.print('- Each resource type access time table')
        DataPrinter.print_table(data)
