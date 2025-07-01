class Singleton(type):
    instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls.instances:
            cls.instances[cls] = super().__call__(*args, **kwargs)
        return cls.instances[cls]

    @classmethod
    def clear(mcs):
        mcs.instances.clear()


class SingletonByKey(type):
    instances = {}

    def __call__(cls, *args, **kwargs):
        key = (args, tuple(kwargs.items()))
        if key not in cls.instances:
            cls.instances[key] = super().__call__(*args, **kwargs)
        return cls.instances[key]

    @classmethod
    def clear(cls):
        cls.instances = {}
