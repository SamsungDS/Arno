from core.config.nand_parameters.templates.tlc_template import TLCTemplate


class TLCExample(TLCTemplate):
    def __init__(self, *args, **kwargs):
        self.set('CAPACITY_Gb', 45.79)
        self.set('SLC_tR', 25)
        self.set('SLC_tPROG', 70)
        self.set('MLC_tR', 25)
        self.set('MLC_tPROG', 70)
        self.set('TLC_4K_tR', 45)
        self.set('TLC_16K_tR', 45)
        self.set('TLC_tPROG', 450)
        self.set('tBERS', 5000)
        self.set('tSUS', 50)
        self.set('WL_COUNT', 10)
        self.set('SSL_COUNT', 6)
        self.set('BLOCK_COUNT', 2048)
        self.set('SPARE_BLOCK_COUNT', 258)
        self.set('PAGE_COUNT', 210)
        self.set('ECC_PARITY_RATIO', 1.125)
        self.set('NAND_IO_Mbps', 2400)
        super().__init__(*args, **kwargs)
