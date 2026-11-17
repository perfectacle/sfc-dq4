"""메시지 번호 → 번호가 밀려도 바뀌지 않는 이름표. 걷기 검사 기준(ch1-walk-messages.toml)이 번호 대신 이것으로 견준다.

1·2·3장 사건 메시지는 장마다 차례로 이어 매겨서(dq4chapter1.chapter2_message·chapter3_message, 사건 모듈 등록 차례), 앞
장이나 앞 모듈이 메시지를 하나 더하면 뒤 번호가 모두 밀린다. 번호로 견주면 내용이 같아도 기준이 통째로 바뀐다.

  사건 메시지  「장.이름@글」 또는 「장.모듈.이름@글」(ch1.alex_talk@1a2b3c4d, ch3.E.letter2@…). 이름은 사건 모듈의 MESSAGES
               키, 모듈은 등록 키(2장 E1~, 3장 L·S·…). 같은 글이 여러 사건에 있어도 이름으로 갈린다
  그 밖        「@글」. 번호가 고정인 서장·시스템·옮긴 인물 대사. 같은 글이 이름 없는 번호 여럿에 있으면 「@글#k」(번호
               차례로 k 번째)

「글」 은 빌드가 롬에 넣은 메시지(빌드 폴더 messages.json 의 내용)의 SHA-1 앞 8자리라, 글이 바뀌면 이름표도 바뀌어 검사가
실패한다. 사건 메시지의 첫 번호는 messages.json 에서 1장 사건 메시지(dq4ch1event.MESSAGES)가 차례로 놓인 자리를 찾아 정하고,
2·3장 사건 메시지가 그 자리에서 이어지는지 함께 확인한다(맞지 않으면 ValueError: 이름을 틀리게 붙이지 않음).

  uv run --locked python sfc/dq4/tools/dq4msglabels.py --messages work/ch1/messages.json E71 129   # 번호 → 이름표
  uv run --locked python sfc/dq4/tools/dq4msglabels.py --messages work/ch1/messages.json --relabel  # 번호 기준을 이름표로
"""
import argparse
import hashlib
import json
from pathlib import Path

# 자리가 맞는지 볼 때, 빌드가 롬에 넣으며 이름·조사를 바꾸는 메시지가 있어 모두 같지는 않다(모듈마다 69~100% 같음).
# 한 칸만 어긋나도 0% 라, 이만큼 같으면 그 자리로 친다
MATCH = 0.5


def digest(content):
    return hashlib.sha1(json.dumps(content, ensure_ascii=False).encode('utf-8')).hexdigest()[:8]


def _key(content):
    return json.dumps(content, ensure_ascii=False)


def load(path):
    """messages.json → {번호(int): 내용}."""
    return {int(k, 16): v for k, v in json.loads(Path(path).read_text(encoding='utf-8'))['messages'].items()}


def _matched(messages, first, contents):
    return sum(_key(messages.get(first + k)) == _key(c) for k, c in enumerate(contents))


def _chapter1_first(messages):
    import dq4ch1event
    contents = list(dq4ch1event.MESSAGES.values())
    good = [f for f in sorted(messages) if _matched(messages, f, contents) >= MATCH * len(contents)]
    if len(good) != 1:
        raise ValueError(f'1장 사건 메시지 자리를 하나로 정하지 못함: {[f"{f:03X}" for f in good]}')
    return good[0]


def named(messages):
    """{번호: 이름(글 빼고)} 사건 메시지. 장마다 그 자리에 그 모듈의 메시지가 놓였는지 확인한다."""
    import dq4ch1event
    import dq4ch2event
    import dq4ch3event
    import dq4chapter1
    first = _chapter1_first(messages)
    groups = [('ch1', None, dq4ch1event.message_ids(first), dq4ch1event.MESSAGES)]
    second = dq4chapter1.chapter2_message(first)
    groups.append(('ch2', None, dq4ch2event.message_ids(second), dq4ch2event.MESSAGES))
    groups += [('ch2', c.key, c.msg, c.module.MESSAGES) for c in dq4ch2event.contexts(second)
               if getattr(c.module, 'MESSAGES', None)]
    third = dq4chapter1.chapter3_message(first)
    groups.append(('ch3', None, dq4ch3event.message_ids(third), dq4ch3event.MESSAGES))
    groups += [('ch3', c.key, c.msg, c.module.MESSAGES) for c in dq4ch3event.contexts(third)
               if getattr(c.module, 'MESSAGES', None)]
    out = {}
    for chapter, key, ids, source in groups:
        if not ids:
            continue
        same = sum(_key(messages.get(ids[n])) == _key(source[n]) for n in ids)
        if same < MATCH * len(ids):
            raise ValueError(f'{chapter} {key or "본체"}: 메시지 {len(ids)}개 가운데 {same}개만 자리에 맞음')
        for n, i in ids.items():
            out[i] = '.'.join(p for p in (chapter, key, n) if p)
    return out


def table(messages):
    """{번호: 이름표}. messages 는 load 의 결과."""
    names = named(messages)
    out, seen = {}, {}
    for i in sorted(messages):
        d = digest(messages[i])
        if i in names:
            out[i] = f'{names[i]}@{d}'
        else:
            seen[d] = seen.get(d, 0) + 1
            out[i] = f'@{d}'
            if seen[d] > 1:
                out[i] += f'#{seen[d]}'
    return out


def labels(ids, table_):
    """번호 글(16진) 목록 → 이름표 목록. 잘림 표시('truncated')는 그대로. 롬에 없는 번호는 「?번호」(검사가 기준과 달라 실패)."""
    return [m if m == 'truncated' else table_.get(int(m, 16), f'?{m}') for m in ids]


def relabel(messages_path, path=None):
    """번호로 적은 걷기 기준을 이름표로 바꿔 쓴다. 기준의 모든 번호가 그 빌드에 있고, 이름표가 번호마다 하나뿐이며, 바꾼
    이름표를 다시 번호로 풀면 옛 기준과 똑같을 때만 쓴다(옛 번호 기준과 새 이름표 기준이 같은 메시지를 가리킴). 까닭은 그대로.
    [(변형, 시드, 구간, 번호들, 이름표들)] 을 돌려준다."""
    import dq4ch1walkcheck as wc
    path = path or wc.MESSAGES
    t = table(load(messages_path))
    back = {}
    for i, label in t.items():
        if label in back:
            raise ValueError(f'이름표 {label} 가 {back[label]:03X}·{i:03X} 둘에 붙음')
        back[label] = i
    rows = []
    for (variant, seed, name), e in wc.load_messages(path).items():
        got = labels(e['messages'], t)
        missing = [m for m, g in zip(e['messages'], got) if g.startswith('?')]
        if missing:
            raise ValueError(f'{name}: 빌드에 없는 번호 {missing}')
        again = [f'{back[g]:03X}' for g in got]
        if again != e['messages']:
            raise ValueError(f'{name}: 이름표를 번호로 풀면 {again}, 옛 기준 {e["messages"]}')
        rows.append((variant, seed, name, e['messages'], got))
    wc.write_messages([(v, s, n, g) for v, s, n, _, g in rows], '번호를 이름표로 적음(dq4msglabels)', path, keep_reasons=True)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--messages', required=True, type=Path, help='빌드 폴더의 messages.json')
    ap.add_argument('--relabel', action='store_true', help='번호로 적은 걷기 기준(ch1-walk-messages.toml)을 이름표로 바꿔 씀')
    ap.add_argument('ids', nargs='*')
    a = ap.parse_args()
    if a.relabel:
        for v, s, n, ids, got in relabel(a.messages):
            print(f'{v} {s} {n}: ' + ' '.join(f'{i}={g}' for i, g in zip(ids, got)))
        return 0
    t = table(load(a.messages))
    for m, label in zip(a.ids, labels(a.ids, t)):
        print(m, label)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
