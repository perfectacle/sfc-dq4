"""NDS DQ4 대사 파일(MESS/<언어>/bNNNN000.mpt)을 읽는다. 형식은 nds/dq4/docs/text-format.md.

MPT0 머리(32바이트, 리틀 엔디언 u32 8개): 'MPT0', 파일 크기, 첫 메시지 번호, 마지막 메시지 번호,
항목 수, 색인 위치(0x20), 색인 크기+2, 본문 크기. 색인은 항목마다 6바이트(u16 번호, u16 바이트 길이,
u16 위치/4)이고, 메시지 번호는 머리의 첫 번호 + 색인 번호다(파일 이름 NNNN×1000 과 다를 수 있음).
본문은 파일 끝에서 본문 크기만큼 앞(= 파일 크기 - 본문 크기)부터다. 문자열은 UTF-8.

한글 팬패치는 문자 코드를 그대로 두고 폰트 글리프만 한글로 바꿨다. --kr 을 주면
nds/dq4/tables/kr-font.tsv(일본어 코드 → 한글 음절)로 바꿔 읽는다.

사용:
  python nds/dq4/tools/ndstext.py dump FILE.mpt [--kr]          메시지 번호와 문자열
  python nds/dq4/tools/ndstext.py names JPROOT KRROOT          이름 표(b1000000~b1007000)를 일본어·영어·한글로
  python nds/dq4/tools/ndstext.py stats ROOT                   언어별 파일·문자열 수, 표지 통계
  python nds/dq4/tools/ndstext.py glossary JPROOT KRROOT FCROM  명칭 대조표(마크다운). FC 이름은 dq4 트랙의 dq4data.py 로 읽는다
  python nds/dq4/tools/ndstext.py talk JPROOT [장] [--kr KRROOT] 동료 대화 표(PARAM/param_player_talk<장>.dat) 레코드와 문장
  python nds/dq4/tools/ndstext.py sjis JPROOT [KRROOT] [--kanji]  arm9.bin·오버레이의 Shift_JIS 문자열과 그것을 가리키는 포인터
                                                               (--kanji: 가나 없는 한자·기호 문자열)
JPROOT/KRROOT 는 `krpatch nds unpack` 으로 푼 폴더(그 아래 data/data/MESS/).
"""
import collections
import os
import pathlib
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE = os.path.join(HERE, '..', 'tables', 'kr-font.tsv')
NAME_FILES = {
    'b1000000': '아이템', 'b1001000': '인물', 'b1002000': '몬스터', 'b1003000': '주문·특기',
    'b1004000': '메뉴', 'b1005000': '작전', 'b1006000': '능력치·직업', 'b1007000': '지명·장 제목',
}


def read(path, full=False):
    """[(번호, 문자열)] — 번호는 파일 안(색인) 번호. full 이면 메시지 번호(머리 +08 + 색인 번호)."""
    d = open(path, 'rb').read()
    magic, size, first, _last, count, table, _tsize, dsize = struct.unpack_from('<8I', d, 0)
    if magic != 0x3054504D or size != len(d) or table != 0x20:
        raise ValueError(f'{path}: MPT0 가 아님')
    base = size - dsize
    out = []
    for k in range(count):
        num, length, off = struct.unpack_from('<3H', d, table + 6 * k)
        out.append((first + num if full else num, d[base + off * 4:base + off * 4 + length].decode('utf-8')))
    return out


def kr_table(path=TABLE):
    m = {}
    for line in open(path, encoding='utf-8'):
        code, _jp, hangul, _how = line.rstrip('\n').split('\t')
        m[chr(int(code, 16))] = hangul
    return m


def decode_kr(text, table):
    return ''.join(table.get(c, c) for c in text)


def label(text):
    """이름 표 문자열의 표시용 값. 일본어는 '@1이름@', 영어는 '@0성별@2정관사@3부정관사@4이름@...' 꼴."""
    m = re.search(r'@4([^@]*)@', text) or re.search(r'@1([^@]*)@', text)
    return (m.group(1) if m else text.strip('@')).replace(';', '')


def mess(root, lang):
    return os.path.join(root, 'data', 'data', 'MESS', lang)


def cmd_names(jp_root, kr_root):
    table = kr_table()
    for f, kind in NAME_FILES.items():
        ja = dict(read(os.path.join(mess(jp_root, 'ja'), f + '.mpt')))
        en = dict(read(os.path.join(mess(jp_root, 'en'), f + '.mpt')))
        ko = dict(read(os.path.join(mess(kr_root, 'ja'), f + '.mpt')))
        for num in sorted(ja):
            print(f'{kind}\t{f}:{num}\t{label(ja[num])}\t{label(en.get(num, ""))}\t'
                  f'{label(decode_kr(ko.get(num, ""), table))}')


FC_LISTS = {'아이템': 'item', '몬스터': 'monster', '주문·특기': 'spell', '지명·장 제목': 'place'}


def fc_names(rom):
    """FC 판 이름 목록(dq4 트랙의 dq4data.py, 읽기만)."""
    import importlib
    root = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
    for sub in (('fc', 'dq4', 'tools'),):
        d = os.path.join(root, *sub)
        if os.path.exists(os.path.join(d, 'dq4data.py')):
            sys.path.insert(0, d)
            break
    dq4data = importlib.import_module('dq4data')
    from kr_patch.fc import ines
    prg = ines.prg(open(rom, 'rb').read())
    out = {}
    for kind, lst in FC_LISTS.items():
        out[kind] = [dq4data.dq4text.text(n) for n in dq4data.name_list(prg, lst)[1:]]
    return out


def kana_key(s):
    """히라가나·가타카나 차이, 띄어쓰기·줄바꿈 표지를 무시한 비교 키."""
    s = s.replace(';', '').replace(' ', '').replace('\u3000', '')
    return ''.join(chr(ord(c) + 0x60) if 'ぁ' <= c <= 'ゖ' else c for c in s)


def cmd_glossary(jp_root, kr_root, rom):
    table = kr_table()
    try:
        fc = {k: {kana_key(n) for n in v} for k, v in fc_names(rom).items()}
    except Exception as e:  # FC 도구가 없거나 형식이 바뀌면 FC 열을 비운다
        print(f'<!-- FC 이름을 읽지 못함: {e} -->')
        fc = {}
    for f, kind in NAME_FILES.items():
        ja = dict(read(os.path.join(mess(jp_root, 'ja'), f + '.mpt')))
        en = dict(read(os.path.join(mess(jp_root, 'en'), f + '.mpt')))
        ko = dict(read(os.path.join(mess(kr_root, 'ja'), f + '.mpt')))
        print(f'\n## {kind}\n')
        head = '| 번호 | DS 일본어 | FC 에 같은 이름 | DS 영어 | DS 한글 팬패치 | 채택 |'
        print(head)
        print('| --- | --- | --- | --- | --- | --- |')
        seen = set()
        for num in sorted(ja):
            j = label(ja[num])
            k = label(decode_kr(ko.get(num, ''), table))
            if not j or (j, k) in seen:
                continue
            seen.add((j, k))
            mark = ''
            if kind in fc:
                mark = '있음' if kana_key(j) in fc[kind] else '없음'
            e = label(en.get(num, '')).replace('|', '/')
            print(f'| {num} | {j} | {mark} | {e} | {k} |  |')


TALK_HEAD, TALK_SIZE = 4, 44


def talk_records(root, chapter):
    """동료 대화 표: 머리 4바이트 뒤 44바이트 레코드. +16 u32 가 메시지 번호, 나머지 u16 의 뜻은 text-format.md 「동료 대화 표」."""
    d = open(os.path.join(root, 'data', 'data', 'PARAM', f'param_player_talk{chapter}.dat'), 'rb').read()
    out = []
    for o in range(TALK_HEAD, len(d) - TALK_SIZE + 1, TALK_SIZE):
        r = d[o:o + TALK_SIZE]
        out.append((struct.unpack_from('<I', r, 16)[0], struct.unpack_from('<22H', r)))
    return out


def messages(root, lang='ja'):
    out = {}
    base_dir = mess(root, lang)
    for f in os.listdir(base_dir):
        if f.endswith('.mpt'):
            out.update(read(os.path.join(base_dir, f), full=True))
    return out


def cmd_talk(root, chapters, kr_root=None):
    msgs = messages(root)
    kr = messages(kr_root) if kr_root else {}
    table = kr_table() if kr_root else {}
    for ch in chapters:
        for mid, h in talk_records(root, ch):
            fields = ' '.join(f'{v:04X}' for k, v in enumerate(h) if k not in (8, 9))
            text = kr.get(mid) and decode_kr(kr[mid], table) or msgs.get(mid, '-')
            print(f'{ch}\t{mid}\t{fields}\t' + text.replace('\n', '/'))


def cmd_stats(root):
    base = os.path.join(root, 'data', 'data', 'MESS')
    for lang in sorted(os.listdir(base)):
        files = sorted(f for f in os.listdir(os.path.join(base, lang)) if f.endswith('.mpt'))
        n = sum(len(read(os.path.join(base, lang, f))) for f in files)
        print(f'{lang}\t파일 {len(files)}\t문자열 {n}')
    tags = collections.Counter()
    for f in sorted(os.listdir(os.path.join(base, 'ja'))):
        for _n, t in read(os.path.join(base, 'ja', f)):
            tags.update(re.sub(r'\d+', 'N', m) for m in re.findall(r'@[a-z]\d*@?|%[a-z]\d+', t))
    print(' '.join(f'{k}:{v}' for k, v in tags.most_common(20)))


KANA = re.compile('[\u3040-\u30ff]')
FULL = re.compile('@?[\u3000-\u303f\u4e00-\u9fff\uff01-\uff5e]+')


def modules(root):
    """(이름, 적재 주소, 바이트) — arm9.bin 과 크기가 있는 오버레이. 주소는 y9.bin(오버레이 표 32바이트씩)의 +04."""
    yield 'arm9', 0x02000000, pathlib.Path(root, 'arm9.bin').read_bytes()
    y9 = pathlib.Path(root, 'y9.bin').read_bytes()
    for i in range(len(y9) // 32):
        ram = struct.unpack_from('<I', y9, 32 * i + 4)[0]
        d = pathlib.Path(root, 'overlay9', f'overlay_{i:04d}.bin').read_bytes()
        if len(d) > 32:
            yield f'overlay_{i:04d}', ram, d


def sjis_strings(d, kanji=False):
    """4바이트 맞춘 자리에서 시작해 0 으로 끝나는 Shift_JIS 문자열(가나가 하나 이상, 반각 가나·사용자 정의 문자 없음, 줄바꿈 빼고 두 글자 이상).
    kanji 면 가나 없이 전각 글자(한자·기호)로만 된 것도 낸다. 잡음이 많아 cmd_sjis 가 포인터 있는 것만 남긴다."""
    out = []
    for o in range(0, len(d), 4):
        if o and d[o - 1]:
            continue
        e = d.find(b'\0', o)
        if e - o < 2:
            continue
        try:
            s = d[o:e].decode('cp932')
        except UnicodeDecodeError:
            continue
        if len(s.replace('\n', '')) >= 2 and (KANA.search(s) or kanji and FULL.fullmatch(s)) and not any(c < ' ' and c != '\n' or '\uff61' <= c <= '\uff9f' or '\ue000' <= c <= '\uf8ff' for c in s):
            out.append((o, s))
    return out


def cmd_sjis(jp_root, kr_root=None, kanji=False):
    """모듈, 파일 오프셋, 주소, 가리키는 곳(표면 「표 시작+순번/개수」), 일본어, 한글패치에서 바뀌었으면 한글.
    kanji 면 가나 없는 문자열만, 포인터가 있는 것만 낸다."""
    mods = list(modules(jp_root))
    kr = {n: d for n, _a, d in modules(kr_root)} if kr_root else {}
    table = kr_table() if kr_root else {}
    found = {}
    for name, ram, d in mods:
        for o, s in sjis_strings(d, kanji):
            if not kanji or not KANA.search(s):
                found[ram + o] = (name, o, s)
    refs = collections.defaultdict(list)
    for name, ram, d in mods:
        words = struct.unpack_from(f'<{len(d) // 4}I', d)
        k = 0
        while k < len(words):
            j = k
            while j < len(words) and words[j] in found:
                j += 1
            for i in range(k, j):
                where = f'{name}:{4 * k:x}+{i - k}/{j - k}' if j - k > 1 else f'{name}:{4 * i:x}'
                refs[words[i]].append(where)
            k = j + 1 if j == k else j
    for addr, (name, o, s) in sorted(found.items(), key=lambda x: (x[1][0], x[0])):
        if kanji and not refs[addr]:
            continue
        ko = ''
        if name in kr:
            raw = kr[name][o:kr[name].index(b'\0', o)]
            if raw != s.encode('cp932'):
                ko = decode_kr(raw.decode('cp932', 'replace'), table)
        print(f'{name}\t{o:06X}\t{addr:08X}\t{",".join(refs[addr]) or "-"}\t{s}\t{ko}'.replace('\n', '/'))


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    if argv[0] == 'dump':
        table = kr_table() if '--kr' in argv else None
        for num, text in read(argv[1], full=True):
            if table:
                text = decode_kr(text, table)
            print(f'{num}\t' + text.replace('\n', '\\n'))
    elif argv[0] == 'names':
        cmd_names(argv[1], argv[2])
    elif argv[0] == 'talk':
        rest = [a for a in argv[2:] if not a.startswith('--')]
        kr_root = argv[argv.index('--kr') + 1] if '--kr' in argv else None
        rest = [a for a in rest if a != kr_root]
        cmd_talk(argv[1], [int(a) for a in rest] or range(1, 7), kr_root)
    elif argv[0] == 'glossary':
        cmd_glossary(argv[1], argv[2], argv[3])
    elif argv[0] == 'sjis':
        rest = [a for a in argv[1:] if not a.startswith('--')]
        cmd_sjis(rest[0], rest[1] if len(rest) > 1 else None, '--kanji' in argv)
    elif argv[0] == 'stats':
        cmd_stats(argv[1])
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
