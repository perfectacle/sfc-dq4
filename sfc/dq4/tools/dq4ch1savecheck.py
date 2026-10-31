"""1장 롬에서 저장 → 리셋 → 이어 하기와 전멸 → 교회를, 1장 걷기 검사(dq4ch1walkcheck.py)가 남긴 구간 끝 세이브스테이트에서
본다(MesenCE 헤드리스).

  save   구간 끝에서 바트랜드 교회 36/00 의 신부 옆 칸으로 순간이동해 저장하고, 같은 실행에서 리셋해 타이틀 →
         모험을 한다 → 칸 1 로 잇는다. 이어 하기 루틴(25:824F)이 돌고 DQ5 로고 장면(0F:D93A)은 불리지 않는지,
         불러온 7E:2000~2A9F 가 기록 칸과 같은지(다른 바이트를 적음), 1장 깃발과 맵의 인물 대화 번호(7E:36E0~)가 저장할 때와
         같은지 본다. 리셋 뒤 뜬 메시지 번호와 저장할 때·이어 한 뒤의 화면(sNNNNN.png)을 남긴다
  wipe   호이민 합류 뒤 우물 아래 3B/00 으로 가 일행 HP 를 1, 걸음마다 전투(dq4dungeonencountercheck.rates)로 두고
         싸워 전멸한다. 1장 귀환 자리(교회 신부 앞) 하나로 돌아오는지, 깃발이 그대로인지, 금화가 반이 되는지 본다

  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4ch1walkcheck.py --rom work/ch1/dq4-ch1.sfc --out work/ch1walk
  MESENCE=… LIBDIR=… python sfc/dq4/tools/dq4ch1savecheck.py --rom work/ch1/dq4-ch1.sfc --states work/ch1walk \\
      --out work/ch1save
형식은 sfc/dq4/docs/dq4-chapter1-format.md 「저장과 이어 하기」.
"""
import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DQ5_TOOLS = HERE.parents[1] / 'dq5' / 'tools'
sys.path[:0] = [str(HERE), str(DQ5_TOOLS)]

import dq4ch1walkcheck as walk  # noqa: E402
import dq4dungeonencountercheck as enc  # noqa: E402
import dq4groupcheck  # noqa: E402
import dq4wellresetcheck as well  # noqa: E402
import dq4wellswitch  # noqa: E402
from dq5exitcheck import warp_exit  # noqa: E402
from dq5sram import SLOTS, SIZE as SRAM_SIZE  # noqa: E402

# (장면, 걷기 검사 구간). 그 구간이 끝난 세이브스테이트에서 저장한다
POINTS = [
    ('prologue', 'prologue'),          # 서장 끝, 1장 왕좌의 방 연출 뒤
    # 성 마을 36/00 에서 끝나는 구간은 같은 맵으로 순간이동하면 도착을 알아보지 못해, 이무르 밤 구간 끝에서 저장한다
    ('night', 'night_child'),          # 이무르 밤에 아이에게 들음
    ('hoimin', 'hoimin'),              # 우물 아래에서 호이민 합류
    ('boss', 'boss'),                  # 탑 위 보스 뒤, 아이들이 따라옴
    ('report', 'homecoming'),          # 아이 귀가 뒤, 왕에게 보고하기 전
]
# 신부(10,41)의 오른쪽 옆 칸 (12,41). 순간이동은 목적지에서 아래로 한 걸음 내려 서므로 한 줄 위를 준다
CHURCH = '36/00,12,40'
# 필드는 7E:007F & 7 = 0 인 프레임에만 입력을 읽어(dq4npccheck.TALKS), 짧게 누르면 먹히지 않는다. 서 있으면 뜨는
# 상태·작전 창이 있을 때의 A 는 그 창만 닫으므로 먼저 B 로 닫고 쉬지 않고 돌아서 A 를 누른다. 기록한 뒤
# 「このまま ぼうけんを つづけますか？」 에 A 로 답하면 다시 말을 걸어 한 번 더 기록한다
TALK = 'wait:40,b:8,wait:20,left:20,wait:2,a:8,wait:40,a:8,' + ','.join(['wait:60,a:8'] * 54)
SAVED, RESET, LOADED = well.SAVED, well.RESET, well.LOADED
# 이어 하면 신부 앞에 서므로 남은 A 가 신부와 대화를 연다. 그 창의 한글을 그림으로 남긴다
SHOT = LOADED + 600
# 인물 슬롯 32개의 대화 번호(아래 바이트 32개, 위 바이트 32개). 맵이 쓰는 슬롯은 8 부터 7E:1983 앞까지이고,
# 그 뒤 슬롯에는 앞 맵의 값이 남는다(이어 하기는 리셋으로 지워져 0)
TALKS, TALKS_SIZE, USED_SLOTS = 0x7E36E0, 0x40, 0x7E1983
LOGO = '0FD93A'                        # 프롤로그 뒤 로고 장면의 BRK 19 15(dq4-overture-format.md)
CONTINUE_PATH = '25824F'
MESSAGE = '248BAF'
WELL = dq4wellswitch.FLAG[0] & 0xFFFF
# 우물 아래 3B/00 의 계단 옆. 전투가 끝나면 전멸 처리(01:88EF)를 지난다
WIPE_TO = '3B/00,6,43'
GOLD = 1000
# 1장 귀환 자리(dq4chapter1.return_places): 전멸하면 마지막에 들어간 마을($195E)의 교회 신부 앞
RETURNS = {'36/00': [10, 45], '37/00': [50, 9]}


def flags(ram):
    """7E:2000 부터의 바이트에서 걷기 검사의 깃발."""
    return sorted(k for k, (a, m) in walk.FLAGS.items() if ram[(a & 0xFFFF) - 0x2000] & m)


def used_talks(got, at):
    """그 프레임에 맵이 쓰는 인물 슬롯(8 부터 7E:1983 앞까지)의 대화 번호."""
    table, used = got.get((at, TALKS), b''), got.get((at, USED_SLOTS), b'\0')[0]
    return [f'{table[0x20 + n]:X}{table[n]:02X}' for n in range(8, min(used, 0x20))] if table else None


def church(mesence, rom, state, dest):
    walk.run(mesence, rom, walk.WARP, dest, {'STATE': str(state), 'TO': CHURCH, 'SAVE': 'church.mss', 'SETTLE': '120',
                                             'MAXF': '1500', 'WARPEXIT': f'{warp_exit(rom):X}',
                                             'ANYWHERE': '1', 'ROMPATCH': walk.NO_ENCOUNTERS}, 300)
    text = (dest / 'warp.txt').read_text(encoding='utf-8') if (dest / 'warp.txt').exists() else ''
    found = re.search(r'arrived map (\w\w/\w\w)', text)
    return found[1] if found else None


def save_continue(mesence, rom, state, dest):
    copy = dest / f'{dest.name}-{os.getpid()}.sfc'      # MesenCE 는 배터리 기록을 롬 파일 이름으로 둔다
    shutil.copyfile(rom, copy)
    # 길이는 10진
    dumps = [f'{SAVED - 50}:7E2000:{well.SAVE_SIZE}', f'{SAVED}:700000:{SRAM_SIZE}',
             f'{LOADED}:7E2000:{well.SAVE_SIZE}', f'{LOADED}:7E00BC:2', f'{LOADED}:7E3020:1', f'{LOADED}:7E3080:1']
    for at in (SAVED - 50, LOADED):
        dumps += [f'{at}:{TALKS:06X}:{TALKS_SIZE}', f'{at}:{USED_SLOTS:06X}:1']
    env = dict(os.environ, STATE=str(state), SHOT_DIR=str(dest), NEXT=str(DQ5_TOOLS / 'lua' / 'dq5msg.lua'),
               PRE=f'{TALK},wait:400,{well.CONTINUE}', RESETAT=str(RESET), MAXF=str(SHOT + 10),
               CALLS=f'{CONTINUE_PATH},{LOGO},{MESSAGE}', ROMPATCH=walk.NO_ENCOUNTERS, SHOTS=f'{SAVED - 50},{SHOT}',
               DUMP=';'.join(dumps))
    subprocess.run([str(mesence), '--testrunner', str(copy), str(DQ5_TOOLS / 'lua' / 'dq5cdldump.lua'),
                    '--Snes.DisableFrameSkipping=true'], env=env, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=900, check=False)
    copy.unlink()
    text = (dest / 'msg.txt').read_text(encoding='utf-8') if (dest / 'msg.txt').exists() else ''
    got = {(int(m[1]), int(m[2], 16)): bytes.fromhex(m[3])
           for m in re.finditer(r'(\d+) dump ([0-9A-F]{6}) ([0-9A-F ]+)', text)}
    calls = [(int(f), pc, a) for f, pc, a in re.findall(r'^(\d+) (\w{6}) A=(\w+)', text, re.M)]
    return got, calls


def save_scene(mesence, rom, states, out, name, segment):
    dest = out / name
    dest.mkdir(parents=True)
    arrived = church(mesence, rom, states / segment / 'end.mss', dest / 'warp')
    if arrived != '36/00' or not (dest / 'warp' / 'church.mss').exists():
        return name, {'status': 'failed', 'problems': [f'교회에 닿지 못함({arrived})']}
    got, calls = save_continue(mesence, rom, dest / 'warp' / 'church.mss', dest)
    before, sram, loaded = (got.get(k, b'') for k in ((SAVED - 50, 0x7E2000), (SAVED, 0x700000), (LOADED, 0x7E2000)))
    problems = []
    if not (before and sram and loaded):
        return name, {'status': 'failed', 'problems': ['덤프가 모자람(저장·이어 하기가 끝나지 않음)']}
    # 이어 한 칸: 불러온 7E:2000~2A9F 와 가장 적게 다른 기록 칸
    slots = [sram[at:at + well.SAVE_SIZE] for at in SLOTS]
    number = min(range(len(slots)), key=lambda n: sum(a != b for a, b in zip(slots[n], loaded)))
    slot = slots[number]
    after_reset = [c for c in calls if c[0] >= RESET]
    if not any(pc == CONTINUE_PATH for _, pc, _ in after_reset):
        problems.append('이어 하기 루틴 25:824F 가 돌지 않음')
    if any(pc == LOGO for _, pc, _ in calls):
        problems.append('로고 장면 0F:D93A 가 불림')
    differ = [f'{0x2000 + i:04X}' for i, (a, b) in enumerate(zip(slot, loaded)) if a != b]
    # 우물 깃발은 이어 하기 훅이 끈다(dq4wellswitch)
    unexpected = [a for a in differ if a != f'{WELL:04X}']
    if unexpected:
        problems.append(f'불러온 WRAM 이 기록 칸과 다름: {" ".join(unexpected)}')
    if flags(before) != flags(loaded):
        problems.append(f'깃발이 다름: 저장 {flags(before)}, 이어 하기 {flags(loaded)}')
    if before != slot:
        problems.append(f'기록 칸 {number + 1} 이 저장할 때의 WRAM 과 다름')
    talks = [used_talks(got, at) for at in (SAVED - 50, LOADED)]
    if talks[0] != talks[1]:
        problems.append(f'인물 대화 번호가 다름: 저장 {talks[0]}, 이어 하기 {talks[1]}')
    bc = got.get((LOADED, 0x7E00BC), b'\0\0')
    where = f'{bc[0]:02X}/{bc[1]:02X}'
    if where != '36/00':
        problems.append(f'이어 한 맵 {where}')
    cell = [got.get((LOADED, 0x7E3020), b'\0')[0], got.get((LOADED, 0x7E3080), b'\0')[0]]
    return name, {'status': 'failed' if problems else 'passed', 'problems': problems, 'map': where, 'cell': cell,
                  'flags': flags(loaded), 'slot': number + 1, 'slot_differs': differ, 'people': len(talks[1]),
                  'messages_after_reset': [f'{int(a, 16) & 0xFFFF:03X}' for _, pc, a in after_reset if pc == MESSAGE]}


def wipe_scene(mesence, rom, states, out):
    name = 'wipe'
    dq4groupcheck.WARP = DQ5_TOOLS / 'lua' / 'dq5warptrace.lua'
    gold = f'2019={GOLD & 0xFF:02X};201A={GOLD >> 8:02X};201B=00'
    # 일행 레코드는 7E:2040 부터 42바이트씩, 지금 HP 는 +2
    hp = ';'.join(f'{0x2042 + 42 * n:04X}=01;{0x2043 + 42 * n:04X}=00' for n in range(2))
    got = dq4groupcheck.scene(mesence, rom, states / 'hoimin' / 'end.mss', out, name, TO=WIPE_TO, MAXF='6000',
                              TEST=well.WIPE_TEST, SET=f'{gold};{hp};{WELL:04X}|{dq4wellswitch.FLAG[1]:02X}', ROMPATCH=enc.rates(rom.read_bytes()), TRACE='0188EF',
                              LOG='7E201D')
    rows = list(enc.lines(out / name / 'trace.txt')) if (out / name / 'trace.txt').exists() else []
    ram = (out / name / 'final.wram').read_bytes() if (out / name / 'final.wram').exists() else bytes(0x20000)
    wram = ram[0x2000:0x2000 + well.SAVE_SIZE]
    gold_after = ram[0x2019] | ram[0x201A] << 8 | ram[0x201B] << 16
    party = ram[0x201D]
    hps = [ram[0x2042 + 42 * n] | ram[0x2043 + 42 * n] << 8 for n in range(party)]
    problems = []
    if not any(pc == '0188EF' for _, pc, _ in rows):
        problems.append('전멸 처리 01:88EF 를 지나지 않음')
    if RETURNS.get(got.get('map')) != got.get('cell'):
        problems.append(f'돌아온 자리 {got.get("map")} {got.get("cell")}')
    want = {k for k, v in walk.FLAGS.items() if k in ('CHAPTER1', 'NIGHT_TOLD', 'FLARE', 'REUNITED', 'HOIMIN')}
    if not want <= set(flags(wram)):
        problems.append(f'깃발이 꺼짐: {sorted(want - set(flags(wram)))}')
    if gold_after != GOLD // 2:
        problems.append(f'금화 {gold_after}(기대 {GOLD // 2})')
    if not hps or not hps[0]:
        problems.append('주인공 HP 0')
    return name, {'status': 'failed' if problems else 'passed', 'problems': problems, **got, 'flags': flags(wram),
                  'gold': gold_after, 'party': party, 'hp': hps}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--states', required=True, type=Path, help='dq4ch1walkcheck.py 의 출력 폴더')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--jobs', type=int, default=3)
    ap.add_argument('--only', nargs='+', help='이 장면만(prologue night hoimin boss report wipe)')
    args = ap.parse_args()
    mesence = Path(os.environ['MESENCE'])
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty')
    out.mkdir(parents=True, exist_ok=True)
    rom = out / 'c.sfc'
    shutil.copyfile(args.rom.resolve(), rom)
    states = args.states.resolve()
    keep = set(args.only or [n for n, _ in POINTS] + ['wipe'])
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        jobs = [pool.submit(save_scene, mesence, rom, states, out, n, s) for n, s in POINTS if n in keep]
        if 'wipe' in keep:
            jobs.append(pool.submit(wipe_scene, mesence, rom, states, out))
        results = dict(f.result() for f in jobs)
    ok = all(r['status'] == 'passed' for r in results.values())
    report = {'status': 'passed' if ok else 'failed', 'scenes': results}
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
