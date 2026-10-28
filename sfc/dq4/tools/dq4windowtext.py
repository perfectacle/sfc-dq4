"""창 글자 한글 표(dq4windowname.asm 의 WnText). dq4windowname.apply 가 부른다.
형식은 sfc/dq4/docs/dq4-window-text-format.md 「창 글자」.

롬의 이름 표(21:955D, BRK 88 2B 가 읽는 표)를 일본어 이름으로 nds/dq4/tables/adopt.tsv 의 DS 일본어와 잇고, 맞는 이름만
Galmuri9 그림으로 바꾼다. 번호가 아니라 이름으로 잇는 것은 DQ4 데이터를 옮겨 번호가 바뀌어도 그대로 쓰기 위해서다.
맞지 않는 이름은 표에 넣지 않아 원래 가나로 찍힌다.

뱅크 TEXT_BANK:
  8000 + 종류 × 200  이름 번호 256개 × 16비트: 그림의 뱅크 안 주소, 0 = 없음. 종류 FIXED_KIND 는 창 고정 문구
  9000~              [열 수][열마다 16바이트: 위 줄 8줄, 글자 줄 8줄](1bpp, bit7 = 왼쪽 점)
글자의 맨 윗줄이 위 줄 타일의 7줄째, 나머지 여덟 줄이 글자 줄에 온다(상태 창 이름과 같은 배치).
"""
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DQ5_TOOLS = HERE.parents[1] / 'dq5' / 'tools'
ADOPT = ROOT / 'nds' / 'dq4' / 'tables' / 'adopt.tsv'

TEXT_BANK = 0x58
INDEX = 0x8000
DATA = 0x9000
# 이름 표 번호 → (adopt.tsv 의 표, 창 이름 칸의 최대 열 수, 넘으면 멈출지). 주문 창(28)은 두 칸 넓혀 일곱 칸이고,
# 그보다 긴 이름(몬스터 특기 「얼어붙은 눈보라」)은 가나로 둔다. 전투 몬스터 목록(창 1B)은 이름 아홉 칸이라 넘는 이름은 가나.
KINDS = {5: ('아이템', 10, True), 3: ('주문·특기', 7, False), 4: ('몬스터', 9, False)}
SHIFT = 6                       # render 의 띠(한글 윗줄 = 1줄)를 위 줄 7줄로 내림

# 창 레코드의 가나 항목을 접두 9E k(고정 문구 k)로 바꾼다. 이름 표가 쓰지 않는 종류 7 에 그림을 둔다.
FIXED_KIND = 7
FIXED_PREFIX = 0x9E
# 창 번호 → 오른쪽으로 넓힐 칸 수. 명령 창은 한 항목이 네 칸이라 adopt.tsv 의 긴 이름(「강한 정도」·「조사하다」)
# 대신 두 자 낱말로 줄였다. 「どうする」 창은 「건네기」 석 자가 들어가게 한 칸 넓힌다.
# 09 さくせん, 0B つよさ(「강함 보기」 가 들어가게 한 칸 넓힘), 19·1A·87·88 전투 첫 창, 1C·1D·1E 전투 명령 창
FIXED_WINDOWS = {0x01: 0, 0x10: 1, 0x09: 0, 0x0B: 1,
                 0x19: 0, 0x1A: 0, 0x87: 0, 0x88: 0, 0x1C: 0, 0x1D: 0, 0x1E: 0}
FIXED = {
    'はなす': '대화', 'じゅもん': '주문', 'つよさ': '강함', 'どうぐ': '도구',
    'そうび': '장비', 'さくせん': '작전', 'とびら': '문', 'しらべる': '조사',
    'つかう': '쓰기', 'わたす': '건네기', 'すてる': '버리기',
    'ならびかえをする': '대열 바꾸기', 'さくせんをねる': '작전 짜기',
    'ＨＰとＭＰ': 'HP와 MP', 'こうげきカ': '공격력', 'つよさみる': '강함 보기', 'まんたん': '만땅',
    'たたかう': '싸우기', 'いれかえ': '교체', 'にげる': '도망',
    'こうげき': '공격', 'とくぎ': '특기', 'ぼうぎょ': '방어',
}
# 창 제목(04:AD78 목록). 표에 없는 제목(이름 뒤 「の１」, 이름 입력 등)은 가나로 둔다.
TITLES = {
    'コマンド': '명령', 'どうする': '어떻게', 'だれに': '누구에게', 'どこへ': '어디로',
    'ぶき': '무기', 'せんとう': '전투', 'だれの': '누구의', 'だれが': '누가', 'のどうぐ': '의 도구',
    'せんとうじゅもん': '전투 주문', 'のじゅもん': '의 주문', 'しょうひＭＰ': '소비 MP', 'だれを': '누구를',
    'よろい': '갑옷', 'たて': '방패', 'かぶと': '투구', 'レベル': '레벨', 'しゅび': '수비', 'ぼうぐ': '방어구',
    'せんとうとくぎ': '전투 특기', 'のとくぎ': '의 특기', 'だれと': '누구와', 'だれがたたかう': '누가 싸울까',
}
# 명령 창(01)의 문구. 메시지 창과 함께 보이는 일이 많아 캔버스 밖 전용 칸(BG3 1D0~1FF, 문구마다 6칸)에 둔다
COMMAND_WINDOW = 0x01
COMMAND = ('はなす', 'じゅもん', 'つよさ', 'どうぐ', 'そうび', 'さくせん', 'とびら', 'しらべる')
COMMAND_COLUMNS = 3
TITLE_COUNT = 0x2B              # 제목 2B 부터는 목록 뒤의 코드


def kana_key(text):
    """가타카나를 히라가나로, 빈칸을 빼서 표기 차이를 무시한다."""
    return ''.join(chr(ord(c) - 0x60) if 0x30A1 <= ord(c) <= 0x30F6 else c for c in text if c not in ' 　')


def rom_names(data, table, count=256):
    if str(DQ5_TOOLS) not in sys.path:
        sys.path.insert(0, str(DQ5_TOOLS))
    import dq5text
    from dq5map import Rom
    rom = Rom(bytes(data))
    return [dq5text.text(dq5text.string_codes(rom, dq5text.string(rom, table, n))) for n in range(count)]


def adopted(table):
    with open(ADOPT, encoding='utf-8') as f:
        return {kana_key(r['DS 일본어']): r['채택'] for r in csv.DictReader(f, delimiter='\t')
                if r['표'] == table and r['채택']}


def columns(font, text):
    """한글 문자열 → 열마다 16바이트(위 줄 8 + 글자 줄 8)."""
    import dq4menupatch
    out = []
    for col in dq4menupatch.render(font, text):
        if any(any(row) for row in col[16 - SHIFT:]):
            raise ValueError(f'{text!r}: 글자가 글자 줄 아래로 넘침')
        rows = [[0] * 8] * SHIFT + col[:16 - SHIFT]
        out.append(bytes(int(''.join(map(str, r)), 2) for r in rows))
    return out


def phrases():
    """고정 문구 [(일본어, 한글)]. 번호 k 는 이 순서(FE·FF 를 넘지 않음). 앞 len(COMMAND) 개는 명령 창 전용 번호라,
    같은 낱말이 다른 창·제목에 나오면 뒤에 따로 번호를 받는다(전용 칸의 위 줄 합성이 명령 창 자리에 맞춰져 있음)."""
    out = [(jp, FIXED[jp]) for jp in COMMAND]
    rest = dict(FIXED)
    for jp, ko in TITLES.items():
        rest.setdefault(jp, ko)
    return out + list(rest.items())


def _runs(rom, rec, i, start_ok):
    """rec[i] 부터 가나 한 덩이: (끝, 칸 수, 일본어). 탁점 접두 84·83(제목은 92·93)은 칸을 차지하지 않는다."""
    import dq5text
    j, n = i, 0
    while j < len(rec) and 0x02 <= rec[j] < 0xB0:
        j += 2 if rec[j] in (0x83, 0x84, 0x92, 0x93) else 1
        n += 1
    raw = rec[i:j].replace(b'\x92', b'\x84').replace(b'\x93', b'\x83')
    return j, n, dq5text.text(dq5text.string_codes(rom, raw))


def fixed_records(data, font):
    """FIXED_WINDOWS 의 창 레코드와 제목 목록을 고쳐 쓴 [(파일 자리, 새 바이트)]와 문구 번호 {일본어: k}.
    가나 n 칸과 그 뒤 빈칸 s 개를 9E k 와 빈칸 (n + s − 한글 열 수) 개로 바꿔, 뒤 항목의 열 자리와
    04:B0F0 의 칸 셈($0ADE)을 원래와 같게 둔다. 창 본문은 항목 머리 FE 바로 뒤만 바꾼다."""
    if str(DQ5_TOOLS) not in sys.path:
        sys.path.insert(0, str(DQ5_TOOLS))
    import dq5text
    from dq5map import Rom
    rom = Rom(bytes(data))
    table = phrases()
    numbers = {}
    for k, (jp, _) in enumerate(table[len(COMMAND):], len(COMMAND)):
        numbers.setdefault(jp, k)
    command = {jp: k for k, (jp, _) in enumerate(table[:len(COMMAND)])}
    width = {jp: len(columns(font, ko)) for jp, ko in table}
    korean = dict(table)

    def lorom(addr):
        return ((addr >> 16) & 0x7F) * 0x8000 + (addr & 0x7FFF)

    out = []
    for w, widen in FIXED_WINDOWS.items():
        addr, rec = dq5text.window(rom, w)
        start = rec.index(0xFE)
        new = bytearray(rec[:start])
        i = start
        while i < len(rec):
            if not (0x02 <= rec[i] < 0xB0 and rec[i - 1] == 0xFE):
                new.append(rec[i])
                i += 1
                continue
            j, n, jp = _runs(rom, rec, i, True)
            if jp not in FIXED or (w == COMMAND_WINDOW and jp not in command):
                raise ValueError(f'창 {w:02X}: 「{jp}」 의 한글 문구가 없음')
            k = command[jp] if w == COMMAND_WINDOW else numbers[jp]
            if w == COMMAND_WINDOW and width[jp] > COMMAND_COLUMNS:
                raise ValueError(f'창 {w:02X}: 「{FIXED[jp]}」 {width[jp]}열, 전용 칸은 {COMMAND_COLUMNS}열')
            s = 0
            while j + s < len(rec) and rec[j + s] == 0x01:
                s += 1
            last = j + s >= len(rec) or rec[j + s] == 0xFF
            room = n + s + (widen if last else 0)
            if width[jp] > room:
                raise ValueError(f'창 {w:02X}: 「{korean[jp]}」 {width[jp]}열, 자리 {room}열')
            new += bytes((FIXED_PREFIX, k)) + b'\x01' * max(0, n + s - width[jp])
            i = j + s
        if len(new) > len(rec):
            raise ValueError(f'창 {w:02X}: 고친 레코드가 원래보다 김')
        new[2] += widen
        o = lorom(addr)
        if bytes(data[o:o + len(rec)]) != rec:
            raise ValueError(f'창 {w:02X}: 레코드 자리가 어긋남')
        out.append((o, bytes(new) + b'\xff' * (len(rec) - len(new))))

    # 제목: 이름 자리(E0~) 없이 가나 한 덩이뿐인 제목만 창 안에서 늘어날 수 있다. 쓰는 창마다 제목 자리 + 열 수 ≤ 너비 − 1
    users = {}
    first = rom.u16(dq5text.WINDOWS)
    for w in range((first - (dq5text.WINDOWS & 0xFFFF)) // 2):
        addr, rec = dq5text.window(rom, w)
        # 메뉴 패치가 낮은 WRAM 으로 돌린 창(공용 창·이름 입력)은 롬에 레코드가 없다
        if addr & 0xFFFF >= 0x8000 and rec and not rec[0] & 0x80 and len(rec) > 6 and rec[4] & 0x0F:
            h = dq5text.window_header(rec)
            users.setdefault(h['title'], []).append((w, h['title_x'], h['w'] + FIXED_WINDOWS.get(w, 0)))
    start = lorom(dq5text.WINDOW_TITLES)
    o, old, new = start, bytearray(), bytearray()
    for t in range(TITLE_COUNT):
        e = data.index(0xFF, o)
        rec = bytes(data[o:e])
        old += rec + b'\xff'
        i, cols = 0, 0
        body = bytearray()
        single = len(rec) > 0 and all(0x02 <= b < 0xB0 for b in rec)
        while i < len(rec):
            if not 0x02 <= rec[i] < 0xB0 or rec[i] == 0x01:
                body.append(rec[i])
                cols += 1
                i += 1
                continue
            j, n, jp = _runs(rom, rec, i, False)
            s = 0
            while j + s < len(rec) and rec[j + s] == 0x01:
                s += 1
            if jp not in numbers or (not single and width[jp] > n + s):
                body += rec[i:j]
                cols += n
                i = j
                continue
            body += bytes((FIXED_PREFIX, numbers[jp])) + b'\x01' * max(0, n + s - width[jp])
            cols += max(width[jp], n + s)
            i = j + s
        for w, x, wd in users.get(t, ()):
            if single and x + cols > wd - 1:
                raise ValueError(f'제목 {t:02X} 「{rec.hex()}」: 창 {w:02X} 너비 {wd} 에 {cols}열이 안 들어감')
        new += body + b'\xff'
        o = e + 1
    if len(new) > len(old):
        raise ValueError('고친 제목 목록이 원래보다 김')
    out.append((start, bytes(new) + b'\xff' * (len(old) - len(new))))
    return out, numbers


def build(data, font):
    """뱅크 TEXT_BANK 의 8000~ 에 넣을 바이트와, 종류마다 (이름 수, 한글로 바꾼 수)."""
    index = bytearray(DATA - INDEX)
    body = bytearray()
    report = {}
    for k, (jp, ko) in enumerate(phrases()):
        cols = columns(font, ko)
        at = DATA + len(body)
        index[FIXED_KIND * 0x200 + k * 2:FIXED_KIND * 0x200 + k * 2 + 2] = at.to_bytes(2, 'little')
        body += bytes((len(cols),)) + b''.join(cols)
    report[FIXED_KIND] = (len(phrases()), len(phrases()))
    for kind, (table, limit, strict) in KINDS.items():
        korean = adopted(table)
        names = rom_names(data, kind)
        done = 0
        for n, name in enumerate(names):
            ko = korean.get(kana_key(name))
            if not ko:
                continue
            cols = columns(font, ko)
            if len(cols) > limit:
                if strict:
                    raise ValueError(f'{ko!r}: {len(cols)}열, 창은 {limit}열')
                continue
            at = DATA + len(body)
            index[kind * 0x200 + n * 2:kind * 0x200 + n * 2 + 2] = at.to_bytes(2, 'little')
            body += bytes((len(cols),)) + b''.join(cols)
            done += 1
        report[kind] = (len(names), done)
    if DATA + len(body) > 0x10000:
        raise ValueError('창 글자 그림이 뱅크 하나를 넘음')
    return bytes(index + body), report
