from core.framework.media_common import is_data_cmd


class ChannelArbiter:
    def __init__(self, channel_count):
        self.occupied_buffered_unit_id = [None for _ in range(channel_count)]

    def ask_available(self, ch, buffered_unit_id):
        return self.occupied_buffered_unit_id[ch] is None or self.occupied_buffered_unit_id[ch] == buffered_unit_id

    def update(self, data):
        if is_data_cmd(data['nand_cmd_type']):
            ch, buffered_unit_id = data['channel'], data['buffered_unit_id']
            if data['dlast']:
                self.occupied_buffered_unit_id[ch] = None
            else:
                self.occupied_buffered_unit_id[ch] = buffered_unit_id
