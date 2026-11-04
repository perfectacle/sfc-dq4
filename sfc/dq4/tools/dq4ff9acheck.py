"""MesenCE 로 NMI 작업 FF9A(슬라임 레이스) 동안 창 글자 대기열이 나가는지 검사한다.

FF9A 작업은 03:A211 이 00:8800 으로 고른다. 03:A211 은 03:A1EE 안이고, 03:A1EE 를 부르는 곳은 슬라임 레이스 시설
처리기 06:F21E 하나다(대화 번호 00D, 원래 DQ5 인물로는 19/02 오라클베리 카지노에만 있음). 검사 롬으로 만든 배 선실
상태(dq4freshstate)에서 인물 슬롯의 대화 번호를 00D 로, 코인을 100 으로 두고 파파스에게 말을 걸어 레이스 화면까지
간다(lua/dq4ff9acheck.lua). 롬의 00:FF9A 에서 WqNmiFF9A·WqNmiEntry 자리를 읽어 둔다.

난수(7E:075B~075D)·시각(낮)을 고정하고 걸음 조우를 없앤 채(dq4ch1walkcheck.RNG·DAY_SET·NO_ENCOUNTERS) REPEAT 번 돌려
기록(nmi.txt·inject.txt)이 바이트째 같아야 한다.

통과 조건: FF9A 작업 NMI 가 있고, 그 NMI 마다 WqNmiEntry 가 한 번씩 돌고, FF9A 동안 넣은 대기열 항목이 매번 다음 NMI 에
나간다(항목 수 0, 넣기 전에는 VRAM 이 그 그림과 달랐고 넣은 뒤 같음). --original 은 원본 DQ5 롬이라 FF9A 작업이 도는 것만
본다. --break-entry 는 WqNmiEntry 첫 바이트를 RTL 로 바꾼 채(메모리에서만) 돌린다. 받침은 그대로라 정적 확인은 지나고,
NMI 마다 WqNmiEntry 에 들어가지만 대기열을 보내지 않으므로 이 검사가 실패해야 한다.

  MESENCE=… uv run --locked python sfc/dq4/tools/dq4ff9acheck.py --rom work/ch1/menu.sfc --out work/ff9acheck
  uv run --locked python sfc/dq4/tools/dq4ff9acheck.py --rom 롬 --facts      에뮬레이터 없이 부르는 곳 훑기·받침 바이트

파파스가 선실에 있어야 하므로 DQ5 새 게임이 남은 롬(dq4build 의 menu.sfc 등)으로 돌린다. 형식:
sfc/dq4/docs/dq4-window-text-format.md 「NMI 작업마다 걸기」.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

from dq4ch1walkcheck import DAY_SET, NO_ENCOUNTERS, RNG  # noqa: E402
import dq4freshstate  # noqa: E402
import dq4mesen  # noqa: E402
from dq4windowname import NMI_STUB as FIELD_STUB  # noqa: E402  필드 NMI 받침(JSL WqNmiEntry / JMP $8926)

FF9A_SITE = 0x00FF9A
# 선실에서 위의 파파스에게 말을 걸고(명령 창 → はなす), 레이스 안내를 A 로 넘긴다
PRE = 'b:4,wait:40,up:3,wait:20,a:4,wait:30,a:4,wait:200,' + ','.join(['a:4,wait:60'] * 30)
INJECT = 3
MAXF = 2800
REPEAT = 2


def lorom(addr):
    return (addr >> 16 & 0x7F) * 0x8000 + (addr & 0x7FFF)


def long_at(data, addr, opcode):
    """addr 의 4바이트 명령이 opcode(JML 5C / JSL 22)면 그 대상, 아니면 None."""
    b = data[lorom(addr):lorom(addr) + 4]
    return b[1] | b[2] << 8 | b[3] << 16 if b[0] == opcode else None


def entry_of(data):
    """(WqNmiFF9A, WqNmiEntry, WqNmiFF9A 의 첫 JSL 대상). WqNmiEntry 는 필드 받침 00:FF9E 의 JSL 대상에서 읽는다."""
    ff9a = long_at(data, FF9A_SITE, 0x5C)
    entry = long_at(data, FIELD_STUB, 0x22)
    if ff9a is None or entry is None:
        raise SystemExit(f'00:FF9A·00:FF9E 가 받침이 아님({data[lorom(FF9A_SITE):lorom(FF9A_SITE) + 8].hex(" ")})')
    return ff9a, entry, long_at(data, ff9a, 0x22)


def judge(nmi, inject, original):
    """(통과, 문제 목록). nmi = {작업: (횟수, WqNmiEntry 횟수)}, inject = [(작업, 항목 수, 넣은 뒤 같음, 넣기 전 같음)]."""
    problems = []
    count, entries = nmi.get(0xFF9A, (0, None))
    if not count:
        problems.append('FF9A 작업 NMI 가 없음')
    if not original:
        if count and entries != count:
            problems.append(f'FF9A NMI {count}번 가운데 WqNmiEntry {entries}번')
        if len(inject) != INJECT:
            problems.append(f'넣은 항목 확인 {len(inject)}번(기대 {INJECT})')
        for task, left, same, before in inject:
            if before:
                problems.append(f'작업 {task:04X}: 넣기 전부터 VRAM 이 넣을 그림과 같아 나갔는지 가릴 수 없음')
            elif task != 0xFF9A or left or not same:
                problems.append(f'작업 {task:04X} 항목 수 {left} VRAM {"같음" if same else "다름"}')
    return not problems, problems


def parse(folder):
    nmi = {}
    for line in (folder / 'nmi.txt').read_text().split('\n'):
        parts = line.split()
        if parts:
            nmi[int(parts[0], 16)] = (int(parts[1]), int(parts[3]) if len(parts) > 3 else None)
    inject = []
    for line in (folder / 'inject.txt').read_text().split('\n'):
        parts = line.split()
        if parts:
            inject.append((int(parts[4], 16), int(parts[6]), parts[8] == 'same', parts[10] == 'same'))
    return nmi, inject


# 부르는 곳을 훑을 대상: (이름, CPU 주소). JSL·JML 은 롬 전체, JSR 은 대상과 같은 뱅크만
CALLEES = (('00:8800', 0x008800), ('03:A1EE', 0x03A1EE))
# 받침·레이스 처리기 바이트를 견줄 자리: (이름, CPU 주소, 길이)
RANGES = (('00:FF9A', 0x00FF9A, 4), ('00:FF9E', 0x00FF9E, 7), ('03:A1EE', 0x03A1EE, 0x69), ('06:F210', 0x06F210, 0x12))


def callers(data, target):
    """target 을 부르는 {'JSL': [...], 'JML': [...], 'JSR': [...]}(CPU 주소 'BB:AAAA'). 바이트 모양만 본다."""
    lo, hi, bank = target & 0xFF, target >> 8 & 0xFF, target >> 16
    out = {}
    for name, pattern, banks in (('JSL', bytes((0x22, lo, hi, bank)), None), ('JML', bytes((0x5C, lo, hi, bank)), None),
                                 ('JSR', bytes((0x20, lo, hi)), {bank})):
        hits, i = [], data.find(pattern)
        while i >= 0:
            b = i // 0x8000
            if banks is None or b in banks:
                hits.append(f'{b:02X}:{0x8000 + i % 0x8000:04X}')
            i = data.find(pattern, i + 1)
        out[name] = hits
    return out


def facts(data):
    """에뮬레이터 없이 롬에서 읽는 근거: 부르는 곳, 받침·처리기 바이트(16진), 패치 롬이면 WqNmiFF9A·WqNmiEntry 바이트."""
    out = {'callers': {name: callers(data, addr) for name, addr in CALLEES},
           'bytes': {name: data[lorom(a):lorom(a) + n].hex(' ') for name, a, n in RANGES}}
    ff9a = long_at(data, FF9A_SITE, 0x5C)
    if ff9a is not None:
        out['bytes']['WqNmiFF9A'] = data[lorom(ff9a):lorom(ff9a) + 12].hex(' ')
        entry = long_at(data, FIELD_STUB, 0x22)
        if entry is not None:
            end = data.index(0x6B, lorom(entry))
            out['bytes']['WqNmiEntry'] = data[lorom(entry):end + 1].hex(' ')
    return out


def break_entry(entry):
    """WqNmiEntry 첫 바이트를 RTL(6B)로 바꾸는 ROMPATCH(파일 오프셋=바이트)."""
    return f'{lorom(entry):X}=6B'


def same_runs(folders):
    """실행마다 기록 두 파일이 바이트째 같은지."""
    texts = [tuple((f / n).read_bytes() for n in ('nmi.txt', 'inject.txt')) for f in folders]
    return all(t == texts[0] for t in texts)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', type=Path, required=True)
    dq4freshstate.add_argument(ap)
    ap.add_argument('--original', action='store_true', help='원본 DQ5 롬: FF9A 작업이 도는 것만 본다')
    ap.add_argument('--break-entry', action='store_true', help='WqNmiEntry 를 RTL 로 바꾼 변이(실패해야 함)')
    ap.add_argument('--out', type=Path)
    ap.add_argument('--facts', action='store_true', help='에뮬레이터 없이 부르는 곳 훑기·받침 바이트를 JSON 으로 찍고 끝')
    a = ap.parse_args()
    if a.facts:
        print(json.dumps(facts(a.rom.read_bytes()), ensure_ascii=False, indent=1))
        return 0
    if a.out is None:
        ap.error('--out 이 필요함')
    mesence = os.environ.get('MESENCE')
    if not mesence:
        ap.error('MESENCE 에 MesenCE 실행 파일을 주세요')
    out = a.out.resolve()
    if out.exists() and any(out.iterdir()):
        ap.error(f'{out} 가 비어 있지 않음')
    out.mkdir(parents=True, exist_ok=True)
    data = a.rom.read_bytes()
    env = dict(os.environ, TALK='0D', COINS='100', PRE=PRE, MAXF=str(MAXF), SHOT='1800',
               SET=f'{RNG};{DAY_SET}', ROMPATCH=NO_ENCOUNTERS,
               LIBDIR=os.environ.get('LIBDIR') or subprocess.check_output(
                   ['uv', 'run', '--locked', 'krpatch', 'sfc', 'lua'], text=True).strip())
    report = {'rom': str(a.rom), 'break_entry': a.break_entry}
    if not a.original:
        ff9a, entry, called = entry_of(data)
        env.update(ENTRY=f'{entry:06X}', INJECT=str(INJECT))
        report.update(wq_nmi_ff9a=f'{ff9a:06X}', wq_nmi_entry=f'{entry:06X}')
        if called != entry:
            report['first_call'] = None if called is None else f'{called:06X}'
        if a.break_entry:
            env['ROMPATCH'] += ';' + break_entry(entry)
    state = dq4freshstate.resolve(a.state, mesence, a.rom, out / 'start')
    env['STATE'] = str(state)
    folders = [out / f'run{i + 1}' for i in range(REPEAT)]
    for folder in folders:
        folder.mkdir()
        with (folder / 'mesen.log').open('w') as log:
            dq4mesen.testrunner(mesence, str(a.rom.resolve()), str(HERE / 'lua' / 'dq4ff9acheck.lua'),
                                env=dict(env, SHOT_DIR=str(folder)), stdout=log, stderr=subprocess.STDOUT,
                                timeout=300, check=False)
        if not (folder / 'nmi.txt').exists():
            raise SystemExit(f'{folder.name}/nmi.txt 가 없음(MesenCE 가 MAXF 전에 멈춤)')
    nmi, inject = parse(folders[0])
    ok, problems = judge(nmi, inject, a.original)
    if not same_runs(folders):
        ok, problems = False, problems + ['같은 입력의 실행끼리 기록이 다름']
    if 'first_call' in report:
        ok, problems = False, problems + [f'WqNmiFF9A 의 첫 명령이 WqNmiEntry 를 부르지 않음({report["first_call"]})']
    report.update(status='passed' if ok else 'failed', problems=problems,
                  nmi={f'{k:04X}': {'count': c, 'entry': e} for k, (c, e) in nmi.items()},
                  inject=[{'task': f'{t:04X}', 'left': n, 'vram_same': s, 'vram_same_before': b}
                          for t, n, s, b in inject])
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({k: report[k] for k in ('status', 'problems', 'nmi')}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
