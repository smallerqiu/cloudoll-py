
import time
import threading


"""
雪花算法（全局唯一id）

# 最早是Twitter公司在其内部用于分布式环境下生成唯一ID

# Twitter's Snowflake algorithm implementation which is used to generate distributed IDs.

# https://github.com/twitter-archive/snowflake/blob/snowflake-2010/src/main/scala/com/twitter/service/snowflake/IdWorker.scala
"""


class IdWorker:
    def __init__(self, worker_id, datacenter_id, sequence=0):
         # 位移值
        self.worker_id_bits = 5
        self.datacenter_id_bits = 5
        self.sequence_bits = 12
        
        self.max_worker_id = -1 ^ (-1 << self.worker_id_bits)
        self.max_datacenter_id = -1 ^ (-1 << self.datacenter_id_bits)

        # 参数校验
        if worker_id > self.max_worker_id or worker_id < 0:
            raise ValueError(f'worker_id must be between 0 and {self.max_worker_id}')
        if datacenter_id > self.max_datacenter_id or datacenter_id < 0:
            raise ValueError(f'datacenter_id must be between 0 and {self.max_datacenter_id}')

        self.worker_id = worker_id
        self.datacenter_id = datacenter_id
        self.sequence = sequence
        self.lock = threading.Lock()

        # Twitter Epoch (2010-11-04 01:42:54 UTC)
        self.twepoch = 1288834974657

       

       
        self.worker_id_shift = self.sequence_bits
        self.datacenter_id_shift = self.sequence_bits + self.worker_id_bits
        self.timestamp_left_shift = self.sequence_bits + self.worker_id_bits + self.datacenter_id_bits
        self.sequence_mask = -1 ^ (-1 << self.sequence_bits)

        self.last_timestamp = -1

    def _time_gen(self):
        return int(time.time() * 1000)

    def _til_next_millis(self, last_timestamp):
        timestamp = self._time_gen()
        while timestamp <= last_timestamp:
            timestamp = self._time_gen()
        return timestamp

    def next_id(self):
        with self.lock:
            timestamp = self._time_gen()

            if timestamp < self.last_timestamp:
                raise Exception(f'Clock moved backwards. Refusing to generate id for {self.last_timestamp - timestamp} milliseconds')

            if self.last_timestamp == timestamp:
                self.sequence = (self.sequence + 1) & self.sequence_mask
                if self.sequence == 0:
                    timestamp = self._til_next_millis(self.last_timestamp)
            else:
                self.sequence = 0

            self.last_timestamp = timestamp

            id = ((timestamp - self.twepoch) << self.timestamp_left_shift) | \
                (self.datacenter_id << self.datacenter_id_shift) | \
                (self.worker_id << self.worker_id_shift) | \
                self.sequence

            return id


# eg:
# worker = IdWorker(worker_id=1, datacenter_id=1)
# print(worker.next_id())
