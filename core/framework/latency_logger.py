
from enum import Enum

from core.framework.common import ProductArgs


class LoggingSection(Enum):
    eHostCMDRecv_4KSplit = 1,
    eAll = 999


class SectionInfo:
    def __init__(self):
        self.section = LoggingSection.eAll
        self.entryPos, self.exitPos = None, None  # submodule name


def LatencyLogNode(id):
    node = {'id': id, 'entry_queue': dict()}
    return node


class LatencyLogger:
    def __new__(cls, product_args: ProductArgs = None):
        if not hasattr(cls, 'instance'):
            cls.instance = super().__new__(cls)
        if product_args is not None:
            product_args.set_args_to_class_instance(cls.instance)
            cls.instance.init_latency_logger()
        return cls.instance

    def init_latency_logger(self):
        self.logNodeID = 0
        self.logNode = dict()
        self.loggingSection = dict()

    def set_logging_position(self, name, s_id, section, isStart):
        if s_id not in self.loggingSection:
            self.loggingSection[s_id] = dict()
        self.loggingSection[s_id][name] = [section, isStart]

    def get_section(self, name, s_id):
        if s_id not in self.loggingSection or name not in self.loggingSection[s_id]:
            return LoggingSection.eAll, False
        return self.loggingSection[s_id][name][0], self.loggingSection[s_id][name][1]

    def delete_log_data(self, logID):
        del self.logNode[logID]

    def logging_latency(self, name, s_id, packet):
        if self.param.ENABLE_LATENCY_LOGGER:
            section, isStart = self.get_section(name, s_id)

            if section != LoggingSection.eAll:
                if isStart:
                    node = None
                    if packet['latency_log_id'] == -1:
                        newNode = LatencyLogNode(self.logNodeID)
                        packet['latency_log_id'] = self.logNodeID
                        self.logNode[self.logNodeID] = newNode
                        self.logNodeID += 1
                        node = newNode
                    else:
                        node = self.logNode[packet['latency_log_id']]

                    node['entry_queue'][section] = self.env.now

                else:
                    node = self.logNode[packet['latency_log_id']]
                    if section not in node['entry_queue']:
                        assert 0, 'invalid log section'
