import itertools
from collections import deque
from typing import Union

from core.framework.common import (BufferedUnitType, MemAccessInfo,
                                   QueueDepthChecker, StatusType, eCMDType,
                                   eResourceType)
from core.framework.media_common import *
from core.modules.parallel_unit import ParallelUnit
from product.general.provided_interface import job_generator_pif, job_scheduler_pif
from product.general.provided_interface.product_pif_factory import ProductPIFfactory
from product.general.framework.ppn_translator import PhysicalInfo
from product.general.framework.storage_vcd_variables import VCDVariables
from product.general.framework.timer import Timer


class CacheOpContext:
    def __init__(self):
        self.is_cache_read = False
        self.is_cache_program = False

    def __repr__(self):
        return f'is_cache_read:{self.is_cache_read},is_cache_program:{self.is_cache_program}'


class BufferedUnit:
    def __init__(self, param):
        self.param = param
        self.addr = None
        self.page = None
        self.nand_packet = {}
        self.buffered_nvm_trans_count = 0
        self.MAX_NVM_TRANS_COUNT_PER_BUFFERED_UNIT = param.PLANE * \
            param.FTL_MAP_UNIT_PER_PLANE

    def __len__(self):
        return self.buffered_nvm_trans_count

    def set_buffered_unit_id(self, buffered_unit_id, buffered_unit_type):
        self.nand_packet['buffered_unit_id'] = buffered_unit_id
        self.nand_packet['buffered_unit_type'] = buffered_unit_type

    def construct(self, packet, sbn, physical_info):
        assert packet['cmd_type'] == eCMDType.Read, 'not support meta read yet'
        self.addr = physical_info.addr_offset
        self.page = physical_info.page
        self.nand_packet = {}
        self.nand_packet['cmd_type'] = packet['cmd_type']
        self.nand_packet['slot_id_list'] = [-1] * \
            self.MAX_NVM_TRANS_COUNT_PER_BUFFERED_UNIT

        self.nand_packet['channel'] = physical_info.ch
        self.nand_packet['way'] = physical_info.way
        self.nand_packet['mapunit'] = physical_info.lpo
        self.nand_packet['issue_time'] = packet['issue_time']
        self.nand_packet['page'] = physical_info.page
        self.nand_packet['physical_page'] = physical_info.addr_offset
        self.nand_packet['block'] = sbn
        self.nand_packet['cell_type'] = physical_info.cell_type
        self.nand_packet['physical_info'] = physical_info

        self.nand_packet['user'] = packet['user']
        self.nand_packet['valid_page_bitmap'] = [0] * \
            self.MAX_NVM_TRANS_COUNT_PER_BUFFERED_UNIT
        self.nand_packet['valid_sector_bitmap'] = [None] * \
            self.MAX_NVM_TRANS_COUNT_PER_BUFFERED_UNIT
        self.nand_packet['host_packets'] = [-1] * \
            self.MAX_NVM_TRANS_COUNT_PER_BUFFERED_UNIT
        self.nand_packet['is_seq_buffered_unit'] = packet['seq_flag']
        if packet['seq_flag']:
            self.nand_packet['plane'] = (
                (physical_info.plane // self.param.MULTI_PLANE_READ) * (
                    self.param.MULTI_PLANE_READ %
                    self.param.PLANE))
        else:
            self.nand_packet['plane'] = physical_info.plane
        # TODO 추후 전체 수정 필요할지 고민해보자
        self.nand_packet['lpn_list'] = [-1] * \
            self.MAX_NVM_TRANS_COUNT_PER_BUFFERED_UNIT
        self.nand_packet['ppn_list'] = [-1] * \
            self.MAX_NVM_TRANS_COUNT_PER_BUFFERED_UNIT
        self.nand_packet['cache_id_list'] = [-1] * \
            self.MAX_NVM_TRANS_COUNT_PER_BUFFERED_UNIT
        self.nand_packet['tbt_info'] = [-1] * self.param.PLANE

    def add(self, data, offset):
        self.nand_packet['host_packets'][offset] = data
        self.nand_packet['valid_page_bitmap'][offset] = 1
        self.nand_packet['valid_sector_bitmap'][offset] = data['valid_sector_bitmap'][:]
        self.nand_packet['slot_id_list'][offset] = data['slot_id']
        self.nand_packet['lpn_list'][offset] = data['lpn']
        self.nand_packet['ppn_list'][offset] = data['nvm_transaction_flash'].ppn

        self.buffered_nvm_trans_count += 1

    def get(self):
        return self.nand_packet

    def clear(self):
        self.nand_packet = {}
        self.buffered_nvm_trans_count = 0


class SeqReadBufferedUnit(BufferedUnit):
    def __init__(self, param, stats, id):
        super().__init__(param)
        self.id = id
        self.stats = stats
        self.stats.register_seq_buffer(id)
        self.clear()

    def is_empty(self, offset):
        if self.nand_packet:
            return not self.nand_packet['valid_page_bitmap'][offset]
        return True

    def is_full(self):
        return self.buffered_nvm_trans_count == self.MAX_NVM_TRANS_COUNT_PER_BUFFERED_UNIT

    def get_page_addr(self):
        return self.page

    def add(self, data, offset):
        super().add(data, offset)
        self.stats.update_buffered_nvm_trans_count(
            self.buffered_nvm_trans_count, self.id)

    def clear(self):
        super().clear()
        self.addr = None
        self.stats.update_buffered_nvm_trans_count(0, self.id)

    def is_current_following_offset_empty(self, offset):
        return_val = True
        for offset_idx in range(offset,
                                self.MAX_NVM_TRANS_COUNT_PER_BUFFERED_UNIT):
            if not self.is_empty(offset_idx):
                return_val = False
                break

        return return_val

    def is_previous_offset_valid(self, offset):
        if offset == 0:
            return True
        else:
            return not (self.is_empty(offset - 1))


class SequentialReadBuffer:
    def generate_buffer(self, cls, *args):
        if self.param.MULTI_PLANE_READ == self.param.PLANE:
            return [cls(*args, i)
                    for i in range(self.param.WAY * self.param.CHANNEL)]

        return [cls(*args, i) for i in range(self.param.PLANE * \
                    self.param.WAY * self.param.CHANNEL)]

    def get_id(self, physical_info: PhysicalInfo):
        if self.param.MULTI_PLANE_READ == self.param.PLANE:
            return physical_info.ch * self.param.WAY + physical_info.way

        return physical_info.ch * self.param.WAY * self.param.PLANE + \
            physical_info.way * self.param.PLANE + physical_info.plane

    def __init__(self, env, param, stats, timer_expire_time):
        self.env = env
        self.param = param
        self.stats = stats
        self.timer_expire_time = timer_expire_time
        assert self.param.MULTI_PLANE_READ in (
            self.param.PLANE, 1), 'Not Supported Param'

        self.buffer = self.generate_buffer(
            SeqReadBufferedUnit, self.param, self.stats)
        self.timer = self.generate_buffer(
            Timer, self.env, self.timer_expire_time)

    def __len__(self):
        return len(self.buffer)

    def get_buffered_unit_ptr(self, physical_info: PhysicalInfo):
        return self.buffer[self.get_id(physical_info)]

    def get_timer(self, timer_id):
        return self.timer[timer_id]


class Stats:
    def __init__(self, vcd_manager):
        self.vcd_manager: VCDVariables = vcd_manager
        self.total_read_buffered_unit_issue_count = 0
        self.total_read_nvm_trans_issue_count = 0
        self.seq_read_issued_count = 0
        self.ran_read_issued_count = 0
        self.seq_flag_read_received_count = 0
        self.none_seq_flag_read_received_count = 0
        self.unmap_count = 0
        self.timer_flushed_seq_buffered_unit_count = 0
        self.physicality_broken_seq_buffered_unit_count = 0
        self.buffered_unit_full_seq_buffered_unit_count = 0
        self.read_done_buffered_unit_received_count = 0
        self.read_done_nvm_trans_received_count = 0
        self.read_done_issued_count = 0
        self.lookup_issued_count = 0
        self.timer_expired_count = []
        self.uncor_ppn_count = 0
        self.vcd_manager.add_vcd_dump_var('JG', 'lookup_issue_count', 'int')
        self.vcd_manager.add_vcd_dump_var(
            'JG', 'seq_buffered_unit_issue_count', 'int')
        self.vcd_manager.add_vcd_dump_var(
            'JG', 'ran_buffered_unit_issue_count', 'int')
        self.vcd_manager.add_vcd_dump_var('JG', 'unmapped_read_count', 'int')
        read_user_list = ('host')
        self.read_received_count = {user: 0 for user in read_user_list}

    def received_read(self, user):
        self.read_received_count[user] += 1

    def register_timer(self, TIMER_COUNT):
        for timer_id in range(TIMER_COUNT):
            self.vcd_manager.add_vcd_dump_var(
                'JG', f'timer_{timer_id:d}', 'int')
        self.timer_expired_count = [0 for _ in range(TIMER_COUNT)]

    def timer_flushed(self, timer_id):
        self.timer_flushed_seq_buffered_unit_count += 1
        self.timer_expired_count[timer_id] += 1
        self.vcd_manager.record_log(
            self.timer_expired_count[timer_id],
            'JG',
            f'timer_{timer_id:d}')

    def received_read_done(self, nvm_trans_count):
        self.read_done_buffered_unit_received_count += 1
        self.read_done_nvm_trans_received_count += nvm_trans_count

    def issue_read_done_to_cm(self):
        self.read_done_issued_count += 1

    def received_seq_flag_read(self):
        self.seq_flag_read_received_count += 1

    def received_none_seq_flag_read(self):
        self.none_seq_flag_read_received_count += 1

    def received_unmap(self):
        self.unmap_count += 1
        self.vcd_manager.record_log(
            self.unmap_count, 'JG', 'unmapped_read_count')

    def issued_read(self, nvm_trans_issue_count, is_seq):
        self.total_read_buffered_unit_issue_count += 1
        self.total_read_nvm_trans_issue_count += nvm_trans_issue_count
        if is_seq:
            self.seq_read_issued_count += 1
            self.vcd_manager.record_log(
                self.seq_read_issued_count,
                'JG',
                'seq_buffered_unit_issue_count')
        else:
            self.ran_read_issued_count += 1
            self.vcd_manager.record_log(
                self.ran_read_issued_count,
                'JG',
                'ran_buffered_unit_issue_count')

    def issued_lookup(self, issued_count=1):
        self.lookup_issued_count += issued_count
        self.vcd_manager.record_log(
            self.lookup_issued_count, 'JG', 'lookup_issue_count')

    def register_seq_buffer(self, _id):
        self.vcd_manager.add_vcd_dump_var(
            'JG', f'seq_buffer_nvm_trans_count_{_id:d}', 'int')

    def update_buffered_nvm_trans_count(self, count, _id):
        self.vcd_manager.record_log(
            count, 'JG', f'seq_buffer_nvm_trans_count_{_id:d}')

    def buffered_unit_full(self):
        self.buffered_unit_full_seq_buffered_unit_count += 1

    def physical_sequentiality_broken(self):
        self.physicality_broken_seq_buffered_unit_count += 1

    def increase_uncor_ppn_count(self):
        self.uncor_ppn_count += 1

    def get_uncor_ppn_count(self) -> object:
        return self.uncor_ppn_count

    def print_stats(self):
        for name, value in self.__dict__.items():
            print(f"JG: {name}: {value}")


class JobGenerator(ParallelUnit):

    def generate_dout_case(self, n):
        combinations = list(itertools.product([0, 1], repeat=n))
        filtered_combinations = [combo for combo in combinations if any(combo)]
        return filtered_combinations

    def generate_rule_output(self, input_tuple):
        result = []
        n = len(input_tuple)
        i = 0

        len_to_cmd = [
            0,
            NANDCMDType.Dout_4K,
            NANDCMDType.Dout_8K,
            NANDCMDType.Dout_12K,
            NANDCMDType.Dout_16K]
        while i < n:
            if input_tuple[i] == 1:
                start = i
                length = 0
                while i < n and input_tuple[i] == 1:
                    length += 1
                    i += 1
                result.extend([len_to_cmd[length], start])
            else:
                i += 1

        return tuple(result)

    def init_nand_config(self):
        assert self.param.PLANE in (4, 6, 8), 'Supported Plane Count : 4, 6, 8'
        self.tR_cmd_with_start_plane = dict()
        if self.param.PLANE == 4:
            self.full_plane_tr_type = NANDCMDType.tR_4P
            self.tR_cmd_with_start_plane[(1, 1, 1, 1)] = (NANDCMDType.tR_4P, 0)
            self.tR_cmd_with_start_plane[(1, 1, 0, 0)] = (NANDCMDType.tR_2P, 0)
            self.tR_cmd_with_start_plane[(0, 0, 1, 1)] = (NANDCMDType.tR_2P, 2)
        elif self.param.PLANE == 6:
            self.full_plane_tr_type = NANDCMDType.tR_6P
            self.tR_cmd_with_start_plane[(1, 1, 1, 1, 1, 1)] = (
                NANDCMDType.tR_6P, 0)
        elif self.param.PLANE == 8:
            self.full_plane_tr_type = NANDCMDType.tR_8P
            self.tR_cmd_with_start_plane[(1, 1, 1, 1, 1, 1, 1, 1)] = (
                NANDCMDType.tR_8P, 0)

        for plane_id in range(self.param.PLANE):
            self.tR_cmd_with_start_plane[tuple([1 if offset == plane_id else 0 for offset in range(
                self.param.PLANE)])] = (NANDCMDType.tR_1P, plane_id)

        if self.param.FTL_MAP_UNIT_SIZE == self.param.MAPUNIT_SIZE * 4:
            self.generate_dout_cmd = self.generate_dout_cmd_16k_nvm_trans
        elif self.param.FTL_MAP_UNIT_SIZE == self.param.MAPUNIT_SIZE:
            self.generate_dout_cmd = self.generate_dout_cmd_4k_nvm_trans
        else:
            assert 0, 'Not support yet!'

        bit_count = self.param.PAGE_SIZE // self.param.MAPUNIT_SIZE
        dout_cases = self.generate_dout_case(bit_count)
        self.dout_cmd_with_start_mapunit = dict()
        for case in dout_cases:
            result = self.generate_rule_output(case)
            self.dout_cmd_with_start_mapunit[case] = result

    def __init__(
            self,
            product_args,
            _address=0,
            unit_fifo_num=1,
            unit_domain_num=1):
        super().__init__(product_args, _address, unit_fifo_num, unit_domain_num)
        assert self.address == self.address_map.JG
        self.ENABLE_READ_FAIL = 0
        self.ENABLE_RE_READ_FAIL = 0

        # Added for buffering
        self.STREAM_COUNT = 2

        self.media_perf_record = False
        self.init_nand_config()
        for domain_id in range(unit_domain_num):
            self.generate_submodule(
                self.buffered_unit_read_process, [
                    self.feature.JG_BUFFERED_UNIT_OPERATION], domain_id)
            self.generate_submodule(
                self.nand_job_buffer_allocate, [
                    self.feature.JG_NB_ALLOCATE], domain_id)
            self.generate_submodule(
                self.nand_job_generator_process,
                self.feature.JG_NAND_JOB_TRANSLATE,
                domain_id)
            self.generate_submodule(
                self.nand_job_transfer_process,
                self.feature.JG_NAND_JOB_TRANSFER,
                domain_id)
            self.generate_submodule(
                self.operation_done,
                self.feature.JG_OPERATION_DONE,
                domain_id)

        # for buffering
        self.nvm_trans_handler_submodule = [
            None for _ in range(self.STREAM_COUNT)]
        self.write_handler_submodule = [None for _ in range(self.STREAM_COUNT)]
        for s_id in range(self.STREAM_COUNT):
            self.nvm_trans_handler_submodule[s_id] = self.generate_submodule(
                self.nvm_trans_flash_handler, [
                    self.feature.ZERO, self.feature.JG_NVM_TRANS_FLASH], s_id=s_id)
            self.write_handler_submodule[s_id] = self.generate_submodule(
                self.write_handler, [
                    self.feature.ZERO, self.feature.JG_HANDLE_WRITE_BUFFERED_UNIT], s_id=s_id)
        self.generate_submodule(
            self.sequential_read_handler, [
                self.feature.JG_HANDLE_SEQUENTIAL_BUFFERED_UNIT, self.feature.ZERO])
        self.generate_submodule(
            self.random_read_handler, [
                self.feature.JG_HANDLE_RANDOM_BUFFERED_UNIT, self.feature.ZERO])
        self.generate_submodule(self.command_issue_handler, self.feature.ZERO)

        if self.param.MEDIA_READ_JOB_LOGGING:
            self.job_count = [0] * self.param.TOTAL_PLANE_COUNT
            self.media_read_job_logging_file = open('media_job_log.log', 'w')
            self.media_read_job_logging_file.write(
                'simulation time,media job count(plane id 0~?)\n')

        self.CHIP_COUNT = self.param.WAY * self.param.PLANE
        self.MAPUNIT_PER_PLANE = self.param.PAGE_SIZE // self.param.FTL_MAP_UNIT_SIZE
        self.MAPUNIT_PER_4K = self.param.FTL_MAP_UNIT_SIZE // 4096
        self.NVM_TRANS_COUNT_PER_FULL_PLANE = self.param.PLANE * self.MAPUNIT_PER_PLANE

        self.mapunit_idx_to_page_idx = [
            i //
            self.NVM_TRANS_COUNT_PER_FULL_PLANE for i in range(
                self.NVM_TRANS_COUNT_PER_FULL_PLANE *
                Cell.TLC.value)]
        self.mapunit_idx_to_plane_idx = [
            (i // self.MAPUNIT_PER_PLANE) %
            self.param.PLANE for i in range(
                self.NVM_TRANS_COUNT_PER_FULL_PLANE * Cell.TLC.value)]

        self.plane_unique_id = [[[ch * self.CHIP_COUNT + way * self.param.PLANE + plane
                                  for plane in range(self.param.PLANE)]
                                 for way in range(self.param.WAY)]
                                for ch in range(self.param.CHANNEL)]

        self.buffered_unit_id_allocator = self.allocator_mediator.buffered_unit_id_allocator
        self.nand_job_id_allocator = self.allocator_mediator.nand_job_id_allocator

        self.pif_factory = ProductPIFfactory(self.param)

        # Added for write buffering
        self.buffered_unit_count_per_stream = self.param.WRITE_BUFFERED_UNIT_CNT // self.param.STREAM_COUNT
        self.idx_in_program_unit = [
            [
                [
                    page *
                    self.param.NVM_TRANS_COUNT_PER_FULL_PLANE +
                    plane *
                    self.param.FTL_MAP_UNIT_PER_PLANE +
                    mapunit for mapunit in range(
                        self.param.FTL_MAP_UNIT_PER_PLANE)] for plane in range(
                    self.param.PLANE)] for page in range(
                        Cell.TLC.value)]
        self.buffering_write_packet_list: List[List[List[Union[dict, None]]]] = [
            [[None for _ in range(self.param.WAY)] for _ in range(self.param.CHANNEL)] for _ in
            range(self.STREAM_COUNT)]
        self.buffered_unit_id_to_stream_id = dict()

        # Added for read buffering
        self.stats = Stats(self.vcd_manager)
        self.buffer = SequentialReadBuffer(
            self.env,
            self.param,
            self.stats,
            self.feature.t_sequential_buffering_timer)

        self.ran_read_buffered_unit = BufferedUnit(self.param)
        self.stats.register_timer(len(self.buffer))
        for timer_id in range(len(self.buffer)):
            self.env.process(self.timer_wait_process(timer_id))

        self.buffered_unit_count_for_seq_buffered_unit = self.param.BUFFERED_UNIT_SHARED_1P_SEQ_CNT * \
            self.param.MULTI_PLANE_READ
        self.buffered_unit_count_for_ran_buffered_unit = self.param.BUFFERED_UNIT_SHARED_RAN_CNT

        self.write_buffered_unit_id = 0
        self.read_buffer_list = {}

    def make_js_qd_checker(self):
        for i in range(self.param.CHANNEL):
            self.ts_qd_checker[i] = QueueDepthChecker(
                self.env, qd=self.param.JS_QUEUE_DEPTH)

    @staticmethod
    def is_read_type(cmd_type: eCMDType) -> bool:
        return cmd_type in (eCMDType.Read, eCMDType.MetaRead)

    @staticmethod
    def is_program_type(cmd_type: eCMDType) -> bool:
        return cmd_type in (eCMDType.Write, eCMDType.MetaWrite)

    @staticmethod
    def is_erase_type(cmd_type: eCMDType) -> bool:
        return cmd_type == eCMDType.Erase

    def copy_from_host_packet(self, packet, queue_data):
        queue_data.update({copy_tag: packet[copy_tag]
                          for copy_tag in ('buffered_unit_id', 'user')})
        if 'read_buffered_unit' in packet:
            read_buffered_unit_header = packet['read_buffered_unit']['buffered_unit_header']
            copy_field_list = [
                'cell_type',
                'channel',
                'way',
                'page',
                'physical_page']
            queue_data.update(
                {copy_tag: read_buffered_unit_header[copy_tag] for copy_tag in copy_field_list})
            queue_data['block'] = read_buffered_unit_header['sbn']
        elif 'write_buffered_unit' in packet:
            write_buffered_unit_header = packet['write_buffered_unit']['buffered_unit_header']
            copy_field_list = ['cell_type', 'channel', 'way', 'is_sun_pgm']
            queue_data.update(
                {copy_tag: write_buffered_unit_header[copy_tag] for copy_tag in copy_field_list})
            queue_data['block'] = write_buffered_unit_header['sbn']
        else:
            copy_field_list = [
                'cell_type',
                'channel',
                'way',
                'page',
                'wl',
                'physical_page',
                'block',
                'is_sun_pgm']
            queue_data.update(
                {copy_tag: packet[copy_tag] for copy_tag in copy_field_list if copy_tag in packet})

    def init_queue_data(
            self,
            nand_cmd_type,
            packet,
            cache_op_ctxt=None,
            nand_plane_id=-1,
            is_urgent: bool = False,
            is_meta: bool = False,
            is_reclaim: bool = False):
        queue_data = dict()
        queue_data['time_stamp'] = self.env.now
        queue_data['tfirst'] = False
        queue_data['tlast'] = False
        queue_data['dfirst'] = False
        queue_data['dlast'] = False
        self.copy_from_host_packet(packet, queue_data)

        queue_data['plane'] = nand_plane_id
        queue_data['global_plane_id'] = self.plane_unique_id[queue_data['channel']
                                                             ][queue_data['way']][nand_plane_id]
        queue_data['nand_cmd_type'] = nand_cmd_type
        queue_data['urgent'] = is_urgent
        queue_data['meta'] = is_meta
        queue_data['is_reclaim'] = is_reclaim

        if is_full_plane_tr(
                nand_cmd_type) or nand_cmd_type == NANDCMDType.tProg or nand_cmd_type == NANDCMDType.tBERS:
            queue_data['target_plane_id'] = [
                plane for plane in range(self.param.PLANE)]
        elif nand_cmd_type == NANDCMDType.tR_2P:
            queue_data['target_plane_id'] = [
                queue_data['plane'], queue_data['plane'] + 1]
        else:
            queue_data['target_plane_id'] = [queue_data['plane']]

        if is_read_cmd(nand_cmd_type):
            queue_data['cache_read_ctxt'] = cache_op_ctxt
        elif not is_erase_cmd(nand_cmd_type):
            queue_data['cache_program_ctxt'] = cache_op_ctxt

        queue_data['status'] = None

        return queue_data

    def get_valid_plane_bitmap(self, valid_mapunit_bitmap):
        window_size = self.MAPUNIT_PER_PLANE
        valid_plane_bitmap = tuple(any(valid_mapunit_bitmap[start_mapunit_offset:start_mapunit_offset + window_size])
                                   for start_mapunit_offset in range(0, len(valid_mapunit_bitmap), window_size))
        return valid_plane_bitmap

    def generate_tR_type(self, valid_mapunit_bitmap, urgent: bool) -> tuple:
        """ valid_mapunit_bitmap: indicate valid mapunit in 4-plane """
        if not urgent:
            return self.full_plane_tr_type, 0

        valid_plane_bitmap = self.get_valid_plane_bitmap(valid_mapunit_bitmap)
        if valid_plane_bitmap in self.tR_cmd_with_start_plane:
            if sum(valid_mapunit_bitmap) == 1:
                return NANDCMDType.tR_1P_4K, self.tR_cmd_with_start_plane[valid_plane_bitmap][1]
            else:
                return self.tR_cmd_with_start_plane[valid_plane_bitmap]
        else:
            return self.full_plane_tr_type, 0

    def generate_dma_type(self, valid_mapunit_bitmap):
        """ valid_mapunit_bitmap: indicate valid mapunit in a plane """
        if valid_mapunit_bitmap in self.dout_cmd_with_start_mapunit:
            return self.dout_cmd_with_start_mapunit[valid_mapunit_bitmap]
        else:
            assert 0, 'check all valid bit is 0'

    def set_cmd_attribute(self, preceding_cmd, cur_cmd):
        if is_tr_cmd(preceding_cmd['nand_cmd_type']):
            copy_field_list = ['urgent', 'cache_read_ctxt', 'meta']
        else:  # din cmd
            copy_field_list = ['cache_program_ctxt']
        cur_cmd.update(
            {copy_tag: preceding_cmd[copy_tag] for copy_tag in copy_field_list})

    def add_buffer_ptr_list_to_packet(self, packet, buffered_unit):
        buffer_ptr_list = list()
        for nvm_trans in buffered_unit['nvm_trans_list']:
            try:
                buffer_ptr_list.append(nvm_trans.buffer_ptr)
            except AttributeError:
                buffer_ptr_list.append(MemAccessInfo.INVALID_ADDR)
        packet['buffer_ptr_list'] = buffer_ptr_list

    def set_host_packet_to_dout_cmd(
            self,
            packet,
            data_cmd,
            local_mapunit_idx,
            sbitmap=None):
        nand_cmd_type = data_cmd['nand_cmd_type']
        start_mapunit_offset = data_cmd['plane'] * self.MAPUNIT_PER_PLANE + (
            local_mapunit_idx // self.MAPUNIT_PER_4K)
        end_mapunit_offset = start_mapunit_offset + \
            ((nand_cmd_type.value - NANDCMDType.Dout_4K.value) // self.MAPUNIT_PER_4K) + 1

        data_cmd['slot_id_list'] = packet['slot_id_list'][start_mapunit_offset:end_mapunit_offset]
        data_cmd['host_packet_list'] = packet['host_packets'][start_mapunit_offset:end_mapunit_offset]
        if 'lpn_list' in packet:
            data_cmd['lpn_list'] = packet['lpn_list'][start_mapunit_offset:end_mapunit_offset]
            data_cmd['cache_id_list'] = packet['cache_id_list'][start_mapunit_offset:end_mapunit_offset]

        if sbitmap is not None:
            data_cmd['valid_sector_bitmap'] = sbitmap

    def set_host_packet_to_din_cmd(self, packet, data_cmd, global_mapunit_idx):
        nand_cmd_type = data_cmd['nand_cmd_type']
        assert is_din_cmd(nand_cmd_type)
        assert global_mapunit_idx % self.MAPUNIT_PER_PLANE == 0
        end_mapunit_offset = global_mapunit_idx + self.MAPUNIT_PER_PLANE
        data_cmd['host_packet_list'] = packet['host_packets'][global_mapunit_idx:end_mapunit_offset]

        if 'faked_uncor_sbitmap' in packet:
            data_cmd['faked_uncor_sbitmap'] = packet['faked_uncor_sbitmap'][global_mapunit_idx:end_mapunit_offset]
        if 'lpn_list' in packet:
            desc_num = len(data_cmd['host_packet_list'])
            data_cmd['lpn_list'] = packet['lpn_list'][global_mapunit_idx:global_mapunit_idx + desc_num]

    def set_buffer_ptr_to_din_cmd(self, packet, data_cmd, global_mapunit_idx):
        nand_cmd_type = data_cmd['nand_cmd_type']
        assert is_din_cmd(nand_cmd_type)
        assert global_mapunit_idx % self.MAPUNIT_PER_PLANE == 0
        end_mapunit_offset = global_mapunit_idx + self.MAPUNIT_PER_PLANE
        data_cmd['buffer_ptr_list'] = packet['buffer_ptr_list'][global_mapunit_idx:end_mapunit_offset]

    def get_valid_nvm_trans_bitmap(self, packet):
        if 'read_buffered_unit' in packet:
            return packet['read_buffered_unit']['buffered_unit_header']['valid_bitmap_of_nvm_trans']
        elif 'write_buffered_unit' in packet:
            return packet['write_buffered_unit']['buffered_unit_header']['valid_bitmap_of_nvm_trans']

        return packet['valid_page_bitmap']

    def get_valid_sector_bitmap(self, packet):
        if 'read_buffered_unit' in packet:
            return packet['read_buffered_unit']['buffered_unit_header']['valid_sector_bitmap']

        return packet['valid_sector_bitmap']

    def generate_tr_cmd(self, valid_page_bitmap, packet):
        cmd_type: eCMDType = packet['cmd_type']
        meta: bool = (cmd_type == eCMDType.MetaRead)
        urgent = True

        nand_cmd_type, tr_start_offset = self.generate_tR_type(
            valid_page_bitmap, urgent)
        cache_op_ctxt = CacheOpContext()
        tR_cmd = self.init_queue_data(
            nand_cmd_type,
            packet,
            cache_op_ctxt=cache_op_ctxt,
            nand_plane_id=tr_start_offset,
            is_urgent=urgent,
            is_meta=meta)
        return tR_cmd

    def assign_dout_cmd_per_plane(
            self,
            tR_cmd,
            packet,
            plane,
            meta,
            cur_valid_sector_bitmap):
        bitmap_4k = []
        for cur_offset in range(0, self.param.MAPUNIT_PER_PLANE):
            bitmap_4k.append(int(cur_valid_sector_bitmap[cur_offset]))

        cur_valid_bitmap = tuple(bitmap_4k)
        dout_cmd_list = []
        dma_type_info = self.generate_dma_type(cur_valid_bitmap)
        for idx in range(0, len(dma_type_info), 2):
            nand_cmd_type, dout_start_offset = dma_type_info[idx], dma_type_info[idx + 1]
            dout_cmd = self.init_queue_data(
                nand_cmd_type, packet, nand_plane_id=plane, is_meta=meta)
            self.set_cmd_attribute(tR_cmd, dout_cmd)
            self.set_host_packet_to_dout_cmd(
                packet, dout_cmd, dout_start_offset, cur_valid_sector_bitmap)
            dout_cmd_list.append(dout_cmd)
        return dout_cmd_list

    def generate_dout_cmd_16k_nvm_trans(
            self,
            valid_nvm_trans_bitmap,
            valid_sector_bitmap,
            packet,
            tR_cmd):
        cmd_type: eCMDType = packet['cmd_type']
        meta: bool = (cmd_type == eCMDType.MetaRead)
        dout_cmd_list = []
        for plane, bit in enumerate(valid_nvm_trans_bitmap):
            if bit:
                dout_cmd_list.extend(
                    self.assign_dout_cmd_per_plane(
                        tR_cmd,
                        packet,
                        plane,
                        meta,
                        valid_sector_bitmap[plane]))

        dout_cmd_list[0]['dfirst'] = True
        dout_cmd_list[-1]['dlast'] = True
        return dout_cmd_list

    def generate_dout_cmd_4k_nvm_trans(
            self,
            valid_nvm_trans_bitmap,
            valid_sector_bitmap,
            packet,
            tR_cmd):
        cmd_type: eCMDType = packet['cmd_type']
        meta: bool = (cmd_type == eCMDType.MetaRead)
        dout_cmd_list = []
        for start_mapunit_offset in range(
                0,
                len(valid_nvm_trans_bitmap),
                self.param.MAPUNIT_PER_PLANE):
            cur_valid_bitmap = tuple(
                valid_nvm_trans_bitmap[start_mapunit_offset:start_mapunit_offset + self.param.MAPUNIT_PER_PLANE])
            plane = self.mapunit_idx_to_plane_idx[start_mapunit_offset]
            if any(cur_valid_bitmap):
                dout_cmd_list.extend(
                    self.assign_dout_cmd_per_plane(
                        tR_cmd, packet, plane, meta, cur_valid_bitmap))

        dout_cmd_list[0]['dfirst'] = True
        dout_cmd_list[-1]['dlast'] = True
        return dout_cmd_list

    def read_nand_job_generate(self, packet):
        valid_page_bitmap = self.get_valid_nvm_trans_bitmap(packet)
        valid_sector_bitmap = self.get_valid_sector_bitmap(packet)

        queue_data_list = deque()
        tR_cmd = self.generate_tr_cmd(valid_page_bitmap, packet)
        queue_data_list.append(tR_cmd)

        dout_cmd_list = self.generate_dout_cmd(
            valid_page_bitmap, valid_sector_bitmap, packet, tR_cmd)
        queue_data_list.extend(dout_cmd_list)

        return tR_cmd, queue_data_list

    def program_nand_job_generate(self, packet):
        return self.generate_program_packet(packet)

    def generate_slc_1p_program_packet(self, program_1p_target_plane, packet):
        cmd_type: eCMDType = packet['cmd_type']
        meta: bool = (cmd_type == eCMDType.MetaWrite)
        cache_op_ctxt = CacheOpContext()

        din_cmd = self.init_queue_data(
            NANDCMDType.Din_LSB,
            packet,
            cache_op_ctxt=cache_op_ctxt,
            nand_plane_id=program_1p_target_plane,
            is_meta=meta)
        din_cmd['dfirst'] = True
        din_cmd['dlast'] = True
        start_mapunit_offset = program_1p_target_plane * self.MAPUNIT_PER_PLANE
        self.set_buffer_ptr_to_din_cmd(packet, din_cmd, start_mapunit_offset)

        tprog_cmd = self.init_queue_data(
            NANDCMDType.tProg_1P,
            packet,
            nand_plane_id=program_1p_target_plane,
            is_meta=meta)
        self.set_cmd_attribute(din_cmd, tprog_cmd)
        return [din_cmd, tprog_cmd]

    def generate_program_packet(self, packet):
        nvm_trans_bitmap = self.get_valid_nvm_trans_bitmap(packet)
        din_cmd_list = self.generate_din_cmd(packet, nvm_trans_bitmap)
        first_din_cmd = din_cmd_list[0]
        tprog_cmd = self.generate_tprog_cmd(packet, first_din_cmd)

        data_list = din_cmd_list
        data_list.append(tprog_cmd)
        return data_list

    def generate_din_cmd(self, packet, nvm_trans_bitmap):
        cmd_type: eCMDType = packet['cmd_type']
        meta: bool = (cmd_type == eCMDType.MetaWrite)
        din_cmd_list = []

        cache_pgm_context = CacheOpContext()
        try:
            cache_pgm_context.is_cache_program = (self.param.ENABLE_NAND_CACHE_PROGRAM
                                                  and not meta)
        except KeyError:  # dummy pgm
            pass

        for mapunit_offset in range(
                0,
                len(nvm_trans_bitmap),
                self.MAPUNIT_PER_PLANE):
            page_offset = self.mapunit_idx_to_page_idx[mapunit_offset]
            plane_offset = self.mapunit_idx_to_plane_idx[mapunit_offset]
            is_reclaim = packet.get('is_reclaim', False)
            din_cmd = self.init_queue_data(
                NANDCMDType.Din_LSB +
                page_offset,
                packet,
                cache_op_ctxt=cache_pgm_context,
                nand_plane_id=plane_offset,
                is_meta=meta,
                is_reclaim=is_reclaim)
            if packet['user'] == 'host':
                self.set_host_packet_to_din_cmd(packet, din_cmd, mapunit_offset)
            else:
                self.set_buffer_ptr_to_din_cmd(packet, din_cmd, mapunit_offset)

            din_cmd_list.append(din_cmd)

        din_cmd_list[0]['dfirst'] = True
        din_cmd_list[-1]['dlast'] = True
        return din_cmd_list

    def generate_tprog_cmd(self, packet, first_din_cmd):
        tprog_cmd = self.init_queue_data(
            NANDCMDType.tProg, packet, nand_plane_id=0)
        self.set_cmd_attribute(first_din_cmd, tprog_cmd)
        return tprog_cmd

    def erase_nand_job_generate(self, packet):
        erase_packet = self.init_queue_data(
            NANDCMDType.tBERS, packet, nand_plane_id=0)
        return [erase_packet]

    def nand_job_generate(self, packet):
        cmd_type: eCMDType = packet['cmd_type']

        if self.is_read_type(cmd_type):
            tR_cmd, queue_data_list = self.read_nand_job_generate(packet)
        elif self.is_program_type(cmd_type):
            queue_data_list = self.program_nand_job_generate(packet)
        elif self.is_erase_type(cmd_type):
            queue_data_list = self.erase_nand_job_generate(packet)
        else:
            assert 0
        queue_data_list[0]['tfirst'] = True
        queue_data_list[-1]['tlast'] = True
        return queue_data_list

    def release_done_media_nand_job(self, packet):
        nand_job_id = packet['nand_job_id']
        buffered_unit_id = packet['buffered_unit_id']
        self.release_resource(eResourceType.MediaNandJobID, nand_job_id)
        buffered_unit = self.buffered_unit_id_allocator.read(buffered_unit_id)
        buffered_unit['nand_job_count'] -= 1

    def media_nand_job_done(self, buffered_unit_id):
        buffered_unit = self.buffered_unit_id_allocator.read(buffered_unit_id)
        return buffered_unit['nand_job_count'] == 0

    def operation_done(self, packet, jg_id):
        self.release_done_media_nand_job(packet)

        if packet['status'] != StatusType.CANCEL:
            nand_cmd_type = packet['nand_cmd_type']

        buffered_unit_id = packet['buffered_unit_id']
        if is_dout_cmd(nand_cmd_type):
            if str(buffered_unit_id) not in self.read_buffer_list:
                self.read_buffer_list[str(buffered_unit_id)] = [
                    [-1 for _ in range(0, self.param.MAPUNIT_PER_PLANE)] for _ in range(0, self.param.PLANE)]

            plane_idx = packet['plane']
            valid_sector_bitmap = packet['valid_sector_bitmap']
            valid_idx_list = []

            for mapunit_idx, valid in enumerate(valid_sector_bitmap):
                if valid == 1:
                    valid_idx_list.append(mapunit_idx)

            for idx, resource in enumerate(packet['resource_list']):
                mapunit_idx = valid_idx_list[idx]
                self.read_buffer_list[str(
                    buffered_unit_id)][plane_idx][mapunit_idx] = resource

        if self.media_nand_job_done(buffered_unit_id):
            buffered_unit = self.buffered_unit_id_allocator.read(buffered_unit_id)

            self.release_resource(eResourceType.MediaBufferedUnitID, buffered_unit_id)

            buffered_unit['status'] = packet['status']

            for i, host_packet in enumerate(buffered_unit['host_packets']):
                if host_packet == -1:
                    continue

                plane_idx = i // self.param.PLANE
                mapunit = i % self.param.MAPUNIT_PER_PLANE

                if host_packet['nvm_transaction'].transaction_type == 'read':
                    host_packet['nvm_transaction'].transaction_type = 'nand_read_done'
                    host_packet['nvm_transaction'].buffer_ptr = self.read_buffer_list[str(
                        buffered_unit_id)][plane_idx][mapunit]
                elif host_packet['nvm_transaction'].transaction_type == 'write':
                    host_packet['nvm_transaction'].transaction_type = 'write_done'
                elif host_packet['nvm_transaction'].transaction_type == 'erase':
                    host_packet['nvm_transaction'].transaction_type = 'erase_done'
                self.send_sq(
                    host_packet,
                    self.address,
                    self.address_map.TSU,
                    src_submodule=self.operation_done,
                    src_submodule_id=jg_id)

            if is_dout_cmd(nand_cmd_type):
                del self.read_buffer_list[str(buffered_unit_id)]

    def is_program_type_cmd(self, cmd_type: eCMDType):
        return cmd_type == eCMDType.Write

    def buffered_unit_read_process(self, packet, jg_id):
        buffered_unit_id_list = yield from self.allocate_resource(self.feature.JG_BUFFERED_UNIT_OPERATION, eResourceType.MediaBufferedUnitID, 1, [packet], s_id=jg_id)
        packet['buffered_unit_id'] = buffered_unit_id_list[0]

        packet = job_generator_pif.TransSQ(packet, self.address)

        queue_data_list = self.nand_job_generate_and_update_buffered_unit(packet)
        for queue_data in queue_data_list:
            self.wakeup(
                self.address,
                self.nand_job_buffer_allocate,
                queue_data,
                src_id=jg_id,
                dst_id=jg_id,
                description='TB Allocate')

    def nand_job_buffer_allocate(self, queue_data, jg_id):
        nand_job_id_list = yield from self.allocate_resource(self.feature.JG_NB_ALLOCATE, eResourceType.MediaNandJobID, 1,
                                                     [queue_data], s_id=jg_id)
        queue_data['nand_job_id'] = nand_job_id_list[0]
        self.wakeup(
            self.nand_job_buffer_allocate,
            self.nand_job_generator_process,
            queue_data,
            src_id=jg_id,
            dst_id=jg_id,
            description='Nand Job Generate')

    def nand_job_generator_process(self, queue_data, jg_id):
        queue_data['time_stamp'] = self.env.now
        self.wakeup(
            self.nand_job_generator_process,
            self.nand_job_transfer_process,
            queue_data,
            src_id=jg_id,
            dst_id=jg_id,
            description='Nand Job Transfer')

    def nand_job_transfer_process(self, queue_data, jg_id):
        dbl_info = generate_dbl_info(queue_data)
        self.send_sq(
            job_scheduler_pif.NandJobDBL(
                dbl_info,
                self.address),
            self.address,
            self.address_map.JS,
            dst_fifo_id=eMediaFifoID.IssuePath.value,
            dst_domain_id=queue_data['channel'],
            src_submodule_id=jg_id,
            description=queue_data['nand_cmd_type'].name,
            src_submodule=self.nand_job_transfer_process)

    def nand_job_generate_and_update_buffered_unit(self, packet):
        queue_data_list = self.nand_job_generate(packet)
        nand_job_count = len(queue_data_list)
        buffered_unit = self.buffered_unit_id_allocator.read(packet['buffered_unit_id'])
        buffered_unit['nand_job_count'] = nand_job_count

        return queue_data_list

    def nvm_trans_flash_handler(self, packet, s_id):
        if packet['nvm_transaction'].transaction_type == 'read':
            self.received_seq_read(packet, 0)  # no stream id
        elif packet['nvm_transaction'].transaction_type == 'write':
            self.received_write(packet, s_id)
        elif packet['nvm_transaction'].transaction_type == 'erase':
            assert (packet['nvm_transaction_flash'].address.page == 0)
            nand_packet = self.get_erase_nand_packet(packet)
            self.wakeup(
                self.nvm_trans_flash_handler,
                self.buffered_unit_read_process,
                nand_packet,
                src_id=0,
                dst_id=0,
                description='buffered_unit_read_process')

# For erase
    def get_erase_nand_packet(self, packet) -> dict:

        block = packet['nvm_transaction_flash'].address.block
        ch = packet['nvm_transaction_flash'].address.channel
        way = packet['nvm_transaction_flash'].address.way
        user = 'fbm'

        erase_packet = job_generator_pif.generate_super_block_erase_packet(
            block, ch, way, user, self.address)

        erase_packet['host_packets'] = [packet]

        return erase_packet

# For write
    def received_write(self, packet, device_stream_id):
        assert packet['nvm_transaction'].transaction_type == 'write'
        self.wakeup(
            src_func=self.address,
            dst_func=self.write_handler,
            packet=packet,
            src_id=device_stream_id,
            dst_id=device_stream_id)

    def write_handler(self, packet, device_stream_id):
        nand_packet = self.write_buffering(device_stream_id, packet)
        if nand_packet:
            self.wakeup(
                self.nvm_trans_flash_handler,
                self.buffered_unit_read_process,
                nand_packet,
                src_id=0,
                dst_id=0,
                description='buffered_unit_read_process')

    def write_buffering(self, device_stream_id, packet):
        ch = packet['nvm_transaction_flash'].address.channel
        way = packet['nvm_transaction_flash'].address.way
        plane = packet['nvm_transaction_flash'].address.plane
        page = packet['nvm_transaction_flash'].address.page % Cell.TLC.value
        mapunit = packet['nvm_transaction_flash'].address.lpo

        nand_packet = self.get_program_nand_packet(device_stream_id, packet)

        idx_in_program_unit = self.idx_in_program_unit[page][plane][mapunit]
        idx_in_pgm_unit_by_gaudi_map_unit = idx_in_program_unit

        try:
            nand_packet['valid_page_bitmap'][idx_in_pgm_unit_by_gaudi_map_unit] = int(
                packet is not None)
            nand_packet['valid_sector_bitmap'][idx_in_pgm_unit_by_gaudi_map_unit] = [
                1] * self.param.SECTOR_PER_GAUDI_MAP_UNIT

            if packet and packet.get(
                    'by_hcore') and packet['hcore_cmd_type'] == 'write_uncor':
                nand_packet['faked_uncor_sbitmap'][idx_in_pgm_unit_by_gaudi_map_unit] = [
                    1] * self.param.SECTOR_PER_GAUDI_MAP_UNIT
        except IndexError:
            breakpoint()

        if packet is not None:
            nand_packet['host_packets'][idx_in_pgm_unit_by_gaudi_map_unit] = packet
            nand_packet['slot_id_list'][idx_in_pgm_unit_by_gaudi_map_unit] = packet['slot_id']
            nand_packet['lpn_list'][idx_in_pgm_unit_by_gaudi_map_unit] = packet['lpn']

        if idx_in_pgm_unit_by_gaudi_map_unit == len(
                nand_packet['valid_page_bitmap']) - 1:
            self.buffering_write_packet_list[device_stream_id][ch][way] = None
            return nand_packet

        return {}

    def get_program_nand_packet(self, device_stream_id, packet) -> dict:
        ch = packet['nvm_transaction_flash'].address.channel
        way = packet['nvm_transaction_flash'].address.way  # need to be updated

        if self.buffering_write_packet_list[device_stream_id][ch][way] is None:
            buffered_unit_id = self.write_buffered_unit_id
            self.write_buffered_unit_id += 1
            self.buffered_unit_id_to_stream_id[buffered_unit_id] = device_stream_id
            self.buffering_write_packet_list[device_stream_id][ch][way] = self.generate_write_nand_packet_list(
                packet, device_stream_id, buffered_unit_id)
            self.buffering_write_packet_list[device_stream_id][ch][way][
                'deac'] = 1 if device_stream_id == self.param.WRITE_ZERO_STREAM_START_ID else 0
        return self.buffering_write_packet_list[device_stream_id][ch][way]

    def generate_program_buffered_unit(
            self,
            buffered_unit_id,
            src,
            user,
            packet,
            device_stream_id):
        nand_packet = dict()
        nand_packet['buffered_unit_id'] = buffered_unit_id
        nand_packet['src'] = src
        nand_packet['opcode'] = -1
        nand_packet['slot_id'] = -1
        nand_packet['cmd_type'] = eCMDType.Write
        nand_packet['user'] = user

        # cell_type = physical_info.cell_type
        cell_type = Cell.TLC
        ch = packet['nvm_transaction_flash'].address.channel
        way = packet['nvm_transaction_flash'].address.way
        block = packet['nvm_transaction_flash'].address.block
        page = packet['nvm_transaction_flash'].address.page
        wl = page // Cell.TLC.value
        ssl = 0
        mapunit = packet['nvm_transaction_flash'].address.lpo
        program_nvm_trans_count = cell_type.value * \
            self.param.PLANE * self.param.FTL_MAP_UNIT_PER_PLANE
        program_g_unit_count = program_nvm_trans_count
        nand_packet['valid_page_bitmap'] = [0] * program_g_unit_count
        nand_packet['valid_sector_bitmap'] = [[0 for _ in range(
            self.param.SECTOR_PER_GAUDI_MAP_UNIT)] for _ in range(program_g_unit_count)]
        nand_packet['faked_uncor_sbitmap'] = [[0 for _ in range(
            self.param.SECTOR_PER_GAUDI_MAP_UNIT)] for _ in range(program_g_unit_count)]
        nand_packet['slot_id_list'] = [-1] * program_g_unit_count
        nand_packet['host_packets'] = [{} for _ in range(program_g_unit_count)]
        nand_packet['lpn_list'] = [-1] * program_g_unit_count

        nand_packet['channel'] = ch
        nand_packet['way'] = way
        nand_packet['plane'] = 0
        nand_packet['block'] = block
        nand_packet['page'] = page
        nand_packet['wl'] = wl
        nand_packet['ssl'] = ssl
        nand_packet['mapunit'] = mapunit
        nand_packet['cell_type'] = cell_type
        nand_packet['is_sun_pgm'] = True
        nand_packet['device_stream_id'] = device_stream_id
        return nand_packet

    def generate_write_nand_packet_list(
            self, packet, device_stream_id, buffered_unit_id):
        nand_packet = self.generate_program_buffered_unit(
            buffered_unit_id, self.address, 'host', packet, device_stream_id)
        nand_packet['issue_time'] = self.env.now
        return nand_packet

# for read
    def received_seq_read(self, packet, fifo_id):
        assert (packet['user'] == 'host' in packet['user']
                ) and packet['cmd_type'] == eCMDType.Read
        self.wakeup(
            src_func=self.address,
            dst_func=self.sequential_read_handler,
            packet=packet,
            src_id=fifo_id)

    def sequential_read_handler(self, packet):
        sbn = packet['nvm_transaction_flash'].address.block
        page = packet['nvm_transaction_flash'].address.page
        cell_type = Cell.TLC
        address_offset = page % cell_type.value  # to be reviewed
        wl = page // cell_type.value  # to be reviewed
        ssl = 0
        way = packet['nvm_transaction_flash'].address.way
        ch = packet['nvm_transaction_flash'].address.channel
        plane = packet['nvm_transaction_flash'].address.plane
        lpo = packet['nvm_transaction_flash'].address.lpo

        physical_info = PhysicalInfo(
            address_offset,
            wl,
            ssl,
            page,
            way,
            ch,
            plane,
            lpo,
            cell_type)
        read_buffered_unit = self.buffer.get_buffered_unit_ptr(physical_info)
        if not read_buffered_unit:

            read_buffered_unit.construct(packet, sbn, physical_info)
            buffered_unit_id_list = [
                i for i in range(
                    self.buffered_unit_count_for_seq_buffered_unit)]
            read_buffered_unit.set_buffered_unit_id(
                buffered_unit_id_list, BufferedUnitType.SeqReadBufferedUnit)

        timer: Timer = self.buffer.get_timer(read_buffered_unit.id)
        buffered_unit_offset = self.calculate_buffered_unit_offset(
            physical_info.plane, physical_info.lpo)
        if self.is_physically_sequential(
                read_buffered_unit,
                physical_info,
                buffered_unit_offset):
            read_buffered_unit.add(packet, buffered_unit_offset)
            if read_buffered_unit.is_full():
                yield from timer.reset('Buffered_unit Full')
                self.issue_buffered_unit(
                    self.sequential_read_handler, read_buffered_unit)
                self.stats.buffered_unit_full()
            else:
                yield from timer.reset('Timer Renew')
                yield from timer.start()
        else:
            yield from timer.reset('Sequentiality Broken')
            self.issue_buffered_unit(
                self.sequential_read_handler,
                read_buffered_unit)
            self.stats.physical_sequentiality_broken()
            self.set_job_fail(self.sequential_read_handler)

    def random_read_handler(self, packet):
        sbn = packet['nvm_transaction_flash'].address.block
        page = packet['nvm_transaction_flash'].address.page
        cell_type = Cell.TLC
        address_offset = page % cell_type.value  # to be reviewed
        wl = page // cell_type.value  # to be reviewed
        ssl = 0
        way = packet['nvm_transaction_flash'].address.way
        ch = packet['nvm_transaction_flash'].address.channel
        plane = packet['nvm_transaction_flash'].address.plane
        lpo = packet['nvm_transaction_flash'].address.lpo

        physical_info = PhysicalInfo(
            address_offset,
            wl,
            ssl,
            page,
            way,
            ch,
            plane,
            lpo,
            cell_type)

        self.ran_read_buffered_unit.construct(packet, sbn, physical_info)
        buffered_unit_id_list = [i for i in range(
            self.buffered_unit_count_for_ran_buffered_unit)]
        self.ran_read_buffered_unit.set_buffered_unit_id(
            buffered_unit_id_list, BufferedUnitType.RanReadBufferedUnit)

        buffered_unit_offset = self.calculate_buffered_unit_offset(
            physical_info.plane, physical_info.lpo)
        self.ran_read_buffered_unit.add(packet, buffered_unit_offset)
        self.issue_buffered_unit(
            self.random_read_handler,
            self.ran_read_buffered_unit)

    def timer_wait_process(self, timer_id):
        timer = self.buffer.get_timer(timer_id)
        while True:
            yield timer.doorbell()
            read_buffered_unit = self.buffer.buffer[timer_id]
            if not read_buffered_unit.get():
                continue

            self.issue_buffered_unit(
                self.sequential_read_handler,
                read_buffered_unit)
            self.stats.timer_flushed(timer_id)

    def get_physical_info(self, ppn):
        # sb_cell_type = self.sbn_to_cell_type.get_cell_type(sbn)
        return self.ppn_translator[Cell.TLC].get_physical_info_from_ppn(ppn)

    def calculate_buffered_unit_offset(self, plane, lpo):
        return plane * self.param.FTL_MAP_UNIT_PER_PLANE + lpo

    def is_physically_sequential(
            self,
            read_buffered_unit,
            physical_info,
            buffered_unit_offset):
        if read_buffered_unit.buffered_nvm_trans_count == 0:
            return True
        else:
            return read_buffered_unit.get_page_addr() == physical_info.page and read_buffered_unit.is_current_following_offset_empty(
                buffered_unit_offset) and read_buffered_unit.is_previous_offset_valid(buffered_unit_offset)

    def issue_buffered_unit(self, caller, read_buffered_unit):
        nand_packet = read_buffered_unit.get()
        assert nand_packet, 'read buffered_unit is empty!!'
        read_buffered_unit.clear()
        self.wakeup(
            caller,
            self.command_issue_handler,
            nand_packet,
            description='Read Issue')

        self.stats.issued_read(
            sum(nand_packet['valid_page_bitmap']), caller == self.sequential_read_handler)

    def command_issue_handler(self, nand_packet):
        self.wakeup(
            self.command_issue_handler,
            self.buffered_unit_read_process,
            nand_packet,
            dst_id=0,
            description='buffered_unit_read_process')

    def handle_request(self, packet, fifo_id):
        local_fifo_id = fifo_id % len(eMediaFifoID)
        jg_id = fifo_id // len(eMediaFifoID)

        if packet['src'] == self.address_map.JS:
            queue_data = self.nand_job_id_allocator.read(packet['nand_job_id'])
            assert local_fifo_id == eMediaFifoID.DonePath.value
            self.wakeup(
                self.address,
                self.operation_done,
                queue_data,
                src_id=fifo_id,
                dst_id=jg_id,
                description='Operation Done')
        elif packet['src'] == self.address_map.TSU:
            device_stream_id = packet['host_stream_id']
            self.wakeup(
                self.address,
                self.nvm_trans_flash_handler,
                packet,
                src_id=device_stream_id,
                dst_id=jg_id,
                description='NVM TRANSACTION FLASH IN')
