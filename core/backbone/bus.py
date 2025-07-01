

from collections import deque

from core.backbone.address_map import AddressMap
from core.framework.analyzer import Analyzer
from core.framework.common import ProductArgs
from core.framework.submodule_event import SubmoduleEvent


class BusWaitingQ:
    def __init__(self, env):
        self.env = env
        self.src_event = SubmoduleEvent(env)
        self.dst_event = SubmoduleEvent(env)
        self.src_queue = deque()
        self.dst_queue = deque()

    def append(self, packet):
        self.src_queue.append(packet)

    def start_transfer(self):
        self.src_event.trigger()

    def append_directly(self, packet):
        self.dst_queue.append(packet)

    def start_transfer_directly(self):
        self.dst_event.trigger()


class Bus:
    instance = None

    def __new__(cls, product_args: ProductArgs = None):
        if cls.instance is None:
            cls.instance = super(Bus, cls).__new__(cls)
        if product_args is not None:
            product_args.set_args_to_class_instance(cls.instance)
            cls.instance.init_src_waiting_queue()
        return cls.instance

    def init_src_waiting_queue(self):
        self.analyzer = Analyzer()

        max_address = AddressMap().get_max_address()
        self.waiting_queue: list[BusWaitingQ | None] = [
            None for _ in range(max_address + 1)]

        if self.param.GENERATE_DIAGRAM:
            self.packet_processing = self.packet_processing_with_dst_id

        self.SKIP_BUS_PROCESS = self.param.IP_TRANSACTION_LATENCY_NS == 0
        if self.SKIP_BUS_PROCESS:
            self.push_sq = self.push_sq_directly
            self.start_packet_transfer = self.start_packet_transfer_directly

    def bus_process(self, dst, fifo_id, domain_id):
        waiting_queue: BusWaitingQ = self.waiting_queue[dst][domain_id][fifo_id]
        src_event: SubmoduleEvent = waiting_queue.src_event
        src_queue: deque = waiting_queue.src_queue
        dst_event: SubmoduleEvent = waiting_queue.dst_event
        dst_queue: deque = waiting_queue.dst_queue
        IP_TRANSACTION_LATENCY_NS = self.param.IP_TRANSACTION_LATENCY_NS

        while True:
            yield src_event.wait()
            src_event.reset()
            while src_queue:
                yield self.env.timeout(IP_TRANSACTION_LATENCY_NS)

                dst_queue.append(src_queue.popleft())
                dst_event.trigger()

    def connect_bus(self, dst, dst_fifo_num=1, dst_domain_num=1):
        assert self.waiting_queue[dst] is None, f'address {dst} already exist! check module address is correct'
        self.waiting_queue[dst] = [[BusWaitingQ(self.env) for _ in range(
            dst_fifo_num)] for _ in range(dst_domain_num)]
        if self.SKIP_BUS_PROCESS:
            return

        for dst_fifo_id in range(dst_fifo_num):
            for dst_domain_id in range(dst_domain_num):
                self.env.process(
                    self.bus_process(
                        dst,
                        dst_fifo_id,
                        dst_domain_id))

    def push_sq(self, packet, dst, dst_fifo_id=0, dst_domain_id=0):
        self.waiting_queue[dst][dst_domain_id][dst_fifo_id].append(packet)

    def push_sq_directly(self, packet, dst, dst_fifo_id=0, dst_domain_id=0):
        self.waiting_queue[dst][dst_domain_id][dst_fifo_id].append_directly(
            packet)

    def start_packet_transfer(self, dst, dst_fifo_id, dst_domain_id):
        self.waiting_queue[dst][dst_domain_id][dst_fifo_id].start_transfer()

    def start_packet_transfer_directly(self, dst, dst_fifo_id, dst_domain_id):
        self.waiting_queue[dst][dst_domain_id][dst_fifo_id].start_transfer_directly(
        )

    def packet_processing(self, src, packet, dst_fifo_id, dst_domain_id):
        packet['src'] = src
        return packet

    def packet_processing_with_dst_id(
            self, src, packet, dst_fifo_id, dst_domain_id):
        packet['src'] = src
        packet['bus_dst_fifo_id'] = dst_fifo_id
        packet['bus_dst_domain_id'] = dst_domain_id
        return packet

    def send_sq(self, packet, src, dst, dst_fifo_id=0, dst_domain_id=0):
        send_packet = self.packet_processing(
            src, packet, dst_fifo_id, dst_domain_id)
        self.push_sq(send_packet, dst, dst_fifo_id, dst_domain_id)
        self.vcd_manager.send_sq(src, dst)
        self.start_packet_transfer(dst, dst_fifo_id, dst_domain_id)
