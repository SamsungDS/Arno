from core.framework.core_pif import CommonSQ

# JG


class NandJobDBL(CommonSQ):
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

# TE


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


class DMADone(CommonSQ):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        body_key_list = [
            'nand_job_id',
            'buffered_unit_id',
            'rsvd_1',
        ]

        self.reference_map = {
            'nand_cmd_type': 'opcode',
            'channel': 'nand_job_id',
        }
        super().gen_packet(body_key_list, *args, **kwargs)


class ResumeNandJobRequest(CommonSQ):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        body_key_list = [
            'channel',
            'way',
        ]

        self.reference_map = {
            'nand_cmd_type': 'opcode',
        }
        super().gen_packet(body_key_list, *args, **kwargs)
