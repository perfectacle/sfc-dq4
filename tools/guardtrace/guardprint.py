"""코드 객체 지문. 줄 번호는 빼고 바이트코드·상수·이름·인자 꼴을 본다. 안에 든 함수·클래스 코드는 이름만 넣어,
바깥 함수의 지문이 안쪽 함수 몸을 고쳐도 바뀌지 않게 한다(안쪽은 따로 지문을 받는다)."""
import hashlib
import types


def _const(h, value):
    if isinstance(value, types.CodeType):
        h.update(b'code:' + value.co_qualname.encode() + b'\0')
    elif isinstance(value, (tuple, list)):
        h.update(f'{type(value).__name__}:{len(value)}('.encode())
        for v in value:
            _const(h, v)
        h.update(b')')
    elif isinstance(value, frozenset):
        # 문자열 해시 씨앗에 따라 순서가 달라지므로 원소 지문을 정렬한다
        parts = []
        for v in value:
            sub = hashlib.sha1()
            _const(sub, v)
            parts.append(sub.digest())
        h.update(f'frozenset:{len(parts)}('.encode() + b''.join(sorted(parts)) + b')')
    else:
        h.update(f'{type(value).__name__}:{value!r}\0'.encode('utf-8', 'surrogateescape'))


def fingerprint(code):
    h = hashlib.sha1()
    for field in ('co_argcount', 'co_posonlyargcount', 'co_kwonlyargcount', 'co_nlocals', 'co_flags', 'co_qualname'):
        h.update(f'{field}={getattr(code, field)!r}\0'.encode())
    for field in ('co_names', 'co_varnames', 'co_freevars', 'co_cellvars'):
        h.update(f'{field}={getattr(code, field)!r}\0'.encode())
    h.update(b'code=' + code.co_code + b'\0exc=' + code.co_exceptiontable + b'\0')
    _const(h, code.co_consts)
    return h.hexdigest()


def module_prints(source, filename):
    """원본을 컴파일해 {qualname: 같은 이름 코드들의 지문 목록(원본에 나오는 차례)}. 컴파일하지 못하면 None.
    차례를 지키는 것은 같은 이름(<lambda>·같은 이름 안쪽 함수)끼리 몸을 맞바꾸면 달라져야 하기 때문이다."""
    try:
        top = compile(source, filename, 'exec', dont_inherit=True)
    except (SyntaxError, ValueError):
        return None
    prints = {}

    def walk(code):
        prints.setdefault(code.co_qualname, []).append(fingerprint(code))
        for c in code.co_consts:
            if isinstance(c, types.CodeType):
                walk(c)
    walk(top)
    return prints
