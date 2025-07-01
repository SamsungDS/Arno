from core.framework.data_printer import DataPrinter


class CommandLatencyLogger:
    def __init__(self):
        self.command_latency_log = dict()

    def record_latency(self, cmd_type, cmd_size, latency):
        if cmd_type not in self.command_latency_log:
            self.command_latency_log[cmd_type] = dict()

        if cmd_size not in self.command_latency_log[cmd_type]:
            self.command_latency_log[cmd_type][cmd_size] = {
                'min': float('inf'), 'max': -1, 'latency_sum': 0, 'count': 0}

        if self.command_latency_log[cmd_type][cmd_size]['min'] > latency:
            self.command_latency_log[cmd_type][cmd_size]['min'] = latency
        if self.command_latency_log[cmd_type][cmd_size]['max'] < latency:
            self.command_latency_log[cmd_type][cmd_size]['max'] = latency
        self.command_latency_log[cmd_type][cmd_size]['latency_sum'] += latency
        self.command_latency_log[cmd_type][cmd_size]['count'] += 1

    def print_latency(self):
        data = [['CMD Type',
                 'Size(B)',
                 'Min Latency',
                 "Avg Latency",
                 'Max Latency']]
        for cmd_type, size_dict in self.command_latency_log.items():
            for size, attribute_dict in size_dict.items():
                min_latency = int(attribute_dict['min'])
                avg_latency = int(
                    attribute_dict['latency_sum'] /
                    attribute_dict['count'])
                max_latency = int(attribute_dict['max'])
                data.append([f'{cmd_type.name}',
                             f'{size:d}B',
                             f'{min_latency:d}ns',
                             f'{avg_latency:d}ns',
                             f'{max_latency:d}ns'])

        DataPrinter.print_latency(data)
