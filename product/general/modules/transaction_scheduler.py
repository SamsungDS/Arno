from copy import deepcopy

from core.modules.parallel_unit import ParallelUnit


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
        self.generate_submodule(
            self.schedule_handler,
            self.feature.TSU_HANDLING)
        self.generate_submodule(self.done_handler, self.feature.TSU_DONE)

        self.write_request = []
        self.read_request = []
        self.erase_request = []

    def schedule_handler(self, packet):
        if packet['nvm_transaction'].transaction_type == 'read':
            self.read_request.append(packet)
        elif packet['nvm_transaction'].transaction_type == 'write':
            self.write_request.append(packet)
        elif packet['nvm_transaction'].transaction_type == 'erase':
            self.erase_request.append(packet)

        if len(self.read_request) != 0:
            for i in self.read_request:
                self.read_issue_count += 1
                self.vcd_manager.set_read_issue_count(self.read_issue_count)
                self.send_sq(i, self.address, self.address_map.JG,
                             src_submodule=self.schedule_handler)
                self.read_request.remove(i)
        if len(self.write_request) != 0:
            for i in self.write_request:
                self.write_issue_count += 1
                self.vcd_manager.set_write_issue_count(self.write_issue_count)
                self.send_sq(i, self.address, self.address_map.JG,
                             src_submodule=self.schedule_handler)
                self.write_request.remove(i)

        if len(self.erase_request) != 0:
            for i in self.erase_request:
                self.erase_issue_count += 1
                self.vcd_manager.set_erase_issue_count(self.erase_issue_count)
                self.send_sq(i, self.address, self.address_map.JG,
                             src_submodule=self.schedule_handler)
                packet = deepcopy(i)
                self.wakeup(self.schedule_handler, self.done_handler, packet)
                self.erase_request.remove(i)

    def done_handler(self, packet):
        if packet['nvm_transaction'].transaction_type == 'nand_read_done':
            self.read_done_count += 1
            self.vcd_manager.set_read_done_count(self.read_done_count)
            self.send_sq(
                packet,
                self.address,
                self.address_map.AML,
                src_submodule=self.done_handler)
        elif packet['nvm_transaction'].transaction_type == 'write_done':
            self.write_done_count += 1
            self.vcd_manager.set_write_done_count(self.write_done_count)
            self.send_sq(
                packet,
                self.address,
                self.address_map.AML,
                src_submodule=self.done_handler)
        elif packet['nvm_transaction'].transaction_type == 'erase':
            packet['nvm_transaction'].transaction_type = 'erase_done'
            self.erase_done_count += 1
            self.vcd_manager.set_erase_done_count(self.erase_done_count)
            self.send_sq(
                packet,
                self.address,
                self.address_map.FBM,
                src_submodule=self.done_handler)

    def handle_request(self, request, fifo_id: int):

        src = request['src']

        if src == self.address_map.AML or src == self.address_map.FBM:
            self.wakeup(
                self.address,
                self.schedule_handler,
                request,
                src_id=fifo_id)
        elif src == self.address_map.FIL or src == self.address_map.JG:
            self.wakeup(
                self.address,
                self.done_handler,
                request,
                src_id=fifo_id)

    def print_debug(self):
        pass
