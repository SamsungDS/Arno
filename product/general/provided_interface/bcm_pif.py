
from core.framework.common import TransactionSourceType, eCMDType
from product.general.modules.nvm_transaction_class.nvm_transaction import (
    AddressID, NVMTransaction, NvmTransactionFlash)


class BCMPIF:
    """
    BlockCopyManager 전용 패킷 생성기 (PIF: Packet Interface Format)

    현재 기능:
    - create_read_packet: GC Read 명령 생성
    """

    @staticmethod
    def create_read_packet(
            channel: int,
            way: int,
            plane: int,
            block: int,
            page: int,
            lpo: int,
            stream_id: int,
            buffer_ptr: int,
            old_ppn: int,
            src_num: int,
            user: str = 'gc'
    ) -> dict:
        """
        GC Read 동작을 위한 패킷을 생성합니다.

        Args:
            channel (int): Flash 채널
            way (int): Flash way (CE)
            plane (int): 플래시 칩의 Plane
            block (int): 블록 주소
            page (int): 페이지 주소
            lpo (int): Logical Page Offset (0~3)
            stream_id (int): GC 스트림 ID
            buffer_ptr (int): 할당된 버퍼 포인터
            old_ppn (int): 원본 PPN (Garbage Collection 이전 위치)
            user (str): 사용자 태그 (기본: 'gc_io')
            src_num (int): src_block_pool의 번호
        Returns:
            dict: {'nvm_transaction_flash': NvmTransactionFlash, ...} 구조
        """
        # AddressID 생성 및 필드 설정
        address = AddressID()
        address.channel = channel
        address.way = way
        address.plane = plane
        address.block = block
        address.page = page
        address.lpo = lpo

        # NvmTransactionFlash 생성
        nvm_trans = NvmTransactionFlash(
            address=address,
            transaction_type=eCMDType.Read,
            transaction_source_type=TransactionSourceType.GCIO,
            valid_sector_bitmap=255,  # 전체 섹터 유효 처리
            stream_id=stream_id
        )
        nvm = NVMTransaction(
            lpn=-1,
            transaction_type=eCMDType.Read,
            transaction_source_type=TransactionSourceType.GCIO,
            valid_sector_bitmap=255,  # 전체 섹터 유효 처리
            stream_id=stream_id
        )

        nvm_trans.old_ppn = old_ppn
        nvm_trans.buffer_ptr = buffer_ptr
        nvm.buffer_ptr = buffer_ptr
        # 최종 패킷 구성
        packet = {
            'nvm_transaction_flash': nvm_trans,
            'nvm_transaction': nvm,
            'slot_id': -1,
            'user': user,
            'src_num': src_num,  # 기본값, 필요시 외부에서 수정
            'stream_id': stream_id
        }

        return packet
