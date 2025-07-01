import time
from datetime import datetime, timedelta

try:
    from tqdm import tqdm
    library_imported = True
except ModuleNotFoundError:
    library_imported = False


if library_imported:
    class ProgressPrinter:
        def __init__(self, param, _end_idx, _end_size, _print_period=1):
            self.param = param
            self.is_tqdm_printer = True
            self.end_idx = _end_idx
            self.progress_bar = None
            self.sim_start_time = -1

        def print_sim_progress(self):
            if self.sim_start_time == -1:
                self.sim_start_time = datetime.now()

            if not self.param.PRINT_PROGRESS:
                return

            if self.progress_bar is None:
                self.progress_bar = tqdm(total=self.end_idx, desc="Processing")

            self.progress_bar.update(1)

        def get_elapsed_time_format_line(self):
            self.elapsed_time = datetime.now() - self.sim_start_time
            return self.get_time_format_line(self.elapsed_time)

        def get_time_format_line(self, time):
            time_format_line = f'{time.days} days {str(timedelta(seconds=time.seconds)).zfill(8)}'
            return time_format_line

        def close(self):
            if self.progress_bar is not None:
                self.progress_bar.close()


else:
    class ProgressPrinter:
        def __init__(self, param, _end_idx, _end_size, _print_period=1):
            self.is_tqdm_printer = False
            self.param = param
            self.end_idx = _end_idx
            self.end_idx_digit = len(str(_end_idx))
            self.end_size = _end_size
            self.print_period = _print_period
            assert self.print_period >= 1

            self.sim_start_time = 0
            self.elapsed_time = 0

        def get_elapsed_time_format_line(self):
            self.elapsed_time = datetime.now() - self.sim_start_time
            return self.get_time_format_line(self.elapsed_time)

        def get_time_format_line(self, time):
            time_format_line = f'{time.days} days {str(timedelta(seconds = time.seconds)).zfill(8)}'
            return time_format_line

        def print_sim_progress(self, done_count, done_size):
            if done_count == 1:
                self.sim_start_time = datetime.now()
                self.elapsed_time = datetime.now() - self.sim_start_time

            if not self.param.PRINT_PROGRESS:
                return

            if done_count % self.print_period == 0 or done_count == self.end_idx:
                if self.end_size == 1:
                    expected_left_second = (self.elapsed_time.total_seconds(
                    ) / done_count) * (self.end_idx - done_count)
                else:
                    if done_size == 0:
                        done_size = 1
                    expected_left_second = (self.elapsed_time.total_seconds(
                    ) / done_size) * (self.end_size - done_size)
                expected_left_time = timedelta(seconds=expected_left_second)

                expected_time_line = self.get_time_format_line(
                    expected_left_time)
                print(
                    f"CMD Done / Total ({done_count:>{self.end_idx_digit}} / {self.end_idx:{self.end_idx_digit}}), Elapsed: {self.get_elapsed_time_format_line()}, Left: {expected_time_line}{' '*10}",
                    end='\r',
                    flush=True)

            if done_count == self.end_idx:
                print()

        def close(self):
            pass
