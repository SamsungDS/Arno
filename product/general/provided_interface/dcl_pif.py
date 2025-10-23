from core.framework.common import TransactionSourceType, eCMDType
from core.framework.core_pif import CommonSQ
from product.general.modules.nvm_transaction_class.nvm_transaction import (
    AddressID, NvmTransactionFlash)


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


class FlushSQ(CommonSQ):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        body_key_list = [
            'slot_id',
        ]

        self.reference_map = {
            'cmd_type': 'opcode',
            'user': 'opcode',
        }
        super().gen_packet(body_key_list, *args, **kwargs)


class DCLPIF:
    """
    DataCacheLayer 전용 PIF (Packet Interface Format)
    """

    @staticmethod
    def create_cache_packet(packet: dict, update_fields: dict = None) -> dict:

        # nvm_transaction 복사
        orig_nvm = packet['nvm_transaction']
        new_nvm = type(orig_nvm)(
            transaction_type=orig_nvm.transaction_type,
            transaction_source_type=orig_nvm.transaction_source_type,
            valid_sector_bitmap=orig_nvm.valid_sector_bitmap,
            stream_id=orig_nvm.stream_id,
            lpn=orig_nvm.lpn,
            buffer_ptr=getattr(orig_nvm, 'buffer_ptr', None)
        )

        # 최종 패킷 구성
        new_packet = {
            'nvm_transaction': new_nvm
        }

        return new_packet

    @staticmethod
    def create_write_done_packet(packet: dict) -> dict:
        """
        Host Write Done 패킷 생성
        """
        orig_nvm = packet['nvm_transaction']

        # 새 NVMTransaction 생성 (hazard_flag는 초기화 시 기본값 False)
        new_nvm = type(orig_nvm)(
            stream_id=orig_nvm.stream_id,
            transaction_type=orig_nvm.transaction_type,
            transaction_source_type=TransactionSourceType.UserIO,
            lpn=orig_nvm.lpn,
            valid_sector_bitmap=orig_nvm.valid_sector_bitmap,
            buffer_ptr=orig_nvm.buffer_ptr
            # hazard_flag는 __init__에 없으므로 여기서 안 넣음
        )

        # 최종 패킷 구성: 기존의 host 정보는 유지하되, nvm_transaction만 교체
        done_packet = {
            # 기존의 host 관련 정보 유지
            'slot_id': packet.get('slot_id'),
            'lpn': packet.get('lpn'),
            'host_stream_id': packet.get('host_stream_id'),
            'desc_id': packet.get('desc_id'),
            'seq_flag': packet.get('seq_flag'),
            'is_first_dma': packet.get('is_first_dma'),
            'cmd_id': packet.get('cmd_id'),
            'src': packet.get('src'),
            'dma_latency': packet.get('dma_latency'),
            'dma_unique_id': packet.get('dma_unique_id'),
            'cmd_last_desc': packet.get('cmd_last_desc'),
            'write_zero': packet.get('write_zero'),
            'deac': packet.get('deac'),
            'user': packet.get('user', 'dcl'),

            # ✅ nvm_transaction만 새 것으로 교체
            'nvm_transaction': new_nvm,

            # ✅ 필요 시 추가 필드
            'remain_dma_count': getattr(orig_nvm, 'remain_dma_count', 0)
        }

        return done_packet
