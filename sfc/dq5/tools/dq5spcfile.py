"""DQ5(SFC) 곡·효과음마다 .spc 파일(SPC700 상태 스냅샷, ID666 머리)을 만든다.
곡 변수(E0) 갈래가 있으면 갈래마다 <번호>-<갈래>.spc 도 만든다(효과음은 갈래 00 부터 모두, 곡은 01 부터). 형식은 sfc/dq5/docs/dq5-sound-format.md.

MesenCE testrunner 로 세이브스테이트(배 선실)를 불러 소리 대기열에 `1A 00`(앞 곡 정리) 뒤 곡이면 `01 n`, 효과음이면
`0C n X`(갈래 X)를 넣고, SPC 의 곡 자리에 n 이 오른 프레임의 spcRam·DSP 레지스터·SPC700 레지스터를 lua/dq5spcdump.lua 로 잡는다.
곡 묶음이 「곡을 튼 뒤 보내는 샘플」을 두는 곡도 샘플이 모두 들어간 상태가 되도록, 실행 중에만 곡 묶음의 둘째 바이트를
샘플 수로 바꾼다. 결과는 롬에서 나온 자료라 커밋하지 않는다(비공개 에셋 저장소로).

환경 변수 MESENCE(실행 파일)가 있어야 한다.

  python sfc/dq5/tools/dq5spcfile.py rom/dq5.sfc work/state/ship.mss --out work/sound            # 모두
  python sfc/dq5/tools/dq5spcfile.py rom/dq5.sfc work/state/ship.mss --out work/sound --only 02,33
  --wav  game-music-emu(libgme, 환경 변수 GME_LIB 또는 시스템 라이브러리)로 .spc 를 WAV(32000Hz 스테레오, S-DSP 의
         빠르기)로도 굽는다. 곡은 WAV_SONG 초(기본 30, 끝 4초 줄이기), 효과음은 WAV_SFX 초(기본 4). 들어 보기용이라
         짧게 둔다. 끝까지 들으려면 .spc 를 튼다
  --free-watch  dq5build.py 의 원래 롬 빈 자리 22곳에 롬 읽기·실행 감시를 걸고, 곡마다 읽힌 것을 free-watch.txt 로 모은다
  --index-only  에뮬레이터를 돌리지 않고 --out 의 index.json 에 장면(scene)·이 곡을 쓰는 맵(maps)만 다시 넣는다
  --wav-only  에뮬레이터를 돌리지 않고 --out 의 songs/·sfx/ 에 있는 .spc 와 index.json 으로 WAV 만 다시 굽는다
"""
import argparse
import concurrent.futures
import ctypes
import ctypes.util
import json
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom  # noqa: E402
from dq5song import header, walk  # noqa: E402
from dq5sound import map_songs  # noqa: E402
from dq5spc import SEQUENCE_COUNT, body, sequences, song_sets  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LUA = os.path.join(HERE, 'lua', 'dq5spcdump.lua')
# 고정 목록(2B:C429)의 32~3D·46 과 그 사이 시퀀스는 효과음으로 친다. 00 은 빈 시퀀스.
SFX_FROM = 0x32
SONG_SECONDS, SFX_SECONDS, FADE_MS = 180, 5, 10000
# 장면으로 쓰임을 확인한 것과 맵 곡 표(dq5sound.py, 23:FD6A +5)에서 나온 것(dq5-sound-format.md 「곡 번호와 장면」·「효과음」).
# 소리를 듣고 붙인 이름이 아니다.
SCENES = {
    0x00: '빈 시퀀스(5바이트), 맵 30/00 의 곡', 0x01: '맵 곡 38곳(그룹 00·01·02·05)', 0x02: '필드 세계 0',
    0x03: '마법 융단', 0x04: '배, 배 선실(04-01 은 배에 탔을 때 0C 04 01); 맵 곡 17/00~04·27/00;'
                 ' ヘンリー 를 쫓는 パパス 장면(15:F309)에서 줄임',
    0x05: '필드 세계 1; 맵 곡 22/00~03', 0x06: '맵 곡 60곳(그룹 18~21, 1D/00·1D/01 등)', 0x07: '맵 곡 19/02',
    0x08: '맵 곡 16곳(그룹 1B·23)', 0x09: '맵 곡 106곳(03/05 등; 노예 시절 시작 장면 뒤 03/05 에서 01 09)',
    0x0A: '맵 곡 80곳(그룹 03·04·31~35; 03/02 에서 실측)', 0x0B: '파파스가 ゲマ 에게 쓰러지는 장면(07/02)',
    0x0C: '맵 곡 20곳(그룹 24~2F)', 0x0D: '天空城; 맵 곡 그룹 06(9곳)', 0x0E: '필드 세계 2', 0x0F: '맵 곡 1F/01',
    0x10: '타이틀 화면(DRAGON QUEST V 글자, 전원 켠 뒤 1647 프레임 01 10)', 0x11: '맵 곡 1F/0A',
    0x13: '맵 곡 0E/02·21/05·21/0D', 0x17: '전투', 0x1D: '여관에서 잘 때', 0x1F: '전투 승리',
    0x20: '교회에서 기록했을 때(25:FD03·FD07)',
    0x32: '대화 창이 열릴 때', 0x33: '명령 창 열기·고르기', 0x34: '창 닫기',
    0x37: '공격이 맞을 때(전투에서 쓴 갈래 X = 01·02·03·04·07, 03·04 는 잡음)',
    0x44: 'トロッコ 가 구를 때(51/54, 끝 칸에서 02 44 로 멈춤)',
}


def kind(n):
    return 'sfx' if n >= SFX_FROM else 'song'


def regs(path):
    out = {}
    for line in open(path):
        k, _, v = line.strip().partition('=')
        if k.startswith('spc.') or k == 'frame':
            out[k] = v
    return out


def num(v):
    return int(v == 'true') if v in ('true', 'false') else int(v)


def pack(ram, dsp, r, title, game='Dragon Quest V', seconds=SONG_SECONDS, comment=''):
    """표준 SPC 파일(v0.30, ID666 글자 꼴)."""
    ram = bytearray(ram)
    g = {k: num(v) for k, v in r.items() if k != 'frame'}
    # $F0~$FF 는 입출력 레지스터. 스냅샷의 레지스터 값을 RAM 자리에 넣어 플레이어가 그대로 되살리게 한다.
    ram[0xF0] = 0x0A
    ram[0xF1] = (g['spc.timer0.enabled'] | g['spc.timer1.enabled'] << 1 | g['spc.timer2.enabled'] << 2
                 | g['spc.romEnabled'] << 7)
    ram[0xF2] = g['spc.dspReg'] & 0xFF
    ram[0xF3] = dsp[g['spc.dspReg'] & 0x7F]
    for i in range(4):
        ram[0xF4 + i] = g[f'spc.cpuRegs[{i}]'] & 0xFF
    ram[0xF8], ram[0xF9] = g['spc.ramReg[0]'] & 0xFF, g['spc.ramReg[1]'] & 0xFF
    for i in range(3):
        ram[0xFA + i] = g[f'spc.timer{i}.target'] & 0xFF
    ram[0xFD:0x100] = b'\0\0\0'
    h = bytearray(0x100)
    h[0:33] = b'SNES-SPC700 Sound File Data v0.30'
    h[0x21:0x24] = b'\x1a\x1a\x1a'
    h[0x24] = 30
    h[0x25:0x27] = (g['spc.pc'] & 0xFFFF).to_bytes(2, 'little')
    h[0x27], h[0x28], h[0x29] = g['spc.a'] & 0xFF, g['spc.x'] & 0xFF, g['spc.y'] & 0xFF
    h[0x2A], h[0x2B] = g['spc.ps'] & 0xFF, g['spc.sp'] & 0xFF

    def text(off, n, s):
        b = s.encode('ascii', 'replace')[:n]
        h[off:off + len(b)] = b

    text(0x2E, 32, title)
    text(0x4E, 32, game)
    text(0x6E, 16, 'sfc-dq4')
    text(0x7E, 32, comment)
    text(0xA9, 3, str(seconds))
    text(0xAC, 5, str(FADE_MS))
    text(0xB1, 32, 'Koichi Sugiyama')
    h[0xD2] = 0x30
    extra = bytes(ram[0xFFC0:0x10000])
    return bytes(h) + bytes(ram) + bytes(dsp) + bytes(64) + extra


def render(spc_path, wav_path, seconds, fade=4, rate=32000):
    """libgme 로 .spc 를 굽는다."""
    lib = ctypes.CDLL(os.environ.get('GME_LIB') or ctypes.util.find_library('gme') or 'libgme.dylib')
    lib.gme_open_file.restype = ctypes.c_char_p
    lib.gme_start_track.restype = ctypes.c_char_p
    lib.gme_play.restype = ctypes.c_char_p
    emu = ctypes.c_void_p()
    err = lib.gme_open_file(spc_path.encode(), ctypes.byref(emu), rate)
    if err:
        raise RuntimeError(err.decode())
    lib.gme_start_track(emu, 0)
    if fade:
        lib.gme_set_fade(emu, (seconds - fade) * 1000)
    total = seconds * rate * 2
    buf = (ctypes.c_short * 8192)()
    pcm = bytearray()
    while len(pcm) < total * 2:
        lib.gme_play(emu, 8192, buf)
        pcm += bytes(buf)
    lib.gme_delete(emu)
    pcm = bytes(pcm[:total * 2])
    head = b'fmt ' + struct.pack('<IHHIIHH', 16, 1, 2, rate, rate * 4, 4, 16) + b'data' + struct.pack('<I', len(pcm))
    with open(wav_path, 'wb') as f:
        f.write(b'RIFF' + struct.pack('<I', 4 + len(head) + len(pcm)) + b'WAVE' + head + pcm)


def variants(rom):
    """{시퀀스: 갈래 수}. 시퀀스 명령 E0 [오프셋][값] 은 곡 변수(스크립트 00~14 가 X 로 둠)가 값과 같으면 뛴다.
    흐름을 따라 닿는 E0 의 값은 늘 01 부터 이어지므로 갈래 수 = 가장 큰 값 + 1."""
    out = {}
    for i, a, n in sequences(rom):
        seq = bytes(body(rom, a, n))
        if not seq or i == 0:
            continue
        _, offs = header(seq)
        vals = set()
        for st in offs:
            seen, _ = walk(seq, st)
            vals |= {seq[pc + 3] for pc in seen if seq[pc] == 0xE0}
        out[i] = max(vals) + 1 if vals else 1
    return out


def targets(rom, want):
    """[(시퀀스, X, 파일 이름 줄기)]. 곡은 01 n(X 없음)과 갈래가 있으면 0C n X(X ≥ 1), 효과음은 갈래마다 0C n X."""
    var = variants(rom)
    out = []
    for n in want:
        if kind(n) == 'song':
            out.append((n, None, f'{n:02X}'))
            out += [(n, x, f'{n:02X}-{x:02X}') for x in range(1, var[n])]
        else:
            out += [(n, x, f'{n:02X}-{x:02X}') for x in range(var[n])]
    return out


def song_maps(rom):
    """{곡 번호: ['BC/BD', …]} 맵 레코드 +5 로 그 곡을 쓰는 실내 맵."""
    out = {}
    for bc, bd, song in map_songs(rom):
        out.setdefault(song, []).append(f'{bc:02X}/{bd:02X}')
    return out


def run_one(mesence, libdir, rom, state, n, x, stem, work, free=''):
    out = os.path.join(work, f'run{stem}')
    os.makedirs(out, exist_ok=True)
    cmd = f'10:1A:00:00;14:01:{n:02X}:00' if x is None else f'10:1A:00:00;14:0C:{n:02X}:{x:02X}'
    env = dict(os.environ, LIBDIR=libdir, SHOT_DIR=out, STATE=os.path.abspath(state), CMDS=cmd,
               WAITSONG=f'{n:02X}', FULLSET=f'{n:02X}', MAXF='900', FREEWATCH=free)
    subprocess.run([mesence, '--testrunner', os.path.abspath(rom), LUA], env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
    return out


def wav_entry(entry, folder, k):
    sec = int(os.environ.get('WAV_SONG', '30')) if k == 'song' else int(os.environ.get('WAV_SFX', '4'))
    render(os.path.join(folder, entry['file']), os.path.join(folder, entry['id'] + '.wav'), sec, 4 if k == 'song' else 0)
    entry['wav'] = entry['id'] + '.wav'
    entry['wav_seconds'] = sec
    entry['wav_rate'] = 32000


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rom')
    ap.add_argument('state')
    ap.add_argument('--out', required=True)
    ap.add_argument('--only')
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--wav', action='store_true')
    ap.add_argument('--wav-only', action='store_true')
    ap.add_argument('--free-watch', action='store_true')
    ap.add_argument('--index-only', action='store_true')
    a = ap.parse_args()
    mesence = os.environ.get('MESENCE')
    if not mesence:
        print('MESENCE 환경 변수가 필요함', file=sys.stderr)
        return 1
    if a.index_only:
        rom = Rom(open(a.rom, 'rb').read())
        maps = song_maps(rom)
        for folder in ('songs', 'sfx'):
            path = os.path.join(a.out, folder, 'index.json')
            if not os.path.exists(path):
                continue
            entries = json.load(open(path, encoding='utf-8'))
            for e in entries:
                n = int(e['sequence'], 16)
                e['scene'] = SCENES.get(n)
                e['maps'] = maps.get(n, [])
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(entries, f, ensure_ascii=False, indent=1)
                f.write('\n')
        return 0
    if a.wav_only:
        for k, folder in (('song', 'songs'), ('sfx', 'sfx')):
            path = os.path.join(a.out, folder, 'index.json')
            if not os.path.exists(path):
                continue
            entries = json.load(open(path, encoding='utf-8'))
            for e in entries:
                if a.only and e['id'] not in a.only.upper().split(','):
                    continue
                wav_entry(e, os.path.join(a.out, folder), k)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(entries, f, ensure_ascii=False, indent=1)
                f.write('\n')
        return 0
    libdir = subprocess.run(['krpatch', 'sfc', 'lua'], capture_output=True, text=True, check=True).stdout.strip()
    rom = Rom(open(a.rom, 'rb').read())
    seqs = {i: (addr, ln) for i, addr, ln in sequences(rom)}
    want = [int(x, 16) for x in a.only.split(',')] if a.only else list(range(1, SEQUENCE_COUNT))
    jobs = targets(rom, want)
    sets = {i: smp for i, _, smp in song_sets(rom)}
    maps = song_maps(rom)
    work = os.path.abspath(os.path.join(a.out, 'runs'))
    free = ''
    if a.free_watch:
        from dq5build import cpu, free_ranges
        free = ','.join(f'{cpu(o).replace(":", "")}-{cpu(o + n - 1).replace(":", "")}' for o, n in free_ranges(rom.d))
    with concurrent.futures.ThreadPoolExecutor(a.jobs) as ex:
        dirs = list(ex.map(lambda t: run_one(mesence, libdir, a.rom, a.state, *t, work, free), jobs))
    index = {'songs': [], 'sfx': []}
    for (n, x, stem), d in zip(jobs, dirs):
        r = regs(os.path.join(d, 'regs.txt'))
        ram = open(os.path.join(d, 'spc.bin'), 'rb').read()
        dsp = open(os.path.join(d, 'dsp.bin'), 'rb').read()
        k = kind(n)
        found = any(ram[0x03B7 + i] and ram[0x03AF + i] == n for i in range(8))
        title = f'DQ5 {"song" if k == "song" else "sfx"} {stem}'
        data = pack(ram, dsp, r, title, seconds=SONG_SECONDS if k == 'song' else SFX_SECONDS,
                    comment=f'sequence {n:02X} at {seqs[n][0] >> 16:02X}:{seqs[n][0] & 0xFFFF:04X}')
        folder = os.path.join(a.out, 'songs' if k == 'song' else 'sfx')
        os.makedirs(folder, exist_ok=True)
        name = f'{stem}.spc'
        with open(os.path.join(folder, name), 'wb') as f:
            f.write(data)
        entry = {'id': stem, 'sequence': f'{n:02X}', 'variant': None if x is None else f'{x:02X}', 'file': name,
                 'scene': SCENES.get(n), 'maps': maps.get(n, []), 'sequence_rom': f'{seqs[n][0] >> 16:02X}:{seqs[n][0] & 0xFFFF:04X}',
                 'sequence_bytes': seqs[n][1], 'samples': [f'{v:02X}' for v in sets[n]],
                 'command': f'01 {n:02X}' if x is None else f'0C {n:02X} {x:02X}', 'frame': int(r['frame']),
                 'playing': found}
        if a.wav:
            wav_entry(entry, folder, k)
        index['songs' if k == 'song' else 'sfx'].append(entry)
        print(f'{k:4} {stem} frame {r["frame"]:>4} {"곡 자리에 있음" if found else "곡 자리에 없음(MAXF 에 잡음)"}')
    if a.free_watch:
        lines = []
        for (n, x, stem), d in zip(jobs, dirs):
            fw = os.path.join(d, 'freewatch.txt')
            hits = [h for h in open(fw).read().split('\n') if h] if os.path.exists(fw) else ['(기록 없음)']
            lines += [f'{stem} {h}' for h in hits]
        with open(os.path.join(a.out, 'free-watch.txt'), 'w') as f:
            f.write('\n'.join(lines) + '\n')
        print(f'빈 자리 감시: 곡·갈래 {len(jobs)}개, 읽힌 기록 {len(lines)}줄')
    for k in index:
        if index[k]:
            with open(os.path.join(a.out, 'songs' if k == 'songs' else 'sfx', 'index.json'), 'w', encoding='utf-8') as f:
                json.dump(index[k], f, ensure_ascii=False, indent=1)
                f.write('\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
