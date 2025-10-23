from collections import deque

import simpy
from core.backbone.address_map import AddressMap
from core.backbone.bus import Bus
from core.framework.analyzer import Analyzer
from core.framework.common import (ProductArgs, RequestResourceInfo,
                                   eRequestType, eResourceType)


class Allocator(type):
    instances = {}

    def __call__(cls, *args, **kwargs):
        key = (args, tuple(kwargs.items()))
        if key not in cls.instances:
            cls.instances[key] = super().__call__(*args, **kwargs)
        return cls.instances[key]

    @classmethod
    def reset(cls):
        cls.instances = {}


class SimpyResourceAllocator(metaclass=Allocator):
    class SimpyResource:
        '''Ask Resource Available to simpy.Resource API'''

        def __init__(self, env, id_count):
            self.available_queue = simpy.Resource(env, id_count)
            self.deque = deque()

        def request(self, count):
            for _ in range(count):
                available = self.available_queue.request()
                yield available
                self.deque.append(available)

        def release(self, count):
            for _ in range(count):
                self.available_queue.release(self.deque.popleft())

    class ResourceIDList:
        def __init__(self, id_count, start_addr):
            self.deque = deque([start_addr + i for i in range(id_count)])

        def __len__(self):
            return len(self.deque)

        def get_id(self, id_count):
            id_list = list()
            for _ in range(id_count):
                id_list.append(self.deque.popleft())
            return id_list

        def return_id(self, id):
            if isinstance(id, list):
                self.deque.extend(id)
            else:
                self.deque.append(id)

    class ResourceBuffer:
        def __init__(self, id_count):
            self.buffer = [None for _ in range(id_count)]
            self.buffer_size = id_count

        def read(self, id):
            return self.buffer[id % self.buffer_size]

        def write(self, id_list, packet_list):
            if packet_list is None:
                return

            assert len(packet_list) == len(id_list)
            for idx, free_id in enumerate(id_list):
                self.buffer[free_id % self.buffer_size] = packet_list[idx]

        def erase(self, id):
            if isinstance(id, list):
                for i in id:
                    try:
                        self.buffer[i % self.buffer_size] = None
                    except IndexError:
                        return
            else:
                try:
                    self.buffer[id % self.buffer_size] = None
                except IndexError:
                    return

    class ResourceAnalyzer:
        def __init__(self, env, vcd_manager, resource_type):
            self.env = env
            self.vcd_manager = vcd_manager
            self.resource_type = resource_type
            self.allocated_count = 0
            self.total_allocated_count = 0
            self.resource_enqueue_times = deque()
            self.total_resource_lifetime = 0

        def allocate(self, count):
            self.allocated_count += count
            self.total_allocated_count += count
            self.resource_enqueue_times.extend([int(self.env.now)] * count)
            self.vcd_manager.update_resource_allocate(
                self.resource_type, self.allocated_count)

        def release(self, count):
            self.allocated_count -= count
            for _ in range(count):
                self.total_resource_lifetime += (
                    self.env.now - self.resource_enqueue_times.popleft())

            self.vcd_manager.update_resource_allocate(
                self.resource_type, self.allocated_count)

        def reset_utilization(self):
            self.total_resource_lifetime = 0

    def __init__(
            self,
            product_args: ProductArgs,
            resource_type,
            id_count,
            start_addr=0):
        product_args.set_args_to_class_instance(self)
        self.resource_count = id_count
        self.resource_type = resource_type
        self.simpy_resource = self.SimpyResource(self.env, id_count)
        self.free_id_queue = self.ResourceIDList(id_count, start_addr)
        self.resource_buffer = self.ResourceBuffer(id_count)
        self.resource_analyzer = self.ResourceAnalyzer(
            self.env, self.vcd_manager, resource_type)

    def read(self, resource_id):
        return self.resource_buffer.read(resource_id)

    def write(self, resource_id, data):
        self.resource_buffer.write([resource_id], [data])

    def allocate(self, packet_list=None, request_size=1):
        yield from self.simpy_resource.request(request_size)
        resource_id_list = self.free_id_queue.get_id(request_size)
        self.resource_buffer.write(resource_id_list, packet_list)
        self.resource_analyzer.allocate(request_size)
        return resource_id_list

    def release(self, return_id=-1):
        self.free_id_queue.return_id(return_id)
        self.resource_buffer.erase(return_id)

        if isinstance(return_id, list):
            count = len(return_id)
        else:
            count = 1

        self.resource_analyzer.release(count)
        self.simpy_resource.release(count)


class SimpyContainerAllocator(metaclass=Allocator):
    def __init__(self, product_args: ProductArgs, resource_type, id_count):
        product_args.set_args_to_class_instance(self)
        self.free_id_queue = deque([i for i in range(id_count)])
        self.resource_type = resource_type
        self.resource_buffer = [None for _ in range(id_count)]
        self.available_resource_queue = simpy.Container(
            self.env, id_count, init=id_count)
        self.allocated_count = 0

    def allocate(self, count, packet=None):
        yield self.available_resource_queue.get(count)
        allocate_id_list = list()

        for _ in range(count):
            allocate_id_list.append(self.free_id_queue.popleft())
        self.allocated_count += count
        self.vcd_manager.update_resource_allocate(
            self.resource_type, self.allocated_count)

        return allocate_id_list

    def release(self, return_id_list):
        for return_id in return_id_list:
            self.free_id_queue.append(return_id)

        self.allocated_count -= len(return_id_list)
        self.vcd_manager.update_resource_allocate(
            self.resource_type, self.allocated_count)
        yield self.available_resource_queue.put(len(return_id_list))


class CustomDeque(deque):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.env = args[0]
        self.event = self.env.event()

    def append(self, x):
        super().append(x)
        self.event.succeed()
        self.event = self.env.event()


class ModuleTransactionAllocator(metaclass=Allocator):
    def __init__(self, product_args: ProductArgs):
        product_args.set_args_to_class_instance(self)
        self.address_map = AddressMap()
        self.analyzer = Analyzer()
        self.bus = Bus()

        self.resource_producer_address = [-1 for index,
                                          value in enumerate(eResourceType)]
        self.resource_producer_allocation_domain = [
            0 for index, value in enumerate(eResourceType)]
        self.resource_producer_release_domain = [
            0 for index, value in enumerate(eResourceType)]
        self.resource_producer_allocation_fifo = [
            -1 for index, value in enumerate(eResourceType)]
        self.resource_producer_release_fifo = [
            -1 for index, value in enumerate(eResourceType)]
        self.resource_alloc_feature = [-1 for index,
                                       value in enumerate(eResourceType)]
        self.resource_release_feature = [-1 for index,
                                         value in enumerate(eResourceType)]
        self.allocation_request_count = [
            0 for index, value in enumerate(eResourceType)]
        self.allocated_count = [0 for index, value in enumerate(eResourceType)]

        self.allocation_requester_fifo = CustomDeque(self.env)
        self.release_requester_fifo = CustomDeque(self.env)

        self.env.process(self.allocate_requester())
        self.env.process(self.release_requester())

        self.request_limit = 2
        self.request_count = [[0 for index,
                               value in enumerate(eResourceType)] for index,
                              value in enumerate(self.address_map.address_name_dict)]
        self.receive_call_back_event = [
            self.env.event() for index, value in enumerate(
                self.address_map.address_name_dict)]

        self.pending_job = {}
        self.unique_key = 0

    def set_resource_producer_address(
            self,
            resource_type,
            address,
            allocation_fifo_id=0,
            release_fifo_id=0,
            alloc_domain=0,
            release_domain=0):
        self.resource_producer_address[resource_type] = address
        self.resource_producer_allocation_fifo[resource_type] = allocation_fifo_id
        self.resource_producer_release_fifo[resource_type] = release_fifo_id
        self.resource_producer_allocation_domain[resource_type] = alloc_domain
        self.resource_producer_release_domain[resource_type] = release_domain

    def set_feature_id(
            self,
            resource_type,
            alloc_feature_id,
            release_feature_id):
        self.resource_alloc_feature[resource_type] = alloc_feature_id
        self.resource_release_feature[resource_type] = release_feature_id

    def allocate_requester(self):
        while True:
            yield self.allocation_requester_fifo.event
            while self.allocation_requester_fifo:
                packet: RequestResourceInfo = self.allocation_requester_fifo.popleft()
                resource_type_int = packet['resource_type'].value
                self.allocation_request_count[resource_type_int] += packet['request_size']
                self.bus.send_sq(
                    packet,
                    packet['request_ip'],
                    self.resource_producer_address[resource_type_int],
                    self.resource_producer_allocation_fifo[resource_type_int])

    def release_requester(self):
        while True:
            yield self.release_requester_fifo.event
            while self.release_requester_fifo:
                packet: RequestResourceInfo = self.release_requester_fifo.popleft()
                yield self.env.timeout(self.feature.get_latency(self.resource_release_feature[packet['resource_type'].value]))
                resource_type_int = packet['resource_type'].value
                self.bus.send_sq(
                    packet,
                    packet['request_ip'],
                    self.resource_producer_address[resource_type_int],
                    self.resource_producer_release_fifo[resource_type_int])

    def allocate_call_back(self, packet):
        src_address = packet['src']
        resource_type = packet['resource_type']
        self.allocated_count[resource_type.value] += packet['request_size']
        self.vcd_manager.update_resource_allocate(
            resource_type, self.allocated_count[resource_type.value])

        self.request_count[src_address][resource_type.value] -= 1
        self.receive_call_back_event[src_address].succeed()
        self.receive_call_back_event[src_address] = self.env.event()

        pending_job = self.pending_job[packet['unique_key']]
        del self.pending_job[packet['unique_key']]
        return pending_job

    def allocate(
            self,
            resource_type,
            request_size,
            src_address,
            packet,
            allocation_callback_fifo_id=0):
        if self.request_count[src_address][resource_type.value] == self.request_limit:
            yield self.receive_call_back_event[src_address]

        self.pending_job[self.unique_key] = packet
        self.allocation_requester_fifo.append(
            RequestResourceInfo(
                resource_type,
                eRequestType.Allocate,
                src_address,
                self.unique_key,
                request_size,
                requestCallbackFifoID=allocation_callback_fifo_id))
        self.unique_key += 1
        self.request_count[src_address][resource_type.value] += 1

    def release(self, resource_type, return_id=-1):
        self.allocated_count[resource_type.value] -= len(return_id)
        self.vcd_manager.update_resource_allocate(
            resource_type, self.allocated_count[resource_type.value])
        packet = RequestResourceInfo(
            resource_type,
            eRequestType.Release,
            0,
            0,
            len(return_id),
            return_id)
        self.release_requester_fifo.append(packet)

    def print_debug(self):
        if any(self.request_count):
            print("if you're seeing this debug info, (1.accessed one resource_type from multiple submodules(in same ip)) or (2.resource_dead_lock)")
            for address, ip_list in enumerate(self.request_count):
                dead_lock_resource = [
                    eResourceType(index) for index,
                    value in enumerate(ip_list) if value != 0]
                if dead_lock_resource:
                    print(
                        ' - hang ip:',
                        self.address_map.get_name(address),
                        '/ hang resource type:',
                        dead_lock_resource)
