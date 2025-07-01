from core.backbone.address_map import AddressMap
from core.config.core_feature import CoreFeature, FeatureInfo
from product.general.config.storage_parameters import Parameter


class OperationFrequency:
    def __init__(self):
        self.address_map = AddressMap()
        self.HCLK = 250
        self.FCLK = 300

        self.param = Parameter()

        self.frequency_map = {
            self.address_map.HOST: -1,
            self.address_map.NVMe: self.HCLK,
            self.address_map.JG: self.FCLK,
            self.address_map.JS: self.FCLK,
            self.address_map.NFC: self.FCLK,
            self.address_map.ECC: self.param.NAND_IO_Mbps // 4,
            self.address_map.NAND: self.param.NAND_IO_Mbps // 4,
            self.address_map.BA: self.FCLK,
            self.address_map.DCL: self.HCLK,
            self.address_map.AML: self.HCLK,
            self.address_map.TSU: self.HCLK,
            self.address_map.FBM: self.HCLK,
            self.address_map.SRAM: self.HCLK}

    def get_operating_frequency(self, address):
        return self.frequency_map[address]


class Feature(CoreFeature):
    def __init__(self):
        super().__init__()
        self.param = Parameter()
        self.operating_freq = OperationFrequency()

        self.DEFAULT_LATENCY = 250  # 850
        self.MULTI = self.gen_feature_id()

        self.BACK_BONE = self.gen_feature_id()
        self.CORE_SRAM = self.gen_feature_id()
        self.PCIe_PHY = self.gen_feature_id()

        self.non_implementation_module_list = {self.BACK_BONE: 'BACK_BONE',
                                               self.PCIe_PHY: 'PCIe_PHY',
                                               }
        # NVME
        self.PCIE_HOST_IF_HANDLING = self.gen_feature_id()
        self.PCIE_RDMA = self.gen_feature_id()
        self.PCIE_WDMA = self.gen_feature_id()
        self.NVME_CMD_SRAM_TRANSFER = self.gen_feature_id()
        self.NVME_RTT_CMD_TRANSFER = self.gen_feature_id()
        self.NVME_WRITE_DONE_CREATE_DESC_RELEASE = self.gen_feature_id()
        self.NVME_READ_DESC_RELEASE = self.gen_feature_id()
        self.NVME_READ_DONE_CREATE = self.gen_feature_id()
        self.NVME_H2D_DONE_HANDLING = self.gen_feature_id()
        self.NVME_RESPONSE_CMD_TRANSFER = self.gen_feature_id()
        self.NVME_CMD_FETCH_JOB_CREATE = self.gen_feature_id()
        self.NVME_WRITE_CMD_Q_HANDLING = self.gen_feature_id()
        self.NVME_WRITE_4K_IO_CREATE = self.gen_feature_id()
        self.NVME_4K_RTT_DESC_CREATE_Q_INSERT = self.gen_feature_id()
        self.NVME_WRITE_BACK_REQUEST = self.gen_feature_id()
        self.NVME_READ_CMD_Q_HANDLING = self.gen_feature_id()
        self.NVME_READ_4K_IO_CREATE = self.gen_feature_id()
        self.NVME_NVME_IREAD_REQUEST = self.gen_feature_id()

        self.t_sequential_buffering_timer = self.param.NAND_PARAM[
            self.param.NAND_PRODUCT]['SLC_tR'] * 1e3

        # JG
        self.JG_BUFFERED_UNIT_OPERATION = self.gen_feature_id()
        self.JG_NCORE_ISSUE = self.gen_feature_id()
        self.JG_NB_ALLOCATE = self.gen_feature_id()
        self.JG_OPERATION_DONE = self.gen_feature_id()
        self.JG_NAND_JOB_TRANSLATE = self.gen_feature_id()
        self.JG_NAND_JOB_TRANSFER = self.gen_feature_id()
        self.JG_CONTEXT_FROM_NCORE_READ = self.gen_feature_id()
        self.JG_TASKWRITE_SEQREAD = self.gen_feature_id()
        self.JG_TASKWRITE_READ = self.gen_feature_id()
        self.JG_TASKWRITE_WRITE = self.gen_feature_id()
        self.JG_TASK_DOORBELL = self.gen_feature_id()
        self.JG_NVM_TRANS_FLASH = self.gen_feature_id()
        self.JG_HANDLE_SEQUENTIAL_BUFFERED_UNIT = self.gen_feature_id()
        self.JG_HANDLE_RANDOM_BUFFERED_UNIT = self.gen_feature_id()
        self.JG_HANDLE_WRITE_BUFFERED_UNIT = self.gen_feature_id()

        # JS
        self.JS_HANGOVER_NAND_JOB = self.gen_feature_id()
        self.JS_SCHEDULING = self.gen_feature_id()
        self.JS_SCHEDULER_OPERATION_DONE = self.gen_feature_id()
        self.JS_EXECUTE = self.gen_feature_id()
        self.JS_EXECUTOR_OPERATION_DONE = self.gen_feature_id()
        self.JS_TRSKIP = self.gen_feature_id()

        # NFC
        self.NFC_OPERATION_DONE = self.gen_feature_id()
        self.NFC_DOUT = self.gen_feature_id()
        self.NFC_DIN = self.gen_feature_id()
        self.NFCP_DOUT = self.gen_feature_id()
        self.NFCP_DIN = self.gen_feature_id()
        self.WRITE_DIGEST = self.gen_feature_id()

        # DCL
        self.DCL_READ_HANDLING = self.gen_feature_id()
        self.DCL_READ_DONE_HANDLING = self.gen_feature_id()
        self.DCL_WRITE_HANDLING = self.gen_feature_id()
        self.DCL_DONE_HANDLING = self.gen_feature_id()

        #AML
        self.AML_DONE_HANDLING = self.gen_feature_id()
        self.AML_WRITE_HANDLING = self.gen_feature_id()
        self.AML_READ_HANDLING = self.gen_feature_id()
        self.AML_ALLOC_DONE = self.gen_feature_id()

        #TSU
        self.TSU_HANDLING = self.gen_feature_id()
        self.TSU_DONE = self.gen_feature_id()

        #FBM
        self.FBM_BLOCK_ALLOC_HANDLING = self.gen_feature_id()
        self.FBM_ERASE_DONE_HANDLING = self.gen_feature_id()

        # SDC
        self.SDC_PS_TIMER = self.gen_feature_id()
        cmd_to_pcie_latency = 378 / 3
        nsr_to_send_latency = 784 / 5
        handle_nand_job_latency = 773 / 10
        io_to_nsp_latency = 977 / 2
        fdma_latency = 225  # 880
        hdma_latency = self.param.HOST_4K_TRANSFER_LATENCY['read']
        wdma_latency = self.param.HOST_4K_TRANSFER_LATENCY['write']
        channel_buffer_to_ecc_latency = 317
        cq_update_latency = self.DEFAULT_LATENCY / 2

        self.feature_list += [
            None for _ in range(
                self.feature_id -
                self.core_feature_max_id +
                1)]

        # Non-implementation Module

        self.feature_list[self.BACK_BONE] = FeatureInfo(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.CORE_SRAM] = FeatureInfo(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.PCIe_PHY] = FeatureInfo(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        self.feature_list[self.SDC_PS_TIMER] = FeatureInfo(1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        self.feature_list[self.PCIE_HOST_IF_HANDLING] = FeatureInfo(
            cmd_to_pcie_latency, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NVME_CMD_SRAM_TRANSFER] = FeatureInfo(
            cmd_to_pcie_latency, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NVME_RTT_CMD_TRANSFER] = FeatureInfo(
            self.calculate_latency(self.address_map.NVMe, cycle=8), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NVME_WRITE_DONE_CREATE_DESC_RELEASE] = FeatureInfo(
            self.calculate_latency(self.address_map.NVMe, cycle=14), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NVME_READ_DESC_RELEASE] = FeatureInfo(
            cq_update_latency, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NVME_READ_DONE_CREATE] = FeatureInfo(
            cq_update_latency, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NVME_H2D_DONE_HANDLING] = FeatureInfo(
            self.calculate_latency(self.address_map.NVMe, cycle=10), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NVME_RESPONSE_CMD_TRANSFER] = FeatureInfo(
            self.calculate_latency(self.address_map.NVMe, cycle=30), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)


        self.feature_list[self.PCIE_RDMA] = FeatureInfo(hdma_latency,0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.PCIE_WDMA] = FeatureInfo(wdma_latency,0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        self.feature_list[self.NVME_CMD_FETCH_JOB_CREATE] = FeatureInfo(
            nsr_to_send_latency, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NVME_WRITE_CMD_Q_HANDLING] = FeatureInfo(
            self.calculate_latency(self.address_map.NVMe, cycle=8), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NVME_WRITE_4K_IO_CREATE] = FeatureInfo(
            self.calculate_latency(self.address_map.NVMe, cycle=8), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NVME_4K_RTT_DESC_CREATE_Q_INSERT] = FeatureInfo(
            self.calculate_latency(self.address_map.NVMe, cycle=8), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NVME_WRITE_BACK_REQUEST] = FeatureInfo(
            self.calculate_latency(self.address_map.NVMe, cycle=1), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NVME_READ_CMD_Q_HANDLING] = FeatureInfo(
            nsr_to_send_latency, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NVME_READ_4K_IO_CREATE] = FeatureInfo(
            nsr_to_send_latency, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NVME_NVME_IREAD_REQUEST] = FeatureInfo(
            22, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        self.feature_list[self.JG_BUFFERED_UNIT_OPERATION] = FeatureInfo(self.calculate_latency(
            self.address_map.JG, cycle=51), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.JG_NCORE_ISSUE] = FeatureInfo(self.calculate_latency(
            self.address_map.JG, cycle=61), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.JG_CONTEXT_FROM_NCORE_READ] = FeatureInfo(self.calculate_latency(
            self.address_map.JG, cycle=61), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.JG_NB_ALLOCATE] = FeatureInfo(self.calculate_latency(
            self.address_map.JG, cycle=41), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.JG_NAND_JOB_TRANSLATE] = FeatureInfo(
            handle_nand_job_latency, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.JG_NAND_JOB_TRANSFER] = FeatureInfo(
            handle_nand_job_latency, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.JG_OPERATION_DONE] = FeatureInfo(self.calculate_latency(
            self.address_map.JG, cycle=28), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.JG_NVM_TRANS_FLASH] = FeatureInfo(self.calculate_latency(
            self.address_map.JG, cycle=1), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.JG_HANDLE_SEQUENTIAL_BUFFERED_UNIT] = FeatureInfo(self.calculate_latency(
            self.address_map.JG, cycle=1), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.JG_HANDLE_RANDOM_BUFFERED_UNIT] = FeatureInfo(self.calculate_latency(
            self.address_map.JG, cycle=1), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.JG_HANDLE_WRITE_BUFFERED_UNIT] = FeatureInfo(self.calculate_latency(
            self.address_map.JG, cycle=1), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)


        self.feature_list[self.JS_HANGOVER_NAND_JOB] = FeatureInfo(
            1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.JS_SCHEDULING] = FeatureInfo(self.calculate_latency(
            self.address_map.JS, cycle=18), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.JS_SCHEDULER_OPERATION_DONE] = FeatureInfo(self.calculate_latency(
            self.address_map.JS, cycle=10), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        self.feature_list[self.JS_EXECUTE] = FeatureInfo(self.calculate_latency(
            self.address_map.JS, cycle=8), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.JS_EXECUTOR_OPERATION_DONE] = FeatureInfo(
            self.calculate_latency(self.address_map.JS, cycle=25), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.JS_TRSKIP] = FeatureInfo(
            handle_nand_job_latency, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        self.feature_list[self.BUFFER_REQUEST_4K_UNIT] = FeatureInfo(
            self.calculate_latency(self.address_map.NVMe, cycle=40), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.BUFFER_RELEASE_4K_UNIT] = FeatureInfo(
            self.calculate_latency(self.address_map.DCL, cycle=80), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        self.feature_list[self.NFCP_DOUT] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NFCP_DIN] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NFC_DOUT] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.NFC_DIN] = FeatureInfo(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.WRITE_DIGEST] = FeatureInfo(self.calculate_latency(
            self.address_map.NFC, cycle=10), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        self.feature_list[self.NFC_OPERATION_DONE] = FeatureInfo(self.calculate_latency(
            self.address_map.NFC, cycle=10), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        self.feature_list[self.DCL_READ_HANDLING] = FeatureInfo(
            50, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.DCL_READ_DONE_HANDLING] = FeatureInfo(
            30, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.DCL_WRITE_HANDLING] = FeatureInfo(
            70, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.DCL_DONE_HANDLING] = FeatureInfo(
            60, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.AML_DONE_HANDLING] = FeatureInfo(
            60, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.AML_WRITE_HANDLING] = FeatureInfo(
            50, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.AML_READ_HANDLING] = FeatureInfo(
            30, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.AML_ALLOC_DONE] = FeatureInfo(
            10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.TSU_HANDLING] = FeatureInfo(
            30, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.TSU_DONE] = FeatureInfo(
            20, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.FBM_BLOCK_ALLOC_HANDLING] = FeatureInfo(
            40, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        self.feature_list[self.FBM_ERASE_DONE_HANDLING] = FeatureInfo(
            10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
