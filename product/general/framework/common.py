from core.framework.common import ProductArgs


class StorageProductArgs(ProductArgs):
    def init_args(self, *args, **kwargs):
        super().init_args(*args, **kwargs)

    def set_args_to_class_instance(self, cls_instance):
        super().set_args_to_class_instance(cls_instance)
        cls_instance.product_args = self
