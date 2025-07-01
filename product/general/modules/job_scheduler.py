from dataclasses import dataclass
from typing import Union

from core.framework.common import (QueueDepthChecker,
                                   eCacheResultType)
from core.framework.fifo_id import NFC_FIFO_ID
from core.framework.media_common import *
from product.general.modules.job_scheduler_class.js_queue import QFacade
from product.general.modules.job_scheduler_class.js_scheduling_context import \
    JSSchedulingContext
from core.modules.parallel_unit import ParallelUnit
from product.general.provided_interface import job_generator_pif, job_scheduler_pif, nand_flash_controller_pif


@dataclass
class Address:
    channel: int = None
    way: int = None
    plane: int = None
    sbn: int = None
    page: int = None


class JobScheduler(ParallelUnit):
    def __init__(
            self,
            product_args,
            _address=0,
            unit_fifo_num=1,
            unit_domain_num=1):
        super().__init__(product_args, _address, unit_fifo_num, unit_domain_num)
        assert self.address == self.address_map.JS

        self.queue_facade = QFacade(self.param, self.vcd_manager)
        self.scheduling_context = JSSchedulingContext(
            self.env, self.param, self.vcd_manager, self.queue_facade)

        self.scheduling_submodule = [None for _ in range(unit_domain_num)]
        for channel_id in range(unit_domain_num):
            self.generate_submodule(
                self.scheduler_operation_done,
                self.feature.JS_SCHEDULER_OPERATION_DONE,
                channel_id)
            self.generate_submodule(
                self.insert_task,
                self.feature.JS_HANGOVER_NAND_JOB,
                channel_id)

            self.scheduling_submodule[channel_id] = self.generate_submodule_without_process(
                self.scheduling, self.feature.JS_SCHEDULING, channel_id)
            self.env.process(self.scheduling(channel_id))

        self.nand_job_id_allocator = self.allocator_mediator.nand_job_id_allocator

        self.ts_qd_checker = dict()

        self.physical_cache_hit_count = 0

        for channel_id in range(unit_domain_num):
            self.generate_submodule(
                self.execute_process,
                self.feature.JS_EXECUTE,
                channel_id)
            self.generate_submodule(
                self.executor_operation_done,
                self.feature.JS_EXECUTOR_OPERATION_DONE,
                channel_id)

        self.tRRC_ns = int(
            self.param.NAND_PARAM[self.param.NAND_PRODUCT]['tRRC'] * 1e3)
        self.tRRC_submodule_list = [
            None for _ in range(
                self.param.CHANNEL *
                self.param.WAY *
                self.param.PLANE)]
        for plane_id in range(
                self.param.CHANNEL *
                self.param.WAY *
                self.param.PLANE):
            self.tRRC_submodule_list[plane_id] = self.generate_submodule(
                self.tRRC_operation, [
                    self.feature.ZERO, self.feature.NAND_TRRC_OPERATION], s_id=plane_id)

        self.physical_cache: List[List[List[Union[Address]]]] = [[[None for _ in range(
            self.param.PLANE)] for _ in range(self.param.WAY)] for _ in range(self.param.CHANNEL)]

        self.physical_cache_latch: List[List[List[List[Union[Address]]]]] = [[[[None for _ in range(
            3)] for _ in range(self.param.PLANE)] for _ in range(self.param.WAY)] for _ in range(self.param.CHANNEL)]

        self.physical_cache_hit_result = {}

        self.nand_job_id_allocator = self.allocator_mediator.nand_job_id_allocator

    def set_ts_qd_checker(self, ts_qd_checker: QueueDepthChecker):
        for i in range(self.param.CHANNEL):
            self.ts_qd_checker[i] = ts_qd_checker[i]

    def scheduler_operation_done(self, packet, channel):
        nand_cmd_type = packet['nand_cmd_type']
        assert channel == get_channel_id(packet)
        self.vcd_manager.record_job_done(channel, nand_cmd_type)

        if is_suspend_cmd(nand_cmd_type):
            if resume_task := self.scheduling_context.handle_suspend_done(
                    packet, self.nand_job_id_allocator):
                self.scheduling_context.set_suspend_start_info(packet)
                self.wakeup(
                    self.address,
                    self.insert_task,
                    resume_task,
                    src_id=channel,
                    dst_id=channel,
                    description=nand_cmd_type.name)
        else:
            if not is_dout_done_cmd(nand_cmd_type):
                self.scheduling_context.done(packet)

            if is_dout_cmd(nand_cmd_type):
                return

            dbl_info = generate_dbl_info(packet)
            self.send_sq(
                job_generator_pif.TaskReleaseDBL(
                    dbl_info,
                    self.address),
                self.address,
                self.address_map.JG,
                dst_fifo_id=eMediaFifoID.DonePath.value,
                dst_domain_id=(
                    packet['channel'] //
                    self.param.RATIO_CHANNEL_TO_JG),
                src_submodule=self.scheduler_operation_done,
                src_submodule_id=channel,
                description=nand_cmd_type.name)

    def release_ts_qd(self, packet):
        ts_id = packet['channel']
        self.ts_qd_checker[ts_id].release_qd()
        self.vcd_manager.update_jg_to_ts_send_count(ts_id, -1)

    def scheduling(self, channel_id):
        while True:
            yield self.scheduling_context.scheduling_event[channel_id]
            while self.queue_facade.ch_task_count[channel_id]:
                yield from self.scheduling_submodule[channel_id].activate_feature(self.feature.JS_SCHEDULING, channel_id)

                if queue_data := self.scheduling_context.select_task(
                        channel_id):
                    self.wakeup(
                        self.scheduling,
                        self.execute_process,
                        queue_data,
                        dst_id=channel_id,
                        src_id=channel_id,
                        description=queue_data['nand_cmd_type'].name)
                else:
                    break

    def insert_task(self, queue_data, channel):
        self.queue_facade.add(queue_data)
        self.scheduling_context.wakeup(channel)
        if self.param.GENERATE_SUBMODULE_DIAGRAM:
            self.record_packet_transfer_to_diagram(
                src_submodule=self.submodule_mapper.get(
                    channel, self.insert_task), dst_submodule=self.submodule_mapper.get(
                    channel, self.scheduling), description='Scheduling', is_send_packet=True)

    def set_scheduling_context(self, ctxt: JSSchedulingContext):
        self.scheduling_context = ctxt
        self.cache_miss_map = {Cell.SLC: eCacheResultType.miss_slc,
                               Cell.MLC: eCacheResultType.miss_mlc,
                               Cell.TLC: eCacheResultType.miss_tlc}

    def record_waf(self, queue_data):
        if not is_tprog_cmd(queue_data['nand_cmd_type']):
            return

        cell_type = queue_data['cell_type']
        if cell_type == Cell.TLC and not queue_data['is_sun_pgm']:
            return

        self.analyzer.total_nand_program_count += 1
        if queue_data['user'] == 'host':
            self.analyzer.total_host_nand_program_count += 1

    def execute_process(self, queue_data, channel):
        self.vcd_manager.record_job_execute(
            channel, queue_data['nand_cmd_type'])
        if self.param.ENABLE_NAND_SUSPEND and queue_data.get(
                'suspend_read', False):
            queue_data['tR_cmd_type'], queue_data['nand_cmd_type'] = queue_data['nand_cmd_type'], NANDCMDType.Suspend
            queue_data['suspend_read'] = False

        self.record_waf(queue_data)

        dbl_info = generate_dbl_info(queue_data)
        send_dbl_info = nand_flash_controller_pif.NandJobDBL(
            dbl_info, self.address)
        self.send_sq(send_dbl_info, self.address, self.address_map.NFC,
                     src_submodule=self.execute_process,
                     src_submodule_id=channel,
                     dst_fifo_id=NFC_FIFO_ID.IssuePath.value,
                     description=queue_data['nand_cmd_type'].name)

    def tRRC_operation(self, packet, plane):
        ch, way = packet['channel'], packet['way']
        self.scheduling_context.start_tRRC(ch, way, plane % self.param.PLANE)
        yield from self.tRRC_submodule_list[plane].activate_feature(self.feature.NAND_TRRC_OPERATION, runtime_latency=self.tRRC_ns)
        self.scheduling_context.end_tRRC(ch, way, plane % self.param.PLANE)

        self.scheduling_context.wakeup(ch)

    def start_tRRC(self, packet, channel):
        global_plane_id = packet['global_plane_id']

        for idx, plane in enumerate(packet['target_plane_id']):
            self.wakeup(
                self.executor_operation_done,
                self.tRRC_operation,
                packet,
                src_id=channel,
                dst_id=idx +
                global_plane_id,
                description='tRRC')

    def send_busy_check(self, packet, channel):
        packet['status_nand_cmd_type'] = NANDCMDType.tNSC
        self.wakeup(
            self.executor_operation_done,
            self.execute_process,
            packet,
            src_id=channel,
            dst_id=channel,
            description='Busy Check')

    def latch_dump_down(self, packet, channel):
        packet['status_nand_cmd_type'] = NANDCMDType.LatchDumpDown
        self.wakeup(
            self.executor_operation_done,
            self.execute_process,
            packet,
            src_id=channel,
            dst_id=channel,
            description='Latch Dump Down')

    def latch_dump_up(self, packet, channel):
        packet['status_nand_cmd_type'] = NANDCMDType.LatchDumpUp
        self.wakeup(
            self.executor_operation_done,
            self.execute_process,
            packet,
            src_id=channel,
            dst_id=channel,
            description='Latch Dump Up')

    def executor_operation_done(self, packet, channel):
        nand_cmd_type = packet.get(
            'status_nand_cmd_type',
            packet['nand_cmd_type'])
        is_cache_read = False
        cache_read_ctxt = packet.get('cache_read_ctxt', None)
        if cache_read_ctxt is not None:
            is_cache_read = cache_read_ctxt.is_cache_read

        operation_done_flag = True
        if is_dout_done_cmd(nand_cmd_type):
            self.wakeup(
                self.executor_operation_done,
                self.scheduler_operation_done,
                job_scheduler_pif.DMADone(
                    packet,
                    self.address),
                dst_id=channel,
                src_id=channel,
                description=nand_cmd_type.name)
            return
        elif is_din_cmd(nand_cmd_type):
            if packet['dlast'] and need_latch_dump_up(packet):
                self.latch_dump_up(packet, channel)
                operation_done_flag = False
        elif is_tr_cmd(nand_cmd_type) or is_tprog_cmd(nand_cmd_type) or is_erase_cmd(nand_cmd_type) or is_suspend_cmd(nand_cmd_type):
            self.send_busy_check(packet, channel)
            if is_tr_cmd(nand_cmd_type):
                self.start_tRRC(packet, channel)
            operation_done_flag = False
        elif is_busy_cmd(nand_cmd_type) and is_cache_read:
            self.latch_dump_down(packet, channel)
            operation_done_flag = False
        elif is_busy_cmd(nand_cmd_type) and is_suspend_cmd(packet['nand_cmd_type']):
            request_info = {
                'nand_cmd_type': packet['nand_cmd_type'],
                'channel': packet['channel'],
                'way': packet['way'],
                'plane': packet['plane']}
            self.wakeup(
                self.executor_operation_done,
                self.scheduler_operation_done,
                job_scheduler_pif.ResumeTaskRequest(
                    request_info,
                    self.address),
                dst_id=packet['channel'],
                src_id=channel,
                description='Request resume task')
            packet['nand_cmd_type'] = packet['tR_cmd_type']
            del packet['status_nand_cmd_type']
            self.wakeup(
                self.executor_operation_done,
                self.execute_process,
                packet,
                src_id=channel,
                dst_id=channel,
                description='tR after suspend')
            operation_done_flag = False

        if operation_done_flag:
            nand_cmd_type = packet['nand_cmd_type']

            self.wakeup(
                self.executor_operation_done,
                self.scheduler_operation_done,
                packet,
                dst_id=packet['channel'],
                src_id=channel,
                description=nand_cmd_type.name)

    def debug_count(self, data: dict):
        cmd_type = data['nand_cmd_type']
        assert is_tr_cmd(cmd_type)

        if cmd_type == NANDCMDType.tR_1P:
            self.physical_cache_hit_count += 4
        elif cmd_type == NANDCMDType.tR_2P:
            self.physical_cache_hit_count += 8
        elif cmd_type == NANDCMDType.tR_4P:
            self.physical_cache_hit_count += 16
        elif cmd_type == NANDCMDType.tR_1P_4K:
            self.physical_cache_hit_count += 1

    def handle_request(self, dbl_info, fifo_id):
        local_fifo_id = fifo_id % self.fifo_num
        channel_id = fifo_id // self.fifo_num
        if isinstance(dbl_info, job_scheduler_pif.DMADone):
            self.wakeup(
                self.address,
                self.executor_operation_done,
                dbl_info,
                src_id=channel_id,
                dst_id=channel_id,
                description=dbl_info['nand_cmd_type'].name)
        else:
            queue_data = self.nand_job_id_allocator.read(dbl_info['nand_job_id'])
            if dbl_info['src'] == self.address_map.JG:
                assert local_fifo_id == eMediaFifoID.IssuePath.value
                self.wakeup(
                    self.address,
                    self.insert_task,
                    queue_data,
                    src_id=fifo_id,
                    dst_id=channel_id,
                    description=queue_data['nand_cmd_type'].name)
            elif dbl_info['src'] == self.address_map.NFC:
                self.wakeup(
                    self.address,
                    self.executor_operation_done,
                    queue_data,
                    src_id=channel_id,
                    dst_id=channel_id,
                    description='OperationDone')
            else:
                assert 'Wrong src'
