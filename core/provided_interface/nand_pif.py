from core.framework.core_pif import CommonSQ


class NANDDBL(CommonSQ):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        body_key_list = [
            'buffered_unit_id',
            'nand_job_id',
        ]

        self.reference_map = {
        }
        super().gen_packet(body_key_list, *args, **kwargs)
