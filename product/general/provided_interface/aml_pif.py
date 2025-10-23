from core.framework.common import eCMDType
from product.general.modules.nvm_transaction_class.nvm_transaction import (
    AddressID, NVMTransaction, NvmTransactionFlash)


class AMLPIF:
    """
    AddressMappingLayer 전용 PIF (Packet Interface Format)
    """

    @staticmethod
    def create_alloc_packet(packet: dict, address) -> dict:
        """
        FBM에 전달할 Page Allocation 요청 패킷 생성
        """
        orig_nvm = packet['nvm_transaction']
        # NVMTransaction 생성
        nvm_trans = type(orig_nvm)(
            stream_id=orig_nvm.stream_id,
            transaction_type=eCMDType.Write,
            transaction_source_type=orig_nvm.transaction_source_type,
            lpn=orig_nvm.lpn,
            valid_sector_bitmap=orig_nvm.valid_sector_bitmap,
            buffer_ptr=orig_nvm.buffer_ptr
        )
        nvm_trans.hazard_flag = getattr(orig_nvm, 'hazard_flag', False)

        # 최종 패킷 구성
        alloc_packet = {'nvm_transaction': nvm_trans, 'nvm_transaction_flash': NvmTransactionFlash(address=address, base_transaction=nvm_trans)}

        return alloc_packet

    @staticmethod
    def create_map_update_packet(packet: dict) -> dict:
        """
        FBM에 전달할 Map Update 요청 패킷 생성
        """
        orig_nvm = packet['nvm_transaction']
        orig_flash = packet['nvm_transaction_flash']

        # AddressID 복사
        address = AddressID()
        address.channel = orig_flash.address.channel
        address.way = orig_flash.address.way
        address.plane = orig_flash.address.plane
        address.block = orig_flash.address.block
        address.page = orig_flash.address.page
        address.lpo = orig_flash.address.lpo

        # NVMTransaction 생성
        nvm_trans = NVMTransaction(
            stream_id=orig_nvm.stream_id,
            transaction_type=orig_nvm.transaction_type,
            transaction_source_type=orig_nvm.transaction_source_type,
            lpn=orig_nvm.lpn,
            valid_sector_bitmap=orig_nvm.valid_sector_bitmap,
            buffer_ptr=orig_nvm.buffer_ptr
        )
        nvm_trans.hazard_flag = getattr(orig_nvm, 'hazard_flag', False)

        # NvmTransactionFlash 생성
        nvm_flash = NvmTransactionFlash(
            address=address,
            transaction_type=orig_flash.transaction_type,
            transaction_source_type=orig_flash.transaction_source_type,
            valid_sector_bitmap=orig_flash.valid_sector_bitmap,
            stream_id=orig_flash.stream_id
        )
        nvm_flash.ppn = orig_flash.ppn
        nvm_flash.old_ppn = getattr(orig_flash, 'old_ppn', None)
        nvm_flash.unmap_check = getattr(orig_flash, 'unmap_check', False)

        # 최종 패킷 구성
        update_packet = {
            'nvm_transaction': nvm_trans,
            'nvm_transaction_flash': nvm_flash
        }

        return update_packet
