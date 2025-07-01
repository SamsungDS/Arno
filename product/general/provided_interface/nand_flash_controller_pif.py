from core.framework.core_pif import CommonSQ


class NandJobDBL(CommonSQ):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        body_key_list = [
            'buffered_unit_id',
            'nand_job_id',
            'rsvd_1',
        ]

        self.reference_map = {
        }
        super().gen_packet(body_key_list, *args, **kwargs)


class NandJobReleaseDBL(CommonSQ):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        body_key_list = [
            'nand_job_id',
            'buffered_unit_id',
            'rsvd_1',
        ]

        self.reference_map = {
        }
        super().gen_packet(body_key_list, *args, **kwargs)


class BufferAllocDoneSQ(CommonSQ):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        body_key_list = [
            'buffer_address'
        ]

        self.reference_map = {
            'resource_type': 'opcode',
            'alloc_status': 'opcode',
            'resource_id': 'buffer_address'

        }
        super().gen_packet(body_key_list, *args, **kwargs)
