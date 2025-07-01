from core.backbone.address_map import AddressMap


class CorePIF:
    def ReadDoneSQ(self, packet, address):
        return packet

    def HMBAccessSQ(self, packet, address):
        return packet


class ProductPIFfactory:
    def __init__(self, param):
        self.address_map = AddressMap()

        from product import general
        self.host_top_pif = general.provided_interface.nvme_pif
        self.dcl_pif = general.provided_interface.dcl_pif
        self.host_top_address = self.address_map.NVMe

    def ReadDoneSQ(self, packet, address):
        return self.host_top_pif.ReadDoneSQ(
            packet, address), self.host_top_address

    def HMBAccessSQ(self, packet, address):
        return self.host_top_pif.HMBAccessSQ(
            packet, address), self.host_top_address
