import inspect

import numpy as np
from core.framework.common import ProductArgs


def VCDManagerFuncDecorator(func):
    def check_enable_vcd(self, *args, **kwargs):
        if self.param.ENABLE_VCD:
            return func(self, *args, **kwargs)
        else:
            return
    return check_enable_vcd


def VCDManagerClassDecorator(cls):
    for name, function in inspect.getmembers(cls, inspect.isfunction):
        if '__new__' not in name:
            setattr(cls, name, VCDManagerFuncDecorator(function))
    return cls


@VCDManagerClassDecorator
class VCDManager:
    def __new__(cls, product_args: ProductArgs = None):
        if not hasattr(cls, 'instance'):
            cls.instance = super().__new__(cls)
        if product_args:
            product_args.set_args_to_class_instance(cls.instance)
            cls.instance.init_vcd_manager()
        return cls.instance

    def init_vcd_manager(self):
        self.vcd_file_name = self.param.VCD_FILE_NAME
        if self.param.VCD_DUMP_END_TIME_MS > 0:
            self.VCD_DUMP_END_TIME_NS = self.param.VCD_DUMP_END_TIME_MS * 1e6
        else:
            self.VCD_DUMP_END_TIME_NS = np.inf

        self.vcd_wire_name = ['a']
        self.vcd_wire_name_change_ptr = 0
        self.cur_time = 0

        if hasattr(self, 'vcd_file'):
            self.vcd_file.close()
        self.vcd_file = open(self.vcd_file_name, 'w')
        self.init_vcd_file()
        self.vcd_dump_var_list = dict()

    def close_vcd_file(self):
        self.vcd_file.close()

    def init_vcd_file(self):
        self.vcd_file.write('$timescale\n\t1ns\n$end\n')

    def add_vcd_dump_var(self, module_name, dump_var, var_type='b'):
        if module_name not in self.vcd_dump_var_list:
            self.vcd_dump_var_list[module_name] = dict()
        self.vcd_dump_var_list[module_name][dump_var] = {
            'wire_name': None,
            'type': var_type
        }

    def del_vcd_dump_var(self, module_name, dump_var):
        try:
            del self.vcd_dump_var_list[module_name][dump_var]
        except BaseException:
            print(f'{module_name}, {dump_var} do not exist')

    def dfs(self):
        self.vcd_wire_name[self.vcd_wire_name_change_ptr] = chr(
            ord(self.vcd_wire_name[self.vcd_wire_name_change_ptr]) + 1)
        if ord(self.vcd_wire_name[self.vcd_wire_name_change_ptr]) > 122:  # 'z'
            self.vcd_wire_name[self.vcd_wire_name_change_ptr] = 'a'
            self.vcd_wire_name_change_ptr -= 1

            if self.vcd_wire_name_change_ptr < 0:
                self.vcd_wire_name = ['a' for _ in range(
                    len(self.vcd_wire_name) + 1)]
            else:
                self.dfs()

    def create_vcd_wire_name(self):
        out_name = ''.join(self.vcd_wire_name)
        self.dfs()
        self.vcd_wire_name_change_ptr = len(self.vcd_wire_name) - 1
        return out_name

    def add_vcd_module_done(self):
        self.vcd_file.write('$scope module Simpy $end\n')
        for module, var_dict in self.vcd_dump_var_list.items():
            self.vcd_file.write('$scope module ' + module + ' $end\n')
            for var_name in var_dict.keys():
                var_dict[var_name]['wire_name'] = self.create_vcd_wire_name()
                if var_dict[var_name]['type'] == 'b':
                    self.vcd_file.write(
                        '$var wire 1 ' +
                        var_dict[var_name]['wire_name'] +
                        ' ' +
                        str(var_name) +
                        ' $end\n')
                elif var_dict[var_name]['type'] == 'int':
                    self.vcd_file.write(
                        '$var wire 32 ' +
                        var_dict[var_name]['wire_name'] +
                        ' ' +
                        str(var_name) +
                        ' [31:0] ' +
                        '$end\n')
                elif var_dict[var_name]['type'] == 'int64':
                    self.vcd_file.write(
                        '$var wire 64 ' +
                        var_dict[var_name]['wire_name'] +
                        ' ' +
                        str(var_name) +
                        ' [63:0] ' +
                        '$end\n')
                else:
                    print(
                        var_dict[var_name]['type'] +
                        ' Not Supported VCD Type Yet')
                    exit()

            self.vcd_file.write('$upscope $end\n')
        self.vcd_file.write('$upscope $end\n')
        self.vcd_file.write('$enddefinitions $end\n$dumpvars\n')

        for var_dict in self.vcd_dump_var_list.values():
            for var_dict_val in var_dict.values():
                self.vcd_file.write('b0 ' + var_dict_val['wire_name'] + '\n')

        self.vcd_file.write('$end\n')

    def record_log(self, target_var, module_name, var_name):
        if self.env.now > self.VCD_DUMP_END_TIME_NS:
            return

        module_name, var_name = self.remove_indent(
            module_name), self.remove_indent(var_name)
        if self.env.now != self.cur_time:
            self.vcd_file.write(f'#{int(self.env.now):d}\n')
            self.cur_time = self.env.now
        target_var = target_var if isinstance(
            target_var, str) else str(
            format(
                target_var, 'b'))
        self.vcd_file.write(' b' +
                            target_var +
                            ' ' +
                            str(self.vcd_dump_var_list[module_name][var_name]['wire_name']) +
                            '\n')

    def remove_indent(self, line):
        return ''.join(line.split())

    def add_vcd_dump_vars(self, q):
        name = self.remove_indent(q.popleft())  # module name
        while (len(q)):
            varName = self.remove_indent(q.popleft())  # sub module name
            self.add_vcd_dump_var(name, varName, 'int')
