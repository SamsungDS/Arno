from core.framework.common import MemAccessInfo, eCMDType, eResourceType
from core.modules.parallel_unit import ParallelUnit
from product.general.provided_interface import pcie_pif, nvme_pif


class HDMA(ParallelUnit):
    def __init__(self, product_args, _address, unit_fifo_num=1):
        super().__init__(product_args, _address, unit_fifo_num)
        assert self.address == self.address_map.HDMA

        # for write dma, cmd response to host
        self.generate_submodule(self.wdma_top, self.feature.ZERO)

        # for read write
        self.tx_handler_submodule = self.generate_submodule(
            self.tx_handler, [
                self.feature.ZERO, self.feature.NVME_RTT_CMD_TRANSFER, self.feature.NVME_RESPONSE_CMD_TRANSFER])

        # for memc
        self.generate_submodule(
            self.data_copy_to_memory, [
                self.feature.MIN_NS])
        self.generate_submodule(
            self.data_copy_from_memory, [
                self.feature.MIN_NS])

    def reset_test(self):
        pass

    def wdma_top(self, packet):
        send_packet = nvme_pif.HDMADoneSQ(packet, self.address)
        self.send_sq(
            send_packet,
            self.address,
            self.address_map.NVMe,
            src_submodule=self.wdma_top)

    def tx_handler(self, packet):
        if packet['cmd_type'] == eCMDType.Read:
            yield from self.tx_handler_submodule.activate_feature(self.feature.ZERO)
            self.wakeup(self.tx_handler, self.data_copy_from_memory, packet)
        else:
            assert packet['cmd_type'] == eCMDType.Write
            yield from self.tx_handler_submodule.activate_feature(self.feature.NVME_RTT_CMD_TRANSFER)
            send_packet = pcie_pif.DMASQ(packet, self.address)
            self.send_sq(
                send_packet,
                self.address,
                self.address_map.PCIe,
                src_submodule=self.tx_handler)

    def data_copy_to_memory(self, packet):
        size_b = packet['desc_id']['sector_count'] * self.param.SECTOR_SIZE
        yield from self.memc.write_memory(MemAccessInfo(packet['desc_id']['buffer_ptr'], eResourceType.WriteBuffer, _request_size_B=size_b))
        self.wakeup(self.data_copy_to_memory, self.wdma_top, packet)

    def data_copy_from_memory(self, packet):

        size_B = packet['desc_id']['sector_count'] * self.param.SECTOR_SIZE
        yield from self.memc.read_memory(MemAccessInfo(packet['nvm_transaction'].buffer_ptr, eResourceType.ReadBuffer, _request_size_B=size_B))

        send_packet = pcie_pif.DMASQ(packet, self.address)
        self.send_sq(
            send_packet,
            self.address,
            self.address_map.PCIe,
            src_submodule=self.data_copy_from_memory,
            description='Read Completion')

    def handle_request(self, packet, fifo_id):
        if packet['src'] == self.address_map.NVMe:
            self.wakeup(self.address, self.tx_handler, packet, src_id=fifo_id)
        elif packet['src'] == self.address_map.PCIe:
            if packet['cmd_type'] == eCMDType.Read:
                send_packet = nvme_pif.HDMADoneSQ(packet, self.address)
                self.send_sq(send_packet, self.address, self.address_map.NVMe)
            else:
                assert packet['cmd_type'] == eCMDType.Write
                self.wakeup(
                    self.address,
                    self.data_copy_to_memory,
                    packet,
                    src_id=fifo_id)
        else:
            assert 0, 'not support interface'
