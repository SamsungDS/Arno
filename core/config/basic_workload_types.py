import re
from abc import ABC, abstractmethod
from enum import Enum, auto

from core.framework.common import eCMDType

KiB = 1024
MiB = KiB * 1024
GiB = MiB * 1024


class BasicPatternType(Enum):
    Dummy = auto()
    Seq = auto()
    Ran = auto()
    Mixed = auto()


class Pattern(ABC):
    def __init__(
            self,
            cmd_type=None,
            pattern_type=None,
            chunk_size_bytes=0,
            range_bytes=0,
            start_lba=0):
        self.cmd_type = cmd_type
        self.pattern_type = pattern_type
        self.chunk_size_bytes: int = chunk_size_bytes
        self.range_bytes: int = range_bytes
        self.start_lba: int = start_lba

    @abstractmethod
    def get_name(self):
        pass


class BasicPattern(Pattern):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        assert isinstance(self.cmd_type, eCMDType)

    def get_name(self):
        if self.pattern_type == BasicPatternType.Dummy:
            return self.cmd_type.name

        return f'{self.pattern_type.name}{self.cmd_type.name}'


class MixedPattern(Pattern):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cmd_type = (eCMDType.Read, eCMDType.Write, )

    def set_percent(self, read_percent, write_percent):
        self.read_percent = read_percent
        self.write_percent = write_percent

    def get_name(self):
        name = self.pattern_type.name
        for cmd_type in self.cmd_type:
            if cmd_type == eCMDType.Read:
                percent = self.read_percent
            elif cmd_type == eCMDType.Write:
                percent = self.write_percent
            name += f'_{cmd_type.name}{percent:d}'
        return name


class BasicWorkload:
    def __init__(
            self,
            pattern: Pattern,
            *,
            qd: int = 1,
            count: int = None,
            count_ratio: float = 1,
            idle_time_ms: int = 0):
        self.pattern = pattern
        self.qd = qd
        self.cmd_count = count if count else int(
            pattern.range_bytes // pattern.chunk_size_bytes * count_ratio)
        self.count_ratio = count_ratio
        self.name = self.get_workload_name()
        self.idle_time_ms = idle_time_ms

    def get_workload_name(self) -> str:
        return self.pattern.get_name()

    def parse_range_bytes(self, range_bytes: str) -> int:
        units = {
            'KB': KiB,
            'MB': MiB,
            'GB': GiB
        }
        s = range_bytes.strip().upper()
        match = re.match(r'(\d+(?:\.\d+)?)([A-Z]+)', s)
        if not match:
            raise ValueError(
                f"Invalid format: '{range_bytes}'. "
                "Expected format like '128KB', '64MB', '1GB'. "
                "Supported units: KB, MB, GB"
            )
        value, unit = match.groups()
        value = int(value)

        if unit not in units:
            raise ValueError(
                f"Unknown unit '{unit}' in '{range_bytes}'. "
                "Supported units are: KB, MB, GB."
            )
        return value * units[unit]

    def set_range_bytes(self, range_bytes: str):
        range_bytes_int = self.parse_range_bytes(range_bytes)
        self.pattern.range_bytes = range_bytes_int
        self.cmd_count = int(
            range_bytes_int //
            self.pattern.chunk_size_bytes *
            self.count_ratio)

    def __repr__(self):
        return self.name

    def __str__(self):
        return self.name


class PreDefinedWorkload:
    def generate_mixed_workload(self, read_percent, write_percent):
        SeqW_128K_1GB = BasicPattern(
            cmd_type=eCMDType.Write,
            pattern_type=BasicPatternType.Seq,
            chunk_size_bytes=128 * KiB,
            range_bytes=1 * GiB)

        mixed_4K_1GB = MixedPattern(
            pattern_type=BasicPatternType.Mixed,
            chunk_size_bytes=4 * KiB,
            range_bytes=1 * GiB)
        mixed_4K_1GB.set_percent(read_percent, write_percent)
        return (
            BasicWorkload(
                SeqW_128K_1GB, qd=32), BasicWorkload(
                mixed_4K_1GB, qd=512),)

    def __getattr__(self, name):
        if 'mixed' in name:
            read_write_line = name.split('_')[1]
            matches = re.findall(r'([A-Za-z]+)(\d+)', read_write_line)
            components = [(match[0], int(match[1])) for match in matches]
            read_percent, write_percent = 0, 0
            for cmd_type, percentage in components:
                if cmd_type.lower() == 'r':
                    read_percent = percentage
                elif cmd_type.lower() == 'w':
                    write_percent = percentage

            assert read_percent + write_percent == 100, 'read% + write% != 100'
            return self.generate_mixed_workload(read_percent, write_percent)
        else:
            raise SyntaxError

    def __init__(self, param):
        # pattern definition
        SeqW_128K_1GB = BasicPattern(
            cmd_type=eCMDType.Write,
            pattern_type=BasicPatternType.Seq,
            chunk_size_bytes=128 * KiB,
            range_bytes=1 * GiB)
        SeqW_128K_16MB = BasicPattern(
            cmd_type=eCMDType.Write,
            pattern_type=BasicPatternType.Seq,
            chunk_size_bytes=128 * KiB,
            range_bytes=16 * MiB)
        SeqW_128K_64MB = BasicPattern(
            cmd_type=eCMDType.Write,
            pattern_type=BasicPatternType.Seq,
            chunk_size_bytes=128 * KiB,
            range_bytes=64 * MiB)
        SeqW_128K_128MB = BasicPattern(
            cmd_type=eCMDType.Write,
            pattern_type=BasicPatternType.Seq,
            chunk_size_bytes=128 * KiB,
            range_bytes=128 * MiB)
        SeqW_128K_256MB = BasicPattern(
            cmd_type=eCMDType.Write,
            pattern_type=BasicPatternType.Seq,
            chunk_size_bytes=128 * KiB,
            range_bytes=256 * MiB)
        SeqR_128K_1GB = BasicPattern(
            cmd_type=eCMDType.Read,
            pattern_type=BasicPatternType.Seq,
            chunk_size_bytes=128 * KiB,
            range_bytes=1 * GiB)
        SeqR_128K_16MB = BasicPattern(
            cmd_type=eCMDType.Read,
            pattern_type=BasicPatternType.Seq,
            chunk_size_bytes=128 * KiB,
            range_bytes=16 * MiB)
        SeqR_128K_64MB = BasicPattern(
            cmd_type=eCMDType.Read,
            pattern_type=BasicPatternType.Seq,
            chunk_size_bytes=128 * KiB,
            range_bytes=64 * MiB)
        SeqR_128K_128MB = BasicPattern(
            cmd_type=eCMDType.Read,
            pattern_type=BasicPatternType.Seq,
            chunk_size_bytes=128 * KiB,
            range_bytes=128 * MiB)
        SeqR_128K_256MB = BasicPattern(
            cmd_type=eCMDType.Read,
            pattern_type=BasicPatternType.Seq,
            chunk_size_bytes=128 * KiB,
            range_bytes=256 * MiB)
        RanW_4K_1GB = BasicPattern(
            cmd_type=eCMDType.Write,
            pattern_type=BasicPatternType.Ran,
            chunk_size_bytes=4 * KiB,
            range_bytes=1 * GiB)
        RanW_4K_16MB = BasicPattern(
            cmd_type=eCMDType.Write,
            pattern_type=BasicPatternType.Ran,
            chunk_size_bytes=4 * KiB,
            range_bytes=16 * MiB)
        RanW_4K_64MB = BasicPattern(
            cmd_type=eCMDType.Write,
            pattern_type=BasicPatternType.Ran,
            chunk_size_bytes=4 * KiB,
            range_bytes=64 * MiB)
        RanW_4K_128MB = BasicPattern(
            cmd_type=eCMDType.Write,
            pattern_type=BasicPatternType.Ran,
            chunk_size_bytes=4 * KiB,
            range_bytes=128 * MiB)
        RanW_4K_256MB = BasicPattern(
            cmd_type=eCMDType.Write,
            pattern_type=BasicPatternType.Ran,
            chunk_size_bytes=4 * KiB,
            range_bytes=256 * MiB)
        RanR_4K_1GB = BasicPattern(
            cmd_type=eCMDType.Read,
            pattern_type=BasicPatternType.Ran,
            chunk_size_bytes=4 * KiB,
            range_bytes=1 * GiB)
        RanR_4K_16MB = BasicPattern(
            cmd_type=eCMDType.Read,
            pattern_type=BasicPatternType.Ran,
            chunk_size_bytes=4 * KiB,
            range_bytes=16 * MiB)
        RanR_4K_64MB = BasicPattern(
            cmd_type=eCMDType.Read,
            pattern_type=BasicPatternType.Ran,
            chunk_size_bytes=4 * KiB,
            range_bytes=64 * MiB)
        RanR_4K_128MB = BasicPattern(
            cmd_type=eCMDType.Read,
            pattern_type=BasicPatternType.Ran,
            chunk_size_bytes=4 * KiB,
            range_bytes=128 * MiB)
        RanR_4K_256MB = BasicPattern(
            cmd_type=eCMDType.Read,
            pattern_type=BasicPatternType.Ran,
            chunk_size_bytes=4 * KiB,
            range_bytes=256 * MiB)

        # pre-defined workload

        self.performance = (
            BasicWorkload(
                SeqW_128K_1GB, qd=32), BasicWorkload(
                SeqR_128K_1GB, qd=32), BasicWorkload(
                RanW_4K_1GB, qd=512), BasicWorkload(
                    RanR_4K_1GB, qd=512))
        self.performance_ran = (
            BasicWorkload(
                RanW_4K_1GB, qd=512), BasicWorkload(
                RanR_4K_1GB, qd=512))
        self.performance_16MB = (
            BasicWorkload(
                SeqW_128K_16MB, qd=32), BasicWorkload(
                SeqR_128K_16MB, qd=32), BasicWorkload(
                RanW_4K_16MB, qd=512), BasicWorkload(
                    RanR_4K_16MB, qd=512))
        self.performance_64MB = (
            BasicWorkload(
                SeqW_128K_64MB, qd=32), BasicWorkload(
                SeqR_128K_64MB, qd=32), BasicWorkload(
                RanW_4K_64MB, qd=512), BasicWorkload(
                    RanR_4K_64MB, qd=512))
        self.performance_128MB = (
            BasicWorkload(
                SeqW_128K_128MB, qd=32), BasicWorkload(
                SeqR_128K_128MB, qd=32), BasicWorkload(
                RanW_4K_128MB, qd=512), BasicWorkload(
                    RanR_4K_128MB, qd=512))
        self.performance_256MB = (
            BasicWorkload(
                SeqW_128K_256MB, qd=32), BasicWorkload(
                SeqR_128K_256MB, qd=32), BasicWorkload(
                RanW_4K_256MB, qd=512), BasicWorkload(
                    RanR_4K_256MB, qd=512))
