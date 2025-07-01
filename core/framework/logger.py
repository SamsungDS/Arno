import logging


class Logger:
    def __init__(self, env, *, name: str = None, log_flag: bool = False):
        self.env = env
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG if log_flag else logging.WARNING)
        formatter = logging.Formatter('{name}: {message}', style='{')
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        self.logger.addHandler(stream_handler)

    def debug(self, msg: str):
        return self.logger.debug(f'[{self.env.now} ns] {msg}')
