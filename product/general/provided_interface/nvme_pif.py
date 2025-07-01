from core.framework.core_pif import CommonSQ


class DMANotifySQ(CommonSQ):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        body_key_list = [
            'slot_id',
            'desc_id',
        ]

        self.reference_map = {
            'cmd_type': 'opcode',
            'is_din': 'desc_id',
            'lpn': 'slot_id',
            'seq_flag': 'slot_id',
            'cmd_last_desc': 'internal',
            'cache_result': 'debug',
        }
        super().gen_packet(body_key_list, *args, **kwargs)


class WriteCompletionSQ(CommonSQ):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        body_key_list = [
            'slot_id',
        ]

        self.reference_map = {
            'cmd_last_desc': 'internal',
            'cmd_type': 'opcode',
        }
        super().gen_packet(body_key_list, *args, **kwargs)


class TrimDoneSQ(CommonSQ):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        body_key_list = [
            'slot_id',
        ]

        self.reference_map = {
            'cmd_type': 'slot_id'
        }
        super().gen_packet(body_key_list, *args, **kwargs)


class ReadDoneSQ(CommonSQ):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        body_key_list = [
            'read_status',
            'desc_id',
            'slot_id',
            'buffer_address_low',
            'buffer_address_high',
        ]

        self.reference_map = {
            'unmap': 'read_status',
            'is_din': 'slot_id',
            'id': 'desc_id',
            'cache_result': 'debug',
            'cache_id': 'debug',
        }
        super().gen_packet(body_key_list, *args, **kwargs)


class HDMADoneSQ(CommonSQ):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        body_key_list = [
            'slot_id',
            'desc_id',
            'buffer_address_low',
            'buffer_address_high',
        ]

        self.reference_map = {
            'is_din': 'slot_id',
            'id': 'desc_id',
            'cmd_last_desc': 'internal',
            'cmd_type': 'slot_id',
            'lpn': 'slot_id',
            'cache_result': 'debug',
            'cache_id': 'debug',
            'flush_cmd_id': 'debug',

        }
        super().gen_packet(body_key_list, *args, **kwargs)
