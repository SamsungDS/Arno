from dataclasses import dataclass

from core.framework.cell_type import Cell


@dataclass
class PhysicalInfo:
    addr_offset: int = 0
    wl: int = 0
    ssl: int = 0
    page: int = 0
    way: int = 0
    ch: int = 0
    plane: int = 0
    lpo: int = 0
    cell_type: Cell = None

    def __eq__(self, other):
        return (self.addr_offset == other.addr_offset
                and self.way == other.way
                and self.ch == other.ch
                and self.plane == other.plane
                and self.lpo == other.lpo
                and self.cell_type == other.cell_type)

    def __hash__(self):
        return hash(
            (self.addr_offset,
             self.way,
             self.ch,
             self.plane,
             self.lpo,
             self.cell_type))

    def __repr__(self) -> str:
        return f'addr_offset{self.addr_offset:d}_wl{self.wl:d}_ssl{self.ssl:d}_page{self.page:d}_way{self.way:d}_ch{self.ch:d}_plane{self.plane:d}_lpo{self.lpo:d}_celltype{self.cell_type}'
