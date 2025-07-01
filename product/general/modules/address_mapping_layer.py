from core.config.core_parameter import CoreParameter
from core.modules.parallel_unit import ParallelUnit
from product.general.config.storage_feature import Feature
from product.general.config.storage_parameters import Parameter


class AddressMappingLayer(ParallelUnit):
    param: Parameter
    feature: Feature

    def __init__(self, product_args, _address, unit_fifo_num=1):
        super().__init__(product_args, _address, unit_fifo_num)
        assert self.address == self.address_map.AML

        self.generate_submodule(
            self.done_handler,
            self.feature.AML_DONE_HANDLING)
        self.generate_submodule(
            self.write_handler,
            self.feature.AML_WRITE_HANDLING)
        self.generate_submodule(
            self.read_handler,
            self.feature.AML_READ_HANDLING)
        self.generate_submodule(
            self.alloc_done_handler,
            self.feature.AML_ALLOC_DONE)

        self.core = CoreParameter()

        self.page_alloc_count = 0
        self.alloc_request_ppn_count = 0
        self.read_unmap_count = 0
        self.read_map_count = 0
        self.map_update_count = 0
        self.write_done_count = 0
        self.mapping_table = {}

        self.receive_call_back_event = self.env.event()
        self.receive_done_event = self.env.event()

        self.channel_count = self.param.CHANNEL
        self.way_count = self.param.WAY
        self.plane_count = self.param.PLANE
        self.block_count = self.param.BLOCK_PER_PLANE
        self.map_unit_count = self.core.MAPUNIT_PER_PLANE
        self.page_count = self.param.PAGE_PER_BLOCK
        self.lpo_count = 0
        self.write_count = 0
        self.addr = self.AddressID()
        self.plane_allocation_scheme = self.core.PlaneAllocationScheme
        self.requset_page_alloc = 0

    class AddressID:
        def __init__(self):
            self.channel = 0
            self.way = 0
            self.plane = 0
            self.block = 0
            self.page = 0
            self.lpo = 0

    class NvmTransactionFlash:
        def __init__(self, address):
            self.address = address
            self.ppn = 0
            self.unmap_check = False

        def __getitem__(self, key):
            return getattr(self, key)

        def __setitem__(self, key, value):
            return setattr(self, key, value)

        def __delitem__(self, key):
            return delattr(self, key)

        def __contains__(self, key):
            return hasattr(self, key)

        def __repr__(self):
            return f"{self.__dict__}"

    def get_init_ppn(self):
        ppn = (
            ((((self.addr.channel *
                self.way_count) +
               self.addr.way) *
              self.plane_count +
              self.addr.plane) *
             self.block_count +
             self.addr.block) *
            self.page_count +
            self.addr.page)
        return ppn

    def set_mapping_table(self, test_size):
        page = -1
        block = 0
        for i in range(test_size):
            if i % (self.channel_count * self.way_count *
                    self.plane_count * self.map_unit_count) == 0:
                page += 1
            if i % self.map_unit_count == 0:
                self.addr = self.allocate_plane()
                self.addr.block = block
                self.addr.page = page
            ppn = self.get_init_ppn()
            self.mapping_table[i] = ppn * 10 + i % self.map_unit_count
            if page == self.page_count - 1 and i % self.map_unit_count == self.map_unit_count - 1:
                page = 0
                block += 1
                if block == self.block_count:
                    block = 0
        self.write_count = 0

    def allocate_plane(self):
        address = self.AddressID()
        if self.plane_allocation_scheme == 'CWP':
            address.channel = self.write_count % self.channel_count
            address.way = (
                self.write_count // self.channel_count) % self.way_count
            address.plane = (
                self.write_count // (self.channel_count * self.way_count)) % self.plane_count

        elif self.plane_allocation_scheme == 'CPW':
            address.channel = self.write_count % self.channel_count
            address.way = (
                self.write_count // (self.channel_count * self.plane_count)) % self.way_count
            address.plane = (
                self.write_count // self.channel_count) % self.plane_count

        elif self.plane_allocation_scheme == 'WCP':
            address.channel = (
                self.write_count // self.way_count) % self.channel_count
            address.way = self.write_count % self.way_count
            address.plane = (
                self.write_count // (self.way_count * self.channel_count)) % self.plane_count

        elif self.plane_allocation_scheme == 'WPC':
            address.channel = (
                self.write_count // (self.way_count * self.plane_count)) % self.channel_count
            address.way = self.write_count % self.way_count
            address.plane = (
                self.write_count // self.way_count) % self.plane_count

        elif self.plane_allocation_scheme == 'PCW':
            address.channel = (
                self.write_count // self.plane_count) % self.channel_count
            address.way = (self.write_count // (self.plane_count *
                           self.channel_count)) % self.way_count
            address.plane = self.write_count % self.plane_count

        elif self.plane_allocation_scheme == 'PWC':
            address.channel = (
                self.write_count // (self.plane_count * self.way_count)) % self.channel_count
            address.way = (
                self.write_count // self.plane_count) % self.way_count
            address.plane = self.write_count % self.plane_count

        self.write_count += 1
        return address

    def get_new_ppn(self, packet):

        ppn = (
            ((((packet['nvm_transaction_flash'].address.channel *
                self.way_count) +
               packet['nvm_transaction_flash'].address.way) *
                self.plane_count +
                packet['nvm_transaction_flash'].address.plane) *
                self.block_count +
                packet['nvm_transaction_flash'].address.block) *
            self.page_count +
            packet['nvm_transaction_flash'].address.page)
        return ppn

    def get_address(self, packet):
        ppn = packet['nvm_transaction_flash'].ppn
        packet['nvm_transaction_flash'].address.page = ppn % self.page_count
        ppn = ppn // self.page_count
        packet['nvm_transaction_flash'].address.block = ppn % self.block_count
        ppn = ppn // self.block_count
        packet['nvm_transaction_flash'].address.plane = ppn % self.plane_count
        ppn = ppn // self.plane_count
        packet['nvm_transaction_flash'].address.way = ppn % self.way_count
        packet['nvm_transaction_flash'].address.channel = ppn // self.way_count

    def lookup_mapping_table(self, lpn):
        return self.mapping_table[lpn]

    def read_handler(self, packet):
        lpn = packet['nvm_transaction'].lpn
        packet['nvm_transaction_flash'] = self.NvmTransactionFlash(
            self.AddressID())
        if lpn in self.mapping_table:
            self.read_map_count += 1
            packet['nvm_transaction_flash'].ppn = self.lookup_mapping_table(
                lpn) // 10
            packet['nvm_transaction_flash'].address.lpo = self.lookup_mapping_table(
                lpn) % 10
            self.get_address(packet)
            self.send_sq(
                packet,
                self.address,
                self.address_map.TSU,
                src_submodule=self.read_handler)
        else:
            self.read_unmap_count += 1
            packet['nvm_transaction_flash'] = self.NvmTransactionFlash(
                self.AddressID())
            packet['nvm_transaction_flash'].unmap_check = True
            self.send_sq(
                packet,
                self.address,
                self.address_map.TSU,
                src_submodule=self.read_handler)

    def page_allocater(self, packet):

        self.send_sq(
            packet,
            self.address,
            self.address_map.FBM,
            src_submodule=self.write_handler)
        yield self.receive_call_back_event
        self.lpo_count = 0

    def copy_address(self,):
        address = self.AddressID()
        address.channel = self.addr.channel
        address.way = self.addr.way
        address.plane = self.addr.plane
        address.block = self.addr.block
        address.page = self.addr.page
        address.lpo = self.addr.lpo
        return address

    def write_handler(self, packet):
        if self.lpo_count == self.map_unit_count or self.write_count == 0:
            self.addr = self.allocate_plane()
            packet['nvm_transaction_flash'] = self.NvmTransactionFlash(
                self.addr)
            yield from self.page_allocater(packet)
            self.requset_page_alloc += 1

        address = self.copy_address()
        address.lpo = self.lpo_count
        self.lpo_count += 1
        packet['nvm_transaction_flash'] = self.NvmTransactionFlash(address)
        self.alloc_request_ppn_count += 1
        packet['nvm_transaction_flash'].ppn = self.get_new_ppn(packet)
        self.send_sq(
            packet,
            self.address,
            self.address_map.TSU,
            src_submodule=self.write_handler)
        self.receive_done_event.succeed()
        self.receive_done_event = self.env.event()

    def done_handler(self, packet):
        if packet['nvm_transaction'].transaction_type == 'write_done':
            self.mapping_table[packet['nvm_transaction'].lpn] = packet['nvm_transaction_flash'].ppn * \
                10 + packet['nvm_transaction_flash'].address.lpo
            self.write_done_count += 1
            self.map_update_count += 1

        self.send_sq(
            packet,
            self.address,
            self.address_map.DCL,
            src_submodule=self.done_handler)

    def alloc_done_handler(self, packet):
        self.receive_call_back_event.succeed()
        self.receive_call_back_event = self.env.event()
        self.page_alloc_count += 1
        yield self.receive_done_event

    def handle_request(self, packet, fifo_id):
        src = packet['src']
        if src == self.address_map.DCL:

            if packet['nvm_transaction'].transaction_type == 'write':
                self.wakeup(
                    self.address,
                    self.write_handler,
                    packet,
                    src_id=fifo_id)
            elif packet['nvm_transaction'].transaction_type == 'read':
                self.wakeup(
                    self.address,
                    self.read_handler,
                    packet,
                    src_id=fifo_id)
        elif src == self.address_map.FBM:
            self.wakeup(
                self.address,
                self.alloc_done_handler,
                packet,
                src_id=fifo_id)
        elif src == self.address_map.TSU:
            self.wakeup(
                self.address,
                self.done_handler,
                packet,
                src_id=fifo_id)

    def print_debug(self):
        pass
