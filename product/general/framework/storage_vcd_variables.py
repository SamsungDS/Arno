from core.backbone.address_map import AddressMap
from core.framework.common import eCMDType
from core.framework.core_vcd_variables import CoreVCDVariables


class VCDVariables(CoreVCDVariables):
    def init_vcd_variables(self):
        super().init_vcd_variables()

        vcd_cmd_list = [eCMDType.Read, eCMDType.Write, eCMDType.Flush]
        self.cmd_issue_count = {cmd_type: 0 for cmd_type in vcd_cmd_list}
        self.cmd_done_count = {cmd_type: 0 for cmd_type in vcd_cmd_list}
        self.pcie_dma_count = {eCMDType.Read: 0, eCMDType.Write: 0}

        self.address_map = AddressMap()

        self.vcd_manager.add_vcd_dump_var(
            'BA', 'write_buffer_remain_count', 'int')

        for cmd_type in self.cmd_issue_count.keys():
            self.vcd_manager.add_vcd_dump_var(
                'Host', f'CMDIssueCount_{cmd_type.name}', 'int')
            self.vcd_manager.add_vcd_dump_var(
                'Host', f'CMDDoneCount_{cmd_type.name}', 'int')
        self.vcd_manager.add_vcd_dump_var(
            'PCIE', f'PCIeDMACount_{eCMDType.Read}', 'int')
        self.vcd_manager.add_vcd_dump_var(
            'PCIE', f'PCIeDMACount_{eCMDType.Write}', 'int')

        self.vcd_manager.add_vcd_dump_var('Host', 'QD_Count', 'int')
        self.vcd_manager.add_vcd_dump_var('UTP', 'QD_Count', 'int')
        self.vcd_manager.add_vcd_dump_var('UTP', 'RD_REQ_Count', 'int')
        self.vcd_manager.add_vcd_dump_var('UTP', 'RD_CMPL_Count', 'int')
        self.vcd_manager.add_vcd_dump_var('DCL', 'RDBUF_REL_Count', 'int')
        self.vcd_manager.add_vcd_dump_var('TSU', 'write_start_count', 'int')
        self.vcd_manager.add_vcd_dump_var('TSU', 'write_done_count', 'int')
        self.vcd_manager.add_vcd_dump_var('TSU', 'read_start_count', 'int')
        self.vcd_manager.add_vcd_dump_var('TSU', 'read_done_count', 'int')
        self.vcd_manager.add_vcd_dump_var('TSU', 'Issue_ER_Count', 'int')
        self.vcd_manager.add_vcd_dump_var('TSU', 'Done_ER_count', 'int')

    def increase_cmd_issue(self, cmd_type):
        self.cmd_issue_count[cmd_type] += 1
        self.vcd_manager.record_log(
            self.cmd_issue_count[cmd_type],
            'Host',
            f'CMDIssueCount_{cmd_type.name}')

    def increase_cmd_done(self, cmd_type):
        self.cmd_done_count[cmd_type] += 1
        self.vcd_manager.record_log(
            self.cmd_done_count[cmd_type],
            'Host',
            f'CMDDoneCount_{cmd_type.name}')

    def increase_pcie_dma(self, cmd_type):
        self.pcie_dma_count[cmd_type] += 1

    def set_host_qd_count(self, cnt):
        self.vcd_manager.record_log(cnt, 'Host', 'QD_Count')

    def set_nvme_qd_count(self, cnt):
        self.vcd_manager.record_log(cnt, 'UTP', 'QD_Count')

    def set_read_request_count(self, cnt):
        self.vcd_manager.record_log(cnt, 'UTP', 'RD_REQ_Count')

    def set_read_completion_count(self, cnt):
        self.vcd_manager.record_log(cnt, 'UTP', 'RD_CMPL_Count')

    def set_read_buffer_release_done_count(self, cnt):
        self.vcd_manager.record_log(cnt, 'DCL', 'RDBUF_REL_Count')

    def set_write_issue_count(self, cnt):
        self.vcd_manager.record_log(cnt, 'TSU', 'write_start_count')

    def set_write_done_count(self, cnt):
        self.vcd_manager.record_log(cnt, 'TSU', 'write_done_count')

    def set_read_issue_count(self, cnt):
        self.vcd_manager.record_log(cnt, 'TSU', 'read_start_count')

    def set_read_done_count(self, cnt):
        self.vcd_manager.record_log(cnt, 'TSU', 'read_done_count')

    def set_erase_issue_count(self, cnt):
        self.vcd_manager.record_log(cnt, 'TSU', 'Issue_ER_Count')

    def set_erase_done_count(self, cnt):
        self.vcd_manager.record_log(cnt, 'TSU', 'Done_ER_count')
