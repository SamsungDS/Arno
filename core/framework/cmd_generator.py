from core.framework.common import eCMDType


class CommandClassifier:
    workload_type_dict = {'Read': eCMDType.Read,
                          'Write': eCMDType.Write}

    @classmethod
    def translate_str_to_cmd_type(cls, io_type):
        if isinstance(io_type, str):
            io_type = cls.workload_type_dict[io_type]
        return io_type

    @classmethod
    def is_write_cmd(cls, io_type):
        return cls.translate_str_to_cmd_type(io_type) == eCMDType.Write

    @classmethod
    def is_read_cmd(cls, io_type):
        return cls.translate_str_to_cmd_type(io_type) == eCMDType.Read


class CommandGenerator:
    def __init__(self, env, param):
        self.env = env
        self.param = param

    def generate_write_cmd(
            self,
            cmd_id,
            size,
            min_offset,
            base_lba=0,
            init_time=None,
            host_stream_id=0):
        cmd = self.generate_cmd(
            cmd_id,
            'Write',
            size,
            min_offset,
            base_lba,
            init_time)
        cmd['host_stream_id'] = host_stream_id
        return cmd

    def generate_cmd(
            self,
            cmd_id,
            io_type,
            size,
            min_offset,
            base_lba=0,
            init_time=None):
        if isinstance(io_type, str):
            io_type = CommandClassifier.workload_type_dict[io_type]

        cmd = {'cmd_id': cmd_id,
               'cmd_type': io_type,
               'start_lba': (min_offset // self.param.SECTOR_SIZE) + base_lba,
               'lba_count': size // self.param.SECTOR_SIZE,
               'size_b': size,
               'init_time': init_time}
        if init_time is None:
            cmd['init_time'] = self.env.now

        cmd['domain_id'] = 0
        cmd['sq_id'] = 0

        return cmd
