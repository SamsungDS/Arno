
class ExpectedFinalResultAnalyzer:
    def __init__(self):
        self.hanging_job_info = {}

    def set_expected_final_result(self, name, target, expected_output=None):
        assert name not in self.hanging_job_info
        self.hanging_job_info[name] = {
            'info': target, 'expected_output': expected_output}

    def print_hanging_job_info(self):
        for name, info in self.hanging_job_info.items():
            expected_output = info['expected_output']
            cur_info = info['info']

            if expected_output is not None:
                if hasattr(
                        cur_info,
                        '__len__') and not hasattr(
                        expected_output,
                        '__len__'):
                    if info['expected_output'] != len(info['info']):
                        print(
                            f'{name}, expected {expected_output} but {len(cur_info)}')
                else:
                    if info['expected_output'] != info['info']:
                        print(
                            f'{name}, expected {expected_output} but {cur_info}')
            else:
                print(f'{name}, {cur_info}')
