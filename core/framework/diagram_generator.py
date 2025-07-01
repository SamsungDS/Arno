import os
from pathlib import Path

from core.backbone.address_map import AddressMap
from core.framework.file_path_generator import FilePathGenerator, LogOutputType


class DictManager:
    @classmethod
    def generate_dict(cls, src_dict, *key_list):
        for idx, key in enumerate(key_list[:-1]):
            if key not in src_dict:
                src_dict[key] = dict()
            src_dict = src_dict[key]

        last_key = key_list[-1]
        if last_key in src_dict:
            return False

        src_dict[last_key] = 0
        return True

    @classmethod
    def search_dict(cls, map, *args):
        for key in args:
            try:
                map = map[key]
            except KeyError:
                assert 0, 'search_dict with invalid key'

        return map


class PacketTransferRecord:
    def __init__(self, is_submodule_record=False):
        self.order = list()
        self.map = dict()
        self.map_exist_dict = dict()
        self.is_submodule = is_submodule_record

    def generate(self, **kwargs):
        args = list(kwargs.values())
        hash_val = hash(tuple(args))

        if hash_val not in self.map_exist_dict:
            DictManager.generate_dict(self.map, *args)
            self.map_exist_dict[hash_val] = True
            self.order.append({key: value for key, value in kwargs.items()})

    def get_map(self, **kwargs):
        self.generate(**kwargs)
        args = list(kwargs.values())
        map = DictManager.search_dict(self.map, *(args[:-1]))
        return map, args[-1]

    def increase(self, **kwargs):
        map, key = self.get_map(**kwargs)
        map[key] += 1

    def set(self, target_value, **kwargs):
        map, key = self.get_map(**kwargs)
        map[key] = target_value

    def get_value(self, *args):
        return DictManager.search_dict(self.map, *args)

    def get_order(self):
        return self.order


class DiagramGenerator:
    def __init__(self, param, _output_dir_name):
        self.param = param
        self.address_map = AddressMap()

        self.output_dir_name = _output_dir_name
        self.clear()

    def clear(self):
        self.sequence_diagram_file = None
        self.communication_diagram_file = None
        self.simple_record = PacketTransferRecord()
        self.module_record = PacketTransferRecord()
        self.submodule_record = PacketTransferRecord(is_submodule_record=True)
        self.submodule_record_per_module = dict()
        self.submodule_latency_record = dict()

    def increase_packet_transfer(
            self,
            src,
            dst,
            src_fifo_id,
            src_domain_id,
            dst_fifo_id,
            dst_domain_id,
            description):
        if not self.param.GENERATE_DIAGRAM:
            return

        self.simple_record.increase(src=src, dst=dst, description=description)
        self.module_record.increase(
            src=src,
            dst=dst,
            src_fifo_id=src_fifo_id,
            src_domain_id=src_domain_id,
            dst_fifo_id=dst_fifo_id,
            dst_domain_id=dst_domain_id,
            description=description)

    def increase_packet_transfer_with_submodule(
            self,
            module_name,
            src,
            dst,
            submodule_latency,
            description,
            is_send_packet):
        if not self.param.GENERATE_SUBMODULE_DIAGRAM:
            return

        if module_name not in self.submodule_record_per_module:
            self.submodule_record_per_module[module_name] = PacketTransferRecord(
                True)

        if is_send_packet:
            self.submodule_record.increase(
                module_name=module_name,
                src=src,
                dst=dst,
                description=description)
            self.submodule_record_per_module[module_name].increase(
                module_name=module_name, src=src, dst=dst, description=description)
        else:
            self.submodule_record.generate(
                module_name=module_name,
                src=src,
                dst=dst,
                description=description)
            self.submodule_record_per_module[module_name].generate(
                module_name=module_name, src=src, dst=dst, description=description)

        if DictManager.generate_dict(
                self.submodule_latency_record,
                module_name,
                src,
                dst,
                description):
            self.submodule_latency_record[module_name][src][dst][description] = submodule_latency

    def is_module_address(self, target):
        return isinstance(target, int)

    def get_name(self, target, domain_id=None, fifo_id=None):
        if self.is_module_address(target):
            target = self.address_map.get_name(target)

        if domain_id is not None:
            target += f'{domain_id}'
        if fifo_id is not None:
            target += f'_FIFO{fifo_id:d}'
        return target

    def get_participant_name_list(self, transfer_order_list):
        name_set = set()
        name_list = list()  # 순서 보장을 위한 list 선언
        box_participant = dict()

        def add_participant(addr, domain_id, fifo_id):
            name = self.get_name(addr, domain_id, fifo_id)
            if self.is_module_address(addr):
                pure_name = self.get_name(addr)
                name_with_domain_id = self.get_name(addr, domain_id)
                if DictManager.generate_dict(
                        box_participant, pure_name, name_with_domain_id):
                    box_participant[pure_name][name_with_domain_id] = set()
                box_participant[pure_name][name_with_domain_id].add(name)
            else:
                # name_set.add(name)
                if name not in name_set:  # unique element만을 list에 삽입하기 위한 코드
                    name_list.append(name)
                    name_set.add(name)

        for info in transfer_order_list:
            src, dst, src_fifo_id, src_domain_id, dst_fifo_id, dst_domain_id, _, _ = self.translate_info(
                info)
            add_participant(src, src_domain_id, src_fifo_id)
            add_participant(dst, dst_domain_id, dst_fifo_id)

        # return list(name_set), box_participant
        return list(name_list), box_participant  # 순서 보장된 list를 반환

    def open_file_and_write_header(self, directory_name, order_queue):
        diagram_directory_path = os.path.join(
            self.diagram_directory_path, directory_name)
        Path(diagram_directory_path).mkdir(parents=True, exist_ok=True)

        self.sequence_diagram_file = open(
            os.path.join(
                diagram_directory_path,
                f'{directory_name}_sequence.plantuml'),
            'w')
        self.communication_diagram_file = open(
            os.path.join(
                diagram_directory_path,
                f'{directory_name}_communication.plantuml'),
            'w')
        self.sequence_diagram_file.write('@startuml\n')
        self.communication_diagram_file.write('@startuml\n')

        name_list, box_participant = self.get_participant_name_list(
            order_queue)

        def wrapper(target, name, open, sequence=True, communication=True):
            if len(target) != 1:
                if open:
                    if sequence:
                        self.sequence_diagram_file.write(f'box {name}\n')
                    if communication:
                        self.communication_diagram_file.write(
                            f'node {name} ' + '{\n')
                else:
                    if sequence:
                        self.sequence_diagram_file.write('end box\n')
                    if communication:
                        self.communication_diagram_file.write('}\n')

        for module_name, participant_dict in box_participant.items():
            wrapper(participant_dict.keys(), module_name, True, sequence=False)
            for module_with_domain_id_name, participant_set in participant_dict.items():
                wrapper(participant_set, module_with_domain_id_name, True)
                for participant in list(participant_set):
                    self.sequence_diagram_file.write(
                        f'participant {participant}\n')
                    self.communication_diagram_file.write(f'[{participant}]\n')
                wrapper(participant_set, module_with_domain_id_name, False)
            wrapper(
                participant_dict.keys(),
                module_name,
                False,
                sequence=False)

        if name_list:
            for order, name in enumerate(name_list):
                self.sequence_diagram_file.write(
                    f'participant {name} order {order:d}\n')
                self.communication_diagram_file.write(f'component {name}\n')

    def close_file(self):
        self.sequence_diagram_file.write('@enduml\n')
        self.communication_diagram_file.write('@enduml\n')
        self.sequence_diagram_file.close()
        self.communication_diagram_file.close()

    def activate(self, name):
        self.sequence_diagram_file.write(f'activate {name}\n')
        self.sequence_diagram_file.write(f'rnote over {name} : {name}\n')

    def deactivate(self, name):
        self.sequence_diagram_file.write(f'{name}-[hidden]->{name}\n')
        self.sequence_diagram_file.write(f'deactivate {name}\n')\


    def translate_info(self, info):
        def return_value_if_key_exist(key):
            if key in info:
                return info[key]
            return None

        src = info['src']
        dst = info['dst']
        description = return_value_if_key_exist('description')
        module_name = return_value_if_key_exist('module_name')
        src_fifo_id = return_value_if_key_exist('src_fifo_id')
        src_domain_id = return_value_if_key_exist('src_domain_id')
        dst_fifo_id = return_value_if_key_exist('dst_fifo_id')
        dst_domain_id = return_value_if_key_exist('dst_domain_id')

        return src, dst, src_fifo_id, src_domain_id, dst_fifo_id, dst_domain_id, module_name, description

    def generate_file(self, directory_name, record: PacketTransferRecord):
        order_queue = record.get_order()
        self.open_file_and_write_header(directory_name, order_queue)
        prev_src_name, prev_dst_name = None, None
        for idx, info in enumerate(order_queue):
            src, dst, src_fifo_id, src_domain_id, dst_fifo_id, dst_domain_id, module_name, description = self.translate_info(
                info)

            src_name = self.get_name(src, src_domain_id, src_fifo_id)
            dst_name = self.get_name(dst, dst_domain_id, dst_fifo_id)
            if src_name != prev_src_name and src_name != prev_dst_name:
                self.activate(src_name)
            if dst_name != prev_src_name and dst_name != prev_dst_name:
                self.activate(dst_name)
            prev_src_name, prev_dst_name = src_name, dst_name

            if record.is_submodule:
                sq_count = record.get_value(module_name, src, dst, description)
                submodule_latency = self.submodule_latency_record[module_name][src][dst][description]
                if submodule_latency != -1:
                    self.sequence_diagram_file.write(
                        f'{src_name}->{src_name} : {int(submodule_latency):d}ns\n')
                else:
                    self.sequence_diagram_file.write(
                        f'{src_name}->{src_name} : TBD\n')
                self.sequence_diagram_file.write(
                    f'{src_name}->{dst_name} : {description}({sq_count:d})\n')
            else:
                if src_fifo_id is None:
                    value = record.get_value(src, dst, description)
                else:
                    value = record.get_value(
                        src,
                        dst,
                        src_fifo_id,
                        src_domain_id,
                        dst_fifo_id,
                        dst_domain_id,
                        description)
                self.sequence_diagram_file.write(
                    f'{src_name}->{dst_name} : {description}_{value:d}\n')
            self.communication_diagram_file.write(
                f'{src_name}-->{dst_name} : {idx:d}.{description}\n')

            try:
                next_src, next_dst, next_src_fifo_id, next_src_domain_id, next_dst_fifo_id, next_dst_domain_id, _, _ = self.translate_info(
                    order_queue[idx + 1])
                next_src_name = self.get_name(
                    next_src, next_src_domain_id, next_src_fifo_id)
                next_dst_name = self.get_name(
                    next_dst, next_dst_domain_id, next_dst_fifo_id)
            except IndexError:
                next_src_name, next_dst_name = None, None

            if dst_name != next_src_name and dst_name != next_dst_name:
                self.deactivate(dst_name)
            if src_name != next_src_name and src_name != next_dst_name:
                self.deactivate(src_name)

        self.close_file()

    def set_file_directory(self):
        self.file_path_generator = FilePathGenerator(self.param)
        self.diagram_directory_path = self.file_path_generator.get_file_prefix(
            LogOutputType.Diagram.value)

    def generate_module_diagram(self):
        self.set_file_directory()
        self.generate_file('Module', self.module_record)
        self.generate_file('SimpleModule', self.simple_record)

    def generate_submodule_diagram(self):
        self.set_file_directory()
        for module_name in self.submodule_record_per_module.keys():
            self.generate_file(
                f'Submodule_{module_name}',
                self.submodule_record_per_module[module_name])

        self.generate_file('Submodule', self.submodule_record)

    def generate_diagram(self):
        self.set_file_directory()
        if self.param.GENERATE_DIAGRAM:
            self.generate_module_diagram()
        if self.param.GENERATE_SUBMODULE_DIAGRAM:
            self.generate_submodule_diagram()
