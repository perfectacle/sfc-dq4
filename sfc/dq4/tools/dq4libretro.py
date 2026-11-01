"""헤드리스 libretro 프런트엔드(ctypes). SFC 코어(bsnes·snes9x)를 입력·WRAM·화면·소리·상태 저장으로 다룬다.

dq4compatcheck.py 가 쓴다. 코어 파일은 저장소에 두지 않는다(LIBRETRO_BSNES·LIBRETRO_SNES9X).

- bsnes 는 WRAM 을 retro_get_memory_data 로 내주지 않는다. 직렬화 상태의 WRAM_OFFSET 에서 읽고(프레임마다 한 번),
  쓰기는 상태를 고쳐 다시 불러온다. 직렬화가 코어 스레드를 맞추므로 타이밍이 조금 바뀔 수 있다.
- cheat(PAR 코드 AAAAAADD)는 롬·WRAM 쓰기에 쓴다. bsnes 는 cheat 를 풀 때 켜기 전 값을 되돌려 그 사이 게임이 쓴
  값을 덮으므로, 한 번만 쓰는 WRAM 값에는 cheat 대신 poke 를 쓴다.
- 코어 하나가 tools/headless_slots.py 의 자리 하나를 잡는다. close() 하거나 프로세스가 끝나면 놓는다.
"""
import ctypes as C
import os
from pathlib import Path
import sys
import wave
import numpy as np
from PIL import Image

sys.path.append(str(Path(__file__).resolve().parents[3] / 'tools'))
import headless_slots  # noqa: E402

# bsnes 115 직렬화 상태에서 WRAM 128KB 가 시작하는 자리(snes9x WRAM 과 견줘 찾음)
WRAM_OFFSET = 8836
# WRAM 찾기의 표지를 잠깐 써 보는 자리(맨 끝 바이트, 바로 되돌림)
SENTINEL_AT = 0x1FFFF
BSNES_VERSION = '115'
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
        self.slot = headless_slots.acquire(f'libretro {os.path.basename(str(dylib))}')
        try:
            self._open(dylib, rom, sysdir, options)
        except BaseException:
            self.slot.release()
            raise

    def close(self):
        """자리를 놓는다. 코어는 내리지 않으므로 이 뒤에는 run 을 부르지 않는다."""
        self.slot.release()

    def _open(self, dylib, rom, sysdir, options):
        self.path = os.path.realpath(str(dylib))
        self.lib = C.CDLL(dylib)
        self.options = {k.encode(): v.encode() for k, v in (options or {}).items()}
        self._keep = []
        self.pixfmt = 0
        self.wram_ptr = None
        self.buttons = set()
        self.audio = []
        # 코어가 콜백 뒤에도 읽는 문자열은 self 가 쥔 버퍼의 주소로 넘긴다
        self.sysdir = C.create_string_buffer(sysdir.encode())
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
        if si.library_name.decode() == 'bsnes' and si.library_version.decode() != BSNES_VERSION:
            # WRAM_OFFSET 은 이 판의 직렬화 형식에서 잰 값이다
            raise RuntimeError(f'bsnes {si.library_version.decode()}: WRAM_OFFSET 은 bsnes {BSNES_VERSION} 에서만 확인함')
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
            C.cast(data, C.POINTER(C.c_void_p))[0] = C.addressof(self.sysdir)
            return True
        if cmd == 3:
            C.cast(data, C.POINTER(C.c_bool))[0] = True
            return True
        if cmd == 15:
            v = C.cast(data, C.POINTER(Variable))
            key = v.contents.key
            if key in self.options:
                buf = C.create_string_buffer(self.options[key])
                self._keep.append(buf)
                C.cast(data, C.POINTER(C.c_void_p * 2)).contents[1] = C.addressof(buf)
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
        # 프레임마다 numpy 로 바꾸면 snes9x 에서 걷기 시간이 약 30% 늘었다. 바이트만 쥐고 frame 을 읽을 때 바꾼다
        if data:
            self._raw = (C.string_at(data, pitch * h), w, h, pitch)
            self._frame = None

    @property
    def frame(self):
        if getattr(self, '_frame', None) is None and getattr(self, '_raw', None):
            raw, w, h, pitch = self._raw
            if self.pixfmt == 1:
                a = np.frombuffer(raw, np.uint32).reshape(h, pitch // 4)[:, :w]
                rgb = np.stack([(a >> 16) & 255, (a >> 8) & 255, a & 255], -1).astype(np.uint8)
            else:
                a = np.frombuffer(raw, np.uint16).reshape(h, pitch // 2)[:, :w]
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
            self._frame = rgb
        return getattr(self, '_frame', None)

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

    def _locate_wram(self):
        """bsnes 처럼 WRAM 을 API 로 주지 않는 코어: 직렬화 상태의 WRAM 을 코어 이미지의 데이터 세그먼트에서 찾아 그
        주소를 쥔다. 매 프레임 직렬화는 코어를 동기 지점까지 더 돌려 타이밍을 바꾸므로(빌드마다 다르게) 피한다.
        같은 내용의 사본이 있을 수 있어, 후보마다 표지 바이트를 써 보고 직렬화 상태에 그 값이 나타나는 곳만 고른다.
        프레임을 돌리지 않는다. WRAM 이 아직 고르면(부팅 직후) 다음 60프레임 묶음에 다시 본다."""
        segments = data_segments(self.path)
        if not segments:
            self._wram_search = 'none'
            return None
        if self.n < 60 or getattr(self, '_wram_search', None) == self.n // 60:
            return None
        self._wram_search = self.n // 60
        wram = self.save()[0][WRAM_OFFSET:WRAM_OFFSET + 0x20000]
        if len(set(wram)) < 32:
            return None
        candidates = set()
        for start, size in segments:
            blob = C.string_at(start, size)
            for probe in range(0x100, 0x20000 - 64, 0x1F01):
                chunk = wram[probe:probe + 64]
                if len(set(chunk)) < 12:
                    continue
                at = blob.find(chunk)
                while at >= 0:
                    base = at - probe
                    if 0 <= base and blob[base:base + 0x20000] == wram:
                        candidates.add(start + base)
                    at = blob.find(chunk, at + 1)
        live = []
        for addr in candidates:
            cell = C.c_ubyte.from_address(addr + SENTINEL_AT)
            old = cell.value
            cell.value = old ^ 0xA5
            seen = self.save()[0][WRAM_OFFSET + SENTINEL_AT]
            cell.value = old
            if seen == old ^ 0xA5:
                live.append(addr)
        return live[0] if len(live) == 1 else None

    def _has_wram(self):
        """WRAM 을 직접 읽고 쓸 수 있는지. 찾지 못했으면 직렬화로 돌아가지 않고 False(호출이 싸다)."""
        if self.lib.retro_get_memory_size(2) or self.wram_ptr:
            return True
        if getattr(self, '_wram_search', None) == 'none':
            return False
        found = self._locate_wram()
        if found:
            self.wram_ptr = (found, 0x20000)
        return bool(self.wram_ptr)

    @property
    def direct(self):
        """WRAM 을 직접 읽고 쓸 수 있으면(API 또는 찾은 주소) True. 프레임을 돌리지 않는다."""
        return self._has_wram()

    def wram(self):
        size = self.lib.retro_get_memory_size(2)
        if size:
            return (C.c_ubyte * size).from_address(self.lib.retro_get_memory_data(2))
        if self._has_wram():
            return (C.c_ubyte * 0x20000).from_address(self.wram_ptr[0])
        # 찾지 못한 코어(macOS 밖의 bsnes 등): 직렬화 상태에서 읽는다. 타이밍이 흔들릴 수 있다
        if not getattr(self, '_wc', None) or self._wc[0] != self.n:
            st = self.save()[0]
            self._wc = (self.n, (C.c_ubyte * 0x20000).from_buffer_copy(st[WRAM_OFFSET:WRAM_OFFSET + 0x20000]))
        return self._wc[1]

    def rd(self, addr, n=1):
        m = self.wram()
        a = addr & 0x1FFFF
        v = 0
        for k in range(n - 1, -1, -1):
            v = v * 256 + m[a + k]
        return v

    def poke(self, pairs):
        """[(WRAM 주소, 바이트)] 를 한 번 쓴다."""
        if self._has_wram():
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
            # bsnes 63ee22f7(target-libretro/program.cpp decodeSNES)는 16진 소문자만 받는다. snes9x fae2fea 도 소문자를
            # 받는 것을 실측함(7e1f005a → 7E:1F00 = 5A)
            self.lib.retro_cheat_set(i, True, code.lower().encode())

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


def data_segments(path):
    """불러온 이미지 path 의 쓰기 가능한 데이터 세그먼트 [(주소, 크기)]. macOS(Mach-O)만, 그 밖은 빈 목록."""
    import os
    import sys
    if sys.platform != 'darwin':
        return []
    dyld = C.CDLL(None)
    dyld._dyld_image_count.restype = C.c_uint32
    dyld._dyld_get_image_name.restype = C.c_char_p
    dyld._dyld_get_image_header.restype = C.c_void_p
    dyld._dyld_get_image_vmaddr_slide.restype = C.c_long
    want = os.path.realpath(path)
    for i in range(dyld._dyld_image_count()):
        name = dyld._dyld_get_image_name(i)
        if not name or os.path.realpath(name.decode()) != want:
            continue
        header, slide = dyld._dyld_get_image_header(i), dyld._dyld_get_image_vmaddr_slide(i)
        ncmds = C.c_uint32.from_address(header + 16).value
        at, out = header + 32, []                       # mach_header_64 는 32바이트
        for _ in range(ncmds):
            cmd, size = C.c_uint32.from_address(at).value, C.c_uint32.from_address(at + 4).value
            if cmd == 0x19:                             # LC_SEGMENT_64
                name = C.string_at(at + 8, 16).rstrip(b'\0')
                vmaddr, vmsize = C.c_uint64.from_address(at + 24).value, C.c_uint64.from_address(at + 32).value
                if name.startswith(b'__DATA'):
                    out.append((vmaddr + slide, vmsize))
            at += size
        return out
    return []


def write_wav(path, samples, rate):
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(int(round(rate)))
        w.writeframes(samples.astype('<i2').tobytes())
