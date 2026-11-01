"""헤드리스 libretro 프런트엔드(ctypes). SFC 코어(bsnes·snes9x)를 입력·WRAM·화면·소리·상태 저장으로 다룬다.

dq4compatcheck.py 가 쓴다. 코어 파일은 저장소에 두지 않는다(LIBRETRO_BSNES·LIBRETRO_SNES9X).

- bsnes 는 WRAM 을 retro_get_memory_data 로 내주지 않는다. 직렬화 상태의 WRAM_OFFSET 에서 읽고(프레임마다 한 번),
  쓰기는 상태를 고쳐 다시 불러온다. 직렬화가 코어 스레드를 맞추므로 타이밍이 조금 바뀔 수 있다.
- cheat(PAR 코드 AAAAAADD)는 롬·WRAM 쓰기에 쓴다. bsnes 는 cheat 를 풀 때 켜기 전 값을 되돌려 그 사이 게임이 쓴
  값을 덮으므로, 한 번만 쓰는 WRAM 값에는 cheat 대신 poke 를 쓴다.
"""
import ctypes as C
import wave
import numpy as np
from PIL import Image

# bsnes 115 직렬화 상태에서 WRAM 128KB 가 시작하는 자리(snes9x WRAM 과 견줘 찾음)
WRAM_OFFSET = 8836
BTN = {'b': 0, 'y': 1, 'select': 2, 'start': 3, 'up': 4, 'down': 5, 'left': 6, 'right': 7,
       'a': 8, 'x': 9, 'l': 10, 'r': 11}


class GameInfo(C.Structure):
    _fields_ = [('path', C.c_char_p), ('data', C.c_void_p), ('size', C.c_size_t), ('meta', C.c_char_p)]


class Geometry(C.Structure):
    _fields_ = [('base_width', C.c_uint), ('base_height', C.c_uint), ('max_width', C.c_uint),
                ('max_height', C.c_uint), ('aspect_ratio', C.c_float)]


class Timing(C.Structure):
    _fields_ = [('fps', C.c_double), ('sample_rate', C.c_double)]


class AVInfo(C.Structure):
    _fields_ = [('geometry', Geometry), ('timing', Timing)]


class SysInfo(C.Structure):
    _fields_ = [('library_name', C.c_char_p), ('library_version', C.c_char_p), ('valid_extensions', C.c_char_p),
                ('need_fullpath', C.c_bool), ('block_extract', C.c_bool)]


class MemDesc(C.Structure):
    _fields_ = [('flags', C.c_uint64), ('ptr', C.c_void_p), ('offset', C.c_size_t), ('start', C.c_size_t),
                ('select', C.c_size_t), ('disconnect', C.c_size_t), ('len', C.c_size_t), ('addrspace', C.c_char_p)]


class MemMap(C.Structure):
    _fields_ = [('descriptors', C.POINTER(MemDesc)), ('num', C.c_uint)]


class Variable(C.Structure):
    _fields_ = [('key', C.c_char_p), ('value', C.c_char_p)]


ENV = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VIDEO = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AUDIO1 = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
AUDIOB = C.CFUNCTYPE(C.c_size_t, C.POINTER(C.c_int16), C.c_size_t)
POLL = C.CFUNCTYPE(None)
STATE = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)


class Core:
    def __init__(self, dylib, rom, sysdir, options=None):
        self.lib = C.CDLL(dylib)
        self.options = {k.encode(): v.encode() for k, v in (options or {}).items()}
        self._keep = []
        self.pixfmt = 0
        self.frame = None
        self.wram_ptr = None
        self.buttons = set()
        self.audio = []
        self.sysdir = C.c_char_p(sysdir.encode())
        self._cbs = (ENV(self._env), VIDEO(self._video), AUDIO1(self._a1), AUDIOB(self._ab), POLL(lambda: None),
                     STATE(self._state))
        L = self.lib
        L.retro_set_environment(self._cbs[0])
        L.retro_set_video_refresh(self._cbs[1])
        L.retro_set_audio_sample(self._cbs[2])
        L.retro_set_audio_sample_batch(self._cbs[3])
        L.retro_set_input_poll(self._cbs[4])
        L.retro_set_input_state(self._cbs[5])
        L.retro_init()
        si = SysInfo()
        L.retro_get_system_info(C.byref(si))
        self.name = f'{si.library_name.decode()} {si.library_version.decode()}'
        data = open(rom, 'rb').read()
        self._rom = C.create_string_buffer(data, len(data))
        gi = GameInfo(rom.encode(), C.cast(self._rom, C.c_void_p), len(data), None)
        L.retro_load_game.restype = C.c_bool
        if not L.retro_load_game(C.byref(gi)):
            raise RuntimeError(f'{dylib}: 롬을 불러오지 못함')
        av = AVInfo()
        L.retro_get_system_av_info(C.byref(av))
        self.rate = av.timing.sample_rate
        L.retro_set_controller_port_device(0, 1)
        L.retro_get_memory_data.restype = C.c_void_p
        L.retro_get_memory_size.restype = C.c_size_t
        L.retro_serialize_size.restype = C.c_size_t
        L.retro_serialize.restype = C.c_bool
        L.retro_unserialize.restype = C.c_bool
        self.n = 0

    def _env(self, cmd, data):
        cmd &= 0xFFFF
        if cmd == 10:
            self.pixfmt = C.cast(data, C.POINTER(C.c_int)).contents.value
            return True
        if cmd in (9, 31):
            C.cast(data, C.POINTER(C.c_char_p))[0] = self.sysdir.value
            return True
        if cmd == 3:
            C.cast(data, C.POINTER(C.c_bool))[0] = True
            return True
        if cmd == 15:
            v = C.cast(data, C.POINTER(Variable)).contents
            if v.key in self.options:
                buf = C.c_char_p(self.options[v.key])
                self._keep.append(buf)
                v.value = buf.value
                return True
            return False
        if cmd == 36:
            mm = C.cast(data, C.POINTER(MemMap)).contents
            for i in range(mm.num):
                d = mm.descriptors[i]
                if d.start == 0x7E0000 and d.ptr:
                    self.wram_ptr = (d.ptr + d.offset, max(d.len, 0x20000))
            return True
        if cmd == 17:
            C.cast(data, C.POINTER(C.c_bool))[0] = False
            return True
        return False

    def _video(self, data, w, h, pitch):
        if not data:
            return
        if self.pixfmt == 1:
            a = np.frombuffer(C.string_at(data, pitch * h), np.uint32).reshape(h, pitch // 4)[:, :w]
            rgb = np.stack([(a >> 16) & 255, (a >> 8) & 255, a & 255], -1).astype(np.uint8)
        else:
            a = np.frombuffer(C.string_at(data, pitch * h), np.uint16).reshape(h, pitch // 2)[:, :w]
            if self.pixfmt == 2:
                r, g, b = (a >> 11) & 31, (a >> 5) & 63, a & 31
                rgb = np.stack([r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2], -1).astype(np.uint8)
            else:
                r, g, b = (a >> 10) & 31, (a >> 5) & 31, a & 31
                rgb = np.stack([r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2], -1).astype(np.uint8)
        if w >= 512:
            rgb = rgb[:, ::2]
        if h >= 448:
            rgb = rgb[::2]
        self.frame = rgb

    def _a1(self, l, r):
        self.audio.append(np.array([l, r], np.int16))

    def _ab(self, data, frames):
        self.audio.append(np.ctypeslib.as_array(data, (frames * 2,)).copy())
        return frames

    def _state(self, port, device, index, id_):
        if port != 0 or device != 1:
            return 0
        return 1 if any(BTN[b] == id_ for b in self.buttons) else 0

    def run(self, buttons=()):
        self.buttons = set(buttons)
        self.lib.retro_run()
        self.n += 1

    def wram(self):
        p = self.lib.retro_get_memory_data(2)
        size = self.lib.retro_get_memory_size(2)
        if not size and self.wram_ptr:
            p, size = self.wram_ptr
        if not size:
            if not getattr(self, '_wc', None) or self._wc[0] != self.n:
                st = self.save()[0]
                self._wc = (self.n, (C.c_ubyte * 0x20000).from_buffer_copy(st[WRAM_OFFSET:WRAM_OFFSET + 0x20000]))
            return self._wc[1]
        return (C.c_ubyte * size).from_address(p)

    def rd(self, addr, n=1):
        m = self.wram()
        a = addr & 0x1FFFF
        v = 0
        for k in range(n - 1, -1, -1):
            v = v * 256 + m[a + k]
        return v

    def poke(self, pairs):
        """[(WRAM 주소, 바이트)] 를 한 번 쓴다."""
        if self.lib.retro_get_memory_size(2) or self.wram_ptr:
            m = self.wram()
            for a, v in pairs:
                m[a & 0x1FFFF] = v
            return
        raw, n = self.save()
        buf = bytearray(raw)
        for a, v in pairs:
            buf[WRAM_OFFSET + (a & 0x1FFFF)] = v
        self.load((bytes(buf), n))
        self._wc = None

    def set_cheats(self, codes):
        """켜 둘 PAR 코드 전부. 앞서 켠 것은 모두 끈다."""
        self.lib.retro_cheat_reset()
        for i, code in enumerate(codes):
            self.lib.retro_cheat_set(i, True, code.encode())

    def shot(self, path):
        Image.fromarray(self.frame).save(path)

    def take_audio(self):
        a = np.concatenate(self.audio) if self.audio else np.zeros(0, np.int16)
        self.audio = []
        return a

    def save(self):
        n = self.lib.retro_serialize_size()
        buf = C.create_string_buffer(n)
        assert self.lib.retro_serialize(buf, n)
        return (buf.raw, self.n)

    def load(self, st):
        raw, n = st
        buf = C.create_string_buffer(raw, len(raw))
        assert self.lib.retro_unserialize(buf, len(raw))
        self.n = n


def write_wav(path, samples, rate):
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(int(round(rate)))
        w.writeframes(samples.astype('<i2').tobytes())
