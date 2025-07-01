from collections import deque

from core.modules.parallel_unit import ParallelUnit


class Mock(ParallelUnit):
    def __init__(
            self,
            product_args,
            _address=0,
            unit_fifo_num=1,
            unit_domain_num=1):
        super().__init__(product_args, _address, unit_fifo_num, unit_domain_num)
        self.received_packet_queue = deque()

    def received_packet_count(self):
        return len(self.received_packet_queue)

    def pop_received_packet(self):
        return self.received_packet_queue.popleft()

    def clear_received_packet(self):
        self.received_packet_queue = deque()

    def handle_request(self, packet, channel_id):
        packet['recv_time'] = self.env.now
        self.received_packet_queue.append(packet)
