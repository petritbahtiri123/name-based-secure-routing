"""Parent-owned, pagefile-backed Windows benchmark timeline. Never control state."""
import ctypes
import mmap
import struct
import uuid

MAGIC = 0x4E425352544C3031
GUARD = 0x719F250ADB608EC3
EVENTS = ('requested','task_started','connect_first_poll','connected',
          'control_hello_complete','admission_started','route_accepted','admitted',
          'failed','timed_out','cancelled','cleaned')


class Timeline:
    def __init__(self, count, role):
        if not 1 <= count <= 1024 or role not in (1,2):
            raise ValueError('bounded timeline count/role')
        self.count, self.role = count, role
        self.size = 64+256*count
        self.name = 'Local\\NBSR-timeline-'+uuid.uuid4().hex
        frequency = ctypes.c_longlong()
        if not ctypes.windll.kernel32.QueryPerformanceFrequency(ctypes.byref(frequency)):
            raise OSError('QPC frequency unavailable')
        self.frequency = frequency.value
        self.mapping = mmap.mmap(-1,self.size,tagname=self.name)
        self.closed = False
        self.mapping[:] = bytes(self.size)
        self.mapping[:64] = struct.pack('<8Q',MAGIC,1,count,role,self.frequency,0,0,GUARD)
        for slot in range(count):
            struct.pack_into('<Q',self.mapping,64+slot*256+31*8,GUARD)

    def snapshot(self):
        data = self.mapping[:]
        header = struct.unpack_from('<8Q',data)
        if header[:5] != (MAGIC,1,self.count,self.role,self.frequency) or any(header[5:7]) or header[7] != GUARD:
            raise ValueError('corrupt timeline header')
        records=[]
        for slot in range(self.count):
            words=struct.unpack_from('<32Q',data,64+256*slot)
            events=words[:12]
            if words[12] or words[13] != 1 or words[17] or words[19] or words[20] != 1 or words[31] != GUARD or any(words[21:31]):
                raise ValueError(f'incomplete/corrupt timeline slot {slot}')
            seen=[v for v in events if v]
            failures=sum(bool(v) for v in events[8:11])
            if not events[0] or not events[11] or failures > 1 or not (events[7] or failures) or seen != sorted(seen):
                raise ValueError(f'invalid event order slot {slot}')
            for index in range(2,8):
                if events[index] and not events[index-1]:
                    raise ValueError(f'missing predecessor slot {slot}')
            records.append(dict(slot=slot,events=dict(zip(EVENTS,(v or None for v in events))),
                                poll_count=words[14],max_poll_qpc=words[15],last_poll_qpc=words[16],
                                total_poll_qpc=words[18],error_code=words[19]))
        return dict(schema='nbsr-handshake-timeline-v1',role=self.role,qpc_frequency=self.frequency,
                    cross_process_matches=[],correlation='unmatched',records=records)

    def close(self):
        if not self.closed:
            self.mapping.close()
            self.closed=True

    def __enter__(self):
        return self

    def __exit__(self,*args):
        self.close()
