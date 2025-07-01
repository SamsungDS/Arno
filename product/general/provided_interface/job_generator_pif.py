from core.backbone.address_map import AddressMap
from core.framework.common import eCMDType
from core.framework.core_pif import CommonSQ

address_map = AddressMap()


class FlashInsertSQ(CommonSQ):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        body_key_list = [
            'opcode',  # dw1, 0_4, Read, Program, Erase
            'vpage_type',  # dw1, 5_9, VPage Type
            'queue_id',  # dw1, 10_17, IOM에서 부여한 값으로 Producer 종류와 Urgent/Meta/Normal 구분
            'vpage_id',  # dw1, 18_28, VPage 주소
            'rsvd_1',  # dw1, 29_31, reserved
        ]
        self.reference_map = {
            'cmd_type': 'opcode',
            'read_vpage': 'vpage_type',
            'write_vpage': 'vpage_type',
            'valid_page_bitmap': 'vpage_id',
            'user': 'queue_id',
            'dst': 'queue_id',
            'fifo_id': 'queue_id',
            'cell_type': 'vpage_id',
            'page': 'vpage_id',
            'wl': 'vpage_id',
            'physical_page': 'vpage_id',
            'block': 'vpage_id',
            'is_sun_pgm': 'vpage_id',
            'l2p_flag': 'vpage_id',
            'desc_id_list': 'vpage_id',
            'slot_id_list': 'vpage_id',
            'lpn_list': 'vpage_id',
            'cache_id_list': 'vpage_id',
            'archive_idx': 'vpage_id',
            'archive_idxes': 'vpage_id',
            'channel': 'vpage_id',
            'way': 'vpage_id',
            'task_count': 'debug',
            'buffered_unit_id': 'debug',
            'is_reclaim': 'vpage_id'
        }
        if 'vpage_type' not in args[0]:
            args[0]['vpage_type'] = None
        if 'vpage_id' not in args[0]:
            args[0]['vpage_id'] = None
        super().gen_packet(body_key_list, *args, **kwargs)


class TransSQ(CommonSQ):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        body_key_list = [
            'opcode',  # dw1, 0_4, Read/ Program/ Erase
            'queue_id',  # dw1, 5_12, IOM에서 부여한 값으로 Producer 종류와 Urgent/Meta/Normal 구분
            'buffered_unit_id',  # dw1, 13_20, JG에서 InsertSQ를 관리하기 위한 번호
            'vpage_type',  # dw1, 21_25, VPage Type
            'rsvd_1',  # dw1, 26_31, reserved
            'vpage_id',  # dw2, 0_10, VPage 주소
            'rsvd_2',  # dw2, 11_31, reserved
        ]
        self.reference_map = {
            'cmd_type': 'opcode',
            'read_vpage': 'vpage_type',
            'write_vpage': 'vpage_type',
            'valid_page_bitmap': 'vpage_id',
            'user': 'queue_id',
            'dst': 'queue_id',
            'fifo_id': 'queue_id',
            'cell_type': 'vpage_id',
            'page': 'vpage_id',
            'wl': 'vpage_id',
            'physical_page': 'vpage_id',
            'block': 'vpage_id',
            'is_sun_pgm': 'vpage_id',
            'l2p_flag': 'vpage_id',
            'desc_id_list': 'vpage_id',
            'slot_id_list': 'vpage_id',
            'lpn_list': 'vpage_id',
            'cache_id_list': 'vpage_id',
            'archive_idx': 'vpage_id',
            'archive_idxes': 'vpage_id',
            'channel': 'vpage_id',
            'way': 'vpage_id',
            'task_count': 'debug',
            'buffered_unit_id': 'debug',
            'is_seq_vpage': 'vpage_id'  # client

        }
        super().gen_packet(body_key_list, *args, **kwargs)


class TaskReleaseDBL(CommonSQ):
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


def generate_super_block_erase_packet(block, ch, way, user, src_addr):
    erase_packet = {}
    erase_packet['cmd_type'] = eCMDType.Erase
    erase_packet['opcode'] = None
    erase_packet['queue_id'] = None
    erase_packet['buffered_unit_id'] = None
    erase_packet['user'] = user
    erase_packet['channel'] = ch
    erase_packet['way'] = way
    erase_packet['page'] = 0
    erase_packet['block'] = block
    erase_packet = FlashInsertSQ(erase_packet, src_addr)

    return erase_packet
