class Template(dict):
    INVALID = -9999

    def __init__(self, *args, **kwargs):
        super().__init__()
        for key, value in kwargs.items():
            self.set(key, value)

        self.validity_check()

    def set(self, key, value):
        assert key in self, f'nand parameter template violation! {key} not in template.'
        self[key] = value

    def validity_check(self):
        not_set_key_list = list()

        for key, value in self.items():
            if value == Template.INVALID:
                not_set_key_list.append(key)

        if not_set_key_list:
            print(
                f'Error while initiating {self.__class__.__name__} nand parameter.')
            for key in not_set_key_list:
                print(f'{key}', end=',')
            print(' not set')
            assert 0
