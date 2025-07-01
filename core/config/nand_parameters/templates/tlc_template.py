from core.config.nand_parameters.templates.template import Template


class TLCTemplate(Template):
    def __new__(cls, *args, **kwargs):
        param = super().__new__(cls, *args, **kwargs)
        param['CAPACITY_Gb'] = Template.INVALID
        param['SLC_tR'] = Template.INVALID
        param['SLC_tPROG'] = Template.INVALID
        param['MLC_tR'] = Template.INVALID
        param['MLC_tPROG'] = Template.INVALID
        param['TLC_4K_tR'] = Template.INVALID
        param['TLC_16K_tR'] = Template.INVALID
        param['TLC_tPROG'] = Template.INVALID
        param['tBERS'] = Template.INVALID
        param['tSUS'] = Template.INVALID
        param['WL_COUNT'] = Template.INVALID
        param['SSL_COUNT'] = Template.INVALID
        param['BLOCK_COUNT'] = Template.INVALID
        param['SPARE_BLOCK_COUNT'] = Template.INVALID
        param['PAGE_COUNT'] = Template.INVALID
        param['ECC_PARITY_RATIO'] = Template.INVALID
        param['NAND_IO_Mbps'] = Template.INVALID
        param['tRRC'] = 5
        return param
