
from core.framework.common import TransactionSourceType, eCMDType
from product.general.modules.nvm_transaction_class.nvm_transaction import (
    AddressID, NvmTransactionFlash)


class FBMPIF:
    """
    FlashBlockManager 전용 PIF (Packet Interface Format)
    """

    @staticmethod
    def create_erase_packet(
        channel: int,
        way: int,
        plane: int,
        block: int,
        stream_id: int,
        user: str = TransactionSourceType.UserIO
    ) -> dict:
        """Erase 명령 생성"""
        address = AddressID()
        address.channel = channel
        address.way = way
        address.plane = plane
        address.block = block
        address.page = 0
        address.lpo = 0

        nvm_trans = NvmTransactionFlash(
            address=address,
            transaction_type=eCMDType.Erase,
            transaction_source_type=TransactionSourceType.UserIO,
            valid_sector_bitmap=0,
            stream_id=stream_id
        )

        packet = {
            'nvm_transaction_flash': nvm_trans,
            'nvm_transaction': nvm_trans,
            'slot_id': -1,
            'user': user
        }
        return packet

    @staticmethod
    def create_gc_trigger_packet(
        original_packet: dict,
        src_num: int
    ) -> dict:
        """GC 트리거 패킷 생성 (원본 구조 유지 + 필드 업데이트)"""
        # 원본에서 필요한 정보 추출
        orig_nvm = original_packet['nvm_transaction']
        orig_flash = original_packet['nvm_transaction_flash']

        # AddressID 복사
        address = AddressID()
        address.channel = orig_flash.address.channel
        address.way = orig_flash.address.way
        address.plane = orig_flash.address.plane
        address.block = orig_flash.address.block
        address.page = orig_flash.address.page
        address.lpo = orig_flash.address.lpo

        # 새 트랜잭션 생성
        nvm_trans = NvmTransactionFlash(
            address=address,
            transaction_type=orig_nvm.transaction_type,
            transaction_source_type=TransactionSourceType.GCIO,
            valid_sector_bitmap=orig_flash.valid_sector_bitmap,
            stream_id=orig_nvm.stream_id
        )
        nvm_trans.buffer_ptr = getattr(orig_nvm, 'buffer_ptr', None)

        packet = {
            'nvm_transaction_flash': nvm_trans,
            'nvm_transaction': nvm_trans,
            'slot_id': -1,
            'user': 'gc',
            'src_num': src_num,
            'nvm_transaction_flash_list': []
        }
        return packet

    @staticmethod
    def create_urgent_signal(urgent: bool) -> dict:
        """긴급 GC 신호 생성"""
        return {"set_urgent": urgent}
