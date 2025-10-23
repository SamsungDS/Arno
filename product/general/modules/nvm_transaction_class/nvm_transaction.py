class NVMTransaction:
    def __init__(
            self,
            stream_id,
            transaction_source_type,
            transaction_type,
            lpn,
            valid_sector_bitmap,
            buffer_ptr=None):
        self.stream_id = stream_id
        self.transaction_type = transaction_type
        self.transaction_source_type = transaction_source_type
        self.lpn = lpn
        self.valid_sector_bitmap = valid_sector_bitmap
        self.buffer_ptr = buffer_ptr
        self.hazard_flag = False

    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        return setattr(self, key, value)

    def __delitem__(self, key):
        return delattr(self, key)

    def __contains__(self, key):
        return hasattr(self, key)

    def __repr__(self):
        return f"{self.__dict__}"


class NvmTransactionFlash(NVMTransaction):

    def __init__(self, address, base_transaction=None, **kwargs):

        # 기본값 준비
        init_data = {
            'stream_id': -1,
            'transaction_source_type': 'unknown',
            'transaction_type': 'unknown',
            'lpn': -1,
            'valid_sector_bitmap': -1,
            'buffer_ptr': None
        }

        # 1. base_transaction이 있으면 그 값을 기본으로 사용
        if base_transaction is not None:
            if not isinstance(base_transaction, NVMTransaction):
                raise TypeError("base_transaction must be an instance of NVMTransaction")
            init_data.update({
                'stream_id': base_transaction.stream_id,
                'transaction_source_type': base_transaction.transaction_source_type,
                'transaction_type': base_transaction.transaction_type,
                'lpn': base_transaction.lpn,
                'valid_sector_bitmap': base_transaction.valid_sector_bitmap,
                'buffer_ptr': base_transaction.buffer_ptr
            })

        # 2. 명시적으로 전달된 kwargs로 오버라이드
        for key in init_data.keys():
            if key in kwargs:
                init_data[key] = kwargs[key]

        # 3. 부모 클래스 초기화
        super().__init__(
            stream_id=init_data['stream_id'],
            transaction_source_type=init_data['transaction_source_type'],
            transaction_type=init_data['transaction_type'],
            lpn=init_data['lpn'],
            valid_sector_bitmap=init_data['valid_sector_bitmap'],
            buffer_ptr=init_data['buffer_ptr']
        )

        self.address = address
        self.ppn = 0
        self.unmap_check = False
        self.old_ppn = None

    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        return setattr(self, key, value)

    def __delitem__(self, key):
        return delattr(self, key)

    def __contains__(self, key):
        return hasattr(self, key)

    def __repr__(self):
        return f"{self.__dict__}"


class AddressID:
    def __init__(self):
        self.channel = 0
        self.way = 0
        self.plane = 0
        self.block = 0
        self.page = 0
        self.lpo = 0

    def copy_from(self, other):
        """
        다른 객체의 주소 필드 값을 복사합니다.
        같은 필드 구조를 가진 객체라면, 동일한 클래스 타입이 아니어도 복사 가능합니다.
        """
        # AddressID에서 기대하는 속성 목록
        attrs = ['channel', 'way', 'plane', 'block', 'page', 'lpo']

        # other 객체가 필요한 모든 속성을 가지고 있는지 확인
        for attr in attrs:
            if not hasattr(other, attr):
                raise AttributeError(f"복사할 객체에 '{attr}' 속성이 없습니다.")

        # 모든 속성 복사
        for attr in attrs:
            setattr(self, attr, getattr(other, attr))

    def __repr__(self):
        return (f"AddressID(channel={self.channel}, way={self.way}, plane={self.plane}, "
                f"block={self.block}, page={self.page}, lpo={self.lpo})")
