from core.framework.core_pif import CommonSQ


class HDMARequestSQ(CommonSQ):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        body_key_list = [
            'slot_id',
            'desc_id',
            'archive_idx',
            'archive_offset',
            'buffer_address_low',
            'buffer_address_high',
        ]

        self.reference_map = {
            'cmd_type': 'opcode',
            'is_din': 'slot_id',
            'id': 'desc_id',
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
            'flush_cmd_id': 'debug',
        }
        super().gen_packet(body_key_list, *args, **kwargs)
