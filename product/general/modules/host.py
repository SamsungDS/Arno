from core.framework.common import CMD_PATH_FIFO_ID
from core.modules.host import Host


class StorageHost(Host):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def sender(self, cmd):
        self.cmd_outstanding_count += 1
        self.send_sq(
            cmd,
            self.address,
            self.address_map.PCIe,
            dst_fifo_id=CMD_PATH_FIFO_ID.eDown.value,
            description=cmd['cmd_type'].name)
