from collections import defaultdict

from core.backbone.address_map import AddressMap
from core.framework.common import ProductArgs, eResourceType
from core.framework.media_common import *
from core.framework.vcd_manager import VCDManager


class CoreVCDVariables:
    def __new__(cls, product_args: ProductArgs = None):
        if not hasattr(cls, 'instance'):
            cls.instance = super().__new__(cls)
        if product_args:
            product_args.set_args_to_class_instance(cls.instance)
            cls.instance.init_vcd_variables()

        return cls.instance

    def init_vcd_variables(self):
        # LR
        self.vcd_manager = VCDManager(self.product_args)
        self.address_map = AddressMap()

        max_addr = self.address_map.get_max_address()
        self.vcd_send_sq_count = [0 for _ in range(max_addr + 1)]
        self.vcd_recv_sq_count = [0 for _ in range(max_addr + 1)]
        self.vcd_nand_received_count = [0 for _ in range(self.param.CHANNEL)]
        self.vcd_media_last_dma_done_count = [
            0 for _ in range(self.param.CHANNEL)]
        self.vcd_job_execute_job_count = [
            defaultdict(int) for _ in range(
                self.param.CHANNEL)]
        self.vcd_job_scheduler_done_job_count = [
            defaultdict(int) for _ in range(self.param.CHANNEL)]
        self.vcd_job_generator_send_job_count = [
            0 for _ in range(self.param.CHANNEL)]

        for address, ip in self.address_map.address_name_dict.items():
            self.vcd_manager.add_vcd_dump_var(
                'Bus', f'{ip}_SendSQCount', 'int')
            self.vcd_manager.add_vcd_dump_var(
                'Bus', f'{ip}_RecvSQCount', 'int')

        self.vcd_plane_ready_bitmap = [True] * self.param.TOTAL_PLANE_COUNT
        self.vcd_dma_done_bitmap = [False] * self.param.TOTAL_PLANE_COUNT

        for resource_type in eResourceType:
            self.vcd_manager.add_vcd_dump_var(
                'Resource',
                f'{resource_type.__class__.__name__.strip()}.{resource_type.name}',
                'int')

        for channel_id in range(self.param.CHANNEL):
            self.vcd_manager.add_vcd_dump_var(
                'NAND', f'Channel{channel_id:d}_RecvSQCount', 'int')
            self.vcd_manager.add_vcd_dump_var(
                'JS', f'Channel{channel_id:d}_tR_SendTaskCount', 'int')
            self.vcd_manager.add_vcd_dump_var(
                'JS', f'Channel{channel_id:d}_tProg_SendTaskCount', 'int')
            self.vcd_manager.add_vcd_dump_var(
                'JS', f'Channel{channel_id:d}_din_SendTaskCount', 'int')
            self.vcd_manager.add_vcd_dump_var(
                'JS', f'Channel{channel_id:d}_dout_SendTaskCount', 'int')
            self.vcd_manager.add_vcd_dump_var(
                'JS', f'Channel{channel_id:d}_tBERS_SendTaskCount', 'int')
            self.vcd_manager.add_vcd_dump_var(
                'JS', f'Channel{channel_id:d}_BusyCheck_SendTaskCount', 'int')
            self.vcd_manager.add_vcd_dump_var(
                'JS', f'Channel{channel_id:d}_LatchDumpDown_SendTaskCount', 'int')
            self.vcd_manager.add_vcd_dump_var(
                'JS', f'Channel{channel_id:d}_tR_ReceivedTaskDoneCount', 'int')
            self.vcd_manager.add_vcd_dump_var(
                'JS', f'Channel{channel_id:d}_tProg_ReceivedTaskDoneCount', 'int')
            self.vcd_manager.add_vcd_dump_var(
                'JS', f'Channel{channel_id:d}_din_ReceivedTaskDoneCount', 'int')
            self.vcd_manager.add_vcd_dump_var(
                'JS', f'Channel{channel_id:d}_dout_ReceivedTaskDoneCount', 'int')
            self.vcd_manager.add_vcd_dump_var(
                'JS', f'Channel{channel_id:d}_FDMADone_ReceivedCount', 'int')
            self.vcd_manager.add_vcd_dump_var(
                'JS', f'Channel{channel_id:d}_tBERS_ReceivedTaskDoneCount', 'int')
            self.vcd_manager.add_vcd_dump_var(
                'JG', f'Channel{channel_id:d}_JS_SendTaskCount', 'int')
            self.vcd_manager.add_vcd_dump_var(
                'Channel', f'DOut{channel_id:d}', 'b')
            self.vcd_manager.add_vcd_dump_var(
                'Channel', f'Din{channel_id:d}', 'b')
            self.vcd_manager.add_vcd_dump_var(
                'Channel', f'tLatchDumpUp{channel_id:d}', 'b')
            self.vcd_manager.add_vcd_dump_var(
                'Channel', f'tLatchDumpDown{channel_id:d}', 'b')
            self.vcd_manager.add_vcd_dump_var(
                'Channel', f'tNSC{channel_id:d}', 'b')
            self.vcd_manager.add_vcd_dump_var(
                'Channel', f'tR{channel_id:d}', 'b')
            self.vcd_manager.add_vcd_dump_var(
                'Channel', f'tConfirm{channel_id:d}', 'b')
            self.vcd_manager.add_vcd_dump_var(
                'Channel', f'tDoutCMD{channel_id:d}', 'b')
            self.vcd_manager.add_vcd_dump_var(
                'Channel', f'tDinCMD{channel_id:d}', 'b')
            self.vcd_manager.add_vcd_dump_var(
                'Channel', f'tSusCMD{channel_id:d}', 'b')
            self.vcd_manager.add_vcd_dump_var(
                'Channel_LastDMA', f'Channel{channel_id:d}', 'int')
            self.vcd_manager.add_vcd_dump_var(
                'Channel_LastDMA_SlotID', f'Channel{channel_id:d}', 'int')
            for way_id in range(self.param.WAY):
                self.vcd_manager.add_vcd_dump_var(
                    'NAND_LatchDump', f'Channel_{channel_id:d}_Way{way_id:d}', 'b')
                self.vcd_manager.add_vcd_dump_var(
                    'NandBusyCount', f'Channel_{channel_id:d}_Way{way_id:d}', 'b')
                self.vcd_manager.add_vcd_dump_var(
                    'LatchBusyData', f'Channel_{channel_id:d}_Way{way_id:d}', 'int')
                self.vcd_manager.add_vcd_dump_var(
                    'MediaScheduler', f'Channel_{channel_id:d}_Way{way_id:d}_UrgentQ', 'int')
                self.vcd_manager.add_vcd_dump_var(
                    'MediaScheduler', f'Channel_{channel_id:d}_Way{way_id:d}_MetaWriteQ', 'int')
                self.vcd_manager.add_vcd_dump_var(
                    'MediaScheduler', f'Channel_{channel_id:d}_Way{way_id:d}_NormalQ', 'int')
                self.vcd_manager.add_vcd_dump_var(
                    'MediaScheduler', f'Channel_{channel_id:d}_Way{way_id:d}_ResumeQ', 'int')
                self.vcd_manager.add_vcd_dump_var(
                    'MediaScheduler_StarvationCount',
                    f'NormalQ_Channel_{channel_id:d}_Way{way_id:d}',
                    'int')
                self.vcd_manager.add_vcd_dump_var(
                    'MediaScheduler_StarvationCount',
                    f'MetaWriteQ_Channel_{channel_id:d}_Way{way_id:d}',
                    'int')
                self.vcd_manager.add_vcd_dump_var(
                    'MediaScheduler_StarvationCount',
                    f'UrgentQ_Channel_{channel_id:d}_Way{way_id:d}',
                    'int')
                self.vcd_manager.add_vcd_dump_var(
                    'NAND_Suspend', f'Channel_{channel_id:d}_Way{way_id:d}_tSUS', 'b')
                self.vcd_manager.add_vcd_dump_var(
                    'JS', f'suspend_count_ch{channel_id:d}_way{way_id:d}', 'int')
                self.vcd_manager.add_vcd_dump_var(
                    'JS', f'tRES_ch{channel_id:d}_way{way_id:d}', 'int')
                self.vcd_manager.add_vcd_dump_var(
                    'JS', f'suspend_limit_ch{channel_id:d}_way{way_id:d}', 'b')
                for plane_id in range(self.param.PLANE):
                    self.vcd_manager.add_vcd_dump_var(
                        'NandBusyCount', f'Channel_{channel_id:d}_Way{way_id:d}_Plane{plane_id:d}', 'int')
                    self.vcd_manager.add_vcd_dump_var(
                        'NandBusyCount_Latch',
                        f'Channel_{channel_id:d}_Way{way_id:d}_Plane{plane_id:d}',
                        'b')
                    self.vcd_manager.add_vcd_dump_var(
                        'LatchBusyS', f'Channel_{channel_id:d}_Way{way_id:d}_Plane{plane_id:d}', 'b')
                    self.vcd_manager.add_vcd_dump_var(
                        'MediaScheduler', f'Channel_{channel_id:d}_Way{way_id:d}', 'int')
                    self.vcd_manager.add_vcd_dump_var(
                        'JS', f'way_state_ch{channel_id:d}_way{way_id:d}_plane{plane_id:d}', 'int')
                    self.vcd_manager.add_vcd_dump_var(
                        'NAND_Read', f'Channel_{channel_id:d}_Way{way_id:d}_Plane{plane_id:d}_tR', 'b')
                    self.vcd_manager.add_vcd_dump_var(
                        'NAND_Program',
                        f'Channel_{channel_id:d}_Way{way_id:d}_Plane{plane_id:d}_tPROG',
                        'b')
                    self.vcd_manager.add_vcd_dump_var(
                        'NAND_Program',
                        f'Channel_{channel_id:d}_Way{way_id:d}_Plane{plane_id:d}_Din',
                        'b')
                    self.vcd_manager.add_vcd_dump_var(
                        'NAND_Erase', f'Channel_{channel_id:d}_Way{way_id:d}_tBERS', 'b')
                    self.vcd_manager.add_vcd_dump_var(
                        'NAND_Read', f'Channel_{channel_id:d}_Way{way_id:d}_Plane{plane_id:d}_DOut', 'b')
                    self.vcd_manager.add_vcd_dump_var(
                        'NAND_tRRC', f'Channel_{channel_id:d}_Way{way_id:d}_Plane{plane_id:d}', 'b')

        for ecc_id in range(
                self.param.CHANNEL //
                self.param.RATIO_CHANNEL_TO_ECC):
            self.vcd_manager.add_vcd_dump_var(
                'ECC', f'ECC{ecc_id:d}_Active', 'b')

    def update_media_scheduling_queue(
            self, val, ch, way, q_attribute, plane=-1):
        if plane == -1:
            self.vcd_manager.record_log(
                val, 'MediaScheduler', f'Channel_{ch:d}_Way{way:d}_{q_attribute}')
        else:
            self.vcd_manager.record_log(
                val,
                'MediaScheduler',
                f'Channel_{ch:d}_Way{way:d}_{q_attribute}_P{plane:d}')

    def set_tRRC_bitmap(self, val, plane_id):
        channel_id, way_id, local_plane_id = self.get_id(plane_id)
        self.vcd_manager.record_log(
            val,
            'NAND_tRRC',
            f'Channel_{channel_id:d}_Way{way_id:d}_Plane{local_plane_id:d}')

    def latch_dump(self, val, chip_id):
        channel_id, way_id = self.get_chip_id(chip_id)
        self.vcd_manager.record_log(
            val,
            'NAND_LatchDump',
            f'Channel_{channel_id:d}_Way{way_id:d}')

    def get_id(self, plane_id):
        channel_id = plane_id // (self.param.PLANE * self.param.WAY)
        way_id = (plane_id // (self.param.PLANE)) % self.param.WAY
        local_plane_id = plane_id % self.param.PLANE
        return channel_id, way_id, local_plane_id

    def get_chip_id(self, way_id):
        channel_id = way_id // self.param.WAY
        way_id = way_id % self.param.WAY
        return channel_id, way_id

    def nand_operation(self, plane_id, value, cmd_type):
        channel_id, way_id, local_plane_id = self.get_id(plane_id)
        if is_tr_cmd(cmd_type):
            self.vcd_manager.record_log(
                value,
                'NAND_Read',
                f'Channel_{channel_id:d}_Way{way_id:d}_Plane{local_plane_id:d}_tR')
        elif is_tprog_cmd(cmd_type):
            self.vcd_manager.record_log(
                value,
                'NAND_Program',
                f'Channel_{channel_id:d}_Way{way_id:d}_Plane{local_plane_id:d}_tPROG')
        elif is_suspend_cmd(cmd_type):
            self.vcd_manager.record_log(
                value, 'NAND_Suspend', f'Channel_{channel_id:d}_Way{way_id:d}_tSUS')
        else:  # tBERS
            if local_plane_id == 0:
                self.vcd_manager.record_log(
                    value, 'NAND_Erase', f'Channel_{channel_id:d}_Way{way_id:d}_tBERS')

    def nand_dma(self, plane_id, value, is_dout=True):
        channel_id, way_id, local_plane_id = self.get_id(plane_id)

        if is_dout:
            self.vcd_manager.record_log(
                value, 'Channel', f'DOut{channel_id:d}')
            self.vcd_manager.record_log(
                value,
                'NAND_Read',
                f'Channel_{channel_id:d}_Way{way_id:d}_Plane{local_plane_id:d}_DOut')
        else:
            self.vcd_manager.record_log(value, 'Channel', f'Din{channel_id:d}')
            self.vcd_manager.record_log(
                value,
                'NAND_Program',
                f'Channel_{channel_id:d}_Way{way_id:d}_Plane{local_plane_id:d}_Din')

    def ecc_action(self, ecc_id, value):
        self.vcd_manager.record_log(value, 'ECC', f'ECC{ecc_id:d}_Active')

    def send_sq(self, src, dst):
        if not self.param.ENABLE_VCD:
            return

        self.vcd_send_sq_count[src] += 1
        self.vcd_recv_sq_count[dst] += 1
        self.vcd_manager.record_log(
            self.vcd_send_sq_count[src],
            'Bus',
            f'{self.address_map.get_name(src)}_SendSQCount')
        self.vcd_manager.record_log(
            self.vcd_recv_sq_count[dst],
            'Bus',
            f'{self.address_map.get_name(dst)}_RecvSQCount')

    def received_nand_packet(self, channel):
        self.vcd_nand_received_count[channel] += 1
        self.vcd_manager.record_log(
            self.vcd_nand_received_count[channel],
            'NAND',
            f'Channel{channel:d}_RecvSQCount')

    def record_media_dma_done(self, channel, slot_id):
        self.vcd_media_last_dma_done_count[channel] += 1
        self.vcd_manager.record_log(
            self.vcd_media_last_dma_done_count[channel],
            'Channel_LastDMA',
            f'Channel{channel:d}')
        self.vcd_manager.record_log(
            slot_id,
            'Channel_LastDMA_SlotID',
            f'Channel{channel:d}')

    def record_job_execute(self, channel, nand_cmd_type):
        if not self.param.ENABLE_VCD:
            return

        if is_tr_cmd(nand_cmd_type):
            self.vcd_job_execute_job_count[channel]['tr'] += 1
            self.vcd_manager.record_log(
                self.vcd_job_execute_job_count[channel]['tr'],
                'JS',
                f'Channel{channel:d}_tR_SendTaskCount')
        elif is_dout_cmd(nand_cmd_type):
            self.vcd_job_execute_job_count[channel]['dout'] += 1
            self.vcd_manager.record_log(
                self.vcd_job_execute_job_count[channel]['dout'],
                'JS',
                f'Channel{channel:d}_dout_SendTaskCount')
        elif is_tprog_cmd(nand_cmd_type):
            self.vcd_job_execute_job_count[channel]['tprog'] += 1
            self.vcd_manager.record_log(
                self.vcd_job_execute_job_count[channel]['tprog'],
                'JS',
                f'Channel{channel:d}_tProg_SendTaskCount')
        elif is_din_cmd(nand_cmd_type):
            self.vcd_job_execute_job_count[channel]['din'] += 1
            self.vcd_manager.record_log(
                self.vcd_job_execute_job_count[channel]['din'],
                'JS',
                f'Channel{channel:d}_din_SendTaskCount')
        elif is_erase_cmd(nand_cmd_type):
            self.vcd_job_execute_job_count[channel]['erase'] += 1
            self.vcd_manager.record_log(
                self.vcd_job_execute_job_count[channel]['erase'],
                'JS',
                f'Channel{channel:d}_tBERS_SendTaskCount')
        elif is_latch_dump_down(nand_cmd_type):
            self.vcd_job_execute_job_count[channel]['latchdumpdown'] += 1
            self.vcd_manager.record_log(
                self.vcd_job_execute_job_count[channel]['latchdumpdown'],
                'JS',
                f'Channel{channel:d}_LatchDumpDown_SendTaskCount')
        elif is_busy_cmd(nand_cmd_type):
            self.vcd_job_execute_job_count[channel]['abc'] += 1
            self.vcd_manager.record_log(
                self.vcd_job_execute_job_count[channel]['abc'],
                'JS',
                f'Channel{channel:d}_BusyCheck_SendTaskCount')

    def record_job_done(self, channel, nand_cmd_type):
        if not self.param.ENABLE_VCD:
            return

        if is_tr_cmd(nand_cmd_type):
            self.vcd_job_scheduler_done_job_count[channel]['tr'] += 1
            self.vcd_manager.record_log(
                self.vcd_job_scheduler_done_job_count[channel]['tr'],
                'JS',
                f'Channel{channel:d}_tR_ReceivedTaskDoneCount')
        elif is_dout_cmd(nand_cmd_type):
            self.vcd_job_scheduler_done_job_count[channel]['dout'] += 1
            self.vcd_manager.record_log(
                self.vcd_job_scheduler_done_job_count[channel]['dout'],
                'JS',
                f'Channel{channel:d}_dout_ReceivedTaskDoneCount')
        elif is_dout_done_cmd(nand_cmd_type):
            self.vcd_job_scheduler_done_job_count[channel]['doutdone'] += 1
            self.vcd_manager.record_log(
                self.vcd_job_scheduler_done_job_count[channel]['doutdone'],
                'JS',
                f'Channel{channel:d}_FDMADone_ReceivedCount')
        elif is_tprog_cmd(nand_cmd_type):
            self.vcd_job_scheduler_done_job_count[channel]['tprog'] += 1
            self.vcd_manager.record_log(
                self.vcd_job_scheduler_done_job_count[channel]['tprog'],
                'JS',
                f'Channel{channel:d}_tProg_ReceivedTaskDoneCount')
        elif is_din_cmd(nand_cmd_type):
            self.vcd_job_scheduler_done_job_count[channel]['din'] += 1
            self.vcd_manager.record_log(
                self.vcd_job_scheduler_done_job_count[channel]['din'],
                'JS',
                f'Channel{channel:d}_din_ReceivedTaskDoneCount')
        elif is_erase_cmd(nand_cmd_type):
            self.vcd_job_scheduler_done_job_count[channel]['erase'] += 1
            self.vcd_manager.record_log(
                self.vcd_job_scheduler_done_job_count[channel]['erase'],
                'JS',
                f'Channel{channel:d}_tBERS_ReceivedTaskDoneCount')

    def update_JG_to_JS_send_count(self, channel, val):
        self.vcd_job_generator_send_job_count[channel] += val
        self.vcd_manager.record_log(
            self.vcd_job_generator_send_job_count[channel],
            'JG',
            f'Channel{channel:d}_JS_SendTaskCount')

    def update_resource_allocate(self, resource_type, value):
        if not self.param.ENABLE_VCD:
            return

        if isinstance(resource_type, str):
            self.vcd_manager.record_log(value, 'Resource', resource_type)
        else:
            self.vcd_manager.record_log(
                value,
                'Resource',
                f'{resource_type.__class__.__name__.strip()}.{resource_type.name}')

    def update_latch_dump_up_state(self, channel_id, value):
        self.vcd_manager.record_log(
            value, 'Channel', f'tLatchDumpUp{channel_id:d}')

    def update_latch_dump_down_state(self, channel_id, value):
        self.vcd_manager.record_log(
            value, 'Channel', f'tLatchDumpDown{channel_id:d}')

    def update_abc_state(self, channel_id, value):
        self.vcd_manager.record_log(value, 'Channel', f'tNSC{channel_id:d}')

    def update_tR_cmd_state(self, channel_id, value):
        self.vcd_manager.record_log(value, 'Channel', f'tR{channel_id:d}')

    def update_confirm_cmd_state(self, channel_id, value):
        self.vcd_manager.record_log(
            value, 'Channel', f'tConfirm{channel_id:d}')

    def update_dout_cmd_state(self, channel_id, value):
        self.vcd_manager.record_log(
            value, 'Channel', f'tDoutCMD{channel_id:d}')

    def update_din_cmd_state(self, channel_id, value):
        self.vcd_manager.record_log(value, 'Channel', f'tDinCMD{channel_id:d}')

    def update_suspend_cmd_state(self, channel_id, value):
        self.vcd_manager.record_log(value, 'Channel', f'tSusCMD{channel_id:d}')

    def update_nand_busy_bitmap(
            self,
            ch,
            way,
            value,
            plane=-1,
            is_latch=False):
        module_name = 'NandBusyCount_Latch' if is_latch else 'NandBusyCount'
        if plane == -1:
            [
                self.vcd_manager.record_log(
                    value,
                    module_name,
                    f'Channel_{ch:d}_Way{way:d}_Plane{plane:d}') for plane in range(
                    self.param.PLANE)]
        else:
            self.vcd_manager.record_log(
                value, module_name, f'Channel_{ch:d}_Way{way:d}_Plane{plane:d}')

    def update_slatch_state(self, ch, way, plane, value):
        self.vcd_manager.record_log(
            value,
            'LatchBusyS',
            f'Channel_{ch:d}_Way{way:d}_Plane{plane:d}')

    def update_dlatch_state(self, ch, way, value):
        self.vcd_manager.record_log(
            value, 'LatchBusyData', f'Channel_{ch:d}_Way{way:d}')

    def update_normalQ_starvation_count(self, ch, way, value):
        self.vcd_manager.record_log(value,
                                    'MediaScheduler_StarvationCount',
                                    f'NormalQ_Channel_{ch:d}_Way{way:d}')

    def update_metawriteQ_starvation_count(self, ch, way, value):
        self.vcd_manager.record_log(value,
                                    'MediaScheduler_StarvationCount',
                                    f'MetaWriteQ_Channel_{ch:d}_Way{way:d}')

    def update_urgentQ_starvation_count(self, ch, way, value):
        self.vcd_manager.record_log(value,
                                    'MediaScheduler_StarvationCount',
                                    f'UrgentQ_Channel_{ch:d}_Way{way:d}')

    def update_way_state(self, state, ch: int, way: int, plane: int = None):
        if plane is None:
            [
                self.vcd_manager.record_log(
                    state,
                    'JS',
                    f'way_state_ch{ch:d}_way{way:d}_plane{plane:d}') for plane in range(
                    self.param.PLANE)]
        else:
            self.vcd_manager.record_log(
                state, 'JS', f'way_state_ch{ch:d}_way{way:d}_plane{plane:d}')

    def update_suspended_time(self, t_res: float, ch: int, way: int) -> None:
        self.vcd_manager.record_log(
            int(t_res), 'JS', f'tRES_ch{ch:d}_way{way:d}')

    def update_suspend_count(self, count: int, ch: int, way: int) -> None:
        self.vcd_manager.record_log(
            count, 'JS', f'suspend_count_ch{ch:d}_way{way:d}')

    def update_suspend_limit(self, value: int, ch: int, way: int) -> None:
        self.vcd_manager.record_log(
            value, 'JS', f'suspend_limit_ch{ch:d}_way{way:d}')

    def add_vcd_dump_var(self, *args, **kwargs):
        self.vcd_manager.add_vcd_dump_var(*args, **kwargs)

    def record_log(self, *args, **kwargs):
        self.vcd_manager.record_log(*args, **kwargs)

    def add_vcd_module_done(self, *args, **kwargs):
        self.vcd_manager.add_vcd_module_done(*args, **kwargs)
