import sys

from core.backbone.address_map import AddressMap
from core.backbone.bus import Bus
from core.backbone.power_manager import *
from core.framework.allocator import *
from core.framework.allocator_mediator import AllocatorMediator
from core.framework.analyzer import Analyzer
from core.framework.common import *
from core.framework.expected_final_result_analyzer import \
    ExpectedFinalResultAnalyzer
from core.framework.latency_logger import *
from core.framework.logger import Logger
from core.framework.sfr import SFR
from core.framework.submodule import SubModule
from core.framework.timer import FrameworkTimer


class SubmoduleMapper:
    def __init__(self):
        self.map = {}

    def add(self, submodule: SubModule):
        hash_val = (
            submodule.submodule_info.s_id,
            submodule.submodule_info.func.__name__)
        assert hash_val not in self.map
        self.map[hash_val] = submodule

    def get(self, s_id, func):
        if not isinstance(func, str):
            name = func.__name__
        else:
            name = func

        return self.map[(s_id, name)]


class PreAllocator:
    def __init__(self, parallel_unit):
        self.address = parallel_unit.address
        self.env = parallel_unit.env
        self.feature = parallel_unit.feature
        self.remain_resource = [list()
                                for index, value in enumerate(eResourceType)]
        self.pre_alloc_limit = [-1 for index,
                                value in enumerate(eResourceType)]
        self.resource_alloc_feature = [-1 for index,
                                       value in enumerate(eResourceType)]

        self.pre_alloc_event = self.env.event()
        self.pre_alloc_done_event = self.env.event()
        self.pre_alloc_requester_fifo = deque()
        self.parallel_unit = parallel_unit
        self.pre_alloc_call_back_fifo = 0

    def _start_alloc_request(self):
        self.pre_alloc_event.succeed()
        self.pre_alloc_event = self.env.event()

    def set_pre_allocation_info(
            self,
            resource_type,
            pre_alloc_cnt,
            feature_id,
            alloc_call_back_fifo=0):
        self.pre_alloc_limit[resource_type.value] = pre_alloc_cnt
        self.pre_alloc_call_back_fifo = alloc_call_back_fifo
        self.pre_alloc_requester_fifo.append(
            {'resource_type': resource_type, 'request_size': pre_alloc_cnt})
        self.resource_alloc_feature[resource_type.value] = feature_id
        self.requester_submodule = self.parallel_unit.generate_submodule_without_process(
            self.pre_alloc_requester, feature_id)
        self.env.process(self.pre_alloc_requester())
        self._start_alloc_request()

    def get_pre_allocation_resource(self, resource_type, request_size):
        assert (request_size <= self.pre_alloc_limit[resource_type.value])

        while len(self.remain_resource[resource_type.value]) < request_size:
            self._start_alloc_request()
            yield self.pre_alloc_done_event

        ret_list = self.remain_resource[resource_type.value][:request_size]
        del self.remain_resource[resource_type.value][:request_size]
        self.pre_alloc_requester_fifo.append(
            {'resource_type': resource_type, 'request_size': request_size})
        self._start_alloc_request()

        return ret_list

    def alloc_done(self, resource_type, alloc_list):
        self.remain_resource[resource_type].extend(alloc_list)
        self.pre_alloc_done_event.succeed()
        self.pre_alloc_done_event = self.env.event()

    def pre_alloc_requester(self):
        while True:
            yield self.pre_alloc_event
            while self.pre_alloc_requester_fifo:
                pre_alloc_job = self.pre_alloc_requester_fifo.popleft()
                yield from self.parallel_unit.allocate_resource(self.resource_alloc_feature[pre_alloc_job['resource_type'].value],
                                                                pre_alloc_job['resource_type'],
                                                                pre_alloc_job['request_size'],
                                                                allocate_callback_fifo_id=self.pre_alloc_call_back_fifo,
                                                                is_pre_allocator=True)


class ParallelUnit:
    def __init__(
            self,
            product_args: ProductArgs,
            _address,
            unit_fifo_num=1,
            unit_domain_num=1):
        product_args.set_args_to_class_instance(self)
        self.address = _address
        self.analyzer = Analyzer()
        self.framework_timer = FrameworkTimer(self.env)
        self.fifo_num = unit_fifo_num
        self.domain_num = unit_domain_num
        self.unit_latency_ns = self.feature.DEFAULT_LATENCY
        self.power_manager = PowerManager()
        self.address_map = AddressMap()
        self.sfr = SFR()
        self.pre_allocator = [
            None for index,
            value in enumerate(eResourceType)]
        self.name = self.address_map.get_name(self.address)

        self.bus = Bus()
        self.bus.connect_bus(self.address, unit_fifo_num, unit_domain_num)
        self.logger = Logger(
            self.env,
            name=self.__class__.__name__,
            log_flag=self.param.ENABLE_LOGGER)

        self.allocator_mediator = AllocatorMediator(product_args)
        self.submodule_mapper = SubmoduleMapper()
        for domain_id in range(unit_domain_num):
            for fifo_id in range(unit_fifo_num):
                unit_fifo_id = self.get_fifo_id(fifo_id, domain_id)
                submodule = SubModule(self.name,
                                      product_args,
                                      unit_fifo_id,
                                      self.handle_request,
                                      self.feature.ZERO,
                                      user_queue=self.bus.waiting_queue[self.address][domain_id][fifo_id])
                self.submodule_mapper.add(submodule)

        self.analyzer.register_module(self)
        self.hanging_job_info = ExpectedFinalResultAnalyzer()
        self.set_expected_final_result = self.hanging_job_info.set_expected_final_result

        self.memc = None

    def connect_memc(self, memc):
        self.memc = memc

    def handle_request(self, packet, fifo_id):
        pass

    def get_fifo_id(self, fifo_id, domain_id):
        return domain_id * self.fifo_num + fifo_id

    def push_sq(self, packet, src, my_fifo_id=0, my_domain_id=0):
        packet = self.bus.packet_processing(
            src, packet, my_fifo_id, my_domain_id)
        self.bus.push_sq(packet, self.address, my_fifo_id, my_domain_id)

    def start_packet_transfer(self):
        yield self.env.timeout(0)
        for fifo_id in range(self.fifo_num):
            for domain_id in range(self.domain_num):
                self.bus.start_packet_transfer(
                    self.address, fifo_id, domain_id)

    def activate_feature(
            self,
            feature_id,
            s_id=-1,
            runtime_latency=-1,
            runtime_active_power=-1,
            submodule_name=None,
            auto_deactivate=True):
        if submodule_name is None:
            submodule_name = sys._getframe(1).f_code.co_name
        submodule = self.submodule_mapper.get(s_id, submodule_name)

        yield from submodule.activate_feature(feature_id, runtime_latency, runtime_active_power, auto_deactivate)

    def deactivate_feature(self, feature_id, s_id=-1, submodule_name=None):
        if submodule_name is None:
            submodule_name = sys._getframe(1).f_code.co_name
        submodule = self.submodule_mapper.get(s_id, submodule_name)
        submodule.deactivate_feature(self.name, submodule_name, feature_id)

    def generate_submodule(
            self,
            func,
            feature_id,
            s_id=-1,
            q_count=1,
            q_fetch_type=QFetchType.FIFO):
        submodule = SubModule(
            self.name,
            self.product_args,
            s_id,
            func,
            feature_id,
            q_fetch_type,
            q_count)
        self.submodule_mapper.add(submodule)
        return submodule

    def generate_submodule_without_process(self, func, feature_id, s_id=-1):
        submodule = SubModule(
            self.name,
            self.product_args,
            s_id,
            func,
            feature_id,
            is_dummy=True)
        self.submodule_mapper.add(submodule)
        return submodule

    def push_job(self, func, packet, s_id=-1, q_id=0):
        if packet is None:
            return

        submodule = self.submodule_mapper.get(s_id, func)
        submodule.submodule_info.queue[q_id].append(packet)
        submodule.submodule_info.queue_job_count += 1

    def cancel(self, func, s_id=-1):
        submodule = self.submodule_mapper.get(s_id, func)
        submodule.submodule_info.cancel_flag = 1

    def set_job_fail(self, func, s_id=-1, cancel_process=False):
        submodule = self.submodule_mapper.get(s_id, func)
        submodule.submodule_info.job_done_success_flag = 0
        if cancel_process:
            submodule.submodule_info.cancel_flag = 1

    def getJobCount(self, func, s_id=-1):
        submodule = self.submodule_mapper.get(s_id, func)
        return submodule.submodule_info.queue_job_count

    def is_queue_locked(self, func, s_id=-1, q_id=0):
        submodule = self.submodule_mapper.get(s_id, func)
        return submodule.submodule_info.queue[q_id].is_locked

    def lock_queue_fetch(self, func, s_id=-1, q_id=0):
        submodule = self.submodule_mapper.get(s_id, func)
        submodule.submodule_info.queue[q_id].lock()

    def unlock_queue_fetch(self, func, s_id=-1, q_id=0):
        submodule = self.submodule_mapper.get(s_id, func)
        submodule.submodule_info.queue[q_id].unlock()

    def record_packet_transfer_to_diagram(self, **kwargs):
        description = kwargs['description']
        is_send_packet = kwargs['is_send_packet']
        if 'src_name' in kwargs:
            src_name = kwargs['src_name']
            submodule_latency = 0
        elif 'src_submodule' in kwargs:
            submodule = kwargs['src_submodule']
            src_name = submodule.submodule_info.name
            submodule_latency = submodule.submodule_info.latency_log

        if 'dst_name' in kwargs:
            dst_name = kwargs['dst_name']
        elif 'dst_submodule' in kwargs:
            dst_name = kwargs['dst_submodule'].submodule_info.name

        self.analyzer.register_packet_transfer_with_submodule(
            self.name, src_name, dst_name, submodule_latency, description, is_send_packet)

    def get_name(self, address, fifo_id):
        name = self.address_map.get_name(address)
        return f'{name}_{fifo_id:d}'

    def wakeup_submodule(self, event):
        event.succeed()
        event = self.env.event()
        return event

    def wakeup(
            self,
            src_func,
            dst_func,
            packet=None,
            src_id=-1,
            dst_id=-1,
            description='SQ',
            dst_q_id=0):
        dst_submodule = self.submodule_mapper.get(dst_id, dst_func)
        dst_submodule.wakeup(packet, dst_q_id, description)

        if self.param.GENERATE_SUBMODULE_DIAGRAM:
            if isinstance(src_func, int):
                if src_id == -1:
                    print(src_func, dst_func, packet, src_id, dst_id)
                assert src_id != -1, f'Wrong fifo id from module addr:{self.address}, to {dst_func.__name__}'
                src_name = self.get_name(self.address, src_id)
                self.record_packet_transfer_to_diagram(
                    src_name=src_name,
                    dst_submodule=dst_submodule,
                    description=description,
                    is_send_packet=packet is not None)
            else:
                src_submodule = self.submodule_mapper.get(src_id, src_func)
                self.record_packet_transfer_to_diagram(
                    src_submodule=src_submodule,
                    dst_submodule=dst_submodule,
                    description=description,
                    is_send_packet=packet is not None)

    ''' For simulation optimization. Can Eliminate Submodule Map Search Time'''

    def wakeup_by_inst(
            self,
            src_submodule: SubModule | int,
            dst_submodule: SubModule,
            packet=None,
            src_id=None,
            description='SQ',
            dst_q_id=0):
        dst_submodule.wakeup(packet, dst_q_id, description)

        if self.param.GENERATE_SUBMODULE_DIAGRAM:
            if isinstance(src_submodule, int):
                assert src_id is not None, f'Wrong fifo id from module addr:{self.address}, to {dst_submodule.submodule_info.name}'
                src_name = self.get_name(self.address, src_id)
                self.record_packet_transfer_to_diagram(
                    src_name=src_name,
                    dst_submodule=dst_submodule,
                    description=description,
                    is_send_packet=packet is not None)
            else:
                self.record_packet_transfer_to_diagram(
                    src_submodule=src_submodule,
                    dst_submodule=dst_submodule,
                    description=description,
                    is_send_packet=packet is not None)

    def generate_descrption(self, packet_class_name, description):
        if packet_class_name != 'dict':
            if description is not None:
                description = f'{packet_class_name}, \\n{description}'
            else:
                description = f'{packet_class_name}'
        elif description is None:
            description = 'Send SQ'
        return description

    def send_sq(
            self,
            packet,
            src,
            dst,
            dst_fifo_id=0,
            src_submodule=None,
            src_submodule_id=-1,
            dst_domain_id=0,
            description=None):
        if any(
            (self.param.GENERATE_SUBMODULE_DIAGRAM,
             self.param.GENERATE_DIAGRAM)):
            description = self.generate_descrption(
                packet.__class__.__name__, description)

        if self.param.GENERATE_DIAGRAM:
            src_fifo_id = packet.get('bus_dst_fifo_id', 0)
            src_domain_id = packet.get('bus_dst_domain_id', 0)
            self.analyzer.register_packet_transfer(
                self.address,
                dst,
                src_fifo_id,
                src_domain_id,
                dst_fifo_id,
                dst_domain_id,
                description)

        if src_submodule and self.param.GENERATE_SUBMODULE_DIAGRAM:
            src_func = src_submodule
            src_id = src_submodule_id
            src_submodule = self.submodule_mapper.get(src_id, src_func)
            dst_name = self.get_name(dst, dst_fifo_id)
            self.record_packet_transfer_to_diagram(
                src_submodule=src_submodule,
                dst_name=dst_name,
                description=description,
                is_send_packet=True)

        self.bus.send_sq(packet, self.address, dst, dst_fifo_id, dst_domain_id)

    def subscribe_sfr(self, func, name=''):
        if not name:
            name = func.__name__
        self.sfr.register_func(name, func)

    def read_sfr(self, src_func, name, s_id=-1):
        if self.param.GENERATE_SUBMODULE_DIAGRAM:
            self.record_packet_transfer_to_diagram(
                src_name=src_func.__name__,
                dst_name='SFR',
                description='Read SFR',
                is_send_packet=True)
        return self.sfr.read_sfr(name)

    def write_sfr(self, src_func, name, val, s_id=-1):
        if self.param.GENERATE_SUBMODULE_DIAGRAM:
            self.record_packet_transfer_to_diagram(
                src_name=src_func.__name__,
                dst_name='SFR',
                description='Write SFR',
                is_send_packet=True)
        self.sfr.write_sfr(name, val)

    def set_pre_allocation_info(
            self,
            resource_type,
            pre_alloc_cnt,
            feature_id,
            alloc_call_back_fifo=0):
        assert (self.pre_allocator[resource_type.value] is None)
        pre_allocator = PreAllocator(self)
        pre_allocator.set_pre_allocation_info(
            resource_type, pre_alloc_cnt, feature_id, alloc_call_back_fifo)
        self.pre_allocator[resource_type.value] = pre_allocator

    def is_enabled_pre_allocation(self, resource_type):
        return self.pre_allocator[resource_type.value] is not None

    def get_pre_allocation_resource(self, resource_type, request_size):
        alloc_list = yield from self.pre_allocator[resource_type.value].get_pre_allocation_resource(resource_type, request_size)
        return alloc_list

    def allocate_resource(
            self,
            feature_id,
            resource_type,
            request_size=1,
            packet=None,
            src_func=None,
            s_id=-1,
            is_pre_allocator=False,
            allocate_callback_fifo_id=0):
        need_activate_feature = feature_id != -1
        if need_activate_feature:
            if src_func is None:  # this function must be called in Submodule Process !!
                src_func_name = sys._getframe(1).f_code.co_name
            else:
                src_func_name = src_func.__name__
            submodule = self.submodule_mapper.get(s_id, src_func_name)
            yield from submodule.activate_feature(feature_id, auto_deactivate=False)

        dst, dst_fifo_id = self.allocator_mediator.get_destination_info(
            resource_type)
        if dst is not None and dst_fifo_id is not None and need_activate_feature:
            self.analyzer.register_packet_transfer(
                self.address, dst, 0, 0, dst_fifo_id, 0, resource_type.name)
            self.record_packet_transfer_to_diagram(
                src_submodule=submodule,
                dst_name=self.get_name(
                    dst,
                    dst_fifo_id),
                description=f'Allocate {resource_type.name}',
                is_send_packet=True)

        if self.is_enabled_pre_allocation(
                resource_type) and not is_pre_allocator:
            return_list = yield from self.get_pre_allocation_resource(resource_type, request_size)
        else:
            return_list = yield from self.allocator_mediator.allocate(resource_type, request_size, packet, self.address, allocate_callback_fifo_id)

        if need_activate_feature:
            submodule.deactivate_feature(feature_id)

        return return_list

    def release_resource(self,
                         resource_type,
                         return_id=[-1],
                         packet=None,
                         src_func=None,
                         s_id=-1):
        dst, dst_fifo_id = self.allocator_mediator.release(
            resource_type, self.address, return_id)
        if dst is not None and dst_fifo_id is not None:
            if src_func is None:  # this function must be called in Submodule Process !!
                src_func_name = sys._getframe(1).f_code.co_name
            else:
                src_func_name = src_func.__name__
            submodule = self.submodule_mapper.get(s_id, src_func_name)
            self.analyzer.register_packet_transfer(
                self.address, dst, 0, 0, dst_fifo_id, 0, resource_type.name)
            self.record_packet_transfer_to_diagram(
                src_submodule=submodule,
                dst_name=self.get_name(
                    dst,
                    dst_fifo_id),
                description=f'Release {resource_type.name}',
                is_send_packet=True)

    def resource_allocate_callback(self, packet):
        resource_type = packet['resource_type']
        packet['src'] = self.address
        if self.is_enabled_pre_allocation(resource_type):
            self.pre_allocator[resource_type.value].alloc_done(
                resource_type.value, packet['resource_id'])

        pending_job = self.allocator_mediator.allocate_callback(packet)
        if pending_job:
            pending_job['resource_list'] = packet['resource_id']
        return pending_job
