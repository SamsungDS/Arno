import math
import os
import re
from collections import deque

import numpy as np
import pandas as pd
from core.config.core_parameter import CoreParameter


class WorkloadInfo:
    def __init__(self, workload_name, df, qd=None):
        self.name = workload_name
        self.df = df
        self.qd = qd


class WorkloadColumn:
    init_time = 'Init Time (ns)'
    io_type = 'IO Type'
    size = 'Size (B)'
    min_offset = 'Min Offset'
    qd = 'QD'


class WorkloadReader:
    def __init__(self, directory_path, param):
        self.workload_list = deque()
        self.meta_map_file = None
        self.workload_max_offset = 0

        file_name_list = sorted([name for name in os.listdir(directory_path) if os.path.isfile(os.path.join(directory_path, name))])

        meta_map_file = [name for name in file_name_list if name.endswith('.map')]
        if meta_map_file:
            assert len(meta_map_file) == 1, 'Only one meta map file is allowed'
            self.meta_map_file = os.path.join(directory_path, meta_map_file[0])

        workload_file_list = [name for name in file_name_list if name.endswith('.csv') or name.endswith('.txt')]
        for file_name in workload_file_list:
            workload_name = file_name.split('.')[0]
            df = pd.read_csv(os.path.join(directory_path, file_name))
            df = df.iloc[:param.WORKLOAD_LINES]
            df = self.data_processing(df)

            num_write = len(df[df["IO Type"] == "Write"])
            num_read = len(df[df["IO Type"] == "Read"])
            num_flush = len(df[df["IO Type"] == "Flush"])
            print(f"num_write\t{num_write}")
            print(f"num_read\t{num_read}")
            print(f"num_flush\t{num_flush}")
            print("-" * 25)
            print(f"num_total\t{num_write + num_read + num_flush}")

            self.workload_max_offset = max(self.workload_max_offset, self.get_workload_max_byte_offset(df))
            try:
                qd = int(re.search('QD([0-9]+)', file_name).group(1))
                info = WorkloadInfo(workload_name, df, qd)
            except AttributeError:
                info = WorkloadInfo(workload_name, df)
            self.workload_list.append(info)

    def calculate_unmapped_lpn_set(self, mapunit_size):
        written_lpn_set = set()
        unmapped_lpn_set = set()
        for info in self.workload_list:
            df = info.df
            read_write_df = df[(df[WorkloadColumn.io_type] == 'Read') | (df[WorkloadColumn.io_type] == 'Write') | (df[WorkloadColumn.io_type] == 'Flush')]
            for cmd_type, size, min_offset in zip(read_write_df[WorkloadColumn.io_type], read_write_df[WorkloadColumn.size], read_write_df[WorkloadColumn.min_offset]):
                start_lpn = math.floor(min_offset / mapunit_size)
                lpn_count = math.ceil(size / mapunit_size)
                if cmd_type == 'Write':
                    written_lpn_set.update([start_lpn + lpn_offset for lpn_offset in range(lpn_count)])
                else:
                    unmapped_lpn_list = [start_lpn + lpn_offset for lpn_offset in range(lpn_count) if start_lpn + lpn_offset not in written_lpn_set]
                    unmapped_lpn_set.update(unmapped_lpn_list)

        return unmapped_lpn_set

    def generate_prevent_unmap_df(self, param):
        unmapped_lpn_set = self.calculate_unmapped_lpn_set(param.MAPUNIT_SIZE)
        df = pd.DataFrame(columns=self.workload_list[0].df.columns)

        df[WorkloadColumn.init_time] = [0 for _ in range(len(unmapped_lpn_set))]
        df[WorkloadColumn.io_type] = ['Write' for _ in range(len(unmapped_lpn_set))]
        df[WorkloadColumn.size] = [param.MAPUNIT_SIZE for _ in range(len(unmapped_lpn_set))]
        df[WorkloadColumn.min_offset] = [lpn * param.MAPUNIT_SIZE for lpn in sorted(unmapped_lpn_set)]
        df[WorkloadColumn.qd] = [32 for _ in range(len(unmapped_lpn_set))]
        return df

    def get_workload_max_byte_offset(self, df):
        is_read = df[WorkloadColumn.io_type] == 'Read'
        is_write = df[WorkloadColumn.io_type] == 'Write'
        read_write_df = df[is_read | is_write]

        return (read_write_df[WorkloadColumn.size] + read_write_df[WorkloadColumn.min_offset]).max()

    def data_processing(self, df):
        src_time = {'(s)': 1e9, '(ms)': 1e6, '(us)': 1e3, '(ps)': 1e-3}

        # df = df.applymap(lambda x: x.replace(',', '') if isinstance(x, str) else x)
        df = df.map(lambda x: x.replace(',', '') if isinstance(x, str) else x)

        if 'QD' in df.columns or 'QD/I - Queue Depth at Init Time' in df.columns:
            qd_column = [column for column in df if 'QD' in column]
            assert (len(qd_column) == 1), f'invalid csv file, {len(qd_column)}'
            df.rename(columns={qd_column[0]: WorkloadColumn.qd}, inplace=True)

        init_time_column = [column for column in df if 'Init Time' in column]
        assert (len(init_time_column) == 1), f'invalid csv file, {len(init_time_column)}'

        init_time_column = init_time_column[0]
        for src_str, src_val in src_time.items():
            if src_str in init_time_column:
                df[init_time_column] = df[init_time_column].astype('float').apply(lambda x: x * src_val)
                df.rename(columns={init_time_column: 'Init Time (ns)'}, inplace=True)
                assert WorkloadColumn.init_time == 'Init Time (ns)', 'workload support ns scale'
                break

        df['Size (B)'] = df['Size (B)'].astype(int)

        if 'Completion Time (us)' in df:
            df['Completion Time (us)'] = df['Completion Time (us)'].astype('int64').apply(lambda x: x * 1e3)
            df['Latency (us)'] = df['Latency (us)'].astype('int64').apply(lambda x: x * 1e3)
            df['Host Delay (us)'] = df['Host Delay (us)'].astype('int64').apply(lambda x: x * 1e3)

            df.rename(columns={'Completion Time (us)': 'Completion Time (ns)'}, inplace=True)
            df.rename(columns={'Latency (us)': 'Latency (ns)'}, inplace=True)
            df.rename(columns={'Host Delay (us)': 'Host Delay (ns)'}, inplace=True)

        if '0x' in str(df[WorkloadColumn.min_offset].iloc[0]):
            df[WorkloadColumn.min_offset] = df[WorkloadColumn.min_offset].map(lambda x: int(x, 16))
        else:
            df[WorkloadColumn.min_offset] = df[WorkloadColumn.min_offset].astype(np.int64)

        return df


class StorageWorkloadReader(WorkloadReader):
    parent_directory_path = os.path.dirname(os.path.abspath(
                                os.path.dirname(os.path.abspath(
                                    os.path.dirname(os.path.abspath(__file__))))))
    directory_path = os.path.join(parent_directory_path, 'workload')

    @classmethod
    def set_directory_path(cls, directory_path):
        cls.directory_path = directory_path

    def __init__(self, workload_directory_name, param):
        super().__init__(os.path.join(StorageWorkloadReader.directory_path, workload_directory_name), param)


class PCMARK10(StorageWorkloadReader):
    def __init__(self, param):
        super().__init__('PCMARK10', param)
