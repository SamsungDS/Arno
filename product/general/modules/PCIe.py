import math

from core.framework.common import RoundRobinQueues, eCMDType
from core.modules.parallel_unit import ParallelUnit
from product.general.modules.nvme import ePCIeOpcode
from product.general.provided_interface import hdma_pif


class PCIe(ParallelUnit):
    def __init__(self, product_args, _address, unit_fifo_num=1):
        super().__init__(product_args, _address, unit_fifo_num)
        assert self.address == self.address_map.PCIe

        # resource
        self.init_resource()

        # for recv pcie
        self.rx_pcie_handler_submodule = self.generate_submodule(
            self.rx_pcie_handler, [self.feature.PCIE_HOST_IF_HANDLING, self.feature.ZERO])
        self.host_request_dma_size = dict()

        # for dma
        self.user_dma_payload = 512
        if self.user_dma_payload != self.param.SECTOR_SIZE:
            assert 0, 'need to check split_cnt in handling_dma_request'
        self.update_archive_size = 4096
        self.hmd_payload = 32
        self.update_archive_cnt = self.update_archive_size / self.hmd_payload
        self.small_user_cmd_overhead = 9

        self.r_dma_feature_id = self.feature.PCIE_RDMA
        self.w_dma_feature_id = self.feature.PCIE_WDMA
        # R/WDMA = 4K Transfer latency
        self.r_dma_latency_512B = self.feature.get_latency(
            self.r_dma_feature_id) / 8
        self.w_dma_latency_512B = self.feature.get_latency(
            self.w_dma_feature_id) / 8

        self.dma_queue_type = {'user': 0}
        self.dma_rr_queues = RoundRobinQueues(len(self.dma_queue_type))
        self.remain_dma_cnt = {}
        self.dma_unique_id = 0
        self.dma_submodule = self.generate_submodule(
            self.dma, [self.feature.PCIE_RDMA, self.feature.PCIE_WDMA])

        # for QoS
        self.default_write_perf_byte = self.param.HOST_INTERFACE_GEN_TARGET_PERF_MBS[
            self.param.HOST_INTERFACE_GEN]['write'] * 1000
        self.dma_delay_latency_ns = 0
        self.subscribe_sfr(self.dma_delay_detector, 'write_dma_target_perf')

        self.subscribe_sfr(self.block_io)
        self.io_blocked = False

    def block_io(self, flag):
        self.io_blocked = flag

    def init_resource(self):
        pass

    def reset_test(self):
        self.host_request_dma_size = dict()
        self.remain_dma_cnt = {}
        self.dma_unique_id = 0

    def rx_pcie_handler(self, packet):
        yield from self.rx_pcie_handler_submodule.activate_feature(self.feature.PCIE_HOST_IF_HANDLING)
        self.send_sq(
            packet,
            self.address,
            self.address_map.NVMe,
            src_submodule=self.rx_pcie_handler)

    def dma(self, packet):
        # Process One LBA Unit
        latency = packet['dma_latency']
        if packet['cmd_type'] == eCMDType.Read:
            feature_id = self.r_dma_feature_id
            cmd_type = eCMDType.Read
            packet['opcode'] = ePCIeOpcode.ReadCompletion
        else:
            latency += self.dma_delay_latency_ns
            feature_id = self.w_dma_feature_id
            cmd_type = eCMDType.Write

        yield from self.dma_submodule.activate_feature(feature_id, runtime_latency=latency)

        dma_unique_id = packet['dma_unique_id']
        self.remain_dma_cnt[dma_unique_id] -= 1
        # All the DMAs of LBAs were done for one FTL MapUnit
        if self.remain_dma_cnt[dma_unique_id] == 0:
            del self.remain_dma_cnt[dma_unique_id]

            if packet['desc_id']['sector_count'] != 0:
                self.analyzer.increase_data_transfer_done_count(
                    cmd_type, packet['desc_id']['sector_count'] * self.param.SECTOR_SIZE / 4096)

            self.vcd_manager.increase_pcie_dma(cmd_type)

            send_packet = hdma_pif.HDMADoneSQ(packet, self.address)
            self.send_sq(
                send_packet,
                self.address,
                self.address_map.HDMA,
                src_submodule=self.dma,
                description=cmd_type.name +
                ' DMA Done')

        if self.dma_rr_queues.any_remaining_jobs():
            packet = self.dma_rr_queues.pop_round_robin()
            self.wakeup(self.dma, self.dma, packet)

    def handling_dma_request(self, packet, src_fifo):
        # process one FTL MapUnit (4KB)
        # * self.param.SECTOR_SIZE // self.user_dma_payload
        split_cnt = packet['desc_id']['sector_count']

        overhead = self.small_user_cmd_overhead / \
            split_cnt if 1 == self.host_request_dma_size[packet['cmd_id']] else 0
        latency = self.r_dma_latency_512B if packet['cmd_type'] == eCMDType.Read else self.w_dma_latency_512B
        latency += overhead

        packet['dma_latency'] = latency

        split_cnt = math.ceil(split_cnt)
        packet['dma_unique_id'] = self.dma_unique_id
        self.remain_dma_cnt[self.dma_unique_id] = split_cnt
        for _ in range(split_cnt):
            self.dma_rr_queues.push(packet, 0)

        self.dma_unique_id += 1

        # Process Each LBA Units in One FTL MapUnit
        if self.dma_rr_queues.any_remaining_jobs():
            packet = self.dma_rr_queues.pop_round_robin()
            self.wakeup(self.address, self.dma, packet, src_id=src_fifo)

    def handle_request(self, packet, fifo_id):
        if packet['src'] == self.address_map.HOST:
            s_lba, lba_count = packet['start_lba'], packet['lba_count']
            e_lba = s_lba + lba_count - 1

            stPcie = dict()
            stPcie['init_time'] = packet['init_time']
            stPcie['issue_time'] = self.env.now
            stPcie['cmd_type'] = packet['cmd_type']
            stPcie['cmd_id'] = packet['cmd_id']
            stPcie['insert'] = True
            stPcie['is_first_tr'] = True
            # LBA Unit (512B) Range
            stPcie['start_lba'] = s_lba  # start_lba : 0 base
            stPcie['end_lba'] = e_lba  # start_lba : 0 base
            stPcie['lba_size'] = lba_count  # lba_count : 1 base
            # LOGICAL MAP Unit (32KB) Range
            stPcie['start_lpn'] = s_lba // self.param.SECTOR_PER_LOGICAL_MAP_UNIT
            stPcie['end_lpn'] = e_lba // self.param.SECTOR_PER_LOGICAL_MAP_UNIT
            # FTL MAP Unit (4KB) Range
            stPcie['start_g_lpn'] = s_lba // self.param.SECTOR_PER_GAUDI_MAP_UNIT
            stPcie['end_g_lpn'] = e_lba // self.param.SECTOR_PER_GAUDI_MAP_UNIT
            stPcie['latency_log_id'] = -1
            stPcie['sq_id'] = packet['sq_id']
            try:
                stPcie['host_stream_id'] = (
                    stPcie['start_g_lpn']) % (self.param.STREAM_COUNT - self.param.GC_STREAM)
            except KeyError:
                pass
            assert packet['cmd_id'] not in self.host_request_dma_size
            # HOST DMA Size = FTL Map Unit (4KB)
            # The number (32) of FTL Map Units (4KB) per One Command (128KB)
            self.host_request_dma_size[packet['cmd_id']
                                       ] = lba_count // self.param.SECTOR_PER_GAUDI_MAP_UNIT
            self.wakeup(
                self.address,
                self.rx_pcie_handler,
                stPcie,
                src_id=fifo_id)  # host cmd recv
        elif packet['src'] == self.address_map.HDMA:
            self.handling_dma_request(packet, fifo_id)
        elif packet['src'] == self.address_map.NVMe:
            cmd_id = packet['cmd_id']
            try:
                del self.host_request_dma_size[cmd_id]
            except KeyError:
                assert 0, f' {cmd_id} not in host_request_dma_size'
            self.send_sq(
                packet,
                self.address,
                self.address_map.HOST,
                description='Completion')
        else:
            assert 0, 'not support interface'

    def dma_delay_detector(self, write_target_perf_kib):
        if write_target_perf_kib == 0:
            self.dma_delay_latency_ns = 0   # max perf
        else:
            target_byte = write_target_perf_kib * 1024
            assert self.default_write_perf_byte > target_byte, 'invalid target perf'

            diff_byte = self.default_write_perf_byte - target_byte
            diff_latency_ns = (
                diff_byte / self.HOST_INTERFACE_GEN_TARGET_PERF_MBS[self.HOST_INTERFACE_GEN]['write']) * 1e9
            diff_latency_ns /= self.user_dma_payload
            self.dma_delay_latency_ns = diff_latency_ns

    def print_debug(self):
        pass
