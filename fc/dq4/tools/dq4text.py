"""DQ4(FC) 대사 텍스트 풀기. 형식은 docs/dq4-text-format.md.

사용:
  python tools/dq4text.py rom/dq4.nes all              실제로 있는 메시지 전부
  python tools/dq4text.py rom/dq4.nes MSG [개수]      메시지 번호(16진)부터 글자로
  python tools/dq4text.py rom/dq4.nes MSG --bytes     글자 바이트(화면 타일 번호)로
  python tools/dq4text.py rom/dq4.nes MSG[,MSG…] --compare end.ram ...  seq.lua 의 RAM 덤프(창 줄 버퍼 $06AA,
      전투 창이면 옆의 end.nt)가 차례로 찍은 메시지들과 맞는지. 치환 제어(F6 이름 등)는 아무 글자와 맞춤
  python tools/dq4text.py rom/dq4.nes controls        제어 바이트 ED~FF 의 처리기 주소·뜻·쓰는 메시지 수
  python tools/dq4text.py rom/dq4.nes windows         창 문자열 표 16:$A572(그룹, 항목, 루틴/문자열, 글자)
  python tools/dq4text.py rom/dq4.nes export [DIR]    메시지·창 문자열·이름 목록을 기호 텍스트 JSON·TSV 로(기본 work/text).
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


TALK_KIND = 0x058B          # 5 이상이면 메시지 앞에 「＊「」 를 저절로 넣음(16:$85C5), 첫 바이트가 F1 이면 빼고
AUTO_PREFIX = [0x70, 0x6F]
SUBST = {0xEF, 0xF2, 0xF3, 0xF5, 0xF6, 0xF7, 0xF8}   # 메시지 밖 인자로 글자를 넣는 제어
SUBST_MAX = 12                                       # 치환 하나가 넣는 글자 바이트 수의 상한(이름 + もどき 등)


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
    덤프의 $058B 가 5 이상이면 자동 「＊「」 도 넣어 비교한다."""
    lines, where, ram = dump_lines(ram_path)
    stream = []
    for m in msgs:
        bs = shown(message_bytes(rom, m))
        if ram[TALK_KIND] >= 5 and bs[0] != 0xF1:
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
            'auto_quote': bs[0] != 0xF1, 'auto_period': shown(bs) != bs,
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


def write_export(out_dir, msgs, windows, names):
    os.makedirs(out_dir, exist_ok=True)
    legend = {
        'controls': {SYMBOLS[b]: {'byte': f'{b:02X}', 'meaning': CONTROLS[b],
                                  'arg': 'inline' if b in INLINE_ARG else 'slot' if b in SLOT_ARG else None}
                     for b in SYMBOLS},
        'escape': '{XX} = 글자 바이트 XX(16진). ド 는 타일 65, 탁점 3D+ト 는 {3D}ト, 타일 66~69(じだどぶ)는 {66}~{69}',
        'slot': '{NAME:k} 등의 k = 인자 목록 $F9+k(메시지를 부르는 쪽이 채움)',
        'window': '{CALL:nn} = 같은 그룹의 루틴 항목 nn(값 찍기), {INS:nn} = 문자열 항목 nn 끼워 넣기',
        'auto_quote': 'true 면 $058B ≥ 5 인 대화에서 앞에 ＊「 가 붙음(첫 바이트가 F1 이면 false)',
        'auto_period': 'true 면 화면에서 끝 {END} 앞에 。 가 붙음(16:$805A)',
    }
    files = {'dq4-messages': msgs, 'dq4-windows': windows, 'dq4-names': names}
    for name, rows in files.items():
        with open(os.path.join(out_dir, name + '.json'), 'w', encoding='utf-8') as f:
            json.dump({'legend': legend, 'rows': rows}, f, ensure_ascii=False, indent=1)
        cols = list(dict.fromkeys(k for r in rows for k in r if k not in ('codes', 'bytes', 'text')))
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
            write_export(args[0] if args else 'work/text', msgs, windows, names)
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
