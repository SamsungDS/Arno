from collections import deque
from typing import List

from core.framework.common import MemAccessInfo, eCMDType
from core.framework.fifo_id import NFC_FIFO_ID
from core.framework.media_common import generate_dbl_info
from core.framework.submodule import SubModule
from core.modules.parallel_unit import ParallelUnit
from product.general.provided_interface import nand_flash_controller_pif


class ECC(ParallelUnit):
    def __init__(
            self,
            product_args,
            _address=0,
            unit_fifo_num=1,
            unit_domain_num=1):
        super().__init__(product_args, _address, unit_fifo_num, unit_domain_num)
        assert self.address == self.address_map.ECC
        self.media_perf_record = False

        self.ecc_decoding_time = self.feature.get_latency(
            self.feature.ECC_DECODING)

        self.ecc_decoding_queue = list()
        self.ecc_decoding_event = list()
        self.ecc_decoding_job_count = [0] * unit_domain_num
        self.ecc_decoding_channel_ptr = [0] * unit_domain_num

        self.ecc_submodule: List[None | SubModule] = [
            None for _ in range(unit_domain_num)]
        self.ecc_ob_to_sram_submodule: List[None | SubModule] = [
            None for _ in range(unit_domain_num)]
        for ecc_id in range(unit_domain_num):
            self.ecc_ob_to_sram_submodule[ecc_id] = self.generate_submodule(
                self.ecc_ob_to_sram, [self.feature.ECC_TO_SRAM], ecc_id)
            self.ecc_submodule[ecc_id] = self.generate_submodule_without_process(
                self.ecc_decoding, self.feature.ECC_DECODING, ecc_id)
            self.ecc_decoding_event.append(self.env.event())
            self.env.process(self.ecc_decoding(ecc_id))
            self.ecc_decoding_queue.append(list())
            for interleaving_unit in range(self.param.RATIO_CHANNEL_TO_ECC):
                self.ecc_decoding_queue[ecc_id].append(deque())

        #  for debugging
        for ecc_id in range(unit_domain_num):
            for interleaving_unit in range(self.param.RATIO_CHANNEL_TO_ECC):
                self.set_expected_final_result(
                    f'ECC{ecc_id:d}_interleaving_unit{interleaving_unit:d}_decoding_queue',
                    self.ecc_decoding_queue[ecc_id][interleaving_unit],
                    0)
            self.set_expected_final_result(
                f'ECC{ecc_id:d}_decoding_job_count',
                self.ecc_decoding_job_count[ecc_id],
                0)

        self.nand_job_id_allocator = self.allocator_mediator.nand_job_id_allocator
        self.MAPUNIT_PER_4K = self.param.FTL_MAP_UNIT_SIZE // 4096

    def record_debugging_info(self, packet):
        if self.media_perf_record:
            self.analyzer.increase_data_transfer_done_count(eCMDType.Read)

    def ecc_ob_to_sram(self, packet, ecc_id):
        for _ in range(self.MAPUNIT_PER_4K):
            yield from self.ecc_ob_to_sram_submodule[ecc_id].activate_feature(self.feature.ECC_TO_SRAM)

        self.record_debugging_info(packet)
        dbl_info = generate_dbl_info(packet)

        buffer_ptr = None
        if 'buffer_ptr' in packet['host_packet']['nvm_transaction']:  # host read / prefetch read case
            buffer_ptr = packet['host_packet']['nvm_transaction']['buffer_ptr']
        elif 'buffer_ptr' in packet:  # meta read case
            buffer_ptr = packet['buffer_ptr']

        if buffer_ptr != MemAccessInfo.INVALID_ADDR:
            queue_data = self.nand_job_id_allocator.read(packet['nand_job_id'])
            queue_data['fdma_target_buffer_ptr_list'].append(buffer_ptr)

        self.send_sq(
            nand_flash_controller_pif.NandJobDBL(
                dbl_info,
                self.address),
            self.address,
            self.address_map.NFC,
            src_submodule=self.ecc_ob_to_sram,
            src_submodule_id=ecc_id,
            dst_fifo_id=NFC_FIFO_ID.DonePath.value)

    def activate_ecc(self, ecc_id):
        self.vcd_manager.ecc_action(ecc_id, 1)
        for _ in range(self.MAPUNIT_PER_4K):
            yield from self.ecc_submodule[ecc_id].activate_feature(self.feature.ECC_DECODING)
        self.vcd_manager.ecc_action(ecc_id, 0)

    def ecc_decoding(self, ecc_id):
        while True:
            yield self.ecc_decoding_event[ecc_id]
            while self.ecc_decoding_job_count[ecc_id]:
                if self.ecc_decoding_queue[ecc_id][self.ecc_decoding_channel_ptr[ecc_id]]:
                    packet = self.ecc_decoding_queue[ecc_id][self.ecc_decoding_channel_ptr[ecc_id]].popleft(
                    )
                    self.ecc_decoding_job_count[ecc_id] -= 1
                    yield from self.activate_ecc(ecc_id)
                    self.wakeup(
                        self.ecc_decoding,
                        self.ecc_ob_to_sram,
                        packet,
                        ecc_id,
                        ecc_id,
                        description='ECC to SRAM')
                else:
                    self.ecc_decoding_channel_ptr[ecc_id] += 1
                    self.ecc_decoding_channel_ptr[ecc_id] %= self.param.RATIO_CHANNEL_TO_ECC

    def handle_request(self, packet, ecc_id):
        if self.param.IN_ORDER_DATA_TRANSFER:
            interleaving_unit = 0
        else:
            interleaving_unit = packet['channel'] // (
                self.param.CHANNEL // self.param.RATIO_CHANNEL_TO_ECC)
        self.ecc_decoding_job_count[ecc_id] += 1
        self.ecc_decoding_queue[ecc_id][interleaving_unit].append(packet)
        self.ecc_decoding_event[ecc_id] = self.wakeup_submodule(
            self.ecc_decoding_event[ecc_id])
        if self.param.GENERATE_SUBMODULE_DIAGRAM:
            self.record_packet_transfer_to_diagram(
                src_name=self.get_name(
                    self.address,
                    ecc_id),
                dst_submodule=self.submodule_mapper.get(
                    ecc_id,
                    self.ecc_decoding),
                description='ECC Decoding',
                is_send_packet=packet is not None)
