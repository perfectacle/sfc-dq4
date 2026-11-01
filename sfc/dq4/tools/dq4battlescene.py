"""1장 롬의 전투 장면 검사(libretro snes9x·bsnes 헤드리스). 저장 기록(dq4savefixture)으로 전투 직전 상태를 만들어
이어 하기로 시작하고, 전투 한 판을 WRAM 으로 판정한다. 형식은 sfc/dq4/docs/dq4-battle-scene-format.md.

장면(SCENES): 보통 공격(회심 셈)·중간 수비, 도망·도망칠 수 없는 무리·몬스터 도망, 약초, 호이민의 ホイミ, 레벨업 한 번·두 번,
전멸, 탑 위 보스(보스 패치 없이). 알려진 문제를 재는 nosong·growth 는 기본 묶음 밖(--scenes 로 고름).
- 걸음 전투는 조우 루틴 23:E7C2 를 cheat 로 「무리를 7E:1001~ 에 쓰고 구역 레벨 $100F·무리 플래그 $1000 을 둔 뒤
  carry 를 켜 돌아옴」으로 덮어 탑 39/01 (20,16)에서 아래로 한 걸음 내디뎌 붙인다. 전투가 걸리면 cheat 를 풀어
  롬의 「조우 없음」(dq4ch1walkcheck.NO_ENCOUNTERS)으로 돌아간다.
- 몬스터 능력치는 장면마다 롬 사본에서 고친다(보스 장면은 고치지 않음).
- 차례가 오면(창 번호 7E:0A00 이 FF → 17) 장면의 차례 입력을 그 프레임 기준으로 누른다. 몬스터가 다 쓰러지거나
  일행이 다 쓰러지면 A 를 30프레임마다 눌러 메시지를 넘긴다. 전투가 끝난 것은 7E:0070 과 7E:00E6 이 전투 동안
  0 이 아니었다가 둘 다 0 이 된 프레임으로 본다.
- 끝난 뒤: 지금 곡 $1D8B 가 기대 맵 곡이 될 때까지 기다리고(곡 복귀), 장면의 뒤 입력(대화 넘기기)을 누른 다음
  한 방향으로 걸어 칸이 바뀌는지(멈춤 없음) 본다.
- 시드는 전투를 붙이기 직전의 난수 7E:075B~075D(dq4ch1walkcheck.rng_for). 장면마다 한 프로세스가 이어 하기·
  순간이동을 한 번 하고 그 상태를 시드마다 다시 불러 쓴다.

  python sfc/dq4/tools/dq4cores.py
  python sfc/dq4/tools/dq4battlescene.py --rom work/ch1/dq4-ch1-full.sfc --out work/battlescene [--seeds 0,1,2]
      [--scenes attack,flee] [--core snes9x|bsnes|all] [--jobs 4]
결과: OUT/results.json(장면·코어·시드마다 판정과 요약), OUT/<장면>-<코어>/seed-N/*.png.
"""
import argparse
import concurrent.futures
import hashlib
import json
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(HERE.parents[1] / 'dq5' / 'tools')]

import dq4balance  # noqa: E402
import dq4ch1event as ev  # noqa: E402
import dq4ch1walkcheck as wc  # noqa: E402
import dq4compatcheck as cc  # noqa: E402
import dq4cores  # noqa: E402
import dq4savefixture as fx  # noqa: E402

ENCOUNTER = 0x11E7C2              # 23:E7C2 파일 오프셋(dq4battlecheck.ENCOUNTER)
GROUP = 0x7E1001
WINDOW, CURSOR = 0x7E0A00, 0x7E0AD7
TURN_WINDOW = 0x17                # 차례가 올 때 7E:0A00 이 FF 에서 이 값으로 바뀐다(실측)
# 입력을 기다리는 전투 창: 싸우기/도망 1B, 공격/방어/도구 17·1E, 물건 24. 이 창에서는 메시지 넘기기 A 를 누르지 않는다
INPUT_WINDOWS = (0x17, 0x1B, 0x1E, 0x24)
FIELD_WINDOW = 0x01               # 맵의 명령 창: 전투가 끝나 조작이 돌아왔다는 표지
SONG = 0x7E1D8B
SONG_VICTORY, SONG_LOSE = 0x1F, 0x0B
FLAGS_1000, ZONE_LEVEL = 0x7E1000, 0x7E100F
ATTACK_ONLY = (0x73,) * 6            # 행동 여섯을 모두 たたかう(슬라임의 にげる 를 막음)
MONSTER_SLOTS, MONSTER_SLOT = 0x7E07C0, 16
PARTY_SLOTS, PARTY_SLOT = 0x7E0760, 12
HERO = 0x7E2040
RECORD = 42
HP, MP, AGI, STR, DEF, WIS, LUCK, EXP, MAX_HP, MAX_MP, LEVEL, ITEMS, NEXT = (
    0x02, 0x04, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0E, 0x10, 0x12, 0x16, 0x26)
# dq5growth.STATS 차례(최대 HP, 최대 MP, ちから, すばやさ, かしこさ, うんのよさ, みのまもり)의 일행 기록 자리
GROWTH_FIELDS = ((MAX_HP, 2), (MAX_MP, 2), (STR, 1), (AGI, 1), (WIS, 1), (LUCK, 1), (DEF, 1))
GOLD = 0x7E2019
HERB = 0xA1                       # DQ5 やくそう
HOIMI = 0x27                      # 행동 ホイミ(やくそう 도 이 처리 루틴, dq5-data-format 「물건」)
FC_HOIMI = 0x29                   # FC 행동 ID ホイミ(fc/dq4/docs/dq4-data-format.md 「HP 회복」)
FC_RYAN = 6                       # FC 인물 번호 ライアン(dq4data.PARTY)
NO_ITEM = 0xFF
TOWER = '39/01,20,16'
BOSS_CELL = '39/04,46,23'
CHURCH = ('36/00', 10, 45)        # 바트랜드 교회 신부 앞(전멸 뒤 다시 시작 자리, dq4-chapter1-format)
MAP_SKIP = '21A5&BF'              # 맵 곡 건너뛰기 비트를 끈다(새 게임 밑판은 켠 채 기록됨)
STEP_LIMIT, START_LIMIT = 120, 2400
BATTLE_LIMIT = 9000               # 전투가 걸린 뒤 끝나기까지. 넘으면 멈춤
SONG_LIMIT = 900                  # 전투가 끝난 뒤 맵 곡이 돌아오기까지
FINISH_LIMIT = 3000               # 몬스터·일행이 다 쓰러진 뒤 전투가 끝나기까지(레벨업 뒤 멈춤 7,313프레임을 잡음)
MASH = 30

# 차례 입력: (차례가 온 프레임 기준, 버튼). 싸우기/도망 창은 한 줄 두 칸, 공격/방어/도구 창은 한 줄 세 칸(주문이
# 없는 라이언)이고 커서는 창마다 맨 위에서 시작한다.
TURNS = {
    'attack': ((20, 'a'), (50, 'a'), (80, 'a')),
    'defend': ((20, 'a'), (50, 'down'), (80, 'a')),
    'flee': ((20, 'down'), (50, 'a')),
    # 도구 → 셋째 물건(물건 창은 두 칸씩, 앞 둘은 밑판의 ぬののふく·ひのきのぼう라 아래 한 번) → 대상 주인공
    'herb': ((20, 'a'), (50, 'down'), (75, 'down'), (100, 'a'), (140, 'down'), (170, 'a'), (210, 'a')),
}


def monster_patch(rom, n, hp=None, attack=None, defense=None, actions=ATTACK_ONLY):
    """몬스터 레코드(23:8000 + 25n, dq5tables.MONSTER_FIELDS)의 HP·공격·수비·행동 여섯을 바꾼 [(파일 오프셋, 바이트)]."""
    base = wc.MONSTERS + n * 25
    b = {k: rom[base + k] for k in (1, 2, 3, 8, 10)}
    if actions is not None:
        b.update({17 + k: a for k, a in enumerate(actions)})
    if hp is not None:
        b[3], b[10] = hp & 0xFF, b[10] & ~0x07 & 0xFF | hp >> 8 & 7
    if attack is not None:
        b[1], b[8] = attack & 0xFF, b[8] & 0x7F | (attack >> 8 & 1) << 7
    if defense is not None:
        b[2], b[8] = defense & 0xFF, b[8] & 0xBF | (defense >> 8 & 1) << 6
    return [(base + k, v) for k, v in sorted(b.items())]


def flee_tries(scene, turns, switched):
    """도망을 고른 차례 수. 차례 입력이 도중에 바뀌면(then) 바뀐 차례 앞뒤로 나눠 센다."""
    then = scene.get('then', (None, None))[0]
    if scene['turn'] == 'flee':
        return turns if switched is None else switched - 1
    if then == 'flee' and switched is not None:
        return turns - switched + 1
    return 0


def monster_values(rom, n):
    base = wc.MONSTERS + n * 25
    r = rom[base:base + 25]
    return {'hp': r[3] | (r[10] & 7) << 8, 'attack': r[1] | (r[8] >> 7) << 8, 'defense': r[2] | (r[8] >> 6 & 1) << 8,
            'exp': r[5] | r[6] << 8, 'gold': r[7] | (r[8] >> 2 & 3) << 8}


def force_code(group, zone_level, flags=0):
    """23:E7C2 를 덮는 코드: 무리(dq4battlecheck.force_patch 와 같은 바이트) 뒤 $100F = 구역 레벨, $1000 = 무리 플래그."""
    if not 1 <= len(group) <= 4:
        raise ValueError('무리는 1~4종')
    monsters = [m for m, _ in group] + [0xFF] * (4 - len(group))
    counts = [c for _, c in group] + [0] * (4 - len(group))
    data = monsters + counts + [0] * 4
    code = bytearray((0x08, 0xC2, 0x20))
    for k in range(6):
        addr = GROUP + 2 * k
        code += bytes((0xA9, data[2 * k], data[2 * k + 1], 0x8F, addr & 0xFF, addr >> 8 & 0xFF, addr >> 16))
    code += bytes((0xE2, 0x20, 0xA9, zone_level, 0x8F, 0x0F, 0x10, 0x7E, 0xA9, flags, 0x8F, 0x00, 0x10, 0x7E))
    code += bytes((0x28, 0x38, 0x6B))
    return bytes(code)


def group_sentinel(group):
    """전투가 걸렸는지 볼 7E:1001~1004(몬스터 번호, 빈 자리 FF)."""
    return bytes([m for m, _ in group] + [0xFF] * (4 - len(group)))


# --- 기대값(롬 없이 단위 테스트) ---------------------------------------------------------------------------

def normal_values(attack, defense):
    """일행의 たたかう 보통 피해(20:B030, dq5-data-format 「전투 계산식」)가 나올 수 있는 값들(난수마다 하나, 같은
    무게). 맞는 쪽은 몬스터."""
    if attack < defense // 2:
        return [0, 1]
    h = (attack - defense // 2) // 2
    if h <= 0:
        return [0, 1]
    if h < 8:
        return [max(0, h - 1 + r) for r in range(3)]
    return [h * 7 // 8 + r * (h // 4 + 1) // 256 for r in range(256)]


def normal_range(attack, defense):
    v = normal_values(attack, defense)
    return min(v), max(v)


def crit_range(attack):
    """회심(20:AB04): 공격력 × (55 + 난수 0~10) × 4 / 256, 수비 무시."""
    return attack * 55 * 4 // 256, attack * 65 * 4 // 256


def classify_hit(drop, attack, defense, killed=False):
    """몬스터 HP 가 준 양 하나 → 'normal'·'crit'·'kill'·None. 쓰러뜨린 한 방은 남은 HP 만큼만 줄어 보통·회심을 가를
    수 없지만, 그래도 둘 중 큰 최댓값을 넘으면 None."""
    lo, hi = normal_range(attack, defense)
    clo, chi = crit_range(attack)
    if killed:
        return 'kill' if drop <= max(hi, chi) else None
    if clo <= drop <= chi and not lo <= drop <= hi:
        return 'crit'
    if lo <= drop <= hi:
        return 'normal'
    return None


def mean_problem(drops, attack, defense, z=None):
    """보통 피해 여러 개의 평균이 난수 분포의 평균에서 z 표준오차 안인지. 10개 미만이면 보지 않음."""
    z = Z if z is None else z
    if len(drops) < 10:
        return None
    v = normal_values(attack, defense)
    mu = sum(v) / len(v)
    var = sum((x - mu) ** 2 for x in v) / len(v)
    got = sum(drops) / len(drops)
    if abs(got - mu) > z * math.sqrt(var / len(drops)) + 1e-9:
        return f'보통 피해 {len(drops)}개 평균 {got:.2f}, 기대 {mu:.2f} ± {z * math.sqrt(var / len(drops)):.2f}'
    return None


def heal_expect(hp, max_hp, base, width):
    """ホイミ·やくそう(27:8071 의 바탕·폭): 회복 뒤 HP 의 (최소, 최대)."""
    return min(max_hp, hp + base), min(max_hp, hp + base + max(width, 1) - 1)


# --- 통계 구간 -----------------------------------------------------------------------------------------------

Z = 3.29                          # 양쪽 99.9%
ALPHA = 0.001
MIN_N = 30
CRIT_P = 1 / 32                   # 20:C697: 난수(0~31)가 0
# 도망 시도 횟수 $1016(0~3)별 실패 확률: 27:8008 = 02 02 04 08 에서 n 을 골라 난수(0~n-1)가 0 이면 실패
FLEE_FAIL = (1 / 2, 1 / 2, 1 / 4, 1 / 8)


def binom_interval(n, p, alpha=ALPHA):
    """이항(n, p)의 양쪽 1-alpha 구간 (lo, hi): P(X < lo) ≤ alpha/2, P(X > hi) ≤ alpha/2."""
    cdf, lo, hi = 0.0, None, n
    for k in range(n + 1):
        cdf += math.comb(n, k) * p ** k * (1 - p) ** (n - k)
        if lo is None and cdf > alpha / 2:
            lo = k
        if cdf >= 1 - alpha / 2:
            hi = k
            break
    return lo, hi


def flee_expect(tries_by_order):
    """시도 차례별 (시도 수, 실패 수) → (기대 실패 수, 표준편차, 실제 실패 수)."""
    mean = var = got = 0.0
    for k, (n, f) in enumerate(tries_by_order):
        q = FLEE_FAIL[min(k, 3)]
        mean += n * q
        var += n * q * (1 - q)
        got += f
    return mean, math.sqrt(var), got


# --- 판정 ---------------------------------------------------------------------------------------------------

def judge_common(s, expect):
    """모든 장면: 전투가 걸리고, 끝나고(멈춤 없음), 곡이 돌아오고, 걸을 수 있음."""
    problems = []
    if s.get('start') is None:
        return ['전투가 걸리지 않음']
    if s.get('end') is None:
        if s.get('moved_after_timeout'):
            return [f"전투 뒤 {s.get('timeout_at', '?')} 프레임까지 맵 곡이 돌아오지 않음(걷기는 됨, 마지막 곡 {s.get('last_song')})"]
        return [f"전투가 {s.get('timeout_at', '?')} 프레임까지 끝나지 않음(멈춤, 마지막 곡 {s.get('last_song')})"]
    limit = expect.get('finish_limit', FINISH_LIMIT)
    if s.get('finished') is not None and s['end'] - s['finished'] > limit:
        problems.append(f"다 쓰러진 뒤 {s['end'] - s['finished']} 프레임 만에 끝남(한도 {limit})")
    want_song = expect.get('song')
    if want_song is not None and s.get('song_at_end') != want_song:
        problems.append(f"조작이 돌아왔을 때 곡 {s.get('song_at_end')}, 기대 맵 곡 {want_song:02X}")
    if want_song is None and s.get('song_back') is None:
        problems.append(f'다시 시작한 뒤 {SONG_LIMIT} 프레임 안에 곡이 울리지 않음')
    if not s.get('moved'):
        problems.append('끝난 뒤 걷지 못함')
    return problems


def judge_win(s, expect):
    problems = judge_common(s, expect)
    if problems and s.get('end') is None:
        return problems
    after, before = s['after'], s['before']
    if after['map'] != before['map'] or after['cell'] != before['cell']:
        problems.append(f"돌아온 자리 {after['map']} {after['cell']}, 전투 전 {before['map']} {before['cell']}")
    if after['gold'] - before['gold'] != expect['gold']:
        problems.append(f"금화 +{after['gold'] - before['gold']}, 기대 +{expect['gold']}")
    if after['exp'] - before['exp'] != expect['exp']:
        problems.append(f"경험치 +{after['exp'] - before['exp']}, 기대 +{expect['exp']}")
    return problems


def judge_attack(s, expect):
    problems = judge_win(s, expect)
    hits = s.get('hits', [])
    bad = [h for h in hits if h['kind'] is None]
    if bad:
        problems.append(f'보통·회심 어디에도 맞지 않는 피해 {bad}')
    if not hits:
        problems.append('주인공 공격이 몬스터 HP 를 줄이지 않음')
    normal = [h for h in hits if h['kind'] == 'normal']
    if normal:
        m = mean_problem([h['drop'] for h in normal], normal[0]['attack'], normal[0]['defense'])
        if m:
            problems.append(m)
    return problems


def judge_flee(s, expect):
    problems = judge_common(s, expect)
    if s.get('end') is None:
        return problems
    after, before = s['after'], s['before']
    for k in ('gold', 'exp', 'map', 'cell'):
        if after[k] != before[k]:
            problems.append(f'도망 뒤 {k} {after[k]}, 전투 전 {before[k]}')
    if not s.get('turns'):
        problems.append('도망을 고를 차례가 오지 않음')
    elif not s.get('fled'):
        problems.append('도망치지 못하고 끝남')
    return problems


def judge_monflee(s, expect):
    """몬스터가 にげる 로 사라져 끝남: 금화·경험치 그대로, 몬스터 칸 +A 가 00(빈 칸)으로 비어 있음. 쓰러진 몬스터는
    80(있지만 살아 있지 않음)으로 남는다(실측)."""
    problems = judge_common(s, expect)
    if s.get('end') is None:
        return problems
    after, before = s['after'], s['before']
    for k in ('gold', 'exp'):
        if after[k] != before[k]:
            problems.append(f'몬스터가 도망친 뒤 {k} {after[k]}, 전투 전 {before[k]}')
    if s.get('mon_hp_at_finish') != []:
        problems.append(f"몬스터 칸이 남은 채 끝남(HP {s.get('mon_hp_at_finish')}), 도망이 아님")
    return problems


def judge_heal(s, expect):
    """herb·spell: 회복 한 번이 원작 롬의 ホイミ 범위 안, (spell) 호이민 MP 가 ホイミ 값만큼 줆, (herb) 셋째 칸이 빔."""
    problems = judge_common(s, expect)
    heals = s.get('heals', [])
    if not heals:
        return problems + ['HP 회복이 없음']
    h = heals[0]
    lo, hi = heal_expect(h['from'], expect['max_hp'], *expect['amount'])
    if not lo <= h['to'] <= hi:
        problems.append(f"회복 {h['from']} → {h['to']}, 기대 {lo}~{hi}")
    if 'mp_cost' in expect and h.get('caster_mp_drop') != expect['mp_cost']:
        problems.append(f"호이민 MP 가 {h.get('caster_mp_drop')} 줆, 기대 {expect['mp_cost']}")
    if 'item_slot' in expect and (s.get('items_at_finish') or [None] * 12)[expect['item_slot']] != NO_ITEM:
        problems.append(f"몬스터를 쓰러뜨렸을 때 셋째 칸이 남음: {s.get('items_at_finish')}")
    return problems


def judge_levelup(s, expect):
    """곡선과 상관없는 것만 본다: 정한 수만큼 레벨이 오르고, 다음 레벨 경험치 문턱이 지금 경험치보다 크고 앞 문턱보다
    크며, 능력치가 줄지 않음. 곡선 값 자체는 growth 모드(FC 원작과 견줌)가 본다."""
    problems = judge_win(s, expect)
    if s.get('end') is None:
        return problems
    hero, was = s['after']['hero'], s['before']['hero']
    if hero['level'] != expect['level']:
        problems.append(f"레벨 {hero['level']}, 기대 {expect['level']}")
    if not hero['exp'] < hero['next']:
        problems.append(f"경험치 {hero['exp']} 가 다음 레벨 문턱 {hero['next']} 이상")
    if not hero['next'] > was['next']:
        problems.append(f"다음 레벨 문턱 {was['next']} → {hero['next']} 가 늘지 않음")
    down = [k for k, (a, b) in enumerate(zip(was['stats'], hero['stats'])) if b < a]
    if down:
        problems.append(f"능력치가 줆: {was['stats']} → {hero['stats']}")
    return problems


def judge_lose(s, expect):
    problems = judge_common(s, expect)
    if s.get('end') is None:
        return problems
    after = s['after']
    if (after['map'], *after['cell']) != expect['place']:
        problems.append(f"다시 시작 자리 {after['map']} {after['cell']}, 기대 {expect['place']}")
    if after['gold'] != expect['gold']:
        problems.append(f"금화 {after['gold']}, 기대 {expect['gold']}")
    if after['hero']['hp'] != after['hero']['max_hp']:
        problems.append(f"주인공 HP {after['hero']['hp']}/{after['hero']['max_hp']}")
    return problems


def judge_boss(s, expect):
    problems = judge_win(s, expect)
    if s.get('end') is None:
        return problems
    missing = [k for k in ('BOSS_WON', 'KIDS_FOLLOW') if k not in s['after']['flags']]
    if missing:
        problems.append(f'보스 뒤 flag 가 켜지지 않음: {missing}')
    if 'level' in expect and s['after']['hero']['level'] != expect['level']:
        problems.append(f"레벨 {s['after']['hero']['level']}, 기대 {expect['level']}")
    return problems


def judge_noflee(s, expect):
    problems = judge_win(s, expect)
    if s.get('end') is None:
        return problems
    if s.get('flee_tries') != expect['flee_tries'] or s.get('fled'):
        problems.append(f"도망 {s.get('flee_tries')}번(도망침 {s.get('fled')}), 기대 {expect['flee_tries']}번 모두 실패")
    return problems


def judge_nosong(s, expect):
    """맵 곡 건너뛰기 비트를 그대로 둔 기록으로 이어 해도 맵 곡이 울려야 한다."""
    problems = judge_win(s, expect)
    if s.get('map_song') in (0x00, 0xFF):
        problems.insert(0, f"이어 한 뒤 {SONG_LIMIT} 프레임 동안 맵 곡이 울리지 않음($1D8B = {s.get('map_song'):02X})")
    return problems


JUDGES = {'attack': judge_attack, 'armor': judge_attack, 'flee': judge_flee, 'noflee': judge_noflee,
          'herb': judge_heal, 'spell': judge_heal, 'levelup': judge_levelup, 'levelup2': judge_levelup,
          'lose': judge_lose, 'boss': judge_boss, 'monflee': judge_monflee, 'nosong': judge_nosong,
          'growth': judge_levelup}


def distribution(summaries):
    """시드 집합에서 선제·기습·회심·도망 실패가 몇 번 나왔는지. 도망은 선제가 아닌 전투의 시도를 차례별로 센다."""
    out = {'battles': 0, 'preemptive': 0, 'ambush': 0, 'hits': 0, 'crits': 0, 'flee_tries': 0, 'flee_fails': 0,
           'flee_by_try': [[0, 0] for _ in FLEE_FAIL]}
    for s in summaries:
        if s.get('start') is None:
            continue
        out['battles'] += 1
        first = s.get('opening') or 0
        out['preemptive'] += bool(first & 2)
        out['ambush'] += bool(first & 1)
        hits = [h for h in s.get('hits', []) if h['kind'] in ('normal', 'crit')]
        out['hits'] += len(hits)
        out['crits'] += sum(h['kind'] == 'crit' for h in hits)
        tries = s.get('flee_tries') or 0
        fails = tries - (1 if tries and s.get('fled') else 0)
        out['flee_tries'] += tries
        out['flee_fails'] += fails
        if tries and not first & 2:
            for k in range(tries):
                row = out['flee_by_try'][min(k, len(FLEE_FAIL) - 1)]
                row[0] += 1
                row[1] += k < fails
    return out


def distribution_problems(scene, counts, log=None):
    """확률이 문서로 정해진 것만 구간으로 본다. 회심은 보통 공격 30번 이상(1/32), 도망 실패는 시도 30번 이상
    (FLEE_FAIL, 도망칠 수 있는 무리만). 선제·기습은 확률 번호를 재지 않아 「모든 전투는 아님」 만 본다. 표본이 작으면
    건너뛰고 log 에 적는다."""
    log = log if log is not None else []
    problems = []
    n = counts['battles']
    if n >= MIN_N:
        for k in ('preemptive', 'ambush'):
            if counts[k] >= n:
                problems.append(f'{k} {counts[k]}/{n}: 모든 전투')
    else:
        log.append(f'{scene}: 전투 {n} < {MIN_N}, 선제·기습 셈은 보지 않음')
    if counts['hits'] >= MIN_N:
        lo, hi = binom_interval(counts['hits'], CRIT_P)
        if not lo <= counts['crits'] <= hi:
            problems.append(f"회심 {counts['crits']}/{counts['hits']}, 99.9% 구간 {lo}~{hi}")
    elif counts['hits']:
        log.append(f"{scene}: 보통 공격 {counts['hits']} < {MIN_N}, 회심 셈은 보지 않음")
    if scene == 'flee':
        if counts['flee_tries'] >= MIN_N:
            mean, sd, got = flee_expect(counts['flee_by_try'])
            if abs(got - mean) > Z * sd:
                problems.append(f'도망 실패 {got:.0f}, 기대 {mean:.1f} ± {Z * sd:.1f}')
        else:
            log.append(f"{scene}: 도망 {counts['flee_tries']} < {MIN_N}, 실패 비율은 보지 않음")
    return problems


def core_key(name):
    """'Snes9x 1.63 …'·'bsnes 115' → cc.CORES 의 키. 모르는 이름이면 오류."""
    key = name.split()[0].lower()
    if key not in cc.CORES:
        raise ValueError(f'모르는 코어 이름 {name!r}')
    return key


# --- 장면 ---------------------------------------------------------------------------------------------------

# 장면: 기록(SaveSlot.set 꼴), 순간이동 자리, 무리, 몬스터 바꾸기, 구역 레벨, 차례 입력, 끝난 뒤 걷는 쪽.
# hero: 주인공 레벨(곡선 능력치 그대로)·HP 등. 'growth': (레벨, 오를 레벨 수)면 경험치를 그만큼 오르기 직전으로.
SCENES = {
    'attack': {'what': '보통 공격으로 이김(회심 셈, 평균 피해)', 'group': [(0x00, 1)],
               'monsters': {0x00: {'hp': 300, 'defense': 0, 'attack': 0}}, 'hero': {'level': 10}, 'turn': 'attack'},
    # 공격력 40, 수비 50 → h = 7 이라 보통 피해가 6~8 셋뿐(정확 범위)
    'armor': {'what': '중간 수비(50)의 몬스터를 공격', 'group': [(0x00, 1)],
              'monsters': {0x00: {'hp': 60, 'defense': 50, 'attack': 0}}, 'hero': {'level': 10}, 'turn': 'attack'},
    'flee': {'what': '도망(성공할 때까지 거듭)', 'group': [(0x00, 2)], 'monsters': {0x00: {'hp': 2000, 'attack': 0}},
             'zone': 99, 'turn': 'flee'},
    'herb': {'what': '약초로 회복한 뒤 공격', 'group': [(0x00, 1)], 'monsters': {0x00: {'hp': 1, 'defense': 0, 'attack': 0}},
             'hero': {'max_hp': 100, 'hp': 20}, 'items': [0x42, 0x00, HERB], 'turn': 'herb', 'then': ('attack', 1)},
    'spell': {'what': '호이민이 ホイミ 로 주인공을 고친 뒤 도망', 'group': [(0x00, 1)],
              'monsters': {0x00: {'hp': 2000, 'defense': 255, 'attack': 0}}, 'party': 'hoimin',
              'hero': {'level': 5, 'max_hp': 100, 'hp': 40}, 'turn': 'defend', 'then': ('flee', 'heal')},
    'noflee': {'what': '도망칠 수 없는 무리(무리 플래그 bit6)에서 도망 두 번 실패 뒤 공격', 'group': [(0x00, 1)],
               'monsters': {0x00: {'hp': 1, 'defense': 0, 'attack': 0}}, 'group_flags': 0x40, 'turn': 'flee',
               'then': ('attack', 2)},
    # 행동표를 고치지 않아 스ライム 의 にげる(98)가 남는다. 이 행동은 주인공 레벨이 구역 레벨 + 4 보다 클 때만 도망치므로
    # 레벨 10·구역 0. 주인공은 방어만
    'monflee': {'what': '몬스터가 にげる 로 사라짐(행동표 그대로)', 'group': [(0x00, 1)],
                'monsters': {0x00: {'hp': 2000, 'defense': 255, 'attack': 0, 'actions': None}}, 'hero': {'level': 10},
                'turn': 'defend',
                'limit': 30000},
    'levelup': {'what': '레벨업 한 번(5 → 6)', 'group': [(0x00, 1)], 'monsters': {0x00: {'hp': 1, 'defense': 0, 'attack': 0}},
                'growth': (5, 1), 'turn': 'attack'},
    'levelup2': {'what': '한 전투에 레벨업 두 번(5 → 7), 호이민과 함께', 'group': [(0x00, 1)],
                 'monsters': {0x00: {'hp': 1, 'defense': 0, 'attack': 0}}, 'party': 'hoimin', 'growth': (5, 2),
                 'turn': 'attack'},
    'lose': {'what': '전멸 → 바트랜드 교회, 금화 반', 'group': [(0x00, 1)],
             'monsters': {0x00: {'hp': 2000, 'defense': 255, 'attack': 255}}, 'hero': {'hp': 5}, 'turn': 'attack',
             'after_taps': ('b', 12), 'move': 'down'},
    # はがねのつるぎ·かわのよろい 를 밑판의 장비 두 칸(+14 = 03)에 둔다
    'boss': {'what': '탑 위 보스(진짜 능력치), 이긴 뒤 레벨업', 'boss': True, 'party': 'hoimin', 'growth': (12, 1),
             'items': [0x0C, 0x48], 'turn': 'attack', 'after_taps': ('a', 20), 'move': 'down'},
    # 아래 둘은 알려진 문제를 재는 장면이라 기본 묶음(가드)에 넣지 않는다: --scenes 로 고른다
    'nosong': {'what': '새 게임 첫 기록의 맵 곡 건너뛰기 비트를 그대로 두고 이어 함', 'keep_map_skip': True,
               'group': [(0x00, 1)], 'monsters': {0x00: {'hp': 1, 'defense': 0, 'attack': 0}}, 'turn': 'attack'},
    'growth': {'what': '레벨 1 → 10 을 한 전투에(곡선을 FC ライアン 과 견줌)', 'group': [(0x00, 1)],
               'monsters': {0x00: {'hp': 1, 'defense': 0, 'attack': 0}}, 'growth': (1, 9), 'turn': 'attack',
               'limit': 20000, 'finish_limit': 9000},
}
KNOWN_ISSUES = ('nosong', 'growth')
DEFAULT_SCENES = tuple(n for n in SCENES if n not in KNOWN_ISSUES)


def scene_slot(rom_path, rom, scene):
    """장면의 저장 기록. 레벨은 롬의 성장 곡선 값으로 두어(1.5배 규칙에 걸리지 않게) 판정의 기대값으로는 쓰지 않는다."""
    import dq5growth
    from dq5map import Rom
    slot = fx.SaveSlot.new_game(rom_path)
    slot.place = 'batland'
    slot.gold = 1000
    if not scene.get('keep_map_skip'):
        slot.apply_sets(MAP_SKIP)
    if scene.get('party') == 'hoimin':
        slot.effect('hoimin')
        slot.flag('HOIMIN')
    if scene.get('boss'):
        extra, _ = wc.setup(wc.SEGMENTS, [s[0] for s in wc.SEGMENTS].index('boss'))
        slot.apply_sets(extra)
    hero = dict(scene.get('hero', {}))
    rec = dq5growth.record_address(slot.block[0x40])
    r = Rom(rom)
    level = scene['growth'][0] if 'growth' in scene else hero.pop('level', None)
    if level:
        stats = dq5growth.stats_at(r, rec, level)
        for (field, n), v in zip(GROWTH_FIELDS, stats):
            slot._put(HERO + field, v, n)
        slot._put(HERO + HP, stats[0], 2)
        slot._put(HERO + MP, stats[1], 2)
        slot._put(HERO + LEVEL, level)
        exp = dq5growth.exp_at(r, rec, level)
        if 'growth' in scene:
            exp = dq5growth.exp_at(r, rec, level + scene['growth'][1]) - 1
        slot._put(HERO + EXP, exp, 3)
        slot._put(HERO + NEXT, dq5growth.exp_at(r, rec, level + 1), 3)
    if 'max_hp' in hero:
        slot._put(HERO + MAX_HP, hero['max_hp'], 2)
    if 'hp' in hero:
        slot._put(HERO + HP, hero['hp'], 2)
    if 'items' in scene:
        slot.set_hero(items=scene['items'])
    return slot


def original_hoimi(root=ROOT):
    """원작 두 롬에서 ホイミ 의 (바탕, 폭)과 MP. DQ5(rom/dq5.sfc, dq5spell)와 FC DQ4(rom/dq4.nes, dq4data.heal) 가
    다르면 오류. MP 는 DQ5 원작 롬 값(FC 도 3, fc/dq4/docs/dq4-data-format.md 「주문」의 MP 7→4)."""
    import dq5spell
    from dq5map import Rom
    from kr_patch.fc import ines
    sys.path.insert(0, str(root / 'fc' / 'dq4' / 'tools'))
    import dq4data
    r = Rom((root / 'rom' / 'dq5.sfc').read_bytes())
    _, lda, _, _ = dq5spell.handler(r, HOIMI)
    dq5 = dq5spell.amount(r, lda)
    fc = dq4data.heal(ines.prg((root / 'rom' / 'dq4.nes').read_bytes()), FC_HOIMI)
    if tuple(dq5) != tuple(fc):
        raise ValueError(f'ホイミ 양이 DQ5 {dq5} 와 FC {fc} 로 다름: 어느 쪽을 따를지 정한다')
    return tuple(dq5), dq5spell.cost(r, HOIMI)[0]


def fc_growth(level, root=ROOT):
    """FC ライアン(인물 6)의 성장 곡선 기준값을 dq5growth.STATS 차례로(최대 HP, 최대 MP, ちから, すばやさ, かしこさ,
    うんのよさ, みのまもり ← たいりょく)와 그 레벨이 되는 경험치. FC ライアン 은 MP 가 없다(MP 는 0~4번만)."""
    from kr_patch.fc import ines
    sys.path.insert(0, str(root / 'fc' / 'dq4' / 'tools'))
    import dq4data
    prg = ines.prg((root / 'rom' / 'dq4.nes').read_bytes())
    c = lambda stat: dq4data.curve(prg, FC_RYAN, stat, level)[0]  # noqa: E731
    return [c(6), 0, c(1), c(2), c(4), c(5), c(3)], c(0)


def expectations(rom, scene_name, slot):
    """판정에 넘기는 기대값. 금화·경험치는 장면 롬의 몬스터 표와 보상 배율, 레벨은 장면 설정, ホイミ 양은 원작 롬."""
    scene = SCENES[scene_name]
    exp = {'song': None}
    group = list(ev.BOSS_MEMBERS) if scene.get('boss') else scene['group']
    vals = {n: monster_values(rom, n) for n, _ in group}
    exp['gold'] = dq4balance.reward(sum(vals[n]['gold'] * c for n, c in group))
    exp['exp'] = dq4balance.reward(sum(vals[n]['exp'] * c for n, c in group))
    if 'growth' in scene:
        exp['level'] = sum(scene['growth'])
    if 'finish_limit' in scene:
        exp['finish_limit'] = scene['finish_limit']
    if scene_name in ('herb', 'spell'):
        exp['amount'], cost = original_hoimi()
        exp['max_hp'] = slot.hero(MAX_HP, 2)
        if scene_name == 'spell':
            exp['mp_cost'] = cost
        else:
            exp['item_slot'] = 2
    if scene_name == 'noflee':
        exp['flee_tries'] = scene['then'][1]
    if scene_name == 'monflee':
        exp['gold'] = exp['exp'] = 0
    if scene_name == 'lose':
        exp['place'] = CHURCH
        exp['gold'] = slot.gold // 2
    return exp


def growth_table(summary):
    """growth 장면 한 판: 이 롬의 라이안 능력치·다음 경험치와 FC ライアン 곡선 기준값을 견준 줄들."""
    hero = summary['after']['hero']
    level = hero['level']
    fc, _ = fc_growth(level)
    _, fc_next = fc_growth(level + 1)
    names = ('최대HP', '최대MP', 'ちから', 'すばやさ', 'かしこさ', 'うんのよさ', 'みのまもり(FC たいりょく)')
    rows = [(n, a, b) for n, a, b in zip(names, hero['stats'], fc)]
    rows.append(('다음 레벨 경험치', hero['next'], fc_next))
    return level, rows


def rom_bytes(rom, scene):
    """장면 롬: 조우 없음 + 몬스터 바꾸기."""
    data = bytearray(rom)
    for tok in wc.NO_ENCOUNTERS.split(';'):
        off, h = tok.split('=')
        data[int(off, 16):int(off, 16) + len(h) // 2] = bytes.fromhex(h)
    for n, kw in scene.get('monsters', {}).items():
        for off, v in monster_patch(rom, n, **kw):
            data[off] = v
    return bytes(data)


# --- 실행(코어 하나, 장면 하나, 시드 여럿) ---------------------------------------------------------------------

class Run:
    """한 코어에서 장면 하나를 돌린다. dq4compatcheck.Walker 의 step·apply·warp 를 빌려 쓴다."""

    def __init__(self, core_name, rom_path, scene_name, out):
        from dq4libretro import Core
        from dq5exitcheck import warp_exit
        self.scene_name, self.scene = scene_name, SCENES[scene_name]
        self.out = out
        rom = Path(rom_path).read_bytes()
        self.slot = scene_slot(rom_path, rom, self.scene)
        self.expect = expectations(rom, scene_name, self.slot)
        w = cc.Walker.__new__(cc.Walker)
        w.out, w.seed = out, 0
        w.rom = out / 'c.sfc'
        w.rom.write_bytes(rom_bytes(rom, self.scene))
        w.warp_exit = warp_exit(w.rom)
        sram = self.slot.to_sram()
        (out / 'c.srm').write_bytes(sram)
        w.c = Core(str(dq4cores.core_path(core_name)), str(w.rom), str(out))
        try:
            (out / cc.STARTED).write_text(f'{w.c.slot.waited:.3f}')
            w.audio, w.rms = [], []
            w.pokes, w.rom_cheats, w.cheat_key = [], {}, None
            self.w, self.c = w, w.c
            self.core = w.c.name
            fx.load_sram(w.c, sram)
        except BaseException:
            fx.close(w.c)
            raise

    def prepare(self):
        """이어 하기 → 순간이동. 전투 직전 상태를 돌려준다."""
        at = fx.boot(self.c, self.slot.goal, step=self.w.step)
        if at is None:
            raise RuntimeError('이어 하기 자리에 서지 않음')
        pins = wc.pins({})
        self.w.warp(BOSS_CELL if self.scene.get('boss') else TOWER, pins, cc.sets(pins))
        # 순간이동 뒤 맵 곡이 울리기까지
        for _ in range(SONG_LIMIT):
            if self.c.rd(SONG) not in (0x00, 0xFF):
                break
            self.w.step()
        self.map_song = self.c.rd(SONG)
        return self.c.save()

    def snapshot(self):
        rd = self.c.rd
        hero = {'level': rd(HERO + LEVEL), 'hp': rd(HERO + HP, 2), 'max_hp': rd(HERO + MAX_HP, 2), 'mp': rd(HERO + MP, 2),
                'exp': rd(HERO + EXP, 3), 'next': rd(HERO + NEXT, 3),
                'stats': [rd(HERO + f, n) for f, n in GROWTH_FIELDS]}
        return {'f': self.c.n, 'map': '%02X/%02X' % (rd(0x7E00BC), rd(0x7E00BD)), 'cell': [rd(0x7E3020), rd(0x7E3080)],
                'song': rd(SONG), 'gold': rd(GOLD, 3), 'exp': hero['exp'], 'hero': hero,
                'items': [rd(HERO + ITEMS + k) for k in range(12)],
                'flags': sorted(k for k, (a, m) in wc.FLAGS.items() if rd(a) & m)}

    def party(self):
        rd = self.c.rd
        n = rd(0x7E201D)
        return [(rd(HERO + k * RECORD + HP, 2), rd(HERO + k * RECORD + MP, 2)) for k in range(max(1, min(n, 4)))]

    def monsters(self):
        out = []
        for k in range(8):
            base = MONSTER_SLOTS + k * MONSTER_SLOT
            flags = self.c.rd(base + 0xA)
            if flags & 0x80:
                out.append((k, self.c.rd(base + 2, 2), bool(flags & 0x40)))
        return out

    def press_for(self, schedule, since):
        rel = self.c.n - since
        for f, k in schedule:
            if f <= rel < f + 4:
                return {k}
        return set()

    def battle(self, seed, state):
        """시드 하나: 상태를 불러 난수를 두고 전투를 붙여 끝까지. 요약 dict."""
        c, w, scene = self.c, self.w, self.scene
        c.load(state)
        w.cheat_key = None
        w.rom_cheats = {}
        c.poke(cc.sets(wc.rng_for(seed)))
        boss = scene.get('boss')
        if not boss:
            c.poke([(GROUP + i, 0) for i in range(8)])
            code = force_code(scene['group'], scene.get('zone', 0), scene.get('group_flags', 0))
            w.rom_cheats = {'force': cc.rom_codes(ENCOUNTER, code)}
        w.apply()
        sentinel = bytes(ev.BOSS_MONSTERS) if boss else group_sentinel(scene['group'])
        s = {'seed': seed, 'map_song': self.map_song, 'start': None, 'end': None, 'turns': 0, 'hits': [],
             'heals': [], 'songs': []}
        before = self.snapshot()
        t0 = c.n
        # 전투 붙이기
        while c.n - t0 < (START_LIMIT if boss else STEP_LIMIT):
            if boss:
                b = {'up'} if c.n - t0 < 20 else ({'a'} if (c.n - t0) % 40 < 4 else set())
            else:
                b = {'down'}
            w.step(b)
            if bytes(c.rd(GROUP + i) for i in range(len(sentinel))) == sentinel:
                break
        else:
            return {**s, 'before': before}
        s['start'] = c.n
        w.rom_cheats = {}
        w.apply()
        # 전투가 걸린 프레임의 자리(내디딘 칸)·곡
        s['before'] = {**self.snapshot(), 'song': before['song']}
        s['opening'] = None
        last_window, turn_at, policy = c.rd(WINDOW), None, TURNS[scene['turn']]
        lose = self.scene_name == 'lose'
        start_map = (c.rd(0x7E00BC), c.rd(0x7E00BD))
        policy_until = 0
        hp_mon = {k: hp for k, hp, _ in self.monsters()}
        party = self.party()
        song = None
        attack = c.rd(PARTY_SLOTS)
        defense = {}
        finished = None
        healed = False
        buttons = set()
        seen_window = False
        while c.n - s['start'] < scene.get('limit', BATTLE_LIMIT):
            w.step(buttons)
            buttons = set()
            cur = c.rd(SONG)
            if cur != song:
                s['songs'].append([c.n - s['start'], cur])
                song = cur
            if s['opening'] is None and c.rd(WINDOW) not in (0x00, 0xFF):
                s['opening'] = c.rd(FLAGS_1000) & 3
                s['flags_100e'] = c.rd(0x7E100E)
            window = c.rd(WINDOW)
            seen_window = seen_window or window not in (0x00, 0xFF, FIELD_WINDOW)
            if last_window == 0xFF and window == TURN_WINDOW:
                turn_at = c.n
                s['turns'] += 1
                then, after = scene.get('then', (None, None))
                if then and 'switched' not in s and (healed if after == 'heal' else s['turns'] > after):
                    policy = TURNS[then]
                    s['switched'] = s['turns']
                attack = c.rd(PARTY_SLOTS)
                policy_until = c.n + max(f for f, _ in policy) + 30
            last_window = window
            # 몬스터 HP 가 준 것(주인공 공격으로 보는 것은 일행이 라이언 하나일 때만)
            mons = self.monsters()
            for k, hp, alive in mons:
                if k not in defense:
                    defense[k] = c.rd(MONSTER_SLOTS + k * MONSTER_SLOT + 8, 2)
                old = hp_mon.get(k, hp)
                if hp < old and len(party) == 1:
                    s['hits'].append({'f': c.n - s['start'], 'drop': old - hp, 'attack': attack, 'defense': defense[k],
                                      'kind': classify_hit(old - hp, attack, defense[k], killed=hp == 0)})
                hp_mon[k] = hp
            now = self.party()
            if now[0][0] > party[0][0] and not s['heals']:
                drop = party[1][1] - now[1][1] if len(now) > 1 else None
                s['heals'].append({'f': c.n - s['start'], 'from': party[0][0], 'to': now[0][0], 'caster_mp_drop': drop})
                healed = True
            elif len(now) > 1 and s['heals'] and s['heals'][-1].get('caster_mp_drop') == 0 and now[1][1] < party[1][1]:
                s['heals'][-1]['caster_mp_drop'] = party[1][1] - now[1][1]
            party = now
            if 'slot_flags' not in s and seen_window:
                s['slot_flags'] = [c.rd(MONSTER_SLOTS + k * MONSTER_SLOT + 0xA) for k in range(4)]
            # 살아 있는(+A bit6) 몬스터가 없거나(빈 목록 포함) 일행 HP 가 모두 0. 전투 창이 뜨기 전에는 보지 않는다
            if finished is None and seen_window and (not any(a for _, _, a in mons) or all(hp == 0 for hp, _ in now)):
                finished = c.n
                s['finished'] = c.n - s['start']
                s['mon_hp_at_finish'] = [hp for _, hp, _ in mons]
                s['slot_flags_at_finish'] = [c.rd(MONSTER_SLOTS + k * MONSTER_SLOT + 0xA) for k in range(4)]
                # 이긴 뒤 몬스터가 떨어뜨린 물건이 들어오기 전
                s['items_at_finish'] = [c.rd(HERO + ITEMS + k) for k in range(12)]
            if not lose and s.get('song_back') is None and finished is not None and cur == before['song']:
                s['song_back'] = c.n - finished
            if turn_at is not None and c.n < policy_until:
                buttons = self.press_for(policy, turn_at)
            elif window not in INPUT_WINDOWS and (c.n - s['start']) % MASH < 4:
                # 메시지 넘기기. 맵으로 돌아오면 이 A 가 명령 창(FIELD_WINDOW)을 연다
                buttons = {'a'}
            if lose:
                if (c.rd(0x7E00BC), c.rd(0x7E00BD)) != start_map:
                    s['end'] = c.n
                    break
            elif window == FIELD_WINDOW and seen_window:
                s['end'] = c.n
                s['song_at_end'] = cur
                break
        if s['end'] is None:
            s['timeout_at'] = c.n - s['start']
            s['last_song'] = f'{c.rd(SONG):02X}'
            c.shot(self.out / f'seed{seed}-timeout.png')
            s['moved_after_timeout'] = self.walk_after(scene)[0]
            return s
        s['battle_frames'] = s['end'] - s['start']
        if s.get('finished') is not None:
            s['finished'] = s['start'] + s['finished']
        s['flee_tries'] = flee_tries(scene, s['turns'], s.get('switched'))
        # 몬스터를 쓰러뜨리거나 일행이 쓰러지지 않고 끝났으면 도망친 것
        s['fled'] = bool(s['flee_tries']) and s.get('finished') is None
        c.shot(self.out / f'seed{seed}-end.png')
        if lose:
            # 다시 시작한 교회에서 마을 곡이 울리기까지
            t = c.n
            while c.n - t < SONG_LIMIT:
                if c.rd(SONG) not in (0x00, 0xFF, SONG_LOSE):
                    s['song_back'] = c.n - s['end']
                    break
                w.step()
        # 끝난 뒤 이어지는 대화(보스 뒤 아이들, 교회 신부)를 넘긴다. 메시지를 넘기던 A 가 연 맵 명령 창은 B 로 닫고,
        # 창이 없을 때는 누르지 않는다(A 가 명령 창을 열어 앞 사람에게 말을 걸지 않게)
        key, taps = scene.get('after_taps', ('a', 0))
        for i in range(taps):
            window = c.rd(WINDOW)
            press = {'b'} if window == FIELD_WINDOW else set() if window == 0xFF else {key}
            for f in range(40):
                w.step(press if f < 4 else set())
        s['moved'], s['after'], s['moved_to'] = self.walk_after(scene)
        c.shot(self.out / f'seed{seed}-after.png')
        return s

    def walk_after(self, scene):
        """메시지를 넘기던 A 가 연 명령 창을 B 로 닫고, 쉰 뒤 한 방향으로 걸어 자리가 바뀌는지."""
        w = self.w
        for _ in range(3):
            for f in range(20):
                w.step({'b'} if f < 4 else set())
        for _ in range(60):
            w.step()
        after = self.snapshot()
        d = scene.get('move', 'up')
        for f in range(24):
            w.step({d})
        for _ in range(30):
            w.step()
        moved = self.snapshot()
        return (moved['map'], moved['cell']) != (after['map'], after['cell']), after, [moved['map'], moved['cell']]


DIGEST_KEYS = ('start', 'end', 'turns', 'opening', 'songs', 'hits', 'heals', 'before', 'after', 'moved_to', 'finished')


def digest(s):
    """같은 입력이면 같아야 하는 요약의 SHA-1 앞 12자리."""
    return hashlib.sha1(json.dumps({k: s.get(k) for k in DIGEST_KEYS}, sort_keys=True).encode()).hexdigest()[:12]


def unit(core_name, rom_path, scene_name, seeds, out, repeat=1):
    """코어 하나·장면 하나를 시드마다 돌려 out/unit.json 에 둔다. repeat 번 같은 상태에서 돌려 요약이 같은지 본다."""
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    run = None
    try:
        run = Run(core_name, rom_path, scene_name, out)
        state = run.prepare()
        results = []
        for seed in seeds:
            t = time.time()
            s = run.battle(seed, state)
            s['seconds'] = round(time.time() - t, 1)
            s['problems'] = JUDGES[scene_name](s, {**run.expect, 'song': run.map_song if scene_name != 'lose' else None})
            s['digests'] = [digest(s)] + [digest(run.battle(seed, state)) for _ in range(repeat - 1)]
            if len(set(s['digests'])) > 1:
                s['problems'].append(f"같은 입력의 실행끼리 다름: {s['digests']}")
            s['status'] = 'failed' if s['problems'] else 'passed'
            results.append(s)
    finally:
        if run is not None:
            fx.close(run.c)
    report = {'core': run.core, 'scene': scene_name, 'map_song': run.map_song, 'expect': run.expect,
              'seconds': round(time.time() - t0, 1), 'results': results}
    (out / 'unit.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('mode', nargs='?', default='check', choices=('check', '_unit'))
    ap.add_argument('--rom', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--scenes', help='쉼표로 고른 장면만')
    ap.add_argument('--scene', help=argparse.SUPPRESS)
    ap.add_argument('--core', choices=('all', *cc.CORES), default='all')
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--repeat', type=int, default=2, help='시드마다 같은 상태에서 몇 번 돌려 요약을 견줄지')
    wc.add_seed_args(ap)
    args = ap.parse_args()
    seeds = wc.seeds_of(args)
    rom = args.rom.resolve()
    out = args.out.resolve()
    if args.mode == '_unit':
        report = unit(args.core, rom, args.scene, seeds, out, args.repeat)
        return 0 if all(r['status'] == 'passed' for r in report['results']) else 1
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    cores = list(cc.CORES) if args.core == 'all' else [args.core]
    for name in cores:
        if not dq4cores.core_path(name).exists():
            raise SystemExit(f'{dq4cores.core_path(name)} 가 없음: sfc/dq4/tools/dq4cores.py 로 빌드')
    names = args.scenes.split(',') if args.scenes else list(DEFAULT_SCENES)
    unknown = [n for n in names if n not in SCENES]
    if unknown:
        raise SystemExit(f'모르는 장면: {unknown}')
    t0 = time.time()
    # 밑판을 먼저 한 번 만들어 프로세스들이 함께 만들지 않게
    fx.SaveSlot.new_game(rom)
    seed_arg = ','.join(map(str, seeds))

    def one(work):
        scene, core = work
        dest = out / f'{scene}-{core}'
        dest.mkdir(parents=True)
        with (dest / 'log.txt').open('w') as log:
            proc = subprocess.Popen([sys.executable, __file__, '_unit', '--core', core, '--scene', scene, '--rom', str(rom),
                                     '--out', str(dest), '--seeds', seed_arg, '--repeat', str(args.repeat)],
                                    stdout=log, stderr=subprocess.STDOUT)
            done = cc.wait_child(proc, dest, 120 + 60 * len(seeds) * args.repeat)
        f = dest / 'unit.json'
        if done and f.exists():
            return json.loads(f.read_text())
        return {'core': core, 'scene': scene, 'results': [{'seed': s, 'status': 'failed',
                                                            'problems': ['프로세스가 결과를 남기지 않음(시간 초과·오류, log.txt)']}
                                                           for s in seeds]}

    work = [(s, c) for s in names for c in cores]
    with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        units = list(pool.map(one, work))
    rows = []
    for u in units:
        for r in u['results']:
            rows.append({'scene': u['scene'], 'core': u['core'], 'seed': r['seed'], 'status': r['status'],
                         'problems': r['problems'], 'battle_frames': r.get('battle_frames'),
                         'turns': r.get('turns'), 'seconds': r.get('seconds'), 'digests': r.get('digests')})
    dist, skipped, growth = {}, [], {}
    for u in units:
        core = core_key(u['core'])
        counts = distribution(u['results'])
        dist[f"{u['scene']}/{core}"] = counts
        # 장면 프로세스가 결과를 남기지 못했으면 그 실패만 적는다
        if not all(r.get('start') is not None for r in u['results']):
            continue
        bad = distribution_problems(u['scene'], counts, skipped)
        if bad:
            rows.append({'scene': u['scene'], 'core': u['core'], 'seed': 'all', 'status': 'failed', 'problems': bad,
                         'battle_frames': None, 'turns': None, 'seconds': None, 'digests': None})
        if u['scene'] == 'growth':
            growth[core] = [growth_table(r) for r in u['results'] if r.get('after')]
    for line in dict.fromkeys(skipped):
        print(f'분포 검사 건너뜀: {line}', file=sys.stderr)
    for core, tables in growth.items():
        for level, table in tables[:1]:
            print(f'growth {core}: 레벨 {level}, 이 롬 / FC ライアン 곡선')
            for name, got, fc in table:
                print(f"  {name}: {got} / {fc}{'' if got == fc else '  다름'}")
    ok = all(r['status'] == 'passed' for r in rows)
    report = {'status': 'passed' if ok else 'failed', 'rom_sha1': hashlib.sha1(rom.read_bytes()).hexdigest(),
              'seeds': seeds, 'seconds': round(time.time() - t0, 1), 'rows': rows, 'distribution': dist,
              'distribution_skipped': list(dict.fromkeys(skipped)),
              'growth': {k: [{'level': lv, 'rows': t} for lv, t in v] for k, v in growth.items()}, 'units': units}
    (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    for r in rows:
        print(json.dumps({k: r[k] for k in ('scene', 'core', 'seed', 'status', 'problems', 'battle_frames', 'turns')},
                         ensure_ascii=False))
    print(json.dumps({'status': report['status'], 'rom_sha1': report['rom_sha1'], 'seconds': report['seconds']}))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
