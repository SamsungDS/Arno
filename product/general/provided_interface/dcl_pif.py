from core.framework.core_pif import CommonSQ


class ReadSQ(CommonSQ):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        body_key_list = [
            'lpn',
            'slot_id',
            'desc_id',
            'cache_id',
        ]

        self.reference_map = {
            'cmd_type': 'opcode',
            'user': 'opcode',
            'seq_flag': 'slot_id'
        }
        super().gen_packet(body_key_list, *args, **kwargs)


class ReadDoneSQ(CommonSQ):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        body_key_list = [
            'lpn',
            'slot_id',
            'cache_id',
            'unmap',
        ]

        self.reference_map = {
            'is_unmap': 'unmap',
            'user': 'opcode',
            'cmd_type': 'opcode',
            'cmd_id': 'slot_id',
            'ppn': 'debug',
            'cache_result': 'debug'
        }
        super().gen_packet(body_key_list, *args, **kwargs)


class WriteSQ(CommonSQ):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        body_key_list = [
            'lpn',
            'slot_id',
        ]

        self.reference_map = {
            'cmd_type': 'opcode',
            'user': 'opcode',
        }
        super().gen_packet(body_key_list, *args, **kwargs)
