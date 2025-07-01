from core.config.core_parameter import CoreParameter
from core.framework.cell_type import Cell


class NANDtProgParser:
    def __init__(self, nand_product):
        self.param = CoreParameter()
        self.nand_product = nand_product
        self.tprog_list_by_cell_type = [
            None for _ in range(Cell.TLC.value + 1)]

        self.parse()

    def get_tprog(self, cell_type: Cell, wl: int = 0):
        try:
            return self.tprog_list_by_cell_type[cell_type.value][wl]
        except IndexError:
            return self.tprog_list_by_cell_type[cell_type.value][0]

    def parse(self, cell_type: Cell = None, f_name=None):
        for cell_type in (Cell.SLC, Cell.MLC, Cell.TLC):
            if self.tprog_list_by_cell_type[cell_type.value] is None:
                self.tprog_list_by_cell_type[cell_type.value] = [
                    self.param.NAND_PARAM[self.nand_product][f'{cell_type.name}_tPROG']]
