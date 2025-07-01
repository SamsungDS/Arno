from core.framework.core_pif import CommonSQ


class AllocateSQ(CommonSQ):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        body_key_list = [
        ]

        self.reference_map = {
            'request_type': 'opcode',
            'resource_type': 'opcode',
            'request_ip': 'src',
            'request_callback_fifo_id': 'src'
        }
        super().gen_packet(body_key_list, *args, **kwargs)


class ReleaseSQ(CommonSQ):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        body_key_list = [
            'buffer_address_low',  # dw1,    0_31,   buffer address low
            'buffer_address_high',  # dw2,    0_31,   buffer address high
        ]

        self.reference_map = {
            'request_type': 'opcode',
            'resource_type': 'opcode',
            'resource_id': 'buffer_address'
        }
        super().gen_packet(body_key_list, *args, **kwargs)
