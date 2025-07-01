from core.framework.core_pif import CommonSQ


class DMASQ(CommonSQ):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        body_key_list = [
            'desc_id',
            'slot_id',
            'buffer_address_low',
            'buffer_address_high',
        ]

        self.reference_map = {
            'is_din': 'slot_id',
            'id': 'desc_id',
        }
        super().gen_packet(body_key_list, *args, **kwargs)
