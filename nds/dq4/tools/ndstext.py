"""NDS DQ4 대사 파일(MESS/<언어>/bNNNN000.mpt)을 읽는다. 형식은 nds/dq4/docs/text-format.md.

MPT0 머리(32바이트, 리틀 엔디언 u32 8개): 'MPT0', 파일 크기, ?, ?, 항목 수, 색인 위치(0x20),
색인 크기+2, 본문 크기. 색인은 항목마다 6바이트(u16 번호, u16 바이트 길이, u16 위치/4)이고,
본문은 파일 끝에서 본문 크기만큼 앞(= 파일 크기 - 본문 크기)부터다. 문자열은 UTF-8.

한글 팬패치는 문자 코드를 그대로 두고 폰트 글리프만 한글로 바꿨다. --kr 을 주면
nds/dq4/tables/kr-font.tsv(일본어 코드 → 한글 음절)로 바꿔 읽는다.

사용:
  python nds/dq4/tools/ndstext.py dump FILE.mpt [--kr]          번호와 문자열
  python nds/dq4/tools/ndstext.py names JPROOT KRROOT          이름 표(b1000000~b1007000)를 일본어·영어·한글로
  python nds/dq4/tools/ndstext.py stats ROOT                   언어별 파일·문자열 수, 표지 통계
  python nds/dq4/tools/ndstext.py glossary JPROOT KRROOT FCROM  명칭 대조표(마크다운). FC 이름은 dq4 트랙의 dq4data.py 로 읽는다
JPROOT/KRROOT 는 `krpatch nds unpack` 으로 푼 폴더(그 아래 data/data/MESS/).
"""
import collections
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE = os.path.join(HERE, '..', 'tables', 'kr-font.tsv')
NAME_FILES = {
    'b1000000': '아이템', 'b1001000': '인물', 'b1002000': '몬스터', 'b1003000': '주문·특기',
    'b1004000': '메뉴', 'b1005000': '작전', 'b1006000': '능력치·직업', 'b1007000': '지명·장 제목',
}


def read(path):
    """[(번호, 문자열)] — 번호는 파일 안 번호. 전체 번호는 파일 이름의 NNNN×1000 + 번호."""
    d = open(path, 'rb').read()
    magic, size, _a, _b, count, table, _tsize, dsize = struct.unpack_from('<8I', d, 0)
    if magic != 0x3054504D or size != len(d) or table != 0x20:
        raise ValueError(f'{path}: MPT0 가 아님')
    base = size - dsize
    out = []
    for k in range(count):
        num, length, off = struct.unpack_from('<3H', d, table + 6 * k)
        out.append((num, d[base + off * 4:base + off * 4 + length].decode('utf-8')))
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
    for sub in (('fc', 'dq4', 'tools'), ('tools',)):
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


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    if argv[0] == 'dump':
        table = kr_table() if '--kr' in argv else None
        for num, text in read(argv[1]):
            if table:
                text = decode_kr(text, table)
            print(f'{num}\t' + text.replace('\n', '\\n'))
    elif argv[0] == 'names':
        cmd_names(argv[1], argv[2])
    elif argv[0] == 'glossary':
        cmd_glossary(argv[1], argv[2], argv[3])
    elif argv[0] == 'stats':
        cmd_stats(argv[1])
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
