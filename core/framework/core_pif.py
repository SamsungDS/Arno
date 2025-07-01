from core.backbone.address_map import AddressMap
from core.config.core_parameter import CoreParameter
from core.framework.exception import (InvalidPif, InvalidReferenceMap,
                                      MismatchPacketInfo, MissingPacketInfo)


def color_str(str, c):
    if c == 'm':    # magenta
        return '\033[35m' + str + '\033[0m'
    elif c == 'y':  # yellow
        return '\033[33m' + str + '\033[0m'


def get_iter_deepcopy(v):
    if isinstance(v, str):
        return v
    elif isinstance(v, list):
        return [
            get_iter_deepcopy(_v) if hasattr(
                _v,
                '__iter__') else _v for i,
            _v in enumerate(v)]
    elif isinstance(v, dict):
        return {
            _k: get_iter_deepcopy(_v) if hasattr(
                _v,
                '__iter__') else _v for _k,
            _v in v.items()}
    else:
        assert 0, f'{type(v)} not support'


class SkipCheckPIFDict(dict):
    def __init__(self, *args: [dict, int], **kwargs):
        self.update(args[0], **kwargs)  # create product dict using src dict

    def gen_packet(self, *args: [dict, int], **kwargs):
        pass

    def get_copy(self):
        return {
            k: get_iter_deepcopy(v) if hasattr(
                v,
                '__iter__') else v for k,
            v in super().items()}


class CheckPIFDict(dict):
    # key_list format : dwN, lowBit_highBit, comment
    #                   eg, dw0 or dw1
    #                        eg, 0_15 or 3_17
    #                                         eg, operation code

    def __init__(self, *args: [dict, int], **kwargs):
        self.head_key_list = [
            'opCode',   # dw0,    0_7,    operation code
            'src',      # dw0,    8_15,   src ip
            'rsvd',     # dw0,    16_31,   reserved
        ]

        self.debug_key_list = [
            'issueTime',
            'debug',
            'internal',
            'bus_dst_fifo_id',
            'bus_dst_domain_id'
        ]

        # updated when product creator called
        self.reference_map = []
        # updated when product creator called
        self.key_list = self.head_key_list + self.debug_key_list
        # updated when product creator called or productSQ['key'] access
        self.key_list_set_pos = {}
        # args[0] : src dict, args[1] : address_map
        self.set_pos = args[1]

        self.address_map = AddressMap()
        self.name = self.address_map.get_name(args[1])
        self.history = list()

    def gen_packet(self, body_key_list, *args: [dict, int], **kwargs):
        self.key_list = self.key_list + body_key_list
        src_name = ''
        if isinstance(
                args[0],
                CommonSQ):                               # productSQ -> productSQ case
            src_name = args[0].__class__.__name__
            for _key in args[0]:
                # if key in product_pif, change set position
                if _key in args[0].key_list and _key in self.key_list and _key in args[0].key_list_set_pos:
                    self.key_list_set_pos[_key] = self.set_pos
            self.history = args[0].history
        # dict -> productSQ case, change set position for every key
        else:
            src_name = 'New Dict'
            init_list = self.head_key_list + self.debug_key_list
            for _i, _v in enumerate(init_list):
                if _v not in args[0]:
                    args[0][_v] = 0
            for _key in args[0]:
                if _key in self.key_list:
                    self.key_list_set_pos[_key] = self.set_pos
        self.history.append(
            f'{self.name} : {src_name} -> {self.__class__.__name__} {self.key_list}')
        self.update(args[0], **kwargs)  # create product dict using src dict

    def assert_if_key_not_in_pif(self, key):
        if key in self.key_list:
            return
        if key in self.reference_map:
            if self.reference_map[key] in self.key_list:
                return
            else:
                ref = color_str(key, "y")
                key = color_str(self.reference_map[key], "y")
                sq_name = color_str(self.__class__.__name__, "m")
                print(f'{ref} is reference {key}, but {key} not in {sq_name}')
                print('reference core_pif_test.py')
                print('  case 1 : test_access_not_in_pif')
                self.print_packet_casting_history()
                raise InvalidReferenceMap()
        else:
            key = color_str(key, "y")
            sq_name = color_str(self.__class__.__name__, "m")
            print(f'{key} not in {sq_name}')
            print('reference core_pif_test.py')
            print('  case 1 : test_access_not_in_pif')
            self.print_packet_casting_history()
            raise InvalidPif()

    def check_set_pos(self, key):
        if key in self.key_list:
            if key not in self.key_list_set_pos:
                print(f'{color_str(key, "y")} have never been set up')
                print('reference core_pif_test.py')
                print('  case 1 : test_bypass_missing_key_in_pif')
                self.print_packet_casting_history()
                raise MissingPacketInfo()
            elif self.key_list_set_pos[key] != super().__getitem__('src'):
                key_set_pos = self.address_map.get_name(
                    self.key_list_set_pos[key])
                sender = self.address_map.get_name(super().__getitem__('src'))
                print(
                    f'{color_str(key, "y")} set_position({key_set_pos}), packet_sender({sender})')
                print('reference core_pif_test.py')
                print('  case 1 : test_access_before_send_sq')
                print('  case 2 : test_missing_casting_send_sq')
                self.print_packet_casting_history()
                raise MismatchPacketInfo()

    def __getitem__(self, key):
        if key not in self.debug_key_list:
            self.assert_if_key_not_in_pif(key)
            if key in self.reference_map:
                self.check_set_pos(self.reference_map[key])
            else:
                self.check_set_pos(key)
        return super().__getitem__(key)

    def __setitem__(self, key, value):
        if key not in self.debug_key_list:
            self.assert_if_key_not_in_pif(key)
            if key in self.key_list:
                self.key_list_set_pos[key] = self.set_pos
            elif key in self.reference_map:
                self.key_list_set_pos[self.reference_map[key]] = self.set_pos
        super().__setitem__(key, value)

    def get_copy(self):
        return {
            k: get_iter_deepcopy(v) if hasattr(
                v,
                '__iter__') else v for k,
            v in super().items()}

    def print_packet_casting_history(self):
        print('* Packet Casting History')
        print('IP : src -> dst [dst_pif key list] < Print Format')
        print(*self.history, sep='\n')
        print()


CommonSQ = CheckPIFDict if CoreParameter().USING_PIF else SkipCheckPIFDict
