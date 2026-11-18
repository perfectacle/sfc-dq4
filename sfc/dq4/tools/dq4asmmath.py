"""asar 식의 셈 차례 검사. 빌드가 조립하는 asm 에서 셈 차례가 다른 연산자가 괄호 없이 섞인 식을 찾는다.

asar 1.91 은 `math pri on` 이 없으면 식을 왼쪽부터 셈한다(xkas 호환). 그래서 `#$5000+(18*32+3)*2` 는
`($5000+579)*2` = `$A486` 이 된다. asar 도 두 셈이 다르면 「xkas style left to right math」 경고를 찍지만 빌드가
asar 출력을 실패 때만 보이므로 묻혔다. 이 검사는 롬 없이 asm 글만 읽어, 우선순위 꺼진 자리의 식에서 한 괄호 단계
안에 등급(`**` > `* / %` > `+ -` > `<< >>` > `& | ^`, asar_math.cpp 의 oper 깊이)이 다른 이항 연산자가 함께 있으면
잡는다. 왼쪽부터 셈한 값과 우선순위 값이 같은 식(등급이 왼쪽부터 내려가기만 하는 식)도 괄호로 뜻을 고정하게 한다.

asm 안에서 정의한 `!이름` 은 asar 처럼 글자 그대로 펼쳐서 본다. 빌드 도구(Python)가 앞에 붙이는 정의는 모두 수
하나라(`dq4windowname.build` 등) 낱말 하나로 친다.

  python sfc/dq4/tools/dq4asmmath.py            # 섞인 식 모두(우선순위 켜진 파일 포함)를 찍음
"""
import importlib
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

# 한 번에 조립하는 파일 묶음(앞에서부터 이어 붙임). `math pri` 상태가 다음 파일로 이어지므로 묶음째 본다.
# 빌드 도구가 asm 을 붙이는 차례를 바꾸면 여기도 고친다(test_dq4asmmath 가 저장소의 모든 .asm 이 든 것을 본다).
# 「모듈:이름」 은 빌드 도구가 앞에 붙이는 Python 글(정의)이다
UNITS = (
    ('dq4battlemsg:WRAM', 'sfc/dq4/tools/dq4windowname.asm', 'sfc/dq4/tools/dq4battlemsg.asm'),  # dq4windowname.build
    ('sfc/dq4/tools/dq4nameentry.asm',),
    ('sfc/dq4/tools/dq4fcslot.asm',),
    ('sfc/dq4/tools/dq4fcpoker.asm',),
    ('sfc/dq4/tools/dq4titlelayers.asm',),
    ('sfc/dq4/tools/dq4titlepatch.asm',),
    ('sfc/dq4/tools/dq4titlepreview.asm',),
)

CLASS = {'**': 4, '*': 3, '/': 3, '%': 3, '+': 2, '-': 2, '<<': 1, '>>': 1, '&': 0, '|': 0, '^': 0}
SPLIT = ('==', '!=', '<=', '>=', '&&', '||', '<', '>')   # 비교·논리: asar 가 셈 전에 나눔
SKIP = {'incbin', 'incsrc', 'print', 'error', 'warn', 'macro', 'endmacro', 'lorom', 'hirom', 'exlorom', 'exhirom',
        'sa1rom', 'fullsa1rom', 'norom', 'math', 'pushpc', 'pullpc', 'endif', 'else', 'endwhile', 'namespace',
        'table', 'cleartable', 'asar', 'check', 'optimize', 'bankcross', 'arch', 'warnings'}
TOKEN = re.compile(r'''\s*(?:
    (?P<str>"[^"]*"|'[^']')
  | (?P<arg><[A-Za-z_]\w*>)
  | (?P<op>\*\*|<<|>>|==|!=|<=|>=|&&|\|\||[-+*/%&|^~<>(),\[\]#])
  | (?P<atom>\$[0-9A-Fa-f]+|[0-9]+|!\w+|\??[A-Za-z_.][\w.]*)
  )''', re.X)


class Mixed:
    def __init__(self, file, line, text, expr, ops, left, pri):
        self.file, self.line, self.text, self.expr, self.ops = file, line, text, expr, ops
        self.left, self.pri = left, pri

    @property
    def order_sensitive(self):
        """등급이 왼쪽부터 내려가기만 하지 않으면 두 셈이 (값에 따라) 다르다."""
        classes = [CLASS[o] for o in self.ops]
        return any(b > a for a, b in zip(classes, classes[1:]))

    def __repr__(self):
        return f'{self.file}:{self.line}: {self.expr}'


def strip_comment(line):
    out, quote = [], None
    for ch in line:
        if quote:
            if ch == quote:
                quote = None
        elif ch in '"\'':
            quote = ch
        elif ch == ';':
            break
        out.append(ch)
    return ''.join(out).rstrip()


def tokens(text):
    pos, out = 0, []
    while pos < len(text):
        if text[pos:].strip() == '':
            break
        m = TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise ValueError(f'읽지 못한 식: {text[pos:]!r} ({text!r})')
        kind = m.lastgroup
        tok = m.group(kind)
        # % 는 피연산자 자리면 2진수 앞머리, 아니면 나머지
        if tok == '%' and (not out or out[-1][0] == 'op' and out[-1][1] not in ')]'):
            b = re.match(r'[01]+', text[m.end():])
            if b:
                out.append(('atom', '%' + b.group()))
                pos = m.end() + b.end()
                continue
        out.append(('atom' if kind in ('str', 'arg', 'atom') else 'op', tok))
        pos = m.end()
    return out


def expand(text, defines, depth=0):
    if depth > 20:
        raise ValueError(f'정의가 끝없이 펼쳐짐: {text}')

    def sub(m):
        name = m.group(1)
        return expand(defines[name], defines, depth + 1) if name in defines else m.group(0)
    return re.sub(r'!(\w+)', sub, text)


def number(tok):
    if tok.startswith('$'):
        return int(tok[1:], 16)
    if tok.startswith('%'):
        return int(tok[1:], 2)
    if tok.isdigit():
        return int(tok)
    if len(tok) == 3 and tok[0] == "'":
        return ord(tok[1])
    return None


def apply(op, a, b):
    return {'**': lambda: a ** b, '*': lambda: a * b, '/': lambda: a // b if b else None,
            '%': lambda: a % b if b else None, '+': lambda: a + b, '-': lambda: a - b,
            '<<': lambda: a << b, '>>': lambda: a >> b, '&': lambda: a & b, '|': lambda: a | b,
            '^': lambda: a ^ b}[op]()


def evaluate(items, pri):
    """items = [값, 연산자, 값, …](값은 int 또는 None). 왼쪽부터(pri=False) 또는 asar 우선순위로 셈한다."""
    if any(v is None for v in items[::2]):
        return None
    if not pri:
        acc = items[0]
        for op, v in zip(items[1::2], items[2::2]):
            acc = apply(op, acc, v)
            if acc is None:
                return None
        return acc
    vals, ops = [items[0]], []
    for op, v in zip(items[1::2], items[2::2]):
        while ops and CLASS[ops[-1]] >= CLASS[op]:
            b, a = vals.pop(), vals.pop()
            vals.append(apply(ops.pop(), a, b))
        ops.append(op)
        vals.append(v)
    while ops:
        b, a = vals.pop(), vals.pop()
        vals.append(apply(ops.pop(), a, b))
    return vals[0]


def segments(toks):
    """한 괄호 단계·쉼표·비교 사이 구간마다 (이항 연산자 목록, 왼쪽부터 값, 우선순위 값, 구간 글)."""
    found = []

    def parse(i, close):
        items, ops, start, text = [], [], i, []
        expect = True                      # 피연산자 자리
        value = None
        while i < len(toks):
            kind, tok = toks[i]
            if kind == 'op' and tok in ('(', '['):
                sub, i = parse(i + 1, ')' if tok == '(' else ']')
                text.append(tok + sub[0] + (')' if tok == '(' else ']'))
                value = sub[1] if tok == '(' else None
                if expect:
                    items.append(value)
                    expect = False
                continue
            if kind == 'op' and tok in (')', ']'):
                if tok != close:
                    raise ValueError(f'괄호가 맞지 않음: {toks}')
                flush(items, ops, text)
                return (''.join(text), evaluate(items, True) if items and len(items) % 2 else None), i + 1
            if kind == 'op' and (tok in (',', '#') or tok in SPLIT):
                flush(items, ops, text)
                items, ops, text, expect = [], [], [], True
                i += 1
                continue
            if kind == 'op' and tok in CLASS or tok == '~':
                if expect:                 # 단항(+ - ~): 다음 피연산자에 붙음
                    text.append(tok)
                    i += 1
                    if i < len(toks) and toks[i][0] == 'atom' and tok != '~':
                        v = number(toks[i][1])
                        items.append(-v if tok == '-' and v is not None else (v if tok == '+' else None))
                        text.append(toks[i][1])
                        expect = False
                        i += 1
                    continue
                ops.append(tok)
                items.append(tok)
                text.append(tok)
                expect = True
                i += 1
                continue
            # 낱말
            if expect:
                items.append(number(tok))
            else:                          # 함수 부르기 뒤 등 낱말이 이어지면 값 모름
                items.append(None)
            text.append(tok)
            expect = False
            i += 1
        flush(items, ops, text)
        return (''.join(text), None), i

    def flush(items, ops, text):
        if len({CLASS[o] for o in ops}) > 1:
            ok = len(items) % 2 == 1 and all(isinstance(x, str) for x in items[1::2])
            found.append((list(ops), evaluate(items, False) if ok else None,
                          evaluate(items, True) if ok else None, ''.join(text)))

    parse(0, None)
    return found


def operand(line):
    """(지시어, 셈할 글) 또는 None. 이름표·정의 줄은 정의 쪽에서 따로 본다."""
    s = line.strip()
    if not s:
        return None
    s = re.sub(r'^\??[A-Za-z_][\w.]*:\s*', '', s)          # 이름표:
    if re.fullmatch(r'[-+]+', s) or re.fullmatch(r'\.[\w.]+', s):
        return None
    if not s:
        return None
    if s.startswith('%'):                               # 매크로 부르기 %이름(인자…)
        m = re.match(r'%\w+\((.*)\)\s*$', s)
        return ('%', m.group(1)) if m else None
    m = re.match(r'[A-Za-z_][\w.]*\s*=\s*(.*)$', s)     # 이름표 = 식
    if m:
        return ('=', m.group(1))
    word, _, rest = s.partition(' ')
    head = word.split('.')[0].lower()
    if head in SKIP or s.startswith('}') or s.startswith('{'):
        return None
    rest = rest.strip()
    if re.fullmatch(r'[-+]+', rest):                    # 이름 없는 이름표로 가지 치기
        return None
    if head in ('if', 'elseif', 'while', 'assert'):
        rest = re.sub(r',\s*".*$', '', rest)            # assert 뒤 알림 글
    return (head, rest)


def source(rel, root=ROOT):
    if ':' in rel:
        module, name = rel.split(':')
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))
        return getattr(importlib.import_module(module), name)
    return (root / rel).read_text(encoding='utf-8')


def mixed(units=UNITS, root=ROOT):
    """모든 묶음에서 등급이 섞인 식(Mixed) 목록. pri 는 그 줄에서 asar 가 우선순위로 셈하는지."""
    out = []
    for unit in units:
        pri, defines = False, {}
        for rel in unit:
            lines = source(rel, root).splitlines()
            for n, raw in enumerate(lines, 1):
                for line in re.split(r'\s:\s', strip_comment(raw)):   # asar 는 「 : 」 로 한 줄에 여러 명령
                    try:
                        pri = statement(line, rel, n, pri, defines, out)
                    except ValueError as e:
                        raise ValueError(f'{rel}:{n}: {e}') from None
    return out


def statement(line, rel, n, pri, defines, out):
    """한 명령을 보고 out 에 더한다. 돌려주는 값은 그 뒤의 우선순위 상태."""
    s = line.strip()
    m = re.match(r'math\s+pri\s+(on|off)\b', s, re.I)
    if m:
        return m.group(1).lower() == 'on'
    if re.match(r'asar\s+1\.(9\d*|[1-9]\d+)\b', s, re.I):
        return True
    d = re.match(r'!(\w+)\s*[:?+#]?=\s*(.*)$', s)
    if d:
        value = d.group(2).strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        # asar 는 정의 값 안의 정의를 정의할 때 펼친다(!i #= !i+1 이 돈다)
        defines[d.group(1)] = value = expand(value, defines)
        text = value
    else:
        got = operand(line)
        text = got[1] if got else ''
    if text:
        for ops, left, right, seg in segments(tokens(expand(text, defines))):
            out.append(Mixed(rel, n, s, seg, ops, (left, right), pri))
    return pri


def main():
    rows = mixed()
    for r in rows:
        left, right = r.left
        val = '' if left is None else f'  왼쪽부터 ${left & 0xFFFFFF:X}, 우선순위 ${right & 0xFFFFFF:X}'
        print(f'{r.file}:{r.line}: {"pri on " if r.pri else "pri off"} '
              f'{"차례 다름" if r.order_sensitive else "차례 같음"}  {r.expr}{val}  ← {r.text}')
    bad = [r for r in rows if not r.pri]
    print(f'섞인 식 {len(rows)}개, 우선순위 꺼진 자리 {len(bad)}개')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
