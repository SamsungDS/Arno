class ContextError(Exception):
    def __init__(self, msg: str):
        super().__init__(msg)


class InvalidSource(Exception):
    def __init__(self, src):
        super().__init__(src)


class InvalidOPCode(Exception):
    def __init__(self, opcode: str):
        super().__init__(opcode)


class InvalidSBN(Exception):
    def __init__(self, sbn: int):
        super().__init__(sbn)


class NoFreeBlock(Exception):
    def __init__(self):
        super().__init__()


class MetaMapNotFoundError(Exception):
    def __init__(self):
        super().__init__()


class InvalidReferenceMap(Exception):
    def __init__(self):
        super().__init__()


class InvalidPif(Exception):
    def __init__(self):
        super().__init__()


class MissingPacketInfo(Exception):
    def __init__(self):
        super().__init__()


class MismatchPacketInfo(Exception):
    def __init__(self):
        super().__init__()
