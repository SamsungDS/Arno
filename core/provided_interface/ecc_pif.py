from core.framework.core_pif import CommonSQ


class ReadDMASQ(CommonSQ):  # for nand
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        body_key_list = [
            'slot_id',  # dw1,    0_15,   Host CMD slot id
            'desc_id',  # dw1,    16_31,  Host descriptor id
        ]

        self.reference_map = {
            'cmd_type': 'opcode',
            'channel': 'debug',
            'meta': 'debug',  # check
            'archive_idx': 'debug',  # check
            'cache_result': 'debug',
            'lpn': 'desc_id',
            'cache_id': 'desc_id',
            'buffer_ptr': 'desc_id',
            'buffered_unit_id': 'debug',
            'nand_job_id': ' debug',
        }
        super().gen_packet(body_key_list, *args, **kwargs)
