from core.framework.common import (BufferedUnitType, MemAccessInfo,
                                   QueueDepthChecker, StatusType,
                                   TransactionSourceType, eCMDType,
                                   eResourceType)
from core.modules.parallel_unit import ParallelUnit
from product.general.provided_interface.dcl_pif import DCLPIF


class DCLStats:
    def __init__(self):
        # Host I/O 카운터
        self.host_read_issue_count = 0
        self.host_write_issue_count = 0
        self.host_write_done_count = 0
        self.host_read_done_count = 0
        self.host_read_done_cq_count = 0

        # 캐시 관련
        self.read_cache_hit_count = 0
        self.write_cache_hit_count = 0
        self.cache_miss_count = 0
        self.cache_evict_count = 0

        # 버퍼 및 완료 처리
        self.read_buffer_release_done_count = 0
        self.nand_write_done_count = 0
        self.wait_cache_write_count = 0

        # AML 상호작용
        self.send_aml_count = 0

        # 기타
        self.hazard_count = 0

    def inc_host_read_issue(self):
        self.host_read_issue_count += 1

    def inc_host_write_issue(self):
        self.host_write_issue_count += 1

    def inc_host_write_done(self):
        self.host_write_done_count += 1

    def inc_host_read_done(self):
        self.host_read_done_count += 1

    def inc_host_read_done_cq(self):
        self.host_read_done_cq_count += 1

    def inc_read_cache_hit(self):
        self.read_cache_hit_count += 1

    def inc_write_cache_hit(self):
        self.write_cache_hit_count += 1

    def inc_cache_miss(self):
        self.cache_miss_count += 1

    def inc_cache_evict(self):
        self.cache_evict_count += 1

    def inc_read_buffer_release_done(self):
        self.read_buffer_release_done_count += 1

    def inc_nand_write_done(self):
        self.nand_write_done_count += 1

    def inc_wait_cache_write(self):
        self.wait_cache_write_count += 1

    def inc_send_aml(self):
        self.send_aml_count += 1

    def inc_hazard(self):
        self.hazard_count += 1

    def print_stats(self):
        print("\n=== DCLStats ===")
        for name, value in self.__dict__.items():
            if not name.startswith('_') and not callable(value):
                print(f"DCL: {name}: {value}")


class DataCacheLayer(ParallelUnit):
    def __init__(self, product_args, _address, unit_fifo_num=1):
        super().__init__(product_args, _address, unit_fifo_num)
        assert self.address == self.address_map.DCL

        self.stats = DCLStats()

        self.generate_submodule(
            self.read_handler,
            self.feature.DCL_READ_HANDLING)
        self.generate_submodule(
            self.read_completion_handler,
            self.feature.DCL_READ_COMPLETION_HANDLING)
        self.generate_submodule(
            self.write_handler,
            self.feature.DCL_WRITE_HANDLING)
        self.generate_submodule(
            self.done_handler,
            self.feature.DCL_DONE_HANDLING)
        self.generate_submodule(self.release_buffer, self.feature.ZERO)
        self.generate_submodule(self.check_write_wait_need, self.feature.ZERO)
        self.generate_submodule(self.flush_handler, self.feature.ZERO)

        self.data_cache_use_count = {}
        self.data_cache_list = {}
        self.wait_read_done_packet = {}
        self.flush_lpn_list = {}

        self.flush_done_count = 0
        self.flush_issue_count = 0

        self.wait_lpn = None
        self.active_lpn = []
        self.data_cache_slot_count = self.param.LOGICAL_CACHE_ENTRY_CNT
        self.data_cache_empty_count = self.data_cache_slot_count
        self.receive_write_done_event = self.env.event()
        self.wait_lpn_use_done = self.env.event()

    class CacheInfo:
        def __init__(self, packet, clean):
            self.cache_packet = packet
            self.is_clean = clean

    def check_cache_hit(self, lpn):
        return lpn in self.data_cache_list

    def read_handler(self, packet):
        lpn = packet['nvm_transaction'].lpn
        if self.check_cache_hit(lpn):
            cache_info = self.data_cache_list[lpn].cache_packet['nvm_transaction']
            self.data_cache_use_count[lpn] += 1
            if cache_info.valid_sector_bitmap == packet['nvm_transaction'].valid_sector_bitmap:
                packet['nvm_transaction'].buffer_ptr = cache_info.buffer_ptr
                self.stats.inc_read_cache_hit()
                self.wakeup(self.read_handler, self.done_handler, packet)
            else:
                self.stats.inc_cache_miss()
                packet['nvm_transaction'].valid_sector_bitmap = ~ cache_info.valid_sector_bitmap & packet['nvm_transaction'].valid_sector_bitmap
                self.stats.inc_send_aml()
                self.send_sq(
                    packet,
                    self.address,
                    self.address_map.AML,
                    src_submodule=self.read_handler)
        else:
            self.stats.inc_cache_miss()
            self.stats.inc_send_aml()
            self.send_sq(
                packet,
                self.address,
                self.address_map.AML,
                src_submodule=self.read_handler)

        if lpn == self.wait_lpn:
            self.wait_lpn_use_done.succeed()
            self.wait_lpn_use_done = self.env.event()
            self.wait_lpn = None
        self.active_lpn.remove(lpn)

    def read_completion_handler(self, packet):
        lpn = packet['nvm_transaction'].lpn
        if lpn in self.data_cache_use_count:
            if self.data_cache_use_count[lpn] > 0:
                self.data_cache_use_count[lpn] -= 1
        if lpn in self.data_cache_use_count:
            if self.data_cache_use_count[lpn] == 0 and lpn in self.wait_read_done_packet:
                self.wakeup(
                    self.read_completion_handler,
                    self.done_handler,
                    self.wait_read_done_packet[lpn])
        if 'nvm_transaction_flash' in packet:
            self.wakeup(self.read_completion_handler, self.release_buffer, packet)
            self.stats.inc_read_buffer_release_done()
            self.vcd_manager.set_read_buffer_release_done_count(
                self.stats.read_buffer_release_done_count)
        if packet['remain_dma_count'] == 0:  # 하나의 Command 완료를 위해 수행해야 하는 잔여 MapUnit 수
            packet['nvm_transaction'].transaction_type = eCMDType.ReadDoneCQ
            self.stats.inc_host_read_done_cq()
            self.send_sq(
                packet,
                self.address,
                self.address_map.NVMe,
                src_submodule=self.read_completion_handler)

    def write_handler(self, packet):
        lpn = packet['nvm_transaction'].lpn
        try:
            if self.check_cache_hit(lpn):
                self.handle_write_hit(lpn, packet)
            else:
                yield from self.handle_write_miss(lpn, packet)
        finally:
            # 공통 처리: LPN 블록 해제 및 활성 상태 제거
            if lpn == self.wait_lpn:
                self.wait_lpn_use_done.succeed()
                self.wait_lpn_use_done = self.env.event()
                self.wait_lpn = None
            self.active_lpn.remove(lpn)

    def handle_write_hit(self, lpn, packet):
        # 1. Hazard 플래그 설정
        packet['nvm_transaction'].hazard_flag = True
        self.stats.inc_hazard()

        # 2. 비트맵 병합: 캐시된 비트맵과 현재 패킷 비트맵 통합
        cached_bitmap = self.data_cache_list[lpn].cache_packet['nvm_transaction'].valid_sector_bitmap
        packet['nvm_transaction'].valid_sector_bitmap |= cached_bitmap

        # 3. 캐시 업데이트: 패킷 복사 후 캐시 갱신
        cache_packet = DCLPIF.create_cache_packet(packet)
        self.data_cache_list[lpn].cache_packet = cache_packet
        self.data_cache_list[lpn].is_clean = False

        # 4. 통계 업데이트
        self.stats.inc_write_cache_hit()

        # 5. 이벤트 트리거: done_handler로 패킷 전달
        done_packet = DCLPIF.create_write_done_packet(packet)

        self.wakeup(self.write_handler, self.done_handler, done_packet)
        # 6. 외부 전송: AML로 패킷 전송
        self.send_sq(
            packet,
            self.address,
            self.address_map.AML,
            src_submodule=self.write_handler
        )

    def handle_write_miss(self, lpn, packet):
        # 1. 캐시가 꽉 찼는지 확인 → 꽉 찼다면 기다림
        if len(self.data_cache_list) == self.data_cache_slot_count:
            yield self.receive_write_done_event
            self.stats.inc_wait_cache_write()

        # 2. 캐시 할당: 새 엔트리 생성
        cache_packet = DCLPIF.create_cache_packet(packet)
        cache = self.CacheInfo(packet=cache_packet, clean=False)
        self.data_cache_empty_count -= 1
        self.data_cache_list[lpn] = cache
        self.data_cache_use_count[lpn] = 0

        # 3. 통계 업데이트
        self.stats.inc_send_aml()

        # 4. 이벤트 트리거: done_handler로 패킷 전달
        done_packet = DCLPIF.create_write_done_packet(packet)
        self.wakeup(self.write_handler, self.done_handler, done_packet)
        # 5. 외부 전송: AML로 패킷 전송
        self.send_sq(
            packet,
            self.address,
            self.address_map.AML,
            src_submodule=self.write_handler
        )

    def release_buffer(self, packet):
        buffer_type = eResourceType.WriteBuffer
        buffer_ptr = packet['nvm_transaction'].buffer_ptr
        if packet['nvm_transaction'].transaction_type == eCMDType.ReadDoneSQ or packet['nvm_transaction'].transaction_type == eCMDType.ReadDoneCQ:
            buffer_type = eResourceType.ReadBuffer
            buffer_ptr = packet['nvm_transaction'].buffer_ptr
        self.release_resource(buffer_type, [buffer_ptr])
        description = 'release' + buffer_type.name
        if self.param.GENERATE_DIAGRAM:
            self.analyzer.register_packet_transfer(
                self.address, self.address_map.BA, 0, 0, 0, 0, description)

    def done_handler(self, packet):
        ts_type = packet['nvm_transaction'].transaction_type

        if ts_type == eCMDType.Read:
            self.handle_read_completion(packet)
        elif ts_type == eCMDType.NANDReadDone:
            self.handle_nand_read_done(packet)
        elif ts_type == eCMDType.WriteDone:
            self.handle_write_done(packet)
        elif ts_type == eCMDType.Write:
            self.handle_cache_write_done(packet)
        else:
            pass

    def handle_read_completion(self, packet):
        """Host Read 요청 완료 처리"""
        packet['nvm_transaction'].transaction_type = eCMDType.CacheReadDone
        self.send_sq(
            packet,
            self.address,
            self.address_map.NVMe,
            src_submodule=self.done_handler
        )

    def handle_nand_read_done(self, packet):
        """NAND에서 읽기 완료된 패킷 처리"""
        self.send_sq(
            packet,
            self.address,
            self.address_map.NVMe,
            src_submodule=self.done_handler
        )

    def flush_handler(self, packet):

        self.flush_issue_count += 1
        # print("dcl flush issue : ", self.flush_issue_count)

        if packet['nvm_transaction'].transaction_type == eCMDType.Flush:
            check = True
            self.flush_lpn_list[(packet['slot_id'], packet['cmd_id'])] = {}
            for lpn in self.data_cache_list:
                for list_key in self.flush_lpn_list:
                    if lpn in self.flush_lpn_list[list_key]:
                        if self.flush_lpn_list[list_key][lpn] == self.data_cache_list[lpn].cache_packet['nvm_transaction'].buffer_ptr:
                            check = False
                            break
                if check:
                    self.flush_lpn_list[(packet['slot_id'], packet['cmd_id'])][lpn] = self.data_cache_list[lpn].cache_packet['nvm_transaction'].buffer_ptr
                else:
                    check = True
            if len(self.flush_lpn_list[(packet['slot_id'], packet['cmd_id'])]) == 0:
                del self.flush_lpn_list[(packet['slot_id'], packet['cmd_id'])]
                packet['nvm_transaction'].transaction_type = eCMDType.FlushDone
                self.send_sq(
                    packet,
                    self.address,
                    self.address_map.NVMe,
                    src_submodule=self.flush_handler)
            else:
                self.send_sq(
                    packet,
                    self.address,
                    self.address_map.AML,
                    src_submodule=self.flush_handler)
        elif packet['nvm_transaction'].transaction_type == eCMDType.FlushDone:
            self.send_sq(
                packet,
                self.address,
                self.address_map.NVMe,
                src_submodule=self.flush_handler)
        else:
            assert False

    def handle_write_done(self, packet):
        """Write 작업 완료 처리 (NAND Write Done)"""
        self.stats.inc_nand_write_done()
        assert packet['nvm_transaction'].transaction_source_type == TransactionSourceType.UserIO

        lpn = packet['nvm_transaction'].lpn
        if len(self.flush_lpn_list) != 0:
            for list_key in self.flush_lpn_list.copy():
                if lpn in self.flush_lpn_list[list_key]:
                    buffer_ptr = packet['nvm_transaction'].buffer_ptr
                    if self.flush_lpn_list[list_key][lpn] == buffer_ptr:
                        del self.flush_lpn_list[list_key][lpn]
                        if len(self.flush_lpn_list[list_key]) == 0:
                            del self.flush_lpn_list[list_key]

                            packet['slot_id'] = list_key[0]
                            packet['cmd_id'] = list_key[1]
                            packet['nvm_transaction'].transaction_type = eCMDType.FlushDone
                            packet['cmd_type'] = eCMDType.Flush
                            self.flush_done_count += 1

                            self.send_sq(
                                packet,
                                self.address,
                                self.address_map.NVMe,
                                src_submodule=self.done_handler)

        if lpn in self.data_cache_list:
            cached_buffer_ptr = self.data_cache_list[lpn].cache_packet['nvm_transaction'].buffer_ptr
            if packet['nvm_transaction'].buffer_ptr == cached_buffer_ptr:
                if self.data_cache_use_count[lpn] != 0:
                    # 아직 사용 중인 경우, 완료 패킷 보류
                    self.wait_read_done_packet[lpn] = packet
                else:
                    del self.data_cache_list[lpn]
                    del self.data_cache_use_count[lpn]
                    # 블로킹 중인 Write 요청 해제
                    self.receive_write_done_event.succeed()
                    self.receive_write_done_event = self.env.event()
                    self.wakeup(self.done_handler, self.release_buffer, packet)
            else:
                # 버퍼 포인터가 다른 경우 → 기존 캐시와 무관
                self.wakeup(self.done_handler, self.release_buffer, packet)
        else:
            # 캐시 미스 상태
            self.wakeup(self.done_handler, self.release_buffer, packet)

    def handle_cache_write_done(self, packet):
        """캐시 Write 요청 완료 처리"""
        packet['nvm_transaction'].transaction_type = eCMDType.CacheWriteDone
        self.stats.inc_host_write_done()
        self.send_sq(
            packet,
            self.address,
            self.address_map.NVMe,
            src_submodule=self.done_handler
        )

    def check_write_wait_need(self, packet):
        lpn = packet['nvm_transaction'].lpn
        if lpn in self.active_lpn:
            self.wait_lpn = lpn
            yield self.wait_lpn_use_done
        self.active_lpn.append(lpn)
        if packet['nvm_transaction'].transaction_type == eCMDType.Write:
            self.wakeup(self.check_write_wait_need, self.write_handler, packet)
        elif packet['nvm_transaction'].transaction_type == eCMDType.Read:
            self.wakeup(self.check_write_wait_need, self.read_handler, packet)

    def handle_request(self, packet, fifo_id):
        assert packet['nvm_transaction'].transaction_source_type == TransactionSourceType.UserIO
        if packet['src'] == self.address_map.NVMe:
            if packet['nvm_transaction'].transaction_type == eCMDType.Read:
                self.stats.inc_host_read_issue()
                self.wakeup(
                    self.address,
                    self.check_write_wait_need,
                    packet,
                    src_id=fifo_id)
            elif packet['nvm_transaction'].transaction_type == eCMDType.Write:
                self.stats.inc_host_write_issue()
                self.wakeup(
                    self.address,
                    self.check_write_wait_need,
                    packet,
                    src_id=fifo_id)
            elif packet['nvm_transaction'].transaction_type == eCMDType.ReadDoneSQ:
                self.stats.inc_host_read_done()
                self.wakeup(
                    self.address,
                    self.read_completion_handler,
                    packet,
                    src_id=fifo_id)
            elif packet['nvm_transaction'].transaction_type == eCMDType.Flush:
                self.wakeup(
                    self.address,
                    self.flush_handler,
                    packet,
                    src_id=fifo_id)

        elif packet['src'] == self.address_map.AML:
            if packet['nvm_transaction'].transaction_type == eCMDType.FlushDone:
                self.wakeup(
                    self.address,
                    self.flush_handler,
                    packet,
                    src_id=fifo_id)
            else:
                self.wakeup(
                    self.address,
                    self.done_handler,
                    packet,
                    src_id=fifo_id)

    def print_debug(self):
        self.stats.print_stats()
