from core.framework.cell_type import Cell
from core.framework.common import ProductArgs
from core.framework.media_common import NANDCMDType


class NANDIOEfficiencyTable:
    def __init__(self, product_args: ProductArgs):
        product_args.set_args_to_class_instance(self)
        self.NAND_IO_LIST = [
            nand_io for nand_io in range(
                1600, 3601, 400)]  # 1600 ~ 3600
        self.CMD_TYPE_LIST = ['RR', 'SR', 'SLC_SW', 'TLC_SW']
        self.CONDITION_LIST = ['W_tFW', 'W/O_tFW']

        self.tNSC = self.param.tNSC
        self.tR_cmd = self.param.tR_cmd
        self.dout_cmd = self.param.tDout_cmd

        self.confirm_cmd = self.param.confirm_cmd
        self.latch_dump_up_cmd = self.param.latch_dump_up_cmd
        self.latch_dump_down_cmd = self.param.latch_dump_down_cmd
        self.din_cmd = self.param.tDin_cmd
        self.suspend_cmd = self.param.tSus_cmd

        parity_ratio = self.param.ECC_PARITY_RATIO
        assert parity_ratio >= 1, 'wrong ecc parity ratio'

        MIN_SIZE = 4096
        assert MIN_SIZE == 4096, 'do not support MIN SIZE smaller than 4096, larger then 4096'
        full_data_size = MIN_SIZE * parity_ratio
        data_toggle = MIN_SIZE * 1e3 / self.param.NAND_IO_Mbps
        parity_toggle = (full_data_size - MIN_SIZE) * \
            1e3 / self.param.NAND_IO_Mbps

        PAGE_PER_4K = self.param.PAGE_SIZE // MIN_SIZE

        self.tDout = {NANDCMDType.Dout_4K +
                      idx: int(data_toggle * (idx + 1)) for idx in range(PAGE_PER_4K)}
        self.tDin = {
            NANDCMDType.Din_LSB +
            page: int(
                data_toggle *
                PAGE_PER_4K) for page in range(
                Cell.TLC.value)}

        self.tDout_parity = {NANDCMDType.Dout_4K +
                             idx: int(parity_toggle *
                                      (idx +
                                       1)) for idx in range(PAGE_PER_4K)}
        self.tDin_parity = {
            NANDCMDType.Din_LSB +
            page: int(
                parity_toggle *
                PAGE_PER_4K) for page in range(
                Cell.TLC.value)}

        self.TABLE = \
            {
                'W_tFW':
                    {
                        'RR':
                            {
                                1600: 0.8,  # Calculated From self.tDout
                                2000: 0.8,
                                2400: 0.8,
                                2800: 0.8,
                                3200: 0.8,
                                3600: 0.8
                            },
                        'SR':
                            {
                                1600: 0.8,  # Calculated From self.tDout
                                2000: 0.8,
                                2400: 0.8,
                                2800: 0.8,
                                3200: 0.8,
                                3600: 0.8
                            },
                        'SLC_SW':
                            {
                                1600: 0.8,
                                2000: 0.8,
                                2400: 0.8,
                                2800: 0.8,
                                3200: 0.8,
                                3600: 0.8
                            },
                        'TLC_SW':
                            {
                                1600: 0.8,
                                2000: 0.8,
                                2400: 0.8,
                                2800: 0.8,
                                3200: 0.8,
                                3600: 0.8
                            }
                    },
                'W/O_tFW':
                    {
                        'RR':
                            {
                                1600: 0.8,
                                2000: 0.8,
                                2400: 0.8,
                                2800: 0.8,
                                3200: 0.8,
                                3600: 0.8
                            },
                        'SR':
                            {
                                1600: 0.8,
                                2000: 0.8,
                                2400: 0.8,
                                2800: 0.8,
                                3200: 0.8,
                                3600: 0.8
                            },
                        'SLC_SW':
                            {
                                1600: 0.8,
                                2000: 0.8,
                                2400: 0.8,
                                2800: 0.8,
                                3200: 0.8,
                                3600: 0.8
                            },
                        'TLC_SW':
                            {
                                1600: 0.8,
                                2000: 0.8,
                                2400: 0.8,
                                2800: 0.8,
                                3200: 0.8,
                                3600: 0.8
                            }
                    }
            }
