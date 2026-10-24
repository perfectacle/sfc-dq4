"""DQ4(FC) 대사 텍스트 풀기. 형식은 docs/dq4-text-format.md.

사용:
  python tools/dq4text.py rom/dq4.nes all              실제로 있는 메시지 전부
  python tools/dq4text.py rom/dq4.nes MSG [개수]      메시지 번호(16진)부터 글자로
  python tools/dq4text.py rom/dq4.nes MSG --bytes     글자 바이트(화면 타일 번호)로
  python tools/dq4text.py rom/dq4.nes MSG --compare end.ram ...  seq.lua 의 RAM 덤프(창 줄 버퍼 $06AA)와 비교

근거 루틴: 0F:$DF99(6비트 부호 읽기), 0F:$DFD5(뱅크 넘김), 16:$8656(메시지 번호 → 시작),
16:$86BA(부호 → 글자, 가나 전환, 사전 단어).
"""
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


LINE_BUF, LINE_W, LINES = 0x06AA, 22, 3   # 창 줄 버퍼: 줄마다 탁점 행 22바이트 + 글자 행 22바이트(16:$830F)
CONTROL_MIN = 0xED                          # 이 값 이상은 16:$80AF 표의 제어 처리기로 감


def buffer_lines(ram):
    """RAM 덤프의 창 줄 버퍼를 메시지 바이트 순서(탁점·반탁점이 글자 앞)로. 빈 줄과 앞 공백은 뺀다."""
    out = []
    for i in range(LINES):
        marks = ram[LINE_BUF + i * 2 * LINE_W:][:LINE_W]
        chars = ram[LINE_BUF + (i * 2 + 1) * LINE_W:][:LINE_W]
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


def message_bytes(rom, msg):
    """메시지 하나를 글자 바이트 목록으로(끝 부호의 글자 바이트까지 포함)."""
    codes = Codes(rom, *rom.start(msg))
    for _ in range(msg & 0x1F):
        while codes.next() != END:
            pass
    kana, out = 0, []
    while True:
        c = codes.next()
        if c == 0x3C:
            kana ^= 1
        elif c > 0x3C:
            out += rom.dict_word(c - 0x3D, codes.next())
        else:
            b = rom.byte(CHARS[0], CHARS[1] + kana * 64 + c)
            if b == 0xF0:
                out += rom.dict_word(0, 0)
            else:
                out.append(b)
            if c == END:
                return out


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


def compare(rom, msg, ram_path):
    """RAM 덤프의 창 줄들이 메시지 글자열(제어 바이트를 뺀 것)에 그 순서대로 이어서 들어 있는지."""
    lines = buffer_lines(open(ram_path, 'rb').read())
    stream = [b for b in shown(message_bytes(rom, msg)) if b < CONTROL_MIN]
    pos = 0
    for ln in lines:
        at = next((i for i in range(pos, len(stream) - len(ln) + 1) if stream[i:i + len(ln)] == ln), None)
        if at is None:
            print(f'{ram_path}: 다름 — 화면 「{text(ln)}」')
            return False
        pos = at + len(ln)
    print(f'{ram_path}: 창 {len(lines)}줄 모두 메시지 {msg:04X} 에 순서대로 있음')
    return bool(lines)


def main():
    rom = Rom(open(sys.argv[1], 'rb').read())
    if sys.argv[2] == 'all':
        ms = valid_messages(rom)
        for m in ms:
            print(f'--- {m:04X}')
            print(text(shown(message_bytes(rom, m))))
        print(f'# 메시지 {len(ms)}개', file=sys.stderr)
        return
    msg = int(sys.argv[2], 16)
    if '--compare' in sys.argv:
        ok = all([compare(rom, msg, p) for p in sys.argv[sys.argv.index('--compare') + 1:]])
        sys.exit(0 if ok else 1)
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
