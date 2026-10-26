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
  --index-only  에뮬레이터를 돌리지 않고 --out 의 index.json 에 장면(scene)·이 곡을 쓰는 맵(maps)·공식 곡명(name)만 다시 넣는다
  --work DIR  MesenCE 실행마다의 덤프(spc.bin 등)를 둘 곳(기본 --out/runs)
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
from dq5spc import RESIDENT_SEQUENCES, SEQUENCE_COUNT, body, ff_list, sequences, song_sets  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LUA = os.path.join(HERE, 'lua', 'dq5spcdump.lua')
# 고정 목록(2B:C429)의 32~3D·46 과 그 사이 시퀀스는 효과음으로 친다. 00 은 빈 시퀀스.
SFX_FROM = 0x32
SONG_SECONDS, SFX_SECONDS, FADE_MS = 180, 5, 10000
# 장면으로 쓰임을 확인한 것과 맵 곡 표(dq5sound.py, 23:FD6A +5)에서 나온 것(dq5-sound-format.md 「곡 번호와 장면」·「효과음」).
# 소리를 듣고 붙인 이름이 아니다.
SCENES = {
    0x00: '빈 시퀀스(5바이트), 맵 30/00 의 곡', 0x01: '성: テルパドール·ラインハット·グランバニア·ようせいのしろ 의 맵 곡 38곳', 0x02: '필드 세계 0',
    0x03: '마법 융단', 0x04: '배, 배 선실(04-01 은 배에 탔을 때 0C 04 01); 맵 곡 17/00~04·27/00;'
                 ' ヘンリー 를 쫓는 パパス 장면(15:F309)에서 줄임',
    0x05: '필드 세계 1; 맵 곡 22/00~03', 0x06: '마을: エルヘブン·オラクルベリー·アルカパ·ジャハンナ·ルラフェン·チゾット·サラボナ·ポートセルミ·サンタローズ 의 맵 곡 60곳', 0x07: '맵 곡 19/02',
    0x08: '작은 마을: カボチ·やまおくのむら 의 맵 곡 16곳', 0x09: '동굴·던전: エビルマウンテン 등 그룹 20개의 맵 곡 106곳(노예 시절 03/05 도; 시작 장면 뒤 03/05 에서 01 09)',
    0x0A: '신전(03)·レヌール城(04)·그룹 31~35 의 맵 곡 80곳(03/02 에서 실측)', 0x0B: '전투에서 전멸했을 때(20:814E BRK 11 0B), 파파스가 쓰러지는 장면(07/02, 02:9DCF)',
    0x0C: '교회·사당·여관: きたのきょうかい·しゅうどういん·うわさのほこら·ネッドのやどや 등 그룹 24~2F 의 맵 곡 20곳'
                 '(수도원 29/00 에서 깨어나는 장면도 이 곡 그대로)', 0x0D: '天空城; 맵 곡 그룹 06(9곳)', 0x0E: '필드 세계 2', 0x0F: '맵 곡 1F/01',
    0x10: '타이틀 화면(DRAGON QUEST V 글자, 전원 켠 뒤 1647 프레임 01 10)', 0x11: '맵 곡 1F/0A(결혼식 뒤); 물의 반지를 가져온 밤 ルドマン 의 말 뒤 05:F50B 가 7E:21DF = 91 로 둠(코드 읽기)',
    0x12: '과거로 가는 장면: プサン 대화 22A → 이벤트 40, 빛바랜 04/00 에서 02:D884(7E:21DF = 92)',
    0x13: '맵 곡 0E/02·21/05·21/0D; 가짜 왕비를 쓰러뜨린 뒤 이벤트 2B 의 06:D2C4(7E:21DF = 93, 코드 읽기)',
    0x14: '음악가(대화 1C8 「今から 曲を 演奏するところ」)가 연주(06:BA0A BRK 0F 14); 이벤트 44 끝 05:FCAD(グランバニア 밤, 7E:21DF = 94, 코드 읽기)',
    0x15: 'グランバニア 즉위식(02/06, 21A8.3 목록 인물의 25:FEBB)·엔딩(2190.7 목록의 02:F6F9) (코드 읽기)',
    0x19: '슬라임 레이스가 시작할 때(11:FB3E)', 0x1A: '슬라임 레이스 도중(11:FB53)', 0x16: '보스 전투(무리 등급 1, 예: 무리 20)', 0x17: '전투',
    0x18: '마지막 보스 전투(エスターク·ミルドラース)', 0x1D: '여관에서 잘 때', 0x1E: 'マリア 의 기도로 33/00 의 문이 열릴 때(03:8E8D)', 0x1F: '전투 승리',
    0x20: '교회에서 기록했을 때(25:FD03·FD07)', 0x21: '레벨이 올랐을 때(25:8B1C)',
    0x22: '물건을 받을 때: ゴールドオーブ 를 바꿔치기(대화 139) 등(06:B682)', 0x23: '저주받은 장비를 했을 때(05:DE06)',
    0x25: '카지노 슬롯이 맞았을 때 5000코인 이상(23:FEB9, 코드 읽기)', 0x26: '같은 때 500코인 이상(코드 읽기)',
    0x27: '같은 때 50코인 이상(코드 읽기)', 0x28: '같은 때 50코인 미만(코드 읽기)',
    0x30: '과거로 가는 장면의 넘어가는 대목(02:D3FB, 7E:21DF = B0)', 0x31: 'ベネット 의 ルラムーン草 실험(대화 1CA → 이벤트 35 의 06:D535)',
    0x32: '대화 창이 열릴 때', 0x33: '명령 창 열기·고르기', 0x34: '창 닫기', 0x35: '문 열기',
    0x38: '공격 주문 연출(メラ~ミナデイン)', 0x39: '숨·ザキ 연출', 0x3A: 'マホカンタ 연출', 0x3B: '카지노 슬롯',
    0x3E: '순간이동 효과 등(맵 루틴)', 0x40: '순간이동(ラマダ 뒤)', 0x46: '상태 주문 연출(ラリホー·マヌーサ 등)',
    0x37: '공격이 맞을 때(전투에서 쓴 갈래 X = 01·02·03·04·07, 03·04 는 잡음)',
    0x44: 'トロッコ 가 구를 때(51/54, 끝 칸에서 02 44 로 멈춤)',
}
# 갈래(곡 변수 X)마다 확인한 쓰임. dq5-sound-format.md 「전투 곡」·「효과음 쓰임」. 「코드 읽기」 는 장면을 띄우지 못한 것.
BRANCH_SCENES = {
    (0x16, 1): '동굴 안 보스 전투(0C 16 01)', (0x17, 1): '동굴 안 전투(0C 17 01, 21/02 에서 마주친 전투로 실측)',
    (0x18, 1): '동굴 안 마지막 보스 전투', (0x32, 0): '대화 창 열기, 전투 메시지 F9',
    (0x33, 0): '필드 명령 창 열기·창에서 고르기·전투 명령 창', (0x34, 3): '창 닫기(B)',
    (0x34, 2): '맵 옮길 때로 보임, 인물 명령 02/06', (0x35, 1): '문 열기(01:E01B, 23/00 에서 とびら)',
    (0x36, 2): 'キメラのつばさ 로 날 때',
    (0x36, 0): '전투(20:F5EE)·파파스 장면', (0x37, 1): '전투에서 맞을 때(26:8Bxx)', (0x37, 2): '전투에서 맞을 때(26:8Bxx)',
    (0x37, 4): '전투에서 맞을 때(26:8Bxx)', (0x37, 3): '전투에서 맞을 때(20:Cxxx·F50A, 잡음)',
    (0x37, 0x0D): '전투에서 맞을 때(20:Cxxx·F50A)', (0x37, 7): '전투 연출(28:804E)', (0x37, 0x11): '파파스 장면',
    (0x37, 0x0E): '전투에서 주문을 외울 때(26:8AFF, 모든 주문)',
    (0x37, 0): '인물 명령 03/05·03/07', (0x37, 0x13): '인물 명령 03/05·03/07', (0x38, 1): '파파스 장면(02:9DFF)',
    (0x3B, 0): '카지노 슬롯에 코인 넣기(11:B4EB)', (0x3B, 1): '슬롯 돌리기 시작(11:B673)',
    (0x3B, 2): '슬롯 릴 하나가 멈출 때(11:B6C3)', (0x3C, 0): '슬롯이 맞았을 때(11:B3B7, 맞음 판정을 롬에서 늘 참으로 덮어 실측)',
    (0x3D, 2): 'ミルドラース 둘째 싸움 앞', (0x3A, 0): 'マホカンタ 「ひかりのかべを つくりだした」(20:F4C1)', (0x35, 0): '전투 뒤 「たからばこを あけた！」(25:89C5)', (0x33, 1): '00:9440 이 A = 32·84·85 일 때 00:9451 에서(카지노 「やってみますか？」 에서 실측)', (0x3D, 1): '인물 명령 03/0A', (0x3E, 5): '인물이 순간이동해 나타날 때'
    '(인라인 명령 2C·2D, 03:AE91; 31/0B 의 몬스터 셋)', (0x3F, 0): 'レヌール城 04/09(29:8044)',
    (0x40, 0): 'ラマダ 를 쓰러뜨린 뒤 03/02 에서 순간이동할 때(02:BBA3)',
    (0x41, 0): 'トロッコ 가 멈출 때(51/54)', (0x42, 0): 'グランバニア 02/07 밤, 21A8.2·21A3.7 에서 (22,13) 에 들어서면 숨은 인물이 23:E7A9 로 울리고 02 42 로 멈춤',
    (0x43, 0): '물 위를 떠내려가는 장면(이벤트 스크립트 15:F635 → 0F:FCAE, 0F:FDD7; 850프레임쯤 울리고 02 43 으로 멈춘 뒤 곡 0C 맵의 침대 있는 방으로)',
    (0x44, 7): '54/53 ミルドラース 장면에서 되풀이', (0x44, 0x0B): '전투 연출',
    (0x45, 1): '54/53 ミルドラース 「わが名は…」 뒤 사라질 때(23:E6A4 → 02:EF26, 2190.5·21E1.0)',
}
# 공식 음반의 곡명(교향조곡 「ドラゴンクエストV」天空の花嫁 의 곡명·메들리 부제)을 위 실측 장면에 짝지은 것.
# 「확정」 은 장면이 곡명과 바로 맞는 것, 「추정」 은 같은 장면에 맞을 곡이 둘 이상이거나 장면이 곡명과 느슨하게 맞는 것.
# 장면을 모르거나 공식 곡명이 없는 효과음 같은 곡(여관·승리·교회 기록 등)은 비운다. dq5-sound-format.md 「곡 이름」.
NAME_SOURCES = ('https://ja.wikipedia.org/wiki/交響組曲「ドラゴンクエストV」天空の花嫁',
                'https://www.inside-games.jp/article/2015/03/02/85484.html')
SONG_NAMES = {
    0x01: ('王宮のトランペット', '확정'), 0x02: ('地平の彼方へ', '확정'), 0x03: ('空飛ぶ絨毯', '확정'),
    0x04: ('大海原へ', '확정'), 0x06: ('街角のメロディ', '추정'), 0x07: ('カジノ都市', '확정'),
    0x08: ('淋しい村', '추정'), 0x09: ('洞窟に魔物の影が', '확정'), 0x0A: ('死の塔', '추정'),
    0x0C: ('聖(ひじり)', '추정'), 0x0D: ('天空城', '확정'), 0x0E: ('暗黒の世界', '확정'),
    0x0F: ('結婚ワルツ', '확정'), 0x10: ('序曲のマーチ', '확정'), 0x11: ('愛の旋律', '추정'),
    0x13: ('さびれた村', '추정'), 0x16: ('不死身の敵に挑む', '확정'), 0x17: ('戦火を交えて', '확정'),
    0x18: ('大魔王', '확정'),
}


def name_fields(n):
    """곡 n 의 index.json 이름 칸. 이름이 없으면 빈 dict."""
    if n not in SONG_NAMES:
        return {}
    name, status = SONG_NAMES[n]
    return {'name': name, 'name_status': status, 'name_source': list(NAME_SOURCES)}


# 전투 연출의 효과음 표(dq5sfx.py, 28:8074 → 28:811E)와 인물 인라인 명령 20 n X 는 롬에서 그대로 붙인다.
_CATALOGUE = {}


def auto_scene(rom, n, x):
    if rom is None or x is None:
        return ''
    if not _CATALOGUE:
        import dq5sfx
        _CATALOGUE.update(dq5sfx.catalogue(rom))
    v = _CATALOGUE.get((n, x))
    if not v:
        return ''
    parts = []
    names = []
    named = [f for f in v['fx'] if f['name']] or v['fx']
    for f in named:
        nm = f['name'] or '번호 %02X' % f['fx']
        if f['cond']:
            # '무기 종류 k(물건·… 등 n개)' 에서 첫 물건 이름만
            inner = f['cond'].split('(')[1].split('·')[0].rstrip(')') if '(' in f['cond'] else f['cond']
            nm = '%s(%s)' % (nm, inner if '무기' in f['cond'] else f['cond'])
        if nm not in names:
            names.append(nm)
    if names:
        parts.append('전투 연출 ' + '·'.join(names[:8]) + (' 등' if len(names) > 8 else ''))
    lists = sorted({p['list'].split()[0] for p in v['npc']})
    if lists:
        parts.append('인물 명령 20(%s)' % '·'.join(lists))
    return ', '.join(parts)


def scene(n, x, rom=None):
    """갈래 쓰임이 있으면 그것, 없으면 번호의 쓰임. rom 을 주면 연출 표·인물 명령에서 나온 쓰임을 붙인다."""
    base = BRANCH_SCENES.get((n, x)) or SCENES.get(n)
    extra = auto_scene(rom, n, x)
    if base and extra:
        return f'{base}; {extra}'
    return base or extra or None


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


def run_one(mesence, libdir, rom, state, n, x, stem, work, free='', preload=False):
    out = os.path.join(work, f'run{stem}')
    os.makedirs(out, exist_ok=True)
    play = f'01:{n:02X}:00' if x is None else f'0C:{n:02X}:{x:02X}'
    # 고정 시퀀스(2B:C429) 곡은 「곡 앞」 샘플(2B:C1AE)을 건너뛰고 「곡 뒤」(2B:C1BA)만 보내는데, FULLSET 이 모두를 「곡 앞」 으로
    # 옮겨 하나도 가지 않는다(곡 17 은 8개 중 2개만 SPC 에). 94 n(곡 n 자료 올리기)을 먼저 보내면 모두 올라간다.
    cmd = f'10:1A:00:00;14:94:{n:02X}:00;200:{play}' if preload else f'10:1A:00:00;14:{play}'
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
    ap.add_argument('--work', help='MesenCE 실행마다의 덤프 폴더(기본 --out/runs)')
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
                e['scene'] = scene(n, int(e['variant'], 16) if e.get('variant') else None, rom)
                e['maps'] = maps.get(n, [])
                for k in ('name', 'name_status', 'name_source'):
                    e.pop(k, None)
                if folder == 'songs':
                    e.update(name_fields(n))
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
    work = os.path.abspath(a.work or os.path.join(a.out, 'runs'))
    free = ''
    if a.free_watch:
        from dq5build import cpu, free_ranges
        free = ','.join(f'{cpu(o).replace(":", "")}-{cpu(o + n - 1).replace(":", "")}' for o, n in free_ranges(rom.d))
    with concurrent.futures.ThreadPoolExecutor(a.jobs) as ex:
        preload = {v for v in ff_list(rom, RESIDENT_SEQUENCES) if 0 < v < SFX_FROM}
        dirs = list(ex.map(lambda t: run_one(mesence, libdir, a.rom, a.state, *t, work, free, t[0] in preload), jobs))
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
                 'scene': scene(n, x, rom), 'maps': maps.get(n, []), 'sequence_rom': f'{seqs[n][0] >> 16:02X}:{seqs[n][0] & 0xFFFF:04X}',
                 'sequence_bytes': seqs[n][1], 'samples': [f'{v:02X}' for v in sets[n]],
                 'command': f'01 {n:02X}' if x is None else f'0C {n:02X} {x:02X}', 'frame': int(r['frame']),
                 'playing': found}
        if k == 'song':
            entry.update(name_fields(n))
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
