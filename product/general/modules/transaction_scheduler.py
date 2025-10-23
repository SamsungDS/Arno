from core.framework.common import (BufferedUnitType, MemAccessInfo,
                                   QueueDepthChecker, StatusType,
                                   TransactionSourceType, eCMDType,
                                   eResourceType)
from core.modules.parallel_unit import ParallelUnit
from product.general.modules.nvm_transaction_class.nvm_transaction import (
    AddressID, NvmTransactionFlash)


class TransactionScheduler(ParallelUnit):
    def __init__(self, product_args, _address, unit_fifo_num=1):
        super().__init__(product_args, _address, unit_fifo_num)
        assert self.address == self.address_map.TSU
        self.read_issue_count = 0
        self.write_issue_count = 0
        self.erase_issue_count = 0
        self.read_done_count = 0
        self.write_done_count = 0
        self.erase_done_count = 0
        self.gc_write_issue_count = 0
        self.gc_write_done_count = 0
        self.generate_submodule(
            self.schedule_handler,
            self.feature.TSU_HANDLING)
        self.generate_submodule(self.done_handler, self.feature.TSU_DONE)

        self.state_urgent = 0
        self.write_request = []
        self.read_request = []
        self.erase_request = []
        self.gc_write_request = []
        self.gc_read_request = []
        self.user = 0
        self.gc = 0

        self.receive_call_back_event = self.env.event()

    def schedule_handler(self, packet):

        if packet['nvm_transaction'].transaction_source_type == TransactionSourceType.UserIO:
            self.user += 1
        elif packet['nvm_transaction'].transaction_source_type == TransactionSourceType.GCIO:
            self.gc += 1
        else:
            assert False

        if packet['nvm_transaction'].transaction_source_type == TransactionSourceType.UserIO:
            if packet['nvm_transaction'].transaction_type == eCMDType.Read:
                self.read_request.append(packet)

            elif packet['nvm_transaction'].transaction_type == eCMDType.Write or packet['nvm_transaction'].transaction_type == eCMDType.Flush:
                self.write_request.append(packet)

            elif packet['nvm_transaction'].transaction_type == eCMDType.Erase:
                self.erase_request.append(packet)
        else:
            if packet['nvm_transaction'].transaction_type == eCMDType.Read:
                self.gc_read_request.append(packet)
            elif packet['nvm_transaction'].transaction_type == eCMDType.Write:
                self.gc_write_request.append(packet)

        if len(self.read_request) != 0 and self.state_urgent == 0:
            for read_packet in self.read_request:
                self.read_issue_count += 1
                self.vcd_manager.set_read_issue_count(self.read_issue_count)
                self.send_sq(read_packet, self.address, self.address_map.JG,
                             src_submodule=self.schedule_handler)
                self.read_request.remove(read_packet)
        if len(self.write_request) != 0 and self.state_urgent == 0:
            for write_packet in self.write_request:
                self.write_issue_count += 1
                self.vcd_manager.set_write_issue_count(self.write_issue_count)
                self.send_sq(write_packet, self.address, self.address_map.JG,
                             src_submodule=self.schedule_handler)
                self.write_request.remove(write_packet)

        if len(self.erase_request) != 0:
            for erase_packet in self.erase_request:
                self.erase_issue_count += 1
                self.vcd_manager.set_erase_issue_count(self.erase_issue_count)
                address = AddressID()
                address.copy_from(erase_packet['nvm_transaction_flash'].address)
                erase_done_packet = {'nvm_transaction_flash': NvmTransactionFlash(address=address, transaction_type=eCMDType.Erase, transaction_source_type=TransactionSourceType.UserIO)}
                erase_done_packet['nvm_transaction'] = erase_done_packet['nvm_transaction_flash']
                self.send_sq(erase_packet, self.address, self.address_map.JG,
                             src_submodule=self.schedule_handler)
                self.wakeup(self.schedule_handler, self.done_handler, erase_done_packet)
                self.erase_request.remove(erase_packet)

        if len(self.gc_read_request) != 0:
            for gc_read_packet in self.gc_read_request:
                self.read_issue_count += 1
                self.send_sq(gc_read_packet, self.address, self.address_map.JG,
                             src_submodule=self.schedule_handler)
                self.gc_read_request.remove(gc_read_packet)
        if len(self.gc_write_request) != 0:
            for gc_write_packet in self.gc_write_request:
                self.gc_write_issue_count += 1
                self.send_sq(gc_write_packet, self.address, self.address_map.JG,
                             src_submodule=self.schedule_handler)
                self.gc_write_request.remove(gc_write_packet)

    def done_handler(self, packet):

        if packet['nvm_transaction'].transaction_source_type == TransactionSourceType.UserIO:
            if packet['nvm_transaction'].transaction_type == eCMDType.NANDReadDone:

                self.read_done_count += 1
                self.vcd_manager.set_read_done_count(self.read_done_count)
                self.send_sq(
                    packet,
                    self.address,
                    self.address_map.AML,
                    src_submodule=self.done_handler)
            elif packet['nvm_transaction'].transaction_type == eCMDType.WriteDone:

                self.write_done_count += 1
                self.vcd_manager.set_write_done_count(self.write_done_count)
                self.send_sq(
                    packet,
                    self.address,
                    self.address_map.AML,
                    src_submodule=self.done_handler)

            elif packet['nvm_transaction'].transaction_type == eCMDType.Erase:
                packet['nvm_transaction'].transaction_type = eCMDType.EraseDone
                self.erase_done_count += 1
                self.vcd_manager.set_erase_done_count(self.erase_done_count)
                self.send_sq(
                    packet,
                    self.address,
                    self.address_map.FBM,
                    src_submodule=self.done_handler)
        elif packet['nvm_transaction'].transaction_source_type == TransactionSourceType.GCIO:

            if packet['nvm_transaction'].transaction_type == eCMDType.NANDReadDone:
                self.read_done_count += 1
            if packet['nvm_transaction'].transaction_type == eCMDType.WriteDone:
                self.gc_write_done_count += 1
            self.send_sq(
                packet,
                self.address,
                self.address_map.AML,
                src_submodule=self.done_handler)

    def handle_request(self, packet, fifo_id: int):
        src = packet['src']

        if src == self.address_map.AML or src == self.address_map.FBM:
            self.wakeup(
                self.address,
                self.schedule_handler,
                packet,
                src_id=fifo_id)
        elif src == self.address_map.JG:
            self.wakeup(
                self.address,
                self.done_handler,
                packet,
                src_id=fifo_id)

    def print_debug(self):
        pass
