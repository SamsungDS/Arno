from collections import deque
from enum import Enum, auto

from core.framework.common import (
    CMD_PATH_FIFO_ID,
    eCacheResultType,
    eCMDType,
    eResourceType)
from core.modules.parallel_unit import ParallelUnit
from product.general.provided_interface import dcl_pif, hdma_pif


class ePCIeOpcode(Enum):
    ReadCompletion = auto()
    ResponseHandlingCMDID = auto()  # read
    ResponseHandlingWriteBack = auto()  # write


class eJobDriverId(Enum):
    Read = 0,
    Write = 1,


class NVMeStats:
    def __init__(self):
        self.clear()

    def clear(self):
        self.write_issue_count = 0
        self.write_dealloc_issue_count = 0
        self.write_done_count = 0

    def write_issue(self, deac):
        if deac == 0:
            self.write_issue_count += 1
        else:
            self.write_dealloc_issue_count += 1

    def print_stats(self):
        for name, value in self.__dict__.items():
            print(f"NVMe: {name}: {value}")

    def write_done(self):
        self.write_done_count += 1


class NVMe(ParallelUnit):
    def __init__(self, product_args, _address, unit_fifo_num=1):
        super().__init__(product_args, _address, unit_fifo_num)
        assert self.address == self.address_map.NVMe

        self.stats = NVMeStats()
        self.cmd_queue = None
        self.read_cache = {}

        self.opcode_to_cmd_type = {
            ePCIeOpcode.ResponseHandlingCMDID: eCMDType.Read,
            ePCIeOpcode.ResponseHandlingWriteBack: eCMDType.Write}

        # for recv cmd
        self.generate_submodule(
            self.cmd_receive_logic, [
                self.feature.NVME_CMD_SRAM_TRANSFER])
        self.generate_submodule(
            self.read_cmd_buffer, [
                self.feature.NVME_CMD_SRAM_TRANSFER])

        # for read dma, cmd response to host
        self.read_completion_submodule = self.generate_submodule(
            self.read_completion, [
                self.feature.NVME_READ_DESC_RELEASE, self.feature.NVME_READ_DONE_CREATE])

        # for write dma, cmd response to host
        self.generate_submodule(
            self.write_completion,
            self.feature.NVME_WRITE_DONE_CREATE_DESC_RELEASE)

        # for read write
        self.generate_submodule(self.auto_desc_processor, self.feature.ZERO)

        self.response_handling_submodule = self.generate_submodule(
            self.response_handling, [self.feature.ZERO, self.feature.NVME_H2D_DONE_HANDLING])

        self.generate_submodule(self.dma_done_handler, self.feature.ZERO)

        self.reset_nvme()

        # for read
        self.generate_submodule(self.job_driver,
                                [self.feature.NVME_CMD_FETCH_JOB_CREATE],
                                s_id=eJobDriverId.Read)
        self.generate_submodule(
            self.read_task_generator, [
                self.feature.NVME_READ_4K_IO_CREATE])

        # for write
        self.generate_submodule(self.job_driver,
                                [self.feature.NVME_CMD_FETCH_JOB_CREATE],
                                s_id=eJobDriverId.Write)
        self.generate_submodule(
            self.write_task_generator, [
                self.feature.NVME_WRITE_4K_IO_CREATE])
        self.generate_submodule(
            self.write_desc_generator,
            self.feature.NVME_4K_RTT_DESC_CREATE_Q_INSERT)
        self.generate_submodule(
            self.write_back_handler,
            self.feature.NVME_WRITE_BACK_REQUEST)

        # for read write
        self.job_fetcher_submodule = self.generate_submodule(
            self.job_fetcher, [
                self.feature.NVME_READ_CMD_Q_HANDLING, self.feature.NVME_WRITE_CMD_Q_HANDLING])
        self.dcl_requset_arbiter_submodule = self.generate_submodule(
            self.data_cache_layer_request_arbiter, [
                self.feature.NVME_NVME_IREAD_REQUEST, self.feature.ZERO])
        self.generate_submodule(self.dma_release, self.feature.ZERO)

        self.read_request_cnt = 0
        self.read_completion_count = 0
        self.read_request_count = 0

        self.qd_margin_factor = 4
        self.nvme_qd_size = self.param.FTL_MAP_UNIT_PER_PLANE * self.param.PLANE * \
            self.param.CHANNEL * self.param.WAY * self.param.NAND_CELL_TYPE.value * self.qd_margin_factor

    class NVMTransaction:
        def __init__(
                self,
                stream_id,
                transaction_source_type,
                transaction_type,
                lpn,
                valid_sector_bitmap,
                buffer_ptr=None):
            self.stream_id = stream_id
            self.transaction_type = transaction_type
            self.transaction_source_type = transaction_source_type
            self.lpn = lpn
            self.valid_sector_bitmap = valid_sector_bitmap
            self.buffer_ptr = buffer_ptr

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

    def init_resource(self, qd):
        self.host_cmd_cnt = 0
        self.free_slot_list = deque()
        self.allocated_slot_list = deque()
        self.slot_to_cmd_id = [-1] * qd
        self.slot_to_lpn_cnt = [-1] * qd
        self.slot_to_cache_result = [-1] * qd
        self.remain_dma_cnt = [-1] * qd
        self.remain_valid_dma_cnt = [0] * qd

    def reset_test(self): pass

    def set_qd(self, qd):
        self.init_resource(self.nvme_qd_size)
        for slot_id in range(self.nvme_qd_size):
            self.free_slot_list.append(slot_id)

    def try_new_cmd_receive(self, packet):
        if self.free_slot_list:
            self.host_cmd_cnt += 1
            packet['slot_id'] = slot_id = self.free_slot_list.popleft()
            self.allocated_slot_list.append(slot_id)
            self.vcd_manager.set_nvme_qd_count(len(self.allocated_slot_list))
            self.vcd_manager.increase_cmd_issue(packet['cmd_type'])
            self.slot_to_cmd_id[slot_id] = packet['cmd_id']
            self.slot_to_cache_result[slot_id] = eCacheResultType.get_dict()

            remain_g_lpn_count = self.remain_dma_cnt[slot_id] = packet['end_g_lpn'] - \
                packet['start_g_lpn'] + 1
            # number of FTL Map Units per One Command
            packet['remain_g_lpn_count'] = remain_g_lpn_count
            self.slot_to_lpn_cnt[slot_id] = self.remain_dma_cnt[slot_id] = remain_g_lpn_count
            self.analyzer.increase_cmd_issue(packet)
            self.vcd_manager.increase_cmd_issue(packet['cmd_type'])
            return True
        else:
            return False

    def cmd_receive_logic(self, packet):
        if self.try_new_cmd_receive(packet):
            yield self.env.timeout(0)
            self.wakeup(
                self.cmd_receive_logic,
                self.job_fetcher,
                packet.copy())
        else:
            self.set_job_fail(self.cmd_receive_logic, cancel_process=True)

    def read_cmd_buffer(self, packet):
        self.wakeup(
            self.read_cmd_buffer,
            self.cmd_receive_logic,
            packet)  # host write cmd recv
        self.send_sq(
            packet.copy(),
            self.read_cmd_buffer,
            self.address_map.HOST,
            src_submodule=self.read_cmd_buffer,
            description='Release Host QD')

    def auto_desc_processor(self, packet):
        send_packet = hdma_pif.HDMARequestSQ(packet, self.address)
        send_packet['cmd_id'] = self.slot_to_cmd_id[send_packet['slot_id']]
        self.send_sq(
            send_packet,
            self.address,
            self.address_map.HDMA,
            src_submodule=self.auto_desc_processor)

    def read_completion(self, packet):
        if 'packet_list' in packet:
            del packet['packet_list']
        if packet['opcode'] == ePCIeOpcode.ReadCompletion:
            slot_id = packet['slot_id']
            self.remain_dma_cnt[slot_id] -= 1

            yield from self.read_completion_submodule.activate_feature(self.feature.NVME_READ_DESC_RELEASE)
            self.wakeup(
                self.read_completion,
                self.dma_release,
                packet.get_copy())
            packet['cmd_type'] = eCMDType.ReadDone
            packet['remain_dma_count'] = self.remain_dma_cnt[slot_id]
            yield from self.read_completion_submodule.activate_feature(self.feature.NVME_READ_DONE_CREATE)
            dcl_packet = dcl_pif.ReadDoneSQ(packet.get_copy(), self.address)
            dcl_packet['user'] = 'host'
            if packet['nvm_transaction'].transaction_type == 'nand_read_done':
                self.slot_to_cache_result[slot_id][eCacheResultType.miss] += 1
            else:
                self.slot_to_cache_result[slot_id][eCacheResultType.logical_temporal] += 1

            self.generate_dcl_packet(dcl_packet)
            self.send_sq(
                dcl_packet,
                self.address,

                self.address_map.DCL,
                src_submodule=self.read_completion,
                dst_fifo_id=0)


            if self.remain_dma_cnt[slot_id] == 0:
                packet['cmd_last_desc'] = True
                packet['opcode'] = ePCIeOpcode.ResponseHandlingCMDID
                self.wakeup(
                    self.read_completion,
                    self.response_handling,
                    packet)
        else:
            assert 0, "invalid opCode"

    def write_completion(self, packet):
        # confirm the completion of one FTL MapUnit for one Command
        if packet['desc_id']['id'] != -1 or packet['deac'] == 1:
            self.remain_dma_cnt[packet['slot_id']] -= 1

        packet['cmd_last_desc'] = True if self.remain_dma_cnt[packet['slot_id']] == 0 else False
        self.wakeup(self.write_completion, self.dma_release, packet)

    def response_handling(self, packet):
        if packet['opcode'] == ePCIeOpcode.ResponseHandlingCMDID:
            yield from self.response_handling_submodule.activate_feature(self.feature.ZERO)
        elif packet['opcode'] == ePCIeOpcode.ResponseHandlingWriteBack:
            yield from self.response_handling_submodule.activate_feature(self.feature.NVME_H2D_DONE_HANDLING)
        else:
            assert 0, "invalid opCode"

        slot_id = packet['slot_id']
        cmd_type = self.opcode_to_cmd_type[packet['opcode']]

        packet['cmd_id'] = self.slot_to_cmd_id[slot_id]
        packet['cmd_type'] = cmd_type

        cache_hit_result = eCacheResultType.miss
        if cmd_type == eCMDType.Read:
            cache_hit_result = self.analyzer.get_cmd_cache_hit_result(
                self.slot_to_lpn_cnt[slot_id], self.slot_to_cache_result[slot_id])

        self.analyzer.increase_cmd_done(
            cmd_type, self.slot_to_cmd_id[slot_id], cache_hit_result)
        self.vcd_manager.increase_cmd_done(cmd_type)
        packet['cmd_id'] = self.slot_to_cmd_id[slot_id]
        if packet['opcode'] == ePCIeOpcode.ResponseHandlingWriteBack:
            self.send_sq(
                packet.copy(),
                self.address,
                self.address_map.PCIe,
                src_submodule=self.response_handling,
                description='CMDDone')

        assert slot_id in self.allocated_slot_list, 'already done cmd'
        self.allocated_slot_list.remove(slot_id)
        self.vcd_manager.set_nvme_qd_count(len(self.allocated_slot_list))
        self.free_slot_list.append(slot_id)
        self.wakeup(self.response_handling, self.cmd_receive_logic)

    def dma_done_handler(self, packet):
        if packet['cmd_type'] == eCMDType.Read:
            self.wakeup(
                self.dma_done_handler,
                self.read_completion,
                packet,
                description='Read DMA Done')
            self.read_completion_count += 1
            self.vcd_manager.set_read_completion_count(
                self.read_completion_count)
        else:
            self.wakeup(
                self.dma_done_handler,
                self.write_completion,
                packet,
                description='Write DMA Done')

    def job_fetcher(self, packet):
        cmd_type: eCMDType = packet['cmd_type']
        packet['seq_flag'] = False
        if cmd_type == eCMDType.Read:
            yield from self.job_fetcher_submodule.activate_feature(self.feature.NVME_READ_CMD_Q_HANDLING)
            self.wakeup(
                self.job_fetcher,
                self.job_driver,
                packet,
                dst_id=eJobDriverId.Read,
                description='Read CMD')
        elif cmd_type == eCMDType.Write:
            yield from self.job_fetcher_submodule.activate_feature(self.feature.NVME_WRITE_CMD_Q_HANDLING)
            self.wakeup(
                self.job_fetcher,
                self.job_driver,
                packet,
                dst_id=eJobDriverId.Write,
                description=f'{cmd_type.name} CMD')

        else:
            assert 0, "not support command"
            return

    def job_driver(self, packet, s_id):
        # TR split, TR size == Logical MapUnit Size (32KB)
        split_tr_list = []
        while packet['start_lpn'] != packet['end_lpn']:
            split_tr = packet.copy()
            # Logical MapUnit
            packet['start_lpn'] += 1
            # FTL MapUnit
            packet['start_g_lpn'] = packet['start_lpn'] * \
                self.param.STORAGE_MAP_UNIT_COUNT_PER_LOGICAL_MAPPING_UNIT
            # LBA Unit
            packet['start_lba'] = packet['start_g_lpn'] * \
                self.param.SECTOR_PER_GAUDI_MAP_UNIT

            start_lba_diff = packet['start_lba'] - split_tr['start_lba']
            packet['lba_size'] -= start_lba_diff
            split_tr['lba_size'] = start_lba_diff
            assert packet['lba_size'] > 0

            split_tr['end_lpn'] = split_tr['start_lpn']
            split_tr['end_g_lpn'] = packet['start_g_lpn'] - 1
            split_tr['end_lba'] = packet['start_lba'] - 1

            split_tr_list.append(split_tr)
        split_tr_list.append(packet)

        for tr in split_tr_list:

            yield from self.activate_feature(self.feature.NVME_CMD_FETCH_JOB_CREATE, s_id)
            if s_id == eJobDriverId.Read:

                self.wakeup(
                    self.job_driver,
                    self.read_task_generator,
                    tr,
                    src_id=s_id,
                    description='Read')
            elif s_id == eJobDriverId.Write:
                self.wakeup(
                    self.job_driver,
                    self.write_task_generator,
                    tr,
                    src_id=s_id,
                    description='TR Split ')
            else:
                assert 0, 'invalid path'

    def read_task_generator(self, packet):
        assert packet['start_lpn'] == packet['end_lpn']
        assert packet['lba_size'] > 0
        desc_id_list = yield from self.allocate_resource(self.feature.NVME_READ_4K_IO_CREATE, eResourceType.ReadDMADesc)

        self.read_dma_alloc_Cnt += 1

        packet['desc_id'] = desc_id_list[0]
        sector_offset, sector_count, remnent = self.get_sector_count(packet)
        packet['valid_sector_bitmap'] = (
            [0] * sector_offset) + ([1] * sector_count) + ([0] * remnent)
        packet['is_last_dma'] = True if packet['start_g_lpn'] == packet['end_g_lpn'] else False
        packet['is_valid'] = True
        packet['is_first_dma'] = True
        communication_packet = packet.copy()
        packet['sector_count'] = sector_count
        packet['start_lba'] += sector_count
        packet['lba_size'] -= sector_count
        self.make_desc(packet, communication_packet, True)
        self.wakeup(
            self.read_task_generator,
            self.data_cache_layer_request_arbiter,
            communication_packet,
            description='Send Read')

        if packet['start_g_lpn'] != packet['end_g_lpn']:
            packet['start_g_lpn'] += 1
            packet['start_lba'] = packet['start_g_lpn'] * \
                self.param.SECTOR_PER_GAUDI_MAP_UNIT
            self.set_job_fail(self.read_task_generator)

    def get_sector_count(self, packet):
        offset = packet['start_lba'] % self.param.SECTOR_PER_GAUDI_MAP_UNIT
        remain = self.param.SECTOR_PER_GAUDI_MAP_UNIT - offset
        sector_offset = offset
        remnent = 0 if packet['lba_size'] >= remain else remain - \
            packet['lba_size']
        sector_count = self.param.SECTOR_PER_GAUDI_MAP_UNIT - sector_offset - remnent
        return sector_offset, sector_count, remnent

    def write_task_generator(self, packet):
        # per LogicalMapUnit (32KB) task generator
        assert packet['start_lpn'] == packet['end_lpn']
        assert packet['lba_size'] > 0

        desc_id_list = None
        buffer_list = None

        host_write_start_g_lpn = packet['start_g_lpn']
        host_write_end_g_lpn = packet['end_g_lpn']
        host_write_start_g_lpn_offset = host_write_start_g_lpn % self.param.STORAGE_MAP_UNIT_COUNT_PER_LOGICAL_MAPPING_UNIT
        host_write_end_g_lpn_offset = host_write_end_g_lpn % self.param.STORAGE_MAP_UNIT_COUNT_PER_LOGICAL_MAPPING_UNIT

        # Eight FTL Mapunits (4KB) per LogicalMapUnit (32KB)
        # DMA is performed in the unit of FTL MapUnit (4KB)
        dma_request_size = host_write_end_g_lpn_offset - host_write_start_g_lpn_offset + 1
        buffer_request_size = dma_request_size
        # DMA Descriptor is generated in the unit of FTL MapUnit (4KB)
        desc_id_list = yield from self.allocate_resource(self.feature.NVME_WRITE_4K_IO_CREATE, eResourceType.WriteDMADesc, dma_request_size)
        buffer_list = yield from self.allocate_resource(-1, eResourceType.WriteBuffer, buffer_request_size)

        communication_packet_list = []
        base_g_lpn = packet['start_lpn'] * \
            self.param.STORAGE_MAP_UNIT_COUNT_PER_LOGICAL_MAPPING_UNIT

        # Generate Eight FTL MapUnit Packets (4KB x 8)
        for g_lpn_offset in range(
                self.param.STORAGE_MAP_UNIT_COUNT_PER_LOGICAL_MAPPING_UNIT):
            is_valid = False
            g_lpn = base_g_lpn + g_lpn_offset
            sector_offset, sector_count, remnent = None, None, None

            if host_write_start_g_lpn_offset <= g_lpn_offset <= host_write_end_g_lpn_offset:
                sector_offset, sector_count, remnent = self.get_sector_count(
                    packet)
                is_valid = True

            if sector_offset is not None:
                packet['desc_id'] = desc_id_list.pop()
                packet['buffer_list'] = buffer_list.pop()
                packet['deac'] = 0

                packet['start_g_lpn'] = g_lpn
                packet['start_lba'] = g_lpn * \
                    self.param.SECTOR_PER_GAUDI_MAP_UNIT
                packet['lba_size'] -= sector_count
                packet['valid_sector_bitmap'] = (
                    [0] * sector_offset) + ([1] * sector_count) + ([0] * remnent)
                packet['sector_count'] = sector_count

                # The last FTL MapUnit in one LogicalMapUnit
                packet['is_last_dma'] = len(buffer_list) == 0
                packet['is_valid'] = is_valid

                communication_packet_list.append(packet.copy())
                self.write_dma_alloc_cnt += 1

        is_first = True
        for communication_packet in communication_packet_list:
            communication_packet['is_first_dma'] = is_first
            is_first = False
            self.wakeup(
                self.write_task_generator,
                self.write_desc_generator,
                communication_packet,
                description='FTL MapUnit Split ')

    def make_desc(self, srcPkt, dmaDesc, isRead, buffer_ptr=None):
        dmaDesc['slot_id'] = srcPkt['slot_id']
        dmaDesc['cmd_type'] = srcPkt['cmd_type']
        dmaDesc['issue_time'] = srcPkt['issue_time']
        dmaDesc['lpn'] = srcPkt['start_g_lpn']
        dmaDesc['valid_sector_bitmap'] = srcPkt['valid_sector_bitmap']
        dmaDesc['host_stream_id'] = srcPkt['host_stream_id']
        dmaDesc['desc_id'] = {
            'id': srcPkt['desc_id'],
            'is_last_dma': srcPkt['is_last_dma'],
            'sector_count': srcPkt['sector_count'],
            'is_valid': srcPkt['is_valid'],
            'host_stream_id': srcPkt['host_stream_id'] if 'host_stream_id' in srcPkt else 0}
        if buffer_ptr is not None:
            dmaDesc['desc_id']['buffer_ptr'] = buffer_ptr
        dmaDesc['seq_flag'] = srcPkt['seq_flag']
        dmaDesc['is_first_dma'] = srcPkt['is_first_dma']

    def write_desc_generator(self, packet):
        dma_desc = dict()
        self.make_desc(packet, dma_desc, False, packet['buffer_list'])
        send_packet = hdma_pif.HDMARequestSQ(dma_desc, self.address)
        send_packet['cmd_id'] = self.slot_to_cmd_id[send_packet['slot_id']]
        self.send_sq(
            send_packet,
            self.address,
            self.address_map.HDMA,
            src_submodule=self.write_desc_generator)

    def is_write_completed_packet(self, packet):
        is_normal_write_completed = packet['cmd_last_desc'] and packet.get(
            'delayed_flag', False) is False
        is_fua_write_completed = packet['cmd_last_desc'] and packet.get(
            'delayed_completion', False) is True
        return is_normal_write_completed or is_fua_write_completed

    def write_back_handler(self, packet):
        self.stats.write_done()
        if packet['desc_id']['id'] != -1:
            self.release_resource(
                eResourceType.WriteDMADesc,
                packet['desc_id']['id'])
        if self.is_write_completed_packet(packet):
            write_zero = packet.get('write_zero', False)
            response_packet = {
                'slot_id': packet['slot_id'],
                'opcode': ePCIeOpcode.ResponseHandlingWriteBack,
                'write_zero': write_zero}
            self.wakeup(
                self.write_back_handler,
                self.response_handling,
                response_packet)

    def data_cache_layer_request_arbiter(self, packet):
        cmd_type = packet['cmd_type']
        if cmd_type == eCMDType.Read:

            yield from self.dcl_requset_arbiter_submodule.activate_feature(self.feature.NVME_NVME_IREAD_REQUEST)
            self.read_task_issue_cnt += 1
            self.vcd_manager.set_read_request_count(self.read_task_issue_cnt)

            send_packet = dcl_pif.ReadSQ(packet, self.address)
            send_packet['lpn'] = packet['lpn']

        elif cmd_type == eCMDType.Write:
            yield from self.dcl_requset_arbiter_submodule.activate_feature(self.feature.ZERO)
            send_packet = dcl_pif.WriteSQ(packet, self.address)
            send_packet['lpn'] = packet['lpn']
            send_packet['write_zero'] = False
            send_packet['deac'] = packet.get('deac', 0)
            self.stats.write_issue(send_packet['deac'])
        else:
            assert 0, f' {packet["cmd_type"]} is invalid'

        send_packet['user'] = 'host'
        self.generate_dcl_packet(send_packet)
        self.send_sq(
            send_packet,
            self.address,
            self.address_map.DCL,
            src_submodule=self.data_cache_layer_request_arbiter,
            dst_fifo_id=CMD_PATH_FIFO_ID.eDown.value)

    def binary_list_to_int(self, bits):
        return int(''.join(map(str, bits)), 2)

    def generate_dcl_packet(self, packet):
        if packet['cmd_type'] == eCMDType.Write:
            transaction_type = 'write'
        elif packet['cmd_type'] == eCMDType.ReadDone:
            transaction_type = 'read_done_sq'
        else:
            assert packet['cmd_type'] == eCMDType.Read
            transaction_type = 'read'

        if packet['cmd_type'] == eCMDType.ReadDone:
            packet['nvm_transaction'].transaction_type = transaction_type
        else:
            buffer_ptr = packet.get('desc_id', {}).get('buffer_ptr')
            nvm_transaction = self.NVMTransaction(
                packet['host_stream_id'],
                'user_io',
                transaction_type,
                packet['lpn'],
                self.binary_list_to_int(
                    packet['valid_sector_bitmap']),
                buffer_ptr)
            packet['nvm_transaction'] = nvm_transaction

    def dma_release(self, packet):
        if packet['cmd_type'] == eCMDType.Read:  # READ
            self.read_dma_release_cnt += 1
            self.release_resource(
                eResourceType.ReadDMADesc,
                packet['desc_id']['id'])
        else:   # WRITE
            self.write_dma_release_cnt += 1
            self.wakeup(
                self.dma_release,
                self.data_cache_layer_request_arbiter,
                packet,
                description='Write Task Req')

    def handle_request(self, packet, fifo_id):
        if packet['src'] == self.address_map.PCIe:
            if packet['cmd_type'] == eCMDType.Write:
                self.wakeup(
                    self.address,
                    self.cmd_receive_logic,
                    packet,
                    src_id=fifo_id)  # host write cmd recv
            else:
                self.wakeup(
                    self.address,
                    self.read_cmd_buffer,
                    packet,
                    src_id=fifo_id)  # host read cmd recv
        elif packet['src'] == self.address_map.HDMA:
            self.wakeup(
                self.address,
                self.dma_done_handler,
                packet,
                src_id=fifo_id)
        elif packet['src'] == self.address_map.DCL:
            # Write Command 수행 시, DCL으로부터 cache_write_done 받았을 때에만 Touch 된다.
            if packet['nvm_transaction'].transaction_type == 'cache_write_done':
                self.wakeup(
                    self.address,
                    self.write_back_handler,
                    packet,
                    src_id=fifo_id)
            # Read Command에 대해 Cache Hit인 경우 DCL으로부터 cache_read_done 받았을 때에만
            # Touch 된다.
            elif packet['nvm_transaction'].transaction_type == 'cache_read_done':
                self.read_request_cnt += 1
                self.wakeup(
                    self.address,
                    self.auto_desc_processor,
                    packet,
                    src_id=fifo_id,
                    description='Analyze Ready Q')
            # Read Command에 대해 CM으로부터 nand_read_done 받았을 때에만 Touch 된다.
            elif packet['nvm_transaction'].transaction_type == 'nand_read_done':
                self.read_request_cnt += 1
                packet['cmd_type'] = eCMDType.Read
                self.wakeup(
                    self.address,
                    self.auto_desc_processor,
                    packet,
                    src_id=fifo_id,
                    description='Analyze Ready Q')
            else:   # Read Command에 대해 HDMA가 ReadBuffer로부터 PCIe를 통해 Host로 WriteDMA 완료한 이후, DCL으로부터 read_done_cq 받았을 때에만 Touch 된다.
                assert packet['nvm_transaction'].transaction_type == 'read_done_cq'
                self.send_sq(
                    packet.copy(),
                    self.address,
                    self.address_map.PCIe,
                    src_submodule=self.response_handling,
                    description='DCLDDone')
        elif packet['src'] == self.address_map.BA:
            self.resource_allocate_callback(packet)
        else:
            assert 0, 'not support interface'

    def reset_nvme(self):
        self.read_dma_alloc_Cnt = 0
        self.write_dma_alloc_cnt = 0

        self.read_dma_release_cnt = 0
        self.write_dma_release_cnt = 0

        self.read_task_issue_cnt = 0

        self.read_request_cnt = 0
        self.stats.clear()

    def check_DMA(self, read_dma_run_cnt, write_dma_run_cnt):
        print(
            f'run / alloc read dma alloc cnt: {read_dma_run_cnt, self.read_dma_alloc_Cnt}')
        print(
            f'run / alloc write dma alloc cnt: {write_dma_run_cnt, self.write_dma_alloc_cnt}')
        print(
            f'release read dma cnt: {read_dma_run_cnt, self.read_dma_release_cnt}')
        return read_dma_run_cnt == self.read_dma_release_cnt and write_dma_run_cnt == self.write_dma_alloc_cnt and read_dma_run_cnt == self.read_dma_release_cnt

    def printDebug(self, read_dma_run_cnt, write_dma_run_cnt):
        print('utp debug print')
        print(
            f'- expect / actual read cmd done cnt : {self.analyzer.command_issue_count[eCMDType.Read], self.analyzer.command_done_count[eCMDType.Read]}')
        print(
            f'- expect / actual write cmd done cnt : {self.analyzer.command_issue_count[eCMDType.Write], self.analyzer.command_done_count[eCMDType.Write]}')

        print('hth debug print')
        print(
            f'- run / alloc read dma alloc cnt: {read_dma_run_cnt, self.read_dma_alloc_Cnt}')
        print(
            f'- run / alloc write dma alloc cnt: {write_dma_run_cnt, self.write_dma_alloc_cnt}')
        print(
            f'- release read dma cnt: {read_dma_run_cnt, self.read_dma_release_cnt}')
        print(
            f'- write / read issue cnt to cm: {self.stats.write_issue_count, self.read_task_issue_cnt}')

        print('hdp debug print')
        print(f'- read dma reqeust from ecc : {self.read_request_cnt}')
