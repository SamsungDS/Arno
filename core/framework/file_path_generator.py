import os
from enum import Enum
from pathlib import Path


class LogOutputType(Enum):
    Performance = 0
    Utilization = 1
    IO_Log = 2
    Diagram = 3
    Command_Record = 4
    Power = 5


class FilePathGenerator:
    def __new__(cls, param=None):
        if not hasattr(cls, 'instance'):
            cls.instance = super().__new__(cls)
        if param is not None:
            cls.instance.param = param
            cls.instance.init_generator()

        return cls.instance

    def init_generator(self):
        self.output_dir_name = 'output'
        self.file_prefix = ''
        self.sub_output_dir_name = list()
        try:
            self.folder_name = self.param.OUTPUT_FOLDER_NAME
        except AttributeError:
            self.folder_name = None

        Path(self.output_dir_name).mkdir(parents=True, exist_ok=True)
        if self.folder_name is not None:
            Path(
                os.path.join(
                    '.',
                    self.output_dir_name,
                    self.folder_name)).mkdir(
                parents=True,
                exist_ok=True)
            for output_type in LogOutputType:
                self.sub_output_dir_name.append(output_type.name)
                Path(
                    os.path.join(
                        '.',
                        self.output_dir_name,
                        self.folder_name,
                        output_type.name)).mkdir(
                    parents=True,
                    exist_ok=True)
        else:
            for output_type in LogOutputType:
                self.sub_output_dir_name.append(output_type.name)
                Path(
                    os.path.join(
                        '.',
                        self.output_dir_name,
                        output_type.name)).mkdir(
                    parents=True,
                    exist_ok=True)

    def set_file_prefix(self, workload_name, qd):
        self.file_prefix = f'{workload_name}_QD{qd}_{self.param.NAND_PRODUCT}_channel{self.param.CHANNEL:d}_way{self.param.WAY:d}_plane{self.param.PLANE:d}_NANDIO{self.param.NAND_IO_Mbps:d}'

    def get_file_prefix(self, log_type):
        if self.folder_name is not None:
            return os.path.join(
                '.',
                self.output_dir_name,
                self.folder_name,
                self.sub_output_dir_name[log_type],
                self.file_prefix)
        else:
            return os.path.join(
                '.',
                self.output_dir_name,
                self.sub_output_dir_name[log_type],
                self.file_prefix)
