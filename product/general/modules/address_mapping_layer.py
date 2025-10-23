import copy
import sys

from core.config.core_parameter import CoreParameter
from core.framework.common import (BufferedUnitType, MemAccessInfo,
                                   QueueDepthChecker, StatusType,
                                   TransactionSourceType, eCMDType,
                                   eResourceType)
from core.modules.parallel_unit import ParallelUnit
from product.general.config.storage_feature import Feature
from product.general.config.storage_parameters import Parameter
from product.general.modules.nvm_transaction_class.nvm_transaction import (
    AddressID, NvmTransactionFlash)
from product.general.provided_interface.aml_pif import AMLPIF


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
        self.generate_submodule(
            self.release_done_handler,
            self.feature.AML_RELEASE_DONE)
        self.generate_submodule(
            self.gc_map_update_handler,
            self.feature.AML_DONE_HANDLING)
        self.generate_submodule(
            self.gc_read_handler,
            self.feature.AML_ZERO)
        self.generate_submodule(
            self.urgent_handler,
            self.feature.AML_ZERO)
        self.generate_submodule(
            self.flush_handler,
            self.feature.AML_ZERO)

        self.core = CoreParameter()

        self.page_alloc_count = 0
        self.alloc_request_ppn_count = 0
        self.read_unmap_count = 0
        self.read_map_count = 0
        self.flush_count = 0
        self.map_update_count = 0
        self.write_done_count = 0
        self.read_done_count = 0
        self.page_release_count = 0
        self.requset_page_alloc = 0
        self.last = 0
        self.not_update_map = 0

        self.l2p_size_b = 4
        self.mapping_table = {}
        self.check_hazard_mapping_table = {}
        self.p2l_map = {}
        self.receive_call_back_event = self.env.event()
        self.receive_done_event = self.env.event()
        self.receive_release_done_event = self.env.event()
        self.set_urgent = False
        self.write_pending = []

        self.channel_count = self.param.CHANNEL
        self.way_count = self.param.WAY
        self.block_count = self.param.BLOCK_PER_PLANE
        self.plane_count = self.param.PLANE
        self.page_count = self.param.PAGE_PER_BLOCK
        self.map_unit_count = self.core.MAPUNIT_PER_PLANE
        self.cell_type = self.param.NAND_CELL_TYPE
        self.lpo_count = [0] * self.param.STREAM_COUNT
        self.write_count = [0] * self.param.STREAM_COUNT
        self.gc_write_count = 0
        self.addr = [AddressID()] * self.param.STREAM_COUNT
        self.plane_allocation_scheme = self.core.PlaneAllocationScheme

    class AddressID:
        def __init__(self):
            self.channel = 0
            self.way = 0
            self.plane = 0
            self.block = 0
            self.page = 0
            self.lpo = 0

    def get_init_ppn(self):
        ppn = (
            ((((self.addr[0].channel *
                self.way_count) +
               self.addr[0].way) *
              self.plane_count +
              self.addr[0].plane) *
             self.block_count +
             self.addr[0].block) *
            self.page_count +
            self.addr[0].page)
        return ppn

    def print_unmapped_lpn(self, lpn):
        emphasis = '\033[1m'
        if sys.platform == 'win32':
            emphasis += '\033[7m'
        else:
            emphasis += '\033[5m'
        # print(f"\n{emphasis}\033[33m[WARNING] Host Read 명령이 \'Unmap\' 발생하였습니다. LPN={lpn}({lpn:#x})\033[0m")

    def set_mapping_table(self, test_size):
        assert self.page_count % self.cell_type.value == 0
        page = -1
        block = 0
        for i in range(test_size):
            if i % (self.channel_count * self.way_count *
                    self.plane_count * self.map_unit_count) == 0:
                page += 1
            if i % self.map_unit_count == 0:
                self.addr[0] = self.allocate_plane(0)
                self.addr[0].block = block
                self.addr[0].page = page
            ppn = self.get_init_ppn()
            self.mapping_table[i] = ppn * self.map_unit_count + i % self.map_unit_count
            self.check_hazard_mapping_table[i] = ppn * self.map_unit_count + i % self.map_unit_count
            self.p2l_map[ppn * self.map_unit_count + i % self.map_unit_count] = i
            if page == self.page_count - 1 and i % self.map_unit_count == 3 and self.addr[0].channel == self.channel_count - 1 and self.addr[0].way == self.way_count - 1 and self.addr[0].plane == self.plane_count - 1:
                page = 0
                block += 1
                if block == self.block_count:
                    block = 0
            address = AddressID()
            address.copy_from(self.addr[0])
            yield address
        self.write_count[0] = 0

    def set_sustained_mapping_table(self, size, block_ratio, nead_test_size):
        assert self.page_count % self.cell_type.value == 0
        page = 0
        block = 0
        test_size = int(self.channel_count * self.way_count * self.plane_count * self.block_count * self.page_count * self.map_unit_count * block_ratio * size)

        assert nead_test_size <= test_size, "Increase the block rate or size, or decrease the test size."

        for i in range(test_size):
            assert page <= self.page_count
            if i % self.map_unit_count == 0:
                self.addr[0] = self.allocate_plane(0)
                self.addr[0].block = block
                self.addr[0].page = page
            ppn = self.get_init_ppn()
            self.mapping_table[i] = ppn * self.map_unit_count + i % self.map_unit_count
            self.p2l_map[ppn * self.map_unit_count + i % self.map_unit_count] = i
            if i % self.map_unit_count == 3 and self.addr[0].channel == self.channel_count - 1 and self.addr[0].way == self.way_count - 1 and self.addr[0].plane == self.plane_count - 1:
                block += 1
                if block > self.block_count * block_ratio:
                    block = 0
                    page += 1
            address = AddressID()
            address.copy_from(self.addr[0])
            yield address
        self.write_count[0] = 0
        print("The pages in the block are filled up to page :", page)

    def allocate_plane(self, stream):
        address = AddressID()
        if self.plane_allocation_scheme == 'CWP':
            address.channel = self.write_count[stream] % self.channel_count
            address.way = (
                self.write_count[stream] // self.channel_count) % self.way_count
            address.plane = (
                self.write_count[stream] // (self.channel_count * self.way_count)) % self.plane_count

        elif self.plane_allocation_scheme == 'CPW':
            address.channel = self.write_count[stream] % self.channel_count
            address.way = (
                self.write_count[stream] // (self.channel_count * self.plane_count)) % self.way_count
            address.plane = (
                self.write_count[stream] // self.channel_count) % self.plane_count

        elif self.plane_allocation_scheme == 'WCP':
            address.channel = (
                self.write_count[stream] // self.way_count) % self.channel_count
            address.way = self.write_count[stream] % self.way_count
            address.plane = (
                self.write_count[stream] // (self.way_count * self.channel_count)) % self.plane_count

        elif self.plane_allocation_scheme == 'WPC':
            address.channel = (
                self.write_count[stream] // (self.way_count * self.plane_count)) % self.channel_count
            address.way = self.write_count[stream] % self.way_count
            address.plane = (
                self.write_count[stream] // self.way_count) % self.plane_count

        elif self.plane_allocation_scheme == 'PCW':
            address.channel = (
                self.write_count[stream] // self.plane_count) % self.channel_count
            address.way = (self.write_count[stream] // (self.plane_count *
                           self.channel_count)) % self.way_count
            address.plane = self.write_count[stream] % self.plane_count

        elif self.plane_allocation_scheme == 'PWC':
            address.channel = (
                self.write_count[stream] // (self.plane_count * self.way_count)) % self.channel_count
            address.way = (
                self.write_count[stream] // self.plane_count) % self.way_count
            address.plane = self.write_count[stream] % self.plane_count

        self.write_count[stream] += 1
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

    def page_allocater(self, packet):
        stream = packet['nvm_transaction'].stream_id
        self.addr[stream] = self.allocate_plane(stream)
        alloc_packet = AMLPIF.create_alloc_packet(packet, self.addr[stream])
        self.send_sq(
            alloc_packet,
            self.address,
            self.address_map.FBM,
            src_submodule=self.write_handler)
        yield self.receive_call_back_event
        self.lpo_count[alloc_packet['nvm_transaction'].stream_id] = 0

    def copy_address(self, stream):
        address = AddressID()
        address.channel = self.addr[stream].channel
        address.way = self.addr[stream].way
        address.plane = self.addr[stream].plane
        address.block = self.addr[stream].block
        address.page = self.addr[stream].page
        address.lpo = self.addr[stream].lpo
        return address

    def lookup_mapping_table(self, lpn):
        return self.mapping_table[lpn]

    def read_handler(self, packet):

        lpn = packet['nvm_transaction'].lpn
        packet['nvm_transaction_flash'] = NvmTransactionFlash(
            AddressID())
        if lpn in self.mapping_table:
            self.read_map_count += 1
            packet['nvm_transaction_flash'].ppn = self.lookup_mapping_table(
                lpn) // self.map_unit_count
            packet['nvm_transaction_flash'].address.lpo = self.lookup_mapping_table(
                lpn) % self.map_unit_count
            self.get_address(packet)
            self.send_sq(
                packet,
                self.address,
                self.address_map.TSU,
                src_submodule=self.read_handler)
        else:
            self.read_unmap_count += 1
            self.print_unmapped_lpn(lpn)
            packet['nvm_transaction_flash'] = NvmTransactionFlash(
                AddressID())
            packet['nvm_transaction_flash'].unmap_check = True
            self.send_sq(
                packet,
                self.address,
                self.address_map.TSU,
                src_submodule=self.read_handler)

    def alloc_ppn(self, packet):
        stream = packet['nvm_transaction'].stream_id

        address = self.copy_address(stream)
        address.lpo = self.lpo_count[stream]
        self.lpo_count[stream] += 1
        if packet['nvm_transaction'].transaction_source_type == TransactionSourceType.UserIO:
            packet['nvm_transaction_flash'] = NvmTransactionFlash(address, packet['nvm_transaction'])
        else:
            packet['nvm_transaction_flash'].address = address
        self.alloc_request_ppn_count += 1
        packet['nvm_transaction_flash'].ppn = self.get_new_ppn(packet)

        if packet['nvm_transaction'].transaction_source_type == TransactionSourceType.UserIO and packet['nvm_transaction'].transaction_type != eCMDType.Flush:
            self.check_hazard_mapping_table[packet['nvm_transaction'].lpn] = packet['nvm_transaction_flash'].ppn * self.map_unit_count + packet['nvm_transaction_flash'].address.lpo

    def pending_user_request(self, packet):
        if packet['nvm_transaction'].transaction_source_type == TransactionSourceType.UserIO and self.set_urgent:
            self.write_pending.append(packet)
            return True
        else:
            return False

    def flush_handler(self, packet):
        print(packet)
        print(self.write_count[0])
        stream = packet['nvm_transaction'].stream_id
        while True:
            if self.write_count[stream] % (self.channel_count * self.way_count * self.plane_count * self.map_unit_count * self.cell_type.value) == 0:
                break
            send_packet = copy.deepcopy(packet)
            if self.lpo_count[stream] == self.map_unit_count or self.write_count[stream] == 0:
                yield from self.page_allocater(send_packet)
                self.requset_page_alloc += 1

            self.alloc_ppn(send_packet)
            send_packet['nvm_transaction'].transaction_type = eCMDType.Write
            send_packet['nvm_transaction'].buffer_ptr = -1
            self.send_sq(
                send_packet,
                self.address,
                self.address_map.TSU,
                src_submodule=self.flush_handler)
            self.receive_done_event.succeed()
            self.receive_done_event = self.env.event()
        packet['nvm_transaction'].transaction_type = eCMDType.FlushDone
        self.send_sq(
            packet,
            self.address,
            self.address_map.DCL,
            src_submodule=self.flush_handler)
        print(self.write_count[0])

    def write_handler(self, packet):
        if packet['nvm_transaction'].transaction_type == eCMDType.Write:
            stream = packet['nvm_transaction'].stream_id

            if self.pending_user_request(packet):
                return

            if self.lpo_count[stream] == self.map_unit_count or self.write_count[stream] == 0:
                yield from self.page_allocater(packet)
                self.requset_page_alloc += 1
            if self.write_count[stream] == 0 and stream == 1:
                yield from self.page_allocater(packet)
                self.requset_page_alloc += 1

            self.alloc_ppn(packet)

            self.send_sq(
                packet,
                self.address,
                self.address_map.TSU,
                src_submodule=self.write_handler)
            self.receive_done_event.succeed()
            self.receive_done_event = self.env.event()
        else:
            self.flush_count += 1
            # print(packet, "count", self.flush_count)
            # print(self.write_count[0])
            stream = packet['nvm_transaction'].stream_id
            while True:
                if self.write_count[stream] % (
                        self.channel_count * self.way_count * self.plane_count * self.map_unit_count * self.cell_type.value) == 0 and self.lpo_count[stream] == self.map_unit_count:
                    break
                send_packet = copy.deepcopy(packet)
                if self.lpo_count[stream] == self.map_unit_count or self.write_count[stream] == 0:
                    yield from self.page_allocater(send_packet)
                    self.requset_page_alloc += 1

                self.alloc_ppn(send_packet)
                send_packet['nvm_transaction'].transaction_type = eCMDType.Write
                send_packet['nvm_transaction'].buffer_ptr = -1
                self.send_sq(
                    send_packet,
                    self.address,
                    self.address_map.TSU,
                    src_submodule=self.write_handler)
                self.receive_done_event.succeed()
                self.receive_done_event = self.env.event()
            packet['nvm_transaction'].transaction_type = eCMDType.Flush
            self.send_sq(
                packet,
                self.address,
                self.address_map.TSU,
                src_submodule=self.write_handler)
            # print(self.write_count[0])

    def handle_write_completion(self, packet):
        if packet['nvm_transaction'].transaction_type == eCMDType.WriteDone and packet['nvm_transaction'].hazard_flag == False:
            lpn = packet['nvm_transaction'].lpn
            ppn = packet['nvm_transaction_flash'].ppn
            lpo = packet['nvm_transaction_flash'].address.lpo
            if lpn in self.mapping_table:
                update_packet = AMLPIF.create_map_update_packet(packet)
                update_packet['nvm_transaction_flash'].ppn = self.lookup_mapping_table(lpn) // self.map_unit_count
                update_packet['nvm_transaction_flash'].address.lpo = self.lookup_mapping_table(lpn) % self.map_unit_count

                self.get_address(update_packet)

                old_ppn = self.lookup_mapping_table(lpn)
                self.update_mapping_table(lpn, lpo, ppn, old_ppn)

                self.write_done_count += 1
                self.send_sq(
                    update_packet,
                    self.address,
                    self.address_map.FBM,
                    src_submodule=self.done_handler)
                yield self.receive_release_done_event
            else:
                self.update_mapping_table(lpn, lpo, ppn)
                self.write_done_count += 1

        else:
            if packet['nvm_transaction'].transaction_type == eCMDType.WriteDone:
                self.not_update_map += 1
                self.write_done_count += 1
            else:
                self.read_done_count += 1

    def done_handler(self, packet):
        if packet['nvm_transaction'].buffer_ptr == -1:
            self.send_sq(
                packet,
                self.address,
                self.address_map.FBM,
                src_submodule=self.done_handler)
        else:
            yield from self.handle_write_completion(packet)

            self.send_sq(
                packet,
                self.address,
                self.address_map.DCL,
                src_submodule=self.done_handler)

    def alloc_done_handler(self, packet):
        assert 'set_urgent' not in packet
        self.receive_call_back_event.succeed()
        self.receive_call_back_event = self.env.event()
        self.page_alloc_count += 1
        yield self.receive_done_event

    def release_done_handler(self, packet):
        assert 'set_urgent' not in packet
        self.receive_release_done_event.succeed()
        self.receive_release_done_event = self.env.event()
        self.page_release_count += 1

    def update_mapping_table(self, lpn, lpo, ppn, old_ppn=-1):

        if old_ppn != -1:
            del self.p2l_map[old_ppn]
        self.p2l_map[ppn * self.map_unit_count + lpo] = lpn
        self.mapping_table[lpn] = ppn * self.map_unit_count + lpo
        self.map_update_count += 1
        yield from self.memc.write_memory(MemAccessInfo(self.map_buffer_ptr, eResourceType.MAPBuffer, _request_size_B=self.l2p_size_b))

    def check_update_mapping_table_required(self, packet):
        ppn = self.get_new_ppn(packet)
        lpo = packet['nvm_transaction_flash'].address.lpo
        old_ppn = packet['nvm_transaction_flash'].old_ppn * self.map_unit_count + lpo
        if old_ppn in self.p2l_map:
            lpn = self.p2l_map[old_ppn]
            packet['nvm_transaction'].lpn = lpn
            self.update_mapping_table(lpn, lpo, ppn)

    def gc_map_update_handler(self, packet):
        self.check_update_mapping_table_required(packet)

        self.send_sq(
            packet,
            self.address,
            self.address_map.BCM,
            src_submodule=self.gc_map_update_handler)

    def gc_read_handler(self, packet):
        if packet['nvm_transaction'].transaction_type == eCMDType.Read:
            self.send_sq(
                packet,
                self.address,
                self.address_map.TSU,
                src_submodule=self.gc_map_update_handler)
        elif packet['nvm_transaction'].transaction_type == eCMDType.NANDReadDone:
            self.send_sq(
                packet,
                self.address,
                self.address_map.BCM,
                src_submodule=self.gc_map_update_handler)

    def urgent_handler(self, packet):
        if 'set_urgent' in packet:
            self.set_urgent = packet['set_urgent']
        else:
            assert False

        if self.set_urgent == 0:
            for pending_packet in self.write_pending:
                self.wakeup(
                    self.address,
                    self.write_handler,
                    pending_packet)
            self.write_pending.clear()

    def handle_request(self, packet, fifo_id):
        src = packet['src']
        if src == self.address_map.DCL:
            if packet['nvm_transaction'].transaction_type == eCMDType.Write:
                self.wakeup(
                    self.address,
                    self.write_handler,
                    packet,
                    src_id=fifo_id)
            elif packet['nvm_transaction'].transaction_type == eCMDType.Read:
                self.wakeup(
                    self.address,
                    self.read_handler,
                    packet,
                    src_id=fifo_id)
            elif packet['nvm_transaction'].transaction_type == eCMDType.Flush:
                self.wakeup(
                    self.address,
                    self.write_handler,
                    packet,
                    src_id=fifo_id)
                # self.wakeup(
                #     self.address,
                #     self.flush_handler,
                #     packet,
                #     src_id=fifo_id)
        elif src == self.address_map.FBM:
            if 'set_urgent' in packet:
                self.wakeup(
                    self.address,
                    self.urgent_handler,
                    packet,
                    src_id=fifo_id)
            elif packet['nvm_transaction'].transaction_type == eCMDType.Write:
                self.wakeup(
                    self.address,
                    self.alloc_done_handler,
                    packet,
                    src_id=fifo_id)
            else:
                assert packet['nvm_transaction'].transaction_type == eCMDType.WriteDone, packet
                self.wakeup(
                    self.address,
                    self.release_done_handler,
                    packet,
                    src_id=fifo_id)
        elif src == self.address_map.TSU:
            if packet['nvm_transaction'].transaction_source_type == TransactionSourceType.UserIO:
                self.wakeup(
                    self.address,
                    self.done_handler,
                    packet,
                    src_id=fifo_id)
            elif packet['nvm_transaction'].transaction_source_type == TransactionSourceType.GCIO:
                if packet['nvm_transaction'].transaction_type == eCMDType.WriteDone:
                    self.wakeup(
                        self.address,
                        self.gc_map_update_handler,
                        packet,
                        src_id=fifo_id)
                elif packet['nvm_transaction'].transaction_type == eCMDType.NANDReadDone:
                    self.wakeup(
                        self.address,
                        self.gc_read_handler,
                        packet,
                        src_id=fifo_id)
        elif src == self.address_map.BCM:
            if packet['nvm_transaction'].transaction_type == eCMDType.Write:
                self.wakeup(
                    self.address,
                    self.write_handler,
                    packet,
                    src_id=fifo_id)
            elif packet['nvm_transaction'].transaction_type == eCMDType.Read:
                self.wakeup(
                    self.address,
                    self.gc_read_handler,
                    packet,
                    src_id=fifo_id)

    def print_debug(self):
        pass
