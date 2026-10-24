"""DQ4(FC) 대사 텍스트 풀기. 형식은 fc/dq4/docs/dq4-text-format.md.

사용:
  python fc/dq4/tools/dq4text.py rom/dq4.nes all              실제로 있는 메시지 전부
  python fc/dq4/tools/dq4text.py rom/dq4.nes MSG [개수]      메시지 번호(16진)부터 글자로
  python fc/dq4/tools/dq4text.py rom/dq4.nes MSG --bytes     글자 바이트(화면 타일 번호)로
  python fc/dq4/tools/dq4text.py rom/dq4.nes MSG[,MSG…] --compare end.ram ...  seq.lua 의 RAM 덤프(창 줄 버퍼 $06AA,
      전투 창이면 옆의 end.nt)가 차례로 찍은 메시지들과 맞는지. 치환 제어(F6 이름 등)는 아무 글자와 맞춤
  python fc/dq4/tools/dq4text.py rom/dq4.nes controls        제어 바이트 ED~FF 의 처리기 주소·뜻·쓰는 메시지 수
  python fc/dq4/tools/dq4text.py rom/dq4.nes windows         창 문자열 표 16:$A572(그룹, 항목, 루틴/문자열, 글자)
  python fc/dq4/tools/dq4text.py rom/dq4.nes windows --layout [--meaning]   창 레코드(자리·크기·본문), --meaning 은 갈래마다 뜻
  python fc/dq4/tools/dq4text.py rom/dq4.nes windows --items  본문 바이트의 뜻 표(루틴 항목·항목 루틴·목록·C1·자리 루틴)
  python fc/dq4/tools/dq4text.py rom/dq4.nes windows --trace item.txt ...   lua/textitem.lua 기록을 창 열기마다 한 줄로
  python fc/dq4/tools/dq4text.py rom/dq4.nes windows --compare DIR ...      lua/textlayout.lua 기록의 틀 자리와 레코드 견주기
  python fc/dq4/tools/dq4text.py rom/dq4.nes export [DIR]    메시지·창 문자열·이름 목록을 기호 텍스트 JSON·TSV 로(기본 work/text).
      --check 면 쓰지 않고 기호 → 바이트 왕복과 부호 → 롬 비트열만 검사. 출력은 저작권 텍스트라 커밋하지 않는다

근거 루틴: 0F:$DF99(6비트 부호 읽기), 0F:$DFD5(뱅크 넘김), 16:$8656(메시지 번호 → 시작),
16:$86BA(부호 → 글자, 가나 전환, 사전 단어), 16:$9783·$97B0(창 문자열과 80 이상 바이트).
"""
import json
import os
import re
import sys
import unicodedata

from kr_patch.fc import ines

BLOCKS = (0x16, 0x88B0)      # 32개 메시지 단위 시작 포인터 표
BANK_BOUNDS = (0x16, 0x8960)  # 블록 번호가 이 값보다 작으면 그 순번의 뱅크
CHARS = (0x16, 0x8765)        # 6비트 부호 → 글자 바이트, 가나 모드마다 64개
WORDS = (0x16, 0x87E5)        # 사전 단어 32개 단위 포인터 표(뱅크 1B)
WORD_BANK = 0x1B
END = 0x39                    # 메시지 끝 부호(6비트)
WORD_END = 0xFE


# 글자 바이트 = BG 타일 번호(CHR $1000 폰트). 화면에서 읽어 정했다.
GLYPHS = {0x00: '　', 0x3D: '\u3099', 0x3E: '\u309a'}   # 결합용 탁점·반탁점
for _i, _c in enumerate('0123456789'
                        'あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをんっゃゅょ'):
    GLYPHS[0x01 + _i] = _c
for _i, _c in enumerate('アイエオカキクコサシスソタテトナニヌネノハヒフホマミムメモラルレロンャッドーじだどぶ'):
    GLYPHS[0x40 + _i] = _c
GLYPHS.update({0x3F: '。', 0x6A: '°', 0x6B: '〝', 0x6C: '．', 0x6D: '？', 0x6E: '！', 0x6F: '「',
               0x70: '＊', 0x71: '：', 0x72: '…', 0x73: '†', 0x74: '☠', 0x75: 'Ｍ', 0x76: 'Ｐ', 0x77: 'Ex'})
for _i, _c in enumerate('ＡＢＣＤＥＦＧＨ'):
    GLYPHS[0x78 + _i] = _c
CONTROL = {0xFC: '\n', 0xFB: '\n▼\n', 0xF9: ''}


def text(bs):
    """탁점 3D·반탁점 3E 는 꾸미는 글자 앞에 오므로 그 글자 뒤로 옮겨 찍는다."""
    out, mark = [], ''
    for b in bs:
        if b in (0x3D, 0x3E):
            mark = GLYPHS[b]
        elif b in CONTROL:
            out.append(mark + CONTROL[b])
            mark = ''
        else:
            out.append(GLYPHS.get(b, f'[{b:02X}]') + mark)
            mark = ''
    return unicodedata.normalize('NFC', ''.join(out))


# 창 줄 버퍼 $06AA: 줄마다 탁점 행·글자 행이 창 폭($54)바이트씩, 4줄(16:$85B3, 16:$830F, 16:$862B).
# 창 폭은 필드 16(22칸), 전투 18(24칸). 줄 번호 $0552 는 1·3·5·7(글자 행 순번).
LINE_BUF, LINES = 0x06AA, 4
WIDTH, LINE_NO, ORIGIN_X = 0x54, 0x0552, 0x53
FIELD_W, BATTLE_W = 0x16, 0x18
GLYPH_END = 0x80   # 메시지 글자 바이트는 이 아래. 80~8C 는 창 틀 등
SCREEN_ROW = 0x13   # 글자를 화면에 찍는 행 = $0552 + $13, 탁점은 그 윗행(16:$8335, 16:$8362)
CONTROL_MIN = 0xED                          # 이 값 이상은 16:$80AF 표의 제어 처리기로 감
HANDLERS = (0x16, 0x80AF)                   # 제어 처리기 표, 첨자 = (~바이트) × 2

# 제어 바이트의 뜻. 치환(F5~F8·F2·F3)은 인자 목록 $F9- 에서 하나씩 꺼내 쓰고, 글자는 $0554 에 만든다.
CONTROLS = {
    0xED: '몬스터 깜빡임(1E:$8D0D, 몬스터 칸 $0592)',
    0xEE: '다음 바이트 n 으로 소리: n<40 음악·효과음 n(끝날 때까지 기다림, 0E 제외), n≥40 효과음 n+40',
    0xEF: '$0554 에 준비된 글자열을 그대로(호출한 쪽이 채움)',
    0xF0: 'FC 와 같음',
    0xF1: '이어지는 줄 들여쓰기 0. 메시지 첫 바이트면 자동 「＊「」 를 붙이지 않음',
    0xF2: '$00 포인터의 길이 붙은 이름(뱅크 0B). 인자 하나를 건너뜀',
    0xF3: '주문 이름에서 마지막 글자를 뺌',
    0xF4: '30프레임 쉼',
    0xF5: '주문 이름(인자 = 주문 ID)',
    0xF6: '이름: 인자 n < 80 이면 동료 n&0F, 아니면 몬스터 칸 n&07 의 이름 + (n>>3)&0F 가 0~7 일 때 「Ａ」~「Ｈ」'
          '(몬스터가 동료로 변신했으면 「동료 이름もどき」)',
    0xF7: '아이템 이름(인자 = 아이템 ID)',
    0xF8: '숫자($FD-$FF 24비트, 앞 0 뺌)',
    0xF9: '메시지 끝(줄이 시작 칸이 아니면 줄바꿈)',
    0xFA: '줄바꿈 뒤 끝',
    0xFB: '줄바꿈(시작 칸이면 안 함) 뒤 ▼ 버튼 기다림',
    0xFC: '줄바꿈(시작 칸이면 안 함)',
    0xFD: '줄바꿈 뒤 ▼ 버튼 기다림',
    0xFE: '줄바꿈(언제나)',
    0xFF: '끝(줄바꿈·。 없이)',
}


def _rows_to_lines(rows):
    """(탁점 행, 글자 행) 쌍들을 메시지 바이트 순서(탁점·반탁점이 글자 앞)로. 빈 줄과 앞뒤 공백은 뺀다."""
    out = []
    for marks, chars in rows:
        bs = []
        for m, c in zip(marks, chars):
            if m in (0x3D, 0x3E):
                bs.append(m)
            bs.append(c)
        while bs and bs[-1] == 0:
            bs.pop()
        while bs and bs[0] == 0:
            bs.pop(0)
        if bs:
            out.append(bs)
    return out


def line_width(ram):
    """$54 가 전투 창 폭(18)이면 24칸, 아니면 22칸. 대사가 끝나 다른 창(명령 창 등)이 열리면 $54 가
    그 창 값으로 바뀌므로, 필드 쪽은 $54 를 그대로 믿지 않는다."""
    return BATTLE_W if ram[WIDTH] == BATTLE_W else FIELD_W


def buffer_lines(ram):
    """RAM 덤프의 창 줄 버퍼에서 지금 찍는 줄까지.
    전투 창은 메시지마다 버퍼를 지우지 않고 앞 칸부터 덮어써서 지난 메시지의 탁점이 남는다."""
    w = line_width(ram)
    n = min((ram[LINE_NO] - 1) // 2 + 1, LINES)
    return _rows_to_lines([(ram[LINE_BUF + 2 * i * w:][:w], ram[LINE_BUF + (2 * i + 1) * w:][:w])
                           for i in range(n)])


def screen_lines(ram, nt):
    """전투 창은 nametable 에 바로 찍으므로 화면 쪽에서 읽는다: 줄 i 의 글자 행은 $13 + 2i + 1, 열은 $53 부터."""
    w, x = ram[WIDTH], ram[ORIGIN_X]
    n = min((ram[LINE_NO] - 1) // 2 + 1, LINES)
    rows = []
    for i in range(n):
        y = SCREEN_ROW + 2 * i + 1
        rows.append((nt[(y - 1) * 32 + x:][:w], nt[y * 32 + x:][:w]))
    if any(b >= GLYPH_END for r in rows for b in r[1]):
        return []   # 창 틀 타일이 보이면 명령 창 등이 그 자리를 덮은 것
    return _rows_to_lines(rows)


def dump_lines(ram_path):
    """덤프 하나의 창 줄. 전투 창($54 = 18)이고 옆에 .nt 덤프가 있으면 화면에서 읽는다."""
    ram = open(ram_path, 'rb').read()
    nt_path = ram_path[:-4] + '.nt' if ram_path.endswith('.ram') else None
    if ram[WIDTH] == BATTLE_W and nt_path and os.path.exists(nt_path):
        return screen_lines(ram, open(nt_path, 'rb').read()), 'nametable', ram
    return buffer_lines(ram), '창 줄 버퍼', ram


def off(bank, addr):
    return bank * 0x4000 + (addr & 0x3FFF)


class Rom:
    def __init__(self, data):
        self.prg = ines.prg(data)

    def byte(self, bank, addr):
        return self.prg[off(bank, addr)]

    def word(self, bank, addr):
        return self.byte(bank, addr) | self.byte(bank, addr + 1) << 8

    def start(self, msg):
        block = msg >> 5
        ptr = self.word(BLOCKS[0], BLOCKS[1] + 2 * block)
        n = 0
        while block >= self.byte(BANK_BOUNDS[0], BANK_BOUNDS[1] + n):
            n += 1
        return (WORD_BANK if n == 5 else n), ptr

    def dict_word(self, k, c):
        """사전 단어: 그룹 (k << 1 | c bit5), 그 안 c & 1F 번째, FE 로 끝나는 글자 바이트."""
        bank, addr = WORD_BANK, self.word(WORDS[0], WORDS[1] + 2 * ((k << 1) | (c >> 5 & 1)))
        for _ in range(c & 0x1F):
            while self.byte(bank, addr) != WORD_END:
                addr += 1
            addr += 1
        out = []
        while (b := self.byte(bank, addr)) != WORD_END:
            out.append(b)
            addr += 1
        return out


class Codes:
    """6비트 부호를 0F:$DF99 와 같은 순서로 읽는다: 3바이트에 4개, 뱅크 끝 $BFD8 에서 다음 뱅크."""

    def __init__(self, rom, bank, ptr):
        self.rom, self.bank, self.ptr, self.phase = rom, bank, ptr, 0

    def _advance(self):
        self.ptr += 1
        if self.ptr == 0xBFD8:
            self.bank += 1
            self.ptr = 0x8000
            if self.bank == 5:
                self.bank, self.ptr = WORD_BANK, 0xA500

    def next(self):
        prev = self.rom.byte(self.bank, self.ptr)
        phase = self.phase & 3
        self.phase += 1
        if phase == 0:
            return prev >> 2
        self._advance()
        cur = self.rom.byte(self.bank, self.ptr)
        if phase == 1:
            return (prev & 3) << 4 | cur >> 4
        if phase == 2:
            return (prev & 0x0F) << 2 | cur >> 6
        return prev & 0x3F


NO_AUTO_PERIOD = {0x6E, 0x6D, 0x3F, 0xFB, 0xFE, 0xF4, 0xFF}   # ！ ？ 。 과 제어 몇 개


def shown(bs):
    """화면에 나오는 순서: 끝 F9 앞 글자가 NO_AUTO_PERIOD 가 아니면 게임이 。 를 넣는다(16:$805A)."""
    if bs and bs[-1] == 0xF9 and len(bs) > 1 and bs[-2] not in NO_AUTO_PERIOD:
        return bs[:-1] + [0x3F, 0xF9]
    return bs


def message_codes(rom, msg):
    """메시지 하나의 시작 (뱅크, 주소, 단계 0~3) 과 6비트 부호 목록(끝 부호 39 까지).
    첫 부호는 그 주소 바이트의 bit7·1·3·5(단계 0·1·2·3)에서 시작한다."""
    codes = Codes(rom, *rom.start(msg))
    for _ in range(msg & 0x1F):
        while codes.next() != END:
            pass
    at = (codes.bank, codes.ptr, codes.phase & 3)
    out = []
    while True:
        c = codes.next()
        out.append(c)
        if c > 0x3C:
            out.append(codes.next())
        elif c == END:
            return at, out


def decode(rom, codes):
    """6비트 부호 목록을 글자 바이트로(16:$86BA). 3C 는 가나 모드, 3D~3F 는 다음 부호와 함께 사전 단어."""
    kana, out, it = 0, [], iter(codes)
    for c in it:
        if c == 0x3C:
            kana ^= 1
        elif c > 0x3C:
            out += rom.dict_word(c - 0x3D, next(it))
        else:
            b = rom.byte(CHARS[0], CHARS[1] + kana * 64 + c)
            out += rom.dict_word(0, 0) if b == 0xF0 else [b]
    return out


def message_bytes(rom, msg):
    """메시지 하나를 글자 바이트 목록으로(끝 부호의 글자 바이트까지 포함)."""
    return decode(rom, message_codes(rom, msg)[1])


def block_count():
    return (BANK_BOUNDS[1] - BLOCKS[1]) // 2


def valid_messages(rom):
    """실제로 있는 메시지 번호. 블록 안에서 다음 블록 시작 위치에 닿기 전까지만 센다
    (32개가 안 되는 블록은 뒤 번호가 다음 블록 글을 가리킨다)."""
    out = []
    n = block_count()
    text_end = (WORD_BANK, rom.word(WORDS[0], WORDS[1]))   # 본문 바로 뒤에 사전이 온다
    for b in range(n):
        nxt = rom.start((b + 1) << 5) if b + 1 < n else None
        c = Codes(rom, *rom.start(b << 5))
        for m in range(32):
            if nxt and (c.bank, c.ptr + (1 if c.phase % 4 else 0)) == nxt and (c.phase % 4 == 0 or m):
                break
            if nxt and c.bank == nxt[0] and c.ptr + (1 if c.phase % 4 else 0) > nxt[1]:
                break
            if (c.bank, c.ptr + (1 if c.phase % 4 else 0)) >= text_end and c.bank == WORD_BANK:
                return out
            out.append(b << 5 | m)
            while c.next() != END:
                pass
    return out


AUTO_QUOTE_FROM = 0x0500    # 이 번호부터 메시지 앞에 「＊「」 를 저절로 넣음(첫 바이트가 F1 이면 빼고). 16:$85C5 가 보는
                            # $058B 는 16:$8672 만 쓰고 값은 언제나 메시지 번호 위 바이트라 부르는 쪽과 상관없다
AUTO_PREFIX = [0x70, 0x6F]
SUBST = {0xEF, 0xF2, 0xF3, 0xF5, 0xF6, 0xF7, 0xF8}   # 메시지 밖 인자로 글자를 넣는 제어
SUBST_MAX = 12                                       # 치환 하나가 넣는 글자 바이트 수의 상한(이름 + もどき 등)


def auto_quote(m, bs):
    """메시지 m(글자 바이트 bs)을 찍을 때 앞에 「＊「」 가 붙는지. 대화·이벤트·전투 어느 쪽에서 불러도 같다."""
    return m >= AUTO_QUOTE_FROM and bs[0] != 0xF1


def _match(line, stream, i, j):
    """line[i:] 이 stream[j:] 의 앞부분과 맞으면 다 맞은 뒤의 stream 위치. 치환 제어는 글자 0~SUBST_MAX 개와 맞는다."""
    if i == len(line):
        return j
    if j == len(stream):
        return None
    if stream[j] in SUBST:
        for k in range(min(SUBST_MAX, len(line) - i), -1, -1):
            r = _match(line, stream, i + k, j + 1)
            if r is not None:
                return r
        return None
    if stream[j] != line[i]:
        return None
    return _match(line, stream, i + 1, j + 1)


def compare(rom, msgs, ram_path):
    """덤프의 창 줄들이 메시지 글자열(차례로 찍은 메시지들, 치환 밖의 제어 바이트는 뺌)에 그 순서대로 들어 있는지.
    0500 이상 메시지는 자동 「＊「」 도 넣어 비교한다."""
    lines, where, ram = dump_lines(ram_path)
    stream = []
    for m in msgs:
        bs = shown(message_bytes(rom, m))
        if auto_quote(m, bs):
            bs = AUTO_PREFIX + bs
        stream += [b for b in bs if b < CONTROL_MIN or b in SUBST]
    pos = 0
    for ln in lines:
        at = next((r for j in range(pos, len(stream)) if (r := _match(ln, stream, 0, j)) is not None), None)
        if at is None:
            print(f'{ram_path}: 다름 — 화면 「{text(ln)}」')
            return False
        pos = at
    names = ','.join(f'{m:04X}' for m in msgs)
    print(f'{ram_path}: {where} {len(lines)}줄 모두 메시지 {names} 에 순서대로 있음')
    return bool(lines)


def control_table(rom):
    """제어 바이트마다 (처리기 주소, 그 바이트를 쓰는 메시지 수, 뜻)."""
    used = {}
    for m in valid_messages(rom):
        for b in set(message_bytes(rom, m)):
            if b >= CONTROL_MIN:
                used[b] = used.get(b, 0) + 1
    return [(b, rom.word(HANDLERS[0], HANDLERS[1] + 2 * (~b & 0xFF)), used.get(b, 0), CONTROLS[b])
            for b in range(CONTROL_MIN, 0x100)]


WINDOW_GROUPS = (0x16, 0xA572)   # 그룹마다 항목 포인터 표 주소(그룹 0 = $A578, 1 = $A674)
WINDOW_LIMITS = (0x16, 0xA576)   # 그룹마다 「항목 번호 × 2」 가 이 값보다 작으면 루틴, 아니면 문자열
WINDOW_COUNTS = (0x7E, 0x31)     # 그룹마다 항목 수(다음 표 시작·포인터가 줄어드는 곳까지)


def window_entry(rom, g, n):
    """창 문자열 표 그룹 g 의 항목 n: ('code', 주소) 또는 ('str', 주소, 바이트). 길이는 다음 항목 주소까지."""
    table = rom.word(WINDOW_GROUPS[0], WINDOW_GROUPS[1] + 2 * g)
    addr = rom.word(0x16, table + 2 * n)
    if 2 * n < rom.byte(WINDOW_LIMITS[0], WINDOW_LIMITS[1] + g):
        return ('code', addr)
    end = rom.word(0x16, table + 2 * n + 2)
    return ('str', addr, [rom.byte(0x16, a) for a in range(addr, end)])


def window_bytes(rom, g, n):
    """항목 n 을 찍히는 글자 바이트로(16:$9783). 80 이상 바이트 b 는 같은 그룹 항목 b & 7F:
    루틴이면 그 자리에 (‘code’, 번호), 문자열이면 그 바이트를 넣되 그 안의 80 이상은 건너뜀(16:$97B0)."""
    e = window_entry(rom, g, n)
    if e[0] == 'code':
        return [('code', n)]
    out = []
    for b in e[2]:
        if b < 0x80:
            out.append(b)
            continue
        sub = window_entry(rom, g, b & 0x7F)
        if sub[0] == 'code':
            out.append(('code', b & 0x7F))
        else:
            out += [c for c in sub[2] if c < 0x80]
    return out


def window_text(rom, g, n):
    parts, run = [], []
    for b in window_bytes(rom, g, n):
        if isinstance(b, tuple):
            parts.append(text(run))
            run = []
            e = window_entry(rom, g, b[1])
            parts.append(f'〈{b[1]:02X} 16:${e[1]:04X}〉')
        else:
            run.append(b)
    parts.append(text(run))
    return ''.join(parts)


WINDOW_RECORDS = (0x16, 0xA48A)   # 창 번호 × 2 → 창 레코드 주소(16:$94B5 가 16:$A488 에서 이 주소를 읽음)
WINDOW_COUNT = 0x73               # 16:$A572(창 문자열 표) 앞까지 116개. 마지막 73 은 끝을 정할 다음 포인터가 없어 뺌
# 목록 바이트 Dn 의 n(16:$98EE). 0~5 는 레코드의 항목을 그대로, 6 이상은 표 16:$9905 의 루틴이 항목을 만든다.
LIST_KINDS = {0x6: '16:$9EC3', 0x7: '16:$9ED5', 0x8: '16:$9C18', 0x9: '16:$9E28', 0xA: '16:$9E99',
              0xB: '16:$9EE7', 0xC: '16:$A328', 0xD: '16:$A083', 0xE: '16:$A022', 0xF: '16:$9EFC'}

# 아래 뜻 표의 근거는 fc/dq4/docs/dq4-text-format.md 의 「창 레코드」 절.
LIST_MEANING = {
    0x0: '고르지 않는 창(표시만)', 0x1: '고르는 창', 0x2: '고르는 창', 0x3: '고르는 창', 0x4: '고르는 창',
    0x5: '고르는 창', 0x6: '동료 $F7 의 소지품 8칸', 0x7: '동료 $F7 의 필드 주문', 0x8: '전투 주문 한 쪽(별칭 번호가 쪽)',
    0x9: '전투 도구', 0xA: '장비 칸에 넣을 수 있는 소지품', 0xB: '표시 속도 1~8', 0xC: '(쓰는 창 없음)',
    0xD: '이름 입력 글자판', 0xE: '카지노 코인', 0xF: '수 입력 칸',
}
# 창 문자열 표의 루틴 항목 (그룹, 번호) → 찍는 것.
ITEM_MEANING = {
    (0, 0x00): '동료 이름($F7)', (0, 0x01): '주문 이름(줄 $F3, 모르는 주문은 ？)', (0, 0x02): '골드($6157, 5자리)',
    (0, 0x03): '직업 이름', (0, 0x04): '성별', (0, 0x05): '레벨', (0, 0x06): '금액 입력 칸 0000',
    (0, 0x07): '장비 칸 이름(ぶき·よろい·たて·かぶと, 별칭 번호로)', (0, 0x08): '소지품 이름(줄 $F3)',
    (0, 0x09): '장비 후보 이름(E 표시)', (0, 0x0A): '장비 칸마다 장비한 아이템(앞에 E)', (0, 0x0B): '상점 품목 이름($07BD)',
    (0, 0x0C): '맡긴 아이템 이름($61DB)', (0, 0x0D): 'ちから', (0, 0x0E): '앞 수 항목의 다음 능력치',
    (0, 0x0F): '일행 HP·MP 표(이름, H 지금·최대, M 지금·최대)', (0, 0x10): 'こうげき力',
    (0, 0x11): '커서·화살표 기호', (0, 0x12): 'ルーラ 행선지 이름', (0, 0x13): '동료 이름 + 그 품목을 장비할 수 있으면 Ｅ',
    (0, 0x14): '전투 몬스터 무리 이름', (0, 0x15): '전투 몬스터 무리 마릿수', (0, 0x16): '번호 + 동료 이름(대열 바꾸기)',
    (0, 0x17): '대열 칸 번호 + 이름(빈 칸 ····)', (0, 0x18): '전투 상태 창 한 줄(H, M, 직업 첫 글자：레벨)',
    (0, 0x19): '지금 작전 이름', (0, 0x1A): '작전 고르기 항목', (0, 0x1B): '번호 + 동료 이름', (0, 0x1C): '동료 이름(전투 대상)',
    (0, 0x1D): 'H 값', (0, 0x1E): 'M 값', (0, 0x1F): '직업 첫 글자：레벨', (0, 0x20): '대열 자리 이름',
    (0, 0x21): '값(E00 사는 값, E01 파는 값)', (0, 0x22): '동료 이름($07B0 목록)', (0, 0x23): '번호 + 동료 이름',
    (0, 0x24): '전투 상태 창 머리(╴ + 이름)', (0, 0x25): '$F7 을 수로', (0, 0x26): '장비 표시 E',
    (0, 0x27): '전투 도구 이름', (0, 0x28): '제목 앞 ╴', (0, 0x29): '필드 메시지 창 줄', (0, 0x2A): '전투 메시지 창 줄',
    (0, 0x2B): '작전 이름 앞쪽', (0, 0x2C): '작전 이름 뒤쪽', (0, 0x2D): '몬스터 무리 이름(전투 시험)',
    (0, 0x2E): '몬스터 무리 마릿수(전투 시험)', (0, 0x2F): '몬스터 이름 목록(전투 시험)', (0, 0x30): '이름 입력 칸',
    (0, 0x31): '이름 입력 글자판 한 줄', (0, 0x32): '번호 + 커서 + 동료 이름', (0, 0x33): '동료 이름(마차)',
    (0, 0x34): '최대 HP', (0, 0x35): '장비를 바꾼 뒤 こうげき力', (0, 0x36): '장비를 바꾼 뒤 しゅび力',
    (0, 0x37): '작전 창 いれかえをする',
    (1, 0x00): '전투 상태 한 명분(H, M, 직업：레벨)', (1, 0x01): '타이틀 메뉴 항목', (1, 0x02): '모험의 서 칸(E01 이면 이름까지)',
    (1, 0x03): '성별 고르기', (1, 0x04): '주문 이름', (1, 0x05): '＊．．', (1, 0x06): '전투 몬스터 이름($6E45)',
    (1, 0x07): '전투 몬스터 값', (1, 0x08): '장 + 주인공 이름(모험의 서)', (1, 0x09): '레벨(모험의 서)',
}
# 수 항목이 $03DC 로 고르는 값. 표 16:$BAFE 의 바이트가 전투 쪽 해석기(BRK 00 03)의 값 번호.
STAT_TABLE = (0x16, 0xBAFE)
STAT_NAMES = ['ちから', 'すばやさ', 'たいりょく', 'かしこさ', 'うんのよさ', '최대 HP', '최대 MP', 'こうげき力', 'しゅび力',
              '경험치', '레벨', 'HP', 'MP', '?']
# 항목 루틴 80~9F: (표 $03D7, b & 1F) → 하는 일. 표 0 은 1A 까지, 표 1 은 06 까지가 줄 수를 돌려주는 루틴이고
# 목록을 셀 때($F5 bit7)만 돈다. 나머지는 항목마다 돈다(16:$96E2, 한계 16:$A6DC).
ROUTINE_TABLES = (0x16, 0xA6D8)
ROUTINE_LIMITS = (0x16, 0xA6DC)
ROUTINE_MEANING = {
    (0, 0x00): '줄 수 = 동료 전원(걸러내기 00)', (0, 0x01): '줄 수 = 동료(걸러내기 08)',
    (0, 0x02): '줄 수 = 동료(걸러내기 80)', (0, 0x03): '줄 수 = 전투에 나가는 동료(걸러내기 40)',
    (0, 0x04): '줄 수 = 전투 동료 중 $F7 을 뺀 사람, $07B0 에 목록', (0, 0x05): '줄 수 7(필드 주문)',
    (0, 0x06): '줄 수 4(장비 칸)', (0, 0x07): '줄 수 = 주문이 있는 쪽 수 × 3(전투 주문 2열)', (0, 0x08): '줄 수 5(HP·MP 표)',
    (0, 0x09): '줄 수 8(소지품)', (0, 0x0A): '줄 수 = ルーラ 행선지 수', (0, 0x0B): '줄 수 = 장비 칸에 넣을 수 있는 소지품 수',
    (0, 0x0C): '줄 수 = 대열에서 아직 안 고른 칸', (0, 0x0D): '줄 수 4(대열 칸, $07B0 채움)',
    (0, 0x0E): '줄 수 6 또는 3(작전, 열 수로)', (0, 0x0F): '줄 수 3(전투 상태, 몬스터 AE·BC 와 싸울 때는 2)',
    (0, 0x10): '줄 수 = 몬스터 무리 수, $07B0 에 무리', (0, 0x11): '줄 수 0/1(いれかえ 를 보일지)',
    (0, 0x12): '줄 수 4(전투 도구)', (0, 0x13): '줄 수 = 상점 품목 수($07C4)', (0, 0x14): '줄 수 = 맡긴 아이템 수',
    (0, 0x15): '줄 수 = $F7 의 주문 수', (0, 0x16): '줄 수 1 = $F7 이 ぶきや(トルネコ)일 때만(どうする 의 みる)',
    (0, 0x17): '줄 수 4(메시지 창)', (0, 0x18): '줄 수 117(몬스터 목록, 전투 시험)', (0, 0x19): '줄 수 4(전투 시험 무리)',
    (0, 0x1A): '줄 수 = 이름 입력 글자판 줄', (0, 0x1B): '$F5 bit5 를 켬', (0, 0x1C): '예/아니오 소리(BRK 86 FB)',
    (0, 0x1D): '$03DB = $07B0', (0, 0x1E): '$07B4 bit2 를 끔',
    (1, 0x00): '줄 수 = 타이틀 메뉴 항목(쓴 모험의 서에 따라)', (1, 0x01): '줄 수 = 글자판($07B7)',
    (1, 0x02): '줄 수 0/1', (1, 0x03): '줄 수 = 모험의 서 칸', (1, 0x04): '줄 수 2', (1, 0x05): '줄 수 3',
    (1, 0x06): '줄 수 = 전투 몬스터 무리', (1, 0x07): '$F5 bit1 을 켬(전투 명령 창)',
}
# C1 nn(표 16:$A734): 고른 줄($F8)을 결과로 바꾸는 루틴. 머리 바이트 1 bit3 이면 열 때 같은 표의 0번을 부른다.
C1_MEANING = {
    0x00: '$F8 → 동료 번호(걸러내기 $03DD)', 0x01: '$F8 → 동료 번호(걸러내기 80)', 0x02: '$F8 = $07B0[$F8]',
    0x03: '대열 바꾸기: 고른 동료를 $07B0 에 더함', 0x04: 'おわり 줄이면 $F8 += F0', 0x05: '$07B0~$07B3 → $6E~$71(새 대열)',
    0x06: '타이틀 메뉴: 줄 → 할 일 번호', 0x07: '모험의 서: 줄 → 칸 번호', 0x08: '장비: 고른 줄 → 아이템($07B1)',
    0x09: '$07B5~$07B8 을 0 으로', 0x0A: '$07B4 |= 50, $F5 |= 08',
}
# 자리 루틴(머리 바이트 0 위 니블이 0, 표 16:$A72C). v = 별칭 번호($03D5 >> 4).
PLACE_MEANING = {
    0: 'HP·MP 표: 사람 수 n(1~5)으로 x·폭 = 16:$B875[n−1], y = v 0 → 4, 1 → 16. 6명 이상이면 둘로 나눠 둘째 몫을 곁 창 0F 에',
    1: '전투 상태 창: 전투 동료 n(1~4)으로 x·폭 = 16:$B89F[2n+v], y = v 0 → 2, 1 → 20',
    2: '작전 이름 창: 폭 12, x = v 0 → 16, 1 → 4',
    3: '작전 두 줄 창: x24 폭 6, y = 몬스터 $6E45 가 AE·BC 면 2, 아니면 4',
}
FLAG_MEANING = {0x0: '$F5 |= 41', 0xF: '커서를 옮길 때마다 곁 창을 다시 그림($F5 bit4)'}
FLAG_PAGE = '목록을 쪽으로 자름($03D2 = min($03D1 + ($03D5 & 0F), 줄 수), 넘치면 $F5 bit6). 값은 보지 않음'
MODE_MEANING = '$03C6 = n: 상점 값 0 사는 값·1 파는 값, 모험의 서 0 빈 칸·1 이름, 이름 입력 8 글자판'


def token_meaning(t):
    """본문 갈래 하나의 뜻(위 표에서). 모르는 것은 빈 문자열."""
    kind = t[0]
    if kind == 'item':
        return ITEM_MEANING.get((t[1], t[2]), '') if t[3].startswith('〈') else ''
    if kind == 'cond':
        return ROUTINE_MEANING.get((t[2], t[1]), '')
    if kind == 'list':
        return LIST_MEANING.get(t[1], '')
    if kind == 'call':
        return C1_MEANING.get(t[1], '')
    if kind == 'flag':
        return FLAG_MEANING.get(t[1], FLAG_PAGE)
    if kind == 'mode':
        return MODE_MEANING
    if kind == 'side':
        return f'곁 창 {t[1]:02X} 을 함께 엶'
    return ''


def window_record(rom, n):
    """창 n 의 레코드: (주소, 바이트, 별칭). 첫 바이트의 위 니블이 1 인 레코드는 다음 창의 레코드를 쓰고
    처음 것만 $03D5 = 낮은 니블 × 16 + 1 로 둔다(16:$94DB). 길이는 다음 포인터까지(16:$94F9)."""
    alias = []
    while True:
        addr = rom.word(WINDOW_RECORDS[0], WINDOW_RECORDS[1] + 2 * n)
        end = rom.word(WINDOW_RECORDS[0], WINDOW_RECORDS[1] + 2 * n + 2)
        bs = [rom.byte(0x16, a) for a in range(addr, end)]
        if bs[0] & 0xF0 != 0x10:
            return addr, bs, alias
        alias.append((n, bs[0] & 0x0F))
        n += 1


def window_layout(rom, n):
    """창 n 의 위치·크기·본문(머리 16:$9505, 본문 바이트 갈래 16:$9304·$96B0). x·y·w 는 화면 칸(8화소)."""
    addr, bs, alias = window_record(rom, n)
    b0, b1 = bs[0], bs[1]
    head = 3 if b1 & 0x04 else 2
    lay = {'window': n, 'record': addr, 'alias': alias, 'head': bs[:head],
           'x': 2 * (b0 & 0x0F) if b0 >> 4 else None, 'y': 2 * (b1 >> 4) if b0 >> 4 else None,
           'w': 2 * (b0 >> 4) or None,
           'width_routine': None if b0 >> 4 else b0 & 0x0F, 'cols': b1 & 0x03,
           'init_routine': bool(b1 & 0x08), 'cursor': bs[2] if head == 3 else None, 'body': bs[head:]}
    toks, group, i, body = [], 0, 0, lay['body']
    while i < len(body):
        b = body[i]
        if b < 0x80:
            e = window_entry(rom, group, b)
            toks.append(('item', group, b, window_text(rom, group, b) if e[0] == 'str' else f'〈{b:02X}〉'))
        elif b < 0xA0:
            toks.append(('cond', b & 0x1F))
        elif b < 0xA4:
            toks.append(('condtable', b & 0x03))
        elif b < 0xA8:
            group = b & 0x03
            toks.append(('group', group))
        elif b < 0xB0:
            toks.append(('indent', b - 0xA8))
        elif b < 0xC0:
            toks.append(('flag', b & 0x0F))
        elif b in (0xC0, 0xC1) and i + 1 < len(body):
            toks.append(('side' if b == 0xC0 else 'call', body[i + 1]))
            i += 1
        elif b == 0xC6:
            toks.append(('newline',))
        elif b < 0xD0:
            toks.append(('raw', b))
        elif b < 0xE0:
            toks.append(('list', b & 0x0F))
        else:
            toks.append(('mode', b & 0x1F))
        i += 1
    # 80~BF 가 이어진 묶음은 다음 항목을 그리기 전에 뒤에서부터 읽힌다(16:$96B0). 그래서 묶음 안의 A0~A3(표 고르기)는
    # 그 앞에 있는 루틴에 걸리고, 고른 표($03D7)는 다음 묶음까지 남는다.
    table, run = 0, []
    for k, t in enumerate(toks + [('end',)]):
        if t[0] in ('cond', 'condtable', 'group', 'indent', 'flag'):
            run.append(k)
            continue
        for j in reversed(run):
            if toks[j][0] == 'condtable':
                table = toks[j][1]
            elif toks[j][0] == 'cond':
                toks[j] = ('cond', toks[j][1], table)
        run = []
    lay['tokens'] = toks
    # $03CB(셋째 바이트, 없으면 3)의 bit7-6 이 1 이면 틀을 영역 안쪽 한 칸에 그림(전투 메시지 창 3D·62).
    lay['inset'] = head == 3 and bs[2] >> 6 == 1 and lay['w'] is not None
    lay['frame'] = (lay['x'] + 1, lay['y'], lay['w'] - 2) if lay['inset'] else (lay['x'], lay['y'], lay['w'])
    return lay


def routine_address(rom, table, idx):
    """항목 루틴 (표, 번호)의 주소와 줄 수 루틴인지. 표의 값은 RTS 로 뛰는 주소 − 1."""
    base = rom.word(ROUTINE_TABLES[0], ROUTINE_TABLES[1] + 2 * table)
    counting = 2 * idx < rom.byte(ROUTINE_LIMITS[0], ROUTINE_LIMITS[1] + table)
    return rom.word(0x16, base + 2 * idx) + 1, counting


def meaning_lines(rom):
    """창 본문 바이트의 뜻 표(--items)."""
    out = ['# 루틴 항목(창 문자열 표의 앞쪽 항목, 그룹:번호 주소 뜻)']
    for g, count in enumerate(WINDOW_COUNTS):
        for n in range(count):
            e = window_entry(rom, g, n)
            if e[0] == 'code':
                out.append(f'{g}:{n:02X} 16:${e[1]:04X}  {ITEM_MEANING.get((g, n), "")}')
    stats = [rom.byte(STAT_TABLE[0], STAT_TABLE[1] + i) for i in range(len(STAT_NAMES))]
    out.append('# 수 항목의 값 번호($03DC → 16:$BAFE)')
    out += [f'{i:X} {v:02X}  {name}' for i, (v, name) in enumerate(zip(stats, STAT_NAMES))]
    out.append('# 항목 루틴 80~9F(표:바이트 주소 갈래 뜻)')
    for (table, idx), desc in sorted(ROUTINE_MEANING.items()):
        a, counting = routine_address(rom, table, idx)
        out.append(f'{table}:{0x80 | idx:02X} 16:${a:04X} {"줄 수" if counting else "늘 돎"}  {desc}')
    out.append('# 목록 Dn')
    out += [f'D{n:X} {LIST_KINDS.get(n, "16:$9919"):9s} {LIST_MEANING[n]}' for n in range(16)]
    out.append('# C1 nn(16:$A734)')
    for n, desc in C1_MEANING.items():
        out.append(f'C1 {n:02X} 16:${rom.word(0x16, 0xA734 + 2 * n) + 1:04X}  {desc}')
    out.append('# 자리 루틴(16:$A72C)')
    for n, desc in PLACE_MEANING.items():
        out.append(f'{n} 16:${rom.word(0x16, 0xA72C + 2 * n) + 1:04X}  {desc}')
    out.append(f'# B0~BF: B0 {FLAG_MEANING[0]}, BF {FLAG_MEANING[0xF]}, B1~BE {FLAG_PAGE}')
    out.append(f'# E0~FF: {MODE_MEANING}')
    return out


_PUT = re.compile(r'(\d+)([:m])([0-9A-F]{2})')


def _put_text(cells):
    """textitem.lua 의 put 줄(열:바이트, 열m탁점)을 열 순서로 글자로. FF(빈 칸 채움)는 ·, 80 이상은 {XX}."""
    by = {}
    for t in cells:
        m = _PUT.fullmatch(t)
        by.setdefault(int(m[1]), [None, None])[0 if m[2] == 'm' else 1] = int(m[3], 16)
    out = ''
    for c in sorted(by):
        mark, ch = by[c]
        s = '' if ch is None else '·' if ch == 0xFF else text([ch]) if ch < GLYPH_END else f'{{{ch:02X}}}'
        out += s + ({0x3D: '\u3099', 0x3E: '\u309a'}.get(mark, '') if mark is not None else '')
    return unicodedata.normalize('NFC', out.rstrip('·'))


def trace_lines(path):
    """textitem.lua 의 item.txt 를 창 열기마다 한 줄로: 항목(그룹:번호)「찍은 글」, ?표:루틴→줄 수, 목록·C1·자리."""
    rows, cur, toks, last_cond = [], None, [], None
    for line in open(path):
        line = line.rstrip('\n')
        if line.startswith('  put '):
            if toks:
                toks[-1] += '「' + _put_text(line[6:].split()) + '」'
            continue
        p = line.split()
        if len(p) < 2:
            continue
        f = dict(x.split('=', 1) for x in p[2:] if '=' in x)
        kind = p[1]
        if kind == 'open':
            if cur is not None and toks:
                rows.append(f'{cur} ' + ' '.join(toks))
            cur, toks = f['W'], []
        elif kind == 'top':
            toks.append(f['n'] if f['g'] == '0' else f'{f["g"]}:{f["n"]}')
        elif kind == 'sub':
            toks.append(f'<{f["n"]}>')
        elif kind == 'cond':
            last_cond = (int(f['b'], 16), int(f['T']), int(f['F5'], 16) & 0x80)
        elif kind == '=>' and last_cond:
            b, table, counting = last_cond
            if counting:
                toks.append(f'?{table}:{b:02X}→{f["3D2"]}')
            last_cond = None
        elif kind in ('list', 'place', 'c1', 'mode', 'init'):
            toks.append(f'{kind}{f["n"]}')
    if cur is not None and toks:
        rows.append(f'{cur} ' + ' '.join(toks))
    return rows


def window_callers(rom):
    """롬에서 창을 여는 BRK(뱅크 16 함수 07·09, `00 07 6F nn`·`00 09 6F nn`)를 찾아 창 번호 → [(뱅크, 주소)].
    함수 09 는 $F7 = $07B9 로 두고 연다(16:$89D0). 바이트열로 찾으므로 데이터가 우연히 같은 꼴이면 섞일 수 있다."""
    out = {}
    for m in re.finditer(rb'\x00[\x07\x09]\x6f', rom.prg):
        o = m.start()
        if o + 3 < len(rom.prg):
            out.setdefault(rom.prg[o + 3], []).append((o // 0x4000, 0x8000 + o % 0x4000))
    return out


def token_str(t):
    kind = t[0]
    if kind == 'item':
        return t[3] if t[1] == 0 else f'{t[1]}:{t[3]}'
    if kind == 'list':
        return f'[D{t[1]:X}' + (f' {LIST_KINDS[t[1]]}' if t[1] in LIST_KINDS else '') + ']'
    if kind == 'newline':
        return '/'
    if kind == 'cond' and t[2]:
        return f'?{t[2]}:{t[1]:02X}'
    return {'cond': '?{:02X}', 'condtable': '?표{}', 'group': '그룹{}', 'indent': '+{}', 'flag': 'B{:X}',
            'side': '곁창{:02X}', 'call': 'C1({:02X})', 'raw': '{{{:02X}}}', 'mode': 'E{:02X}'}[kind].format(t[1])


def layout_line(lay):
    if lay['w']:
        pos = f'x{lay["x"]:2d} y{lay["y"]:2d} w{lay["w"]:2d}' + (' 틀안쪽' if lay['inset'] else '')
    else:
        pos = f'자리 루틴 {lay["width_routine"]}  '
    alias = ''.join(f' ={m:02X}({c})' for m, c in lay['alias'])
    head = ' '.join(f'{b:02X}' for b in lay['head'])
    body = ' '.join(token_str(t) for t in lay['tokens'])
    return f'{lay["window"]:02X} 16:${lay["record"]:04X} {pos} 열{lay["cols"]} [{head}]{alias}  {body}'


def _ppu_cells(path):
    """textlayout.lua 의 ppu.txt 를 열기 순번 → {nametable 주소: 그 열기 뒤 처음 쓴 값} 으로.
    창을 닫을 때 같은 칸에 배경을 되돌려 쓰므로 틀은 처음 값에서 찾는다."""
    cells = {}
    for line in open(path):
        if line.strip():
            k, a, first, _ = line.split()
            cells.setdefault(int(k), {})[int(a, 16)] = int(first, 16)
    return cells


def measure_window(cells, scroll_x, scroll_y, at=None):
    """한 진입에서 nametable 에 쓴 ┌(86)와, 그 오른쪽 ┐(89)·아래 └(87)로 화면 칸 (x, y, w, h).
    at=(x, y) 의 ┌ 가 있으면 그것을, 없으면 처음 쓴 ┌ 를 쓴다(같은 진입에서 다른 창을 다시 그리기도 함).
    화면 칸 = (nametable 화소 − 스크롤) / 8 을 64×60 칸으로 감음."""
    def screen(a):
        t, off = (a - 0x2000) >> 10, (a - 0x2000) & 0x3FF
        return ((((t & 1) * 256 + (off & 0x1F) * 8 - scroll_x) // 8) % 64,
                ((((t >> 1) & 1) * 240 + (off >> 5) * 8 - scroll_y) // 8) % 60)
    grid = {screen(a): v for a, v in cells.items() if (a - 0x2000) & 0x3FF < 0x3C0}
    tl = next((screen(a) for a, v in cells.items() if v == 0x86 and (a - 0x2000) & 0x3FF < 0x3C0), None)
    if at in grid and grid[at] == 0x86:
        tl = at
    if not tl:
        return None
    x, y = tl
    w = next((k + 1 for k in range(1, 64) if grid.get((x + k, y)) == 0x89), None)
    h = next((k + 1 for k in range(1, 60) if grid.get((x, y + k)) == 0x87), None)
    return x, y, w, h


def compare_layouts(rom, d):
    """textlayout.lua 결과 폴더 d 의 창 열기마다 레코드의 x·y·w 와 nametable 의 틀 자리를 견준다. (같음, 다름) 수."""
    cells = _ppu_cells(os.path.join(d, 'ppu.txt'))
    opens = [ln.split() for ln in open(os.path.join(d, 'open.txt')) if ' open' in ln]
    same_n = diff_n = 0
    for k, row in enumerate(opens, 1):
        f = dict(p.split('=', 1) for p in row[2:] if '=' in p)
        n = int(f['F6'], 16)
        if n >= WINDOW_COUNT:
            continue
        lay = window_layout(rom, n)
        # 틀은 NMI 가 나중 프레임에 옮기므로 다음 창을 연 뒤에 쓰이기도 한다. 이 열기 뒤의 쓰기를 모두 본다.
        later = {}
        for j in sorted(c for c in cells if c >= k):
            later.update({a: v for a, v in cells[j].items() if a not in later})
        got = measure_window(later, *(int(v) for v in f['scroll'].split(',')), at=(lay['x'], lay['y']))
        want = lay['frame']
        if not got:
            print(f'{d}: 열기 {k} 창 {n:02X} 틀을 못 찾음')
            continue
        same = all(w is None or w == g for w, g in zip(want, got))
        same_n, diff_n = same_n + same, diff_n + (not same)
        print(f'{d}: 열기 {k} 창 {n:02X} 레코드 x{want[0]} y{want[1]} w{want[2]} / nametable x{got[0]} y{got[1]} '
              f'w{got[2]} h{got[3]} {"같음" if same else "다름"}')
    return same_n, diff_n


# 포팅용 기호 텍스트. 글자는 유니코드로, 제어 바이트는 {이름} 이나 {이름:인자} 로, 그 밖은 {XX}(16진 한 바이트).
# 탁점·반탁점(3D·3E) + 글자는 합친 글자 하나로 쓴다. 탁점 글자 타일 65~69(ドじだどぶ)와 겹치므로 하나만 맨 글자로:
# 롬은 ド 를 대개 타일 65 로, じだどぶ 는 언제나 탁점으로 쓰니 ド 는 타일, 3D+ト 는 {3D}ト, 타일 66~69 는 {66} 처럼.
SYMBOLS = {
    0xED: 'FLASH', 0xEE: 'SOUND', 0xEF: 'STR', 0xF0: 'LINE_F0', 0xF1: 'NOINDENT', 0xF2: 'NAMEPTR',
    0xF3: 'SPELLSTEM', 0xF4: 'PAUSE', 0xF5: 'SPELL', 0xF6: 'NAME', 0xF7: 'ITEM', 0xF8: 'NUM',
    0xF9: 'END', 0xFA: 'ENDLINE', 0xFB: 'WAIT', 0xFC: 'LINE', 0xFD: 'WAITLINE', 0xFE: 'BR', 0xFF: 'STOP',
}
SYMBOL_BYTES = {v: k for k, v in SYMBOLS.items()}
INLINE_ARG = {0xEE}                          # 다음 글자 바이트가 인자(16:$8198 이 16:$803F 로 읽음)
SLOT_ARG = {0xF2, 0xF3, 0xF5, 0xF6, 0xF7}    # 인자 목록 $F9+칸 에서 하나씩. 칸 $5B 는 메시지마다 0(16:$8596)
MARKS = (0x3D, 0x3E)
CHAR_OF = {b: c for b, c in GLYPHS.items() if b not in MARKS and b not in (0x66, 0x67, 0x68, 0x69)}
BYTE_OF = {c: b for b, c in CHAR_OF.items()}
TOKEN = re.compile(r'\{([^{}]*)\}|Ex|.', re.S)


def symbolize(bs, ref=None):
    """글자 바이트를 기호 텍스트로. ref 가 있으면 80 이상 바이트를 ref(b) 로(창 문자열의 항목 부르기)."""
    out, i, slot = [], 0, 0
    while i < len(bs):
        b = bs[i]
        if ref and b >= 0x80:
            out.append(ref(b))
        elif b in MARKS and i + 1 < len(bs) and bs[i + 1] in CHAR_OF:
            c = unicodedata.normalize('NFC', CHAR_OF[bs[i + 1]] + GLYPHS[b])
            if len(c) == 1 and c not in BYTE_OF:
                out.append(c)
                i += 2
                continue
            out.append(f'{{{b:02X}}}')
        elif b in INLINE_ARG and i + 1 < len(bs):
            out.append(f'{{{SYMBOLS[b]}:{bs[i + 1]:02X}}}')
            i += 1
        elif b in SLOT_ARG:
            out.append(f'{{{SYMBOLS[b]}:{slot}}}')
            slot += 1
        elif b in SYMBOLS:
            out.append(f'{{{SYMBOLS[b]}}}')
        elif b in CHAR_OF:
            out.append(CHAR_OF[b])
        else:
            out.append(f'{{{b:02X}}}')
        i += 1
    return ''.join(out)


def unsymbolize(s, ref=None):
    """symbolize 의 반대. ref 가 있으면 {CALL:nn}·{STR:nn} 같은 이름을 ref(이름, 인자) 로 바이트로 바꾼다."""
    out, slot = [], 0
    for m in TOKEN.finditer(s):
        tok, inner = m.group(0), m.group(1)
        if inner is None:
            if tok in BYTE_OF:
                out.append(BYTE_OF[tok])
                continue
            d = unicodedata.normalize('NFD', tok)
            mark = {'゙': 0x3D, '゚': 0x3E}.get(d[1:])
            if len(d) != 2 or mark is None or d[0] not in BYTE_OF:
                raise ValueError(f'글자 바이트로 못 바꿈: {tok!r}')
            out += [mark, BYTE_OF[d[0]]]
            continue
        name, _, arg = inner.partition(':')
        if not arg and len(name) == 2 and all(ch in '0123456789ABCDEF' for ch in name):
            out.append(int(name, 16))
        elif name in SYMBOL_BYTES:
            b = SYMBOL_BYTES[name]
            out.append(b)
            if b in INLINE_ARG:
                out.append(int(arg, 16))
            elif b in SLOT_ARG:
                if int(arg) != slot:
                    raise ValueError(f'{tok} 의 칸이 {slot} 이어야 함')
                slot += 1
            elif arg:
                raise ValueError(f'인자가 없는 기호: {tok}')
        elif ref:
            out.append(ref(name, arg))
        else:
            raise ValueError(f'모르는 기호: {tok}')
    return out


def _hex(bs):
    return ' '.join(f'{b:02X}' for b in bs)


def _where(bank, addr):
    return f'{bank:02X}:${addr:04X}'


def export_messages(rom):
    out = []
    for m in valid_messages(rom):
        (bank, addr, phase), codes = message_codes(rom, m)
        bs = decode(rom, codes)
        out.append({
            'id': f'{m:04X}', 'bank': f'{bank:02X}', 'addr': f'${addr:04X}', 'phase': phase,
            'codes': _hex(codes), 'bytes': _hex(bs), 'sym': symbolize(bs),
            'auto_quote': auto_quote(m, bs), 'auto_period': shown(bs) != bs,
            'text': text(shown(bs)),
        })
    return out


def _window_ref(rom, g):
    def ref(b):
        e = window_entry(rom, g, b & 0x7F)
        return f'{{{"CALL" if e[0] == "code" else "INS"}:{b & 0x7F:02X}}}'
    return ref


def _window_unref(rom, g):
    def unref(name, arg):
        n = int(arg, 16)
        if name not in ('CALL', 'INS') or (window_entry(rom, g, n)[0] == 'code') != (name == 'CALL'):
            raise ValueError(f'창 항목 기호가 틀림: {{{name}:{arg}}}')
        return 0x80 | n
    return unref


def export_windows(rom):
    out = []
    for g, count in enumerate(WINDOW_COUNTS):
        for n in range(count):
            e = window_entry(rom, g, n)
            row = {'group': g, 'entry': f'{n:02X}', 'kind': e[0], 'addr': _where(0x16, e[1])}
            if e[0] == 'str':
                row.update(bytes=_hex(e[2]), sym=symbolize(e[2], _window_ref(rom, g)), text=window_text(rom, g, n))
            out.append(row)
    return out


def export_layouts(rom):
    """창 레코드마다 자리·크기와 본문 바이트의 갈래. 항목 글은 dq4-windows 의 (group, entry) 로 찾는다."""
    callers, out = window_callers(rom), []
    for n in range(WINDOW_COUNT):
        lay = window_layout(rom, n)
        body = []
        for t in lay['tokens']:
            op = {'op': t[0]}
            if t[0] == 'item':
                op.update(group=t[1], entry=f'{t[2]:02X}', text=t[3])
            elif t[0] == 'list':
                op.update(kind=t[1], routine=LIST_KINDS.get(t[1]))
            elif t[0] in ('side', 'call'):
                op.update(arg=f'{t[1]:02X}')
            elif t[0] == 'cond':
                op.update(arg=t[1], table=t[2])
            elif t[0] != 'newline':
                op.update(arg=t[1])
            if token_meaning(t):
                op['meaning'] = token_meaning(t)
            body.append(op)
        out.append({
            'window': f'{n:02X}', 'record': _where(0x16, lay['record']), 'head': _hex(lay['head']),
            'alias': ' '.join(f'{m:02X}:{c}' for m, c in lay['alias']),
            'x': lay['x'], 'y': lay['y'], 'w': lay['w'], 'inset': lay['inset'],
            'place_routine': lay['width_routine'],
            'place': PLACE_MEANING.get(lay['width_routine'], '') if lay['w'] is None else '',
            'cols': lay['cols'], 'cursor': lay['cursor'],
            'callers': ' '.join(_where(b, a) for b, a in callers.get(n, [])),
            'tokens': ' '.join(token_str(t) for t in lay['tokens']), 'body': body,
        })
    return out


def name_lists(rom):
    """dq4data.name_list 의 이름마다 (목록, ID, 길이 바이트 주소, 글자 바이트). 0번 빈 이름은 뺀다."""
    import dq4data   # dq4data 가 이 모듈을 import 하므로 함수 안에서
    out = []
    for which in dq4data.LISTS:
        j = dq4data.LISTS.index(which)
        a = rom.word(dq4data.NAMES_BANK, dq4data.NAMES_PTR + 2 * j)
        for k, bs in enumerate(dq4data.name_list(rom.prg, which)):
            if k:
                out.append((which, k - 1, a, bs))
            a += 1 + len(bs)
    return out


def export_names(rom):
    return [{'list': w, 'id': i, 'addr': _where(0x0B, a), 'bytes': _hex(bs), 'sym': symbolize(bs),
             'text': text(bs)} for w, i, a, bs in name_lists(rom)]


def _pack(codes, phase):
    """6비트 부호를 롬과 같은 순서(앞 부호가 높은 비트)로 이어 붙인 바이트와, 바이트마다 부호가 차지한 비트 마스크.
    단계 p 의 첫 부호는 시작 바이트에서 앞 (6p mod 8) 비트 뒤부터 시작한다."""
    pad = 6 * phase % 8
    bits = '0' * pad + ''.join(f'{c:06b}' for c in codes)
    used = '0' * pad + '1' * (len(bits) - pad)
    tail = -len(bits) % 8
    bits, used = bits + '0' * tail, used + '0' * tail
    return [(int(bits[i:i + 8], 2), int(used[i:i + 8], 2)) for i in range(0, len(bits), 8)]


def _back(sym, ref=None):
    try:
        return unsymbolize(sym, ref)
    except ValueError as e:
        print(e)
        return None


def check_export(rom, msgs, windows, names):
    """기호 텍스트 → 바이트가 원래 글자 바이트와 같은지, 메시지는 부호 → 글자 바이트와 부호 → 롬 비트열도."""
    bad = 0
    for r in msgs:
        bs = [int(x, 16) for x in r['bytes'].split()]
        codes = [int(x, 16) for x in r['codes'].split()]
        if _back(r['sym']) != bs or decode(rom, codes) != bs:
            print(f'메시지 {r["id"]}: 되돌린 바이트가 다름')
            bad += 1
            continue
        c = Codes(rom, int(r['bank'], 16), int(r['addr'][1:], 16))
        for p, keep in _pack(codes, r['phase']):
            if (rom.byte(c.bank, c.ptr) ^ p) & keep:
                print(f'메시지 {r["id"]}: 롬 비트열과 다름({c.bank:02X}:${c.ptr:04X})')
                bad += 1
                break
            c._advance()
    for r in windows:
        if r['kind'] == 'str':
            bs = [int(x, 16) for x in r['bytes'].split()]
            if _back(r['sym'], _window_unref(rom, r['group'])) != bs:
                print(f'창 {r["group"]} {r["entry"]}: 되돌린 바이트가 다름')
                bad += 1
    for r in names:
        if _back(r['sym']) != [int(x, 16) for x in r['bytes'].split()]:
            print(f'이름 {r["list"]} {r["id"]}: 되돌린 바이트가 다름')
            bad += 1
    print(f'메시지 {len(msgs)}개, 창 문자열 {sum(r["kind"] == "str" for r in windows)}개, '
          f'이름 {len(names)}개: 다른 것 {bad}개')
    return bad == 0


def write_export(out_dir, msgs, windows, names, layouts):
    os.makedirs(out_dir, exist_ok=True)
    legend = {
        'controls': {SYMBOLS[b]: {'byte': f'{b:02X}', 'meaning': CONTROLS[b],
                                  'arg': 'inline' if b in INLINE_ARG else 'slot' if b in SLOT_ARG else None}
                     for b in SYMBOLS},
        'escape': '{XX} = 글자 바이트 XX(16진). ド 는 타일 65, 탁점 3D+ト 는 {3D}ト, 타일 66~69(じだどぶ)는 {66}~{69}',
        'slot': '{NAME:k} 등의 k = 인자 목록 $F9+k(메시지를 부르는 쪽이 채움)',
        'window': '{CALL:nn} = 같은 그룹의 루틴 항목 nn(값 찍기), {INS:nn} = 문자열 항목 nn 끼워 넣기',
        'auto_quote': 'true 면 화면에서 앞에 ＊「 가 붙음. 번호 0500 이상이고 첫 바이트가 F1 이 아닌 메시지(16:$85C5)',
        'auto_period': 'true 면 화면에서 끝 {END} 앞에 。 가 붙음(16:$805A)',
        'layout': 'x·y·w 는 화면 칸(8화소). inset 이면 틀을 x+1 에 w−2 로 그림. place_routine 이면 자리·폭을 표 16:$A72C '
                  '의 루틴이 정함. tokens: 글 = 창 문자열 항목, [Dn] 목록 시작(n ≥ 6 은 루틴이 항목을 만듦), +n 들여쓰기, '
                  '?nn 항목 루틴(?1:nn 은 표 1), 곁창nn 커서를 따라 함께 여는 창, C1(nn) 루틴, / 줄바꿈, Bn·En·?표n·그룹n 은 '
                  'docs 참고. place 는 자리 루틴의 규칙, body 의 meaning 은 갈래마다 뜻(dq4text.py windows --items 와 같은 표)',
    }
    files = {'dq4-messages': msgs, 'dq4-windows': windows, 'dq4-names': names, 'dq4-window-layouts': layouts}
    for name, rows in files.items():
        with open(os.path.join(out_dir, name + '.json'), 'w', encoding='utf-8') as f:
            json.dump({'legend': legend, 'rows': rows}, f, ensure_ascii=False, indent=1)
        cols = list(dict.fromkeys(k for r in rows for k in r if k not in ('codes', 'bytes', 'text', 'body')))
        with open(os.path.join(out_dir, name + '.tsv'), 'w', encoding='utf-8') as f:
            f.write('\t'.join(cols) + '\n')
            for r in rows:
                f.write('\t'.join(str(r.get(k, '')) for k in cols) + '\n')
    print(f'{out_dir}: ' + ', '.join(f'{n}.json/.tsv' for n in files))


def main():
    rom = Rom(open(sys.argv[1], 'rb').read())
    if sys.argv[2] == 'controls':
        for b, h, n, desc in control_table(rom):
            print(f'{b:02X} 16:${h:04X} 메시지 {n:4d}  {desc}')
        return
    if sys.argv[2] == 'windows' and '--compare' in sys.argv:
        total = [0, 0]
        for d in sys.argv[sys.argv.index('--compare') + 1:]:
            s, b = compare_layouts(rom, d)
            total = [total[0] + s, total[1] + b]
        print(f'같음 {total[0]}, 다름 {total[1]}')
        sys.exit(0 if total[1] == 0 else 1)
    if sys.argv[2] == 'windows' and '--items' in sys.argv:
        print('\n'.join(meaning_lines(rom)))
        return
    if sys.argv[2] == 'windows' and '--trace' in sys.argv:
        for path in sys.argv[sys.argv.index('--trace') + 1:]:
            for row in trace_lines(path):
                print(row)
        return
    if sys.argv[2] == 'windows' and '--layout' in sys.argv:
        callers = window_callers(rom)
        for n in range(WINDOW_COUNT):
            at = ' '.join(_where(b, a) for b, a in callers.get(n, []))
            lay = window_layout(rom, n)
            print(layout_line(lay) + (f'  ← {at}' if at else ''))
            if '--meaning' in sys.argv:
                if lay['w'] is None:
                    print(f'     자리: {PLACE_MEANING.get(lay["width_routine"], "")}')
                for t in lay['tokens']:
                    if token_meaning(t):
                        print(f'     {token_str(t)}: {token_meaning(t)}')
        return
    if sys.argv[2] == 'windows':
        for g, count in enumerate(WINDOW_COUNTS):
            for n in range(count):
                e = window_entry(rom, g, n)
                body = window_text(rom, g, n) if e[0] == 'str' else ''
                print(f'{g} {n:02X} {e[0]:4s} 16:${e[1]:04X}  {body}')
        return
    if sys.argv[2] == 'export':
        args = [a for a in sys.argv[3:] if not a.startswith('--')]
        msgs, windows, names = export_messages(rom), export_windows(rom), export_names(rom)
        if '--check' not in sys.argv:
            write_export(args[0] if args else 'work/text', msgs, windows, names, export_layouts(rom))
        sys.exit(0 if check_export(rom, msgs, windows, names) else 1)
    if sys.argv[2] == 'all':
        ms = valid_messages(rom)
        for m in ms:
            print(f'--- {m:04X}')
            print(text(shown(message_bytes(rom, m))))
        print(f'# 메시지 {len(ms)}개', file=sys.stderr)
        return
    if '--compare' in sys.argv:
        msgs = [int(m, 16) for m in sys.argv[2].split(',')]
        ok = all([compare(rom, msgs, p) for p in sys.argv[sys.argv.index('--compare') + 1:]])
        sys.exit(0 if ok else 1)
    msg = int(sys.argv[2], 16)
    args = [a for a in sys.argv[3:] if not a.startswith('--')]
    for m in range(msg, msg + (int(args[0]) if args else 1)):
        b = message_bytes(rom, m)
        if '--bytes' in sys.argv:
            print(f'{m:04X}:', ' '.join(f'{x:02X}' for x in b))
        else:
            print(f'--- {m:04X}')
            print(text(shown(b)))


if __name__ == '__main__':
    main()
