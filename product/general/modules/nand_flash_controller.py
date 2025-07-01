from collections import deque

from core.framework.cell_type import Cell
from core.framework.common import MemAccessInfo, eResourceType
from core.framework.fifo_id import NFC_FIFO_ID
from core.framework.media_common import (NANDCMDType, eMediaFifoID,
                                         generate_dbl_info, get_channel_id,
                                         is_data_cmd, is_din_cmd, is_dout_cmd)
from core.modules.parallel_unit import ParallelUnit
from core.provided_interface import ecc_pif, nand_pif
from product.general.provided_interface import job_scheduler_pif
from product.general.provided_interface.product_pif_factory import ProductPIFfactory


class NFCStats:
    def __init__(self):
        self.ecc_issued_lpage_count = 0
        self.dma_done_lpage_count = 0
        self.dma_done_nand_cmd_count = 0
        self.dma_done_issued_count = 0

    def ecc_issued(self, issued_count=1):
        self.ecc_issued_lpage_count += issued_count

    def dma_done(self, is_cmd_done):
        if is_cmd_done:
            self.dma_done_nand_cmd_count += 1
        self.dma_done_lpage_count += 1

    def dma_done_issue(self):
        self.dma_done_issued_count += 1

    def print_stats(self):
        for name, value in self.__dict__.items():
            print(f"NFC: {name}: {value}")


class NandFlashController(ParallelUnit):
    def __init__(self, product_args, _address=0, unit_fifo_num=1):
        super().__init__(product_args, _address, unit_fifo_num)
        assert self.address == self.address_map.NFC
        self.SKIP_READ_BUFFER_ALLOC = False

        self.stats = NFCStats()
        self.operation_done_submodule = self.generate_submodule(
            self.operation_done, [self.feature.NFC_OPERATION_DONE])
        self.generate_submodule(self.nand_control, self.feature.MIN_NS)
        self.generate_submodule(
            self.allocate_buffer, [
                self.feature.MIN_NS, self.feature.ZERO])
        self.generate_submodule(
            self.allocate_done_handler, [
                self.feature.MIN_NS, self.feature.ZERO])
        self.generate_submodule(self.dma_done, self.feature.ZERO)

        self.FDMA_BUFFERING_UNIT_COUNT = 4
        self.fdma_buffering_id = 0
        for fdma_id in range(self.FDMA_BUFFERING_UNIT_COUNT):
            self.generate_submodule(self.fdma, [self.feature.ZERO], fdma_id)

        self.nfc_channel_submodule = [None for _ in range(self.param.CHANNEL)]
        self.nfcp_channel_submodule = [None for _ in range(self.param.CHANNEL)]
        self.channel_buffer_submodule = [
            None for _ in range(self.param.CHANNEL)]
        for ch in range(self.param.CHANNEL):
            self.nfc_channel_submodule[ch] = self.generate_submodule(
                self.nfc_channel_operation, [
                    self.feature.ZERO, self.feature.NFC_DIN, self.feature.NFC_DOUT], ch)
            self.nfcp_channel_submodule[ch] = self.generate_submodule(
                self.nfcp_channel_operation, [
                    self.feature.ZERO, self.feature.NFCP_DIN, self.feature.NFCP_DOUT], ch)
            self.channel_buffer_submodule[ch] = self.generate_submodule(
                self.channel_buffer, [self.feature.NAND_CH_BUFFER_TO_ECC], ch)

        self.MAPUNIT_4K_SIZE = self.param.MAPUNIT_SIZE
        self.MAPUNIT_SIZE = self.param.FTL_MAP_UNIT_SIZE
        self.MAPUNIT_PER_PAGE = self.param.PAGE_SIZE // self.MAPUNIT_SIZE
        self.MAPUNIT_PER_PLANE = self.param.PAGE_SIZE // self.MAPUNIT_SIZE
        self.MAPUNIT_PER_4K = self.param.FTL_MAP_UNIT_SIZE // 4096
        data_toggle_per_4k = 4096 / self.param.NAND_IO_Mbps
        self.PAGE_PER_4K = self.param.PAGE_SIZE // 4096
        self.tDout_without_parity = {
            NANDCMDType.Dout_4K +
            idx: int(
                data_toggle_per_4k *
                (
                    idx +
                    1)) for idx in range(
                self.PAGE_PER_4K)}
        self.tDin_without_parity = {
            NANDCMDType.Din_LSB +
            page: int(
                data_toggle_per_4k *
                4) for page in range(
                Cell.TLC.value)}
        self.cmd_to_size_map = {NANDCMDType.Dout_4K: 4 * 1024,
                                NANDCMDType.Dout_8K: 8 * 1024,
                                NANDCMDType.Dout_12K: 12 * 1024,
                                NANDCMDType.Dout_16K: 16 * 1024}
        for cmd, size in self.cmd_to_size_map.items():
            self.cmd_to_size_map[cmd] *= self.param.ECC_PARITY_RATIO

        self.nand_job_id_allocator = self.allocator_mediator.nand_job_id_allocator

        self.dma_done_pending_dict = {}
        self.dma_done_count = {}

        self.pif_factory = ProductPIFfactory(self.param)

    def channel_id_to_ecc_id(self, channel):
        return channel % (self.param.CHANNEL //
                          self.param.RATIO_CHANNEL_TO_ECC)

    def generate_read_ecc_packet(self, packet):
        ecc_packet_list = []
        slot_id_list = deque(packet.get('slot_id_list', []))
        lpn_list = deque(packet.get('lpn_list', []))
        cache_id_list = deque(packet.get('cache_id_list', []))
        host_packet_list = deque(packet.get('host_packet_list', []))

        while host_packet_list:
            ecc_packet = ecc_pif.ReadDMASQ({}, self.address)
            slot_id = slot_id_list.popleft()
            host_packet = host_packet_list.popleft()

            ecc_packet['src'] = self.address_map.NAND
            ecc_packet['channel'] = get_channel_id(packet)
            ecc_packet['slot_id'] = slot_id
            ecc_packet['host_packet'] = host_packet

            if lpn_list:
                ecc_packet['lpn'] = lpn_list.popleft()
            if cache_id_list:
                ecc_packet['cache_id'] = cache_id_list.popleft()

            if self.param.ENABLE_TR_SKIP:
                cache_result = packet['cache_hit_result']
                ecc_packet['cache_result'] = cache_result

            ecc_packet['nand_job_id'] = packet['nand_job_id']
            ecc_packet['buffered_unit_id'] = packet['buffered_unit_id']
            ecc_packet_list.append(ecc_packet)
        return ecc_packet_list

    def generate_meta_and_migration_ecc_packet(self, packet):
        buffer_ptr_list = deque(packet['buffer_ptr_list'])
        ecc_packet_list = []
        while buffer_ptr_list:
            ecc_packet = ecc_pif.ReadDMASQ({}, self.address)
            buffer_ptr = buffer_ptr_list.popleft()

            ecc_packet['src'] = self.address_map.NAND
            ecc_packet['channel'] = get_channel_id(packet)
            ecc_packet['buffer_ptr'] = buffer_ptr
            ecc_packet['nand_job_id'] = packet['nand_job_id']
            ecc_packet['buffered_unit_id'] = packet['buffered_unit_id']
            ecc_packet_list.append(ecc_packet)
        return ecc_packet_list

    def generate_ecc_packet(self, packet):
        ecc_packet_list = list()
        host_packet_list = deque(packet.get('host_packet_list', []))
        buffer_ptr_list = deque(packet.get('buffer_ptr_list', []))
        assert not (host_packet_list and buffer_ptr_list)
        if host_packet_list:
            ecc_packet_list = self.generate_read_ecc_packet(packet)
        elif buffer_ptr_list:  # meta, migration read
            ecc_packet_list = self.generate_meta_and_migration_ecc_packet(
                packet)

        return ecc_packet_list

    def operation_done(self, packet):
        yield from self.operation_done_submodule.activate_feature(self.feature.NFC_OPERATION_DONE)
        nand_cmd = packet['nand_cmd_type']

        if is_dout_cmd(nand_cmd):
            self.wakeup(
                self.operation_done,
                self.channel_buffer,
                packet,
                dst_id=get_channel_id(packet),
                description=nand_cmd.name)

        dbl_info = generate_dbl_info(packet)
        self.send_sq(
            job_scheduler_pif.NandJobReleaseDBL(
                dbl_info,
                self.address),
            self.address,
            self.address_map.JS,
            dst_domain_id=packet['channel'],
            dst_fifo_id=eMediaFifoID.DonePath.value,
            src_submodule=self.operation_done,
            description=packet['nand_cmd_type'].name)

    def get_feature_id_and_time(self, cmd_type: NANDCMDType, is_nfc):
        if is_dout_cmd(cmd_type):
            if is_nfc:
                feature_id = self.feature.NFC_DOUT
            else:
                feature_id = self.feature.NFCP_DOUT
            t_transfer = self.tDout_without_parity[cmd_type]
        else:
            assert is_din_cmd(cmd_type)
            if is_nfc:
                feature_id = self.feature.NFC_DIN
            else:
                feature_id = self.feature.NFCP_DIN
            t_transfer = self.tDin_without_parity[cmd_type]
        return feature_id, t_transfer

    def nfc_channel_operation(self, packet, ch):
        feature_id, t_transfer = self.get_feature_id_and_time(
            packet['nand_cmd_type'], is_nfc=True)
        yield from self.nfc_channel_submodule[ch].activate_feature(feature_id=feature_id, runtime_latency=t_transfer)

    def nfcp_channel_operation(self, packet, ch):
        feature_id, t_transfer = self.get_feature_id_and_time(
            packet['nand_cmd_type'], is_nfc=False)
        yield from self.nfcp_channel_submodule[ch].activate_feature(feature_id=feature_id, runtime_latency=t_transfer)

    def nand_control(self, packet):
        dbl_info = generate_dbl_info(packet)
        send_dbl_info = nand_pif.NANDDBL(dbl_info, self.address)
        nand_cmd_type = packet['nand_cmd_type']
        self.send_sq(send_dbl_info, self.address, self.address_map.NAND,
                     src_submodule=self.nand_control,
                     description=nand_cmd_type.name)

        if is_data_cmd(nand_cmd_type):
            nfc_packet = {'nand_cmd_type': nand_cmd_type}
            self.wakeup(
                self.nand_control,
                self.nfc_channel_operation,
                nfc_packet,
                dst_id=packet['channel'],
                description='NFC Channel Operation')
            self.wakeup(
                self.nand_control,
                self.nfcp_channel_operation,
                nfc_packet,
                dst_id=packet['channel'],
                description='NFCP Channel Operation')

    def allocate_buffer(self, packet):
        nand_cmd_type = packet['nand_cmd_type']

        read_unit_count = (
            nand_cmd_type.value - NANDCMDType.Dout_4K.value + 1) // self.MAPUNIT_PER_4K
        if read_unit_count == 0:
            read_unit_count = 1
        resource_type = eResourceType.ReadBuffer

        yield from self.allocate_resource(self.feature.ZERO, resource_type, read_unit_count, packet, allocate_callback_fifo_id=NFC_FIFO_ID.Resource.value)

    def allocate_done_handler(self, packet):
        for index, value in enumerate(packet['resource_list']):
            packet['host_packet_list'][index]['nvm_transaction']['buffer_ptr'] = value
        self.wakeup(self.allocate_done_handler, self.nand_control,
                    packet, description=packet['nand_cmd_type'].name)

    def need_read_buffer_allocate(self, packet):
        if self.SKIP_READ_BUFFER_ALLOC:
            return False

        try:
            nand_cmd_type = packet['nand_cmd_type']
            return packet['user'] in (
                'host', 'cm') and is_dout_cmd(nand_cmd_type)
        except KeyError:
            return False

    def channel_buffer(self, packet, channel):
        ecc_packet_list = self.generate_ecc_packet(packet)
        packet['ecc_pending_count'] = len(ecc_packet_list)
        packet['fdma_target_buffer_ptr_list'] = deque()

        for ecc_packet in ecc_packet_list:
            for _ in range(self.MAPUNIT_PER_4K):
                yield from self.channel_buffer_submodule[channel].activate_feature(self.feature.NAND_CH_BUFFER_TO_ECC)
            self.send_sq(
                ecc_pif.ReadDMASQ(
                    ecc_packet,
                    self.address),
                self.address,
                self.address_map.ECC,
                dst_domain_id=self.channel_id_to_ecc_id(channel),
                src_submodule=self.channel_buffer,
                src_submodule_id=channel,
                description=packet['nand_cmd_type'].name)
        self.stats.ecc_issued(len(ecc_packet_list))
        yield self.env.timeout(0)

    def dma_done(self, packet):
        packet['ecc_pending_count'] -= 1
        is_dma_done_for_nand_cmd = (packet['ecc_pending_count'] == 0)
        self.stats.dma_done(is_dma_done_for_nand_cmd)
        if is_dma_done_for_nand_cmd:
            dma_done_packet = {
                'nand_cmd_type': NANDCMDType.FDMADone,
                'nand_job_id': packet['nand_job_id'],
                'buffered_unit_id': packet['buffered_unit_id'],
                'channel': packet['channel']}
            self.send_sq(
                job_scheduler_pif.DMADone(
                    dma_done_packet,
                    self.address),
                self.address,
                self.address_map.JS,
                dst_domain_id=get_channel_id(packet),
                dst_fifo_id=eMediaFifoID.DonePath.value,
                src_submodule=self.dma_done,
                description=packet['nand_cmd_type'].name)
            self.stats.dma_done_issue()

    def fdma(self, packet, s_id):
        nand_cmd_type = packet['nand_cmd_type']
        if is_din_cmd(nand_cmd_type):
            if 'buffer_ptr_list' in packet:
                valid_buffer_ptr_list = [
                    ptr for ptr in packet['buffer_ptr_list'] if ptr != MemAccessInfo.INVALID_ADDR]
            # user : host
            elif any('buffer_ptr' in host_packet['nvm_transaction'] for host_packet in packet['host_packet_list']):
                valid_buffer_ptr_list = [
                    host_packet['nvm_transaction']['buffer_ptr'] for host_packet in packet['host_packet_list']]
            else:
                valid_buffer_ptr_list = []
            for buffer_ptr in valid_buffer_ptr_list:
                yield from self.memc.read_memory(MemAccessInfo(buffer_ptr, eResourceType.WriteBuffer,
                                                               _request_size_B=self.param.FTL_MAP_UNIT_SIZE))
            self.wakeup(
                self.fdma,
                self.nand_control,
                packet,
                src_id=s_id,
                description=nand_cmd_type.name)
        elif is_dout_cmd(nand_cmd_type):
            if packet['fdma_target_buffer_ptr_list']:
                buffer_ptr = packet['fdma_target_buffer_ptr_list'].popleft()
                yield from self.memc.write_memory(MemAccessInfo(buffer_ptr, eResourceType.ReadBuffer, _request_size_B=self.param.FTL_MAP_UNIT_SIZE))
            self.wakeup(
                self.fdma,
                self.dma_done,
                packet,
                src_id=s_id,
                description=nand_cmd_type.name)

    def request_fdma(self, queue_data, s_id=-1, caller=None):
        if caller is None:
            caller = self.address
        self.wakeup(
            caller,
            self.fdma,
            queue_data,
            src_id=s_id,
            dst_id=self.fdma_buffering_id)
        self.fdma_buffering_id += 1
        self.fdma_buffering_id %= self.FDMA_BUFFERING_UNIT_COUNT

    def handle_request(self, dbl_info, fifo_id):
        if fifo_id == NFC_FIFO_ID.Resource.value:
            assert dbl_info['src'] == self.address_map.BA
            pending_job = self.resource_allocate_callback(dbl_info)
            self.wakeup(
                self.address,
                self.allocate_done_handler,
                pending_job,
                src_id=fifo_id,
                description='Read Buffer Allocate Done')
        else:
            queue_data = self.nand_job_id_allocator.read(dbl_info['nand_job_id'])
            if dbl_info['src'] == self.address_map.NAND:
                assert fifo_id == NFC_FIFO_ID.DonePath.value
                self.wakeup(
                    self.address,
                    self.operation_done,
                    queue_data,
                    src_id=fifo_id,
                    description='NAND Operation Done')
            elif dbl_info['src'] == self.address_map.ECC:
                assert fifo_id == NFC_FIFO_ID.DonePath.value
                self.request_fdma(queue_data, fifo_id)
            elif dbl_info['src'] == self.address_map.JS:
                assert fifo_id == NFC_FIFO_ID.IssuePath.value
                nand_cmd_type = queue_data.get(
                    'status_nand_cmd_type', queue_data['nand_cmd_type'])
                if self.need_read_buffer_allocate(queue_data):
                    self.wakeup(
                        self.address,
                        self.allocate_buffer,
                        queue_data,
                        src_id=fifo_id,
                        description='Allocate Read Buffer')
                elif is_din_cmd(nand_cmd_type):
                    self.request_fdma(queue_data, fifo_id)
                else:
                    self.wakeup(
                        self.address,
                        self.nand_control,
                        queue_data,
                        src_id=fifo_id,
                        description=queue_data['nand_cmd_type'].name)
            else:
                assert 0
