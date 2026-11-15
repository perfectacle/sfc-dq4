"""배포 관문 워크플로가 시크릿·롬을 내보내지 않는 꼴인지 지킨다.

release-gate.yml(손으로만)이 롬 묶음 시크릿을 guard-shards.yml(workflow_call 전용)에 넘기고, 그 안에서 composite
action ci-roms 가 묶음을 푼다. PR·예약 실행에서 돌거나, 롬이 artifact·캐시로 새거나, 시크릿이 로그에 찍히면 안 된다.
의존성에 YAML 파서가 없어 들여쓰기로 읽는다(이 저장소 워크플로의 꼴: 잡은 2칸, 단계는 6칸 `- `).
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import ci_artifact_check  # noqa: E402
import ci_cache  # noqa: E402

WORKFLOWS = ROOT / '.github' / 'workflows'
GATE = WORKFLOWS / 'release-gate.yml'
WORKFLOW = WORKFLOWS / 'guard-shards.yml'
ACTIONS = ROOT / '.github' / 'actions'
ACTION = ACTIONS / 'ci-roms' / 'action.yml'
ENC_CACHE = ACTIONS / 'enc-cache' / 'action.yml'
SHIP_CACHE = ACTIONS / 'ship-cache' / 'action.yml'
TOOLS_ACTION = ACTIONS / 'ci-tools' / 'action.yml'
ALL_ACTIONS = (ACTION, ENC_CACHE, SHIP_CACHE, TOOLS_ACTION)
# 평문 actions/cache 에 넣어도 되는 자리: 롬과 무관한 도구 빌드와 검사 통과 기록(입력 키·시간)
PLAIN_CACHE_PATHS = ('${{ runner.temp }}/gate-tools/', 'work/cache/guards')
SETUP = ROOT / 'tools' / 'ci_gate_setup.sh'
SECRET_VARS = ('CI_ROM_AGE_KEY', 'CI_ROM_TOKEN', 'GH_TOKEN')
BAD_TRIGGERS = ('pull_request', 'pull_request_target', 'schedule', 'push', 'workflow_run', 'issue_comment')


def top_block(text, key):
    """맨 왼쪽 `key:` 아래 줄들(다음 맨 왼쪽 키 앞까지)."""
    out, inside = [], False
    for line in text.splitlines():
        if re.match(r'^\S', line):
            inside = line.split(':', 1)[0].strip().strip('"\'') == key
            if inside and line.split(':', 1)[1].strip():
                out.append(line.split(':', 1)[1].strip())
            continue
        if inside:
            out.append(line)
    return out


def jobs(text):
    """{잡 이름: [단계 글, …]}."""
    out, job, step = {}, None, None
    for line in top_block(text, 'jobs'):
        m = re.match(r'^  ([A-Za-z0-9_-]+):\s*$', line)
        if m:
            job, step = m[1], None
            out[job] = []
            continue
        if job is None:
            continue
        if re.match(r'^      - ', line):
            out[job].append(line + '\n')
            step = len(out[job]) - 1
        elif step is not None and (line.startswith('        ') or not line.strip()):
            out[job][step] += line + '\n'
        else:
            step = None
    return out


def action_steps(text):
    """composite action 의 단계 글(단계는 4칸 `- `)."""
    out = []
    for line in top_block(text, 'runs'):
        if re.match(r'^    - ', line):
            out.append(line + '\n')
        elif out and (line.startswith('      ') or not line.strip()):
            out[-1] += line + '\n'
    return out


def cache_paths(step):
    """actions/cache 단계의 path 들."""
    block = re.search(r'path:\s*\|\n((?:\s{10,}.+\n)+)', step)
    if block:
        return [x.strip() for x in block[1].splitlines()]
    return [re.search(r'path:\s*(.+)$', step, re.M)[1].strip()]


def with_value(step, key):
    m = re.search(rf'^\s+{key}:\s*(.+)$', step, re.M)
    return m[1].strip() if m else None


def triggers(text):
    return {m[1] for line in top_block(text, 'on') if (m := re.match(r'^  ([A-Za-z_]+):', line))}


def run_texts(step):
    """단계의 run: 글(한 줄이든 | 블록이든)."""
    m = re.search(r'^\s*(?:- )?run:\s*(\|)?(.*)$', step, re.M)
    if not m:
        return ''
    if not m[1]:
        return m[2]
    body = step[m.end():]
    return '\n'.join(line for line in body.splitlines() if line.startswith('          ') or not line.strip())


def prints_secret(line):
    """시크릿 환경 변수를 표준 출력·GitHub 출력 파일로 내는 echo·printf 줄인가."""
    if not re.search(r'\b(echo|printf)\b', line):
        return False
    if not any(re.search(rf'\$\{{?{v}\b', line) for v in SECRET_VARS):
        return False
    target = re.search(r'>+\s*"?([^"\s)]+)', line)
    return not target or 'GITHUB_' in target[1]


class ReleaseGateWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding='utf-8')
        self.jobs = jobs(self.text)

    def test_parser_sees_the_jobs(self):
        self.assertEqual(set(self.jobs), {'build', 'rom', 'shard', 'report'})
        self.assertTrue(all(self.jobs.values()))

    def test_gate_is_manual_only(self):
        gate = GATE.read_text(encoding='utf-8')
        self.assertEqual(triggers(gate), {'workflow_dispatch'})
        for bad in BAD_TRIGGERS:
            self.assertNotRegex('\n'.join(top_block(gate, 'on')), rf'\b{bad}\b')

    def test_shards_workflow_is_call_only(self):
        self.assertEqual(triggers(self.text), {'workflow_call'})

    def test_only_known_callers_pass_rom_secrets(self):
        """guard-shards.yml 을 부르는 워크플로는 release-gate.yml(손으로만)과 ci.yml(pr-guards 잡, 같은 저장소 브랜치 PR
        만 — test_pr_guards_workflow 가 조건을 지킨다)뿐이고, 시크릿은 이름을 대어 넘긴다(inherit 금지)."""
        callers = sorted(p.name for p in WORKFLOWS.glob('*.y*ml') if 'guard-shards.yml' in p.read_text(encoding='utf-8')
                         and p != WORKFLOW)
        self.assertEqual(callers, ['ci.yml', 'release-gate.yml'])
        gate = GATE.read_text(encoding='utf-8')
        self.assertNotRegex(gate, r'secrets:\s*inherit')
        self.assertRegex(gate, r'uses:\s*\./\.github/workflows/guard-shards\.yml')
        self.assertRegex(gate, r'mode:\s*release\b')
        # workflow_dispatch 의 number 입력도 문자열로 넘어가 workflow_call 의 number 입력이 받지 않는다
        self.assertIn('shards: ${{ fromJSON(inputs.shards) }}', gate)

    def test_permissions_read_only(self):
        for text in (self.text, GATE.read_text(encoding='utf-8')):
            self.assertEqual([x.strip() for x in top_block(text, 'permissions') if x.strip()], ['contents: read'])
            self.assertNotRegex(text, r':\s*write\b')

    def test_actions_pinned_to_commits(self):
        for f in (WORKFLOW, GATE, *ALL_ACTIONS):
            for m in re.finditer(r'uses:\s*(\S+)', f.read_text(encoding='utf-8')):
                if m[1].startswith('./.github/'):
                    continue
                self.assertRegex(m[1], r'^[\w.-]+/[\w./-]+@[0-9a-f]{40}$', m[1])

    def test_roms_come_only_from_the_composite_action(self):
        uses = [s for steps in self.jobs.values() for s in steps if './.github/actions/ci-roms' in s]
        self.assertEqual(len(uses), sum('ci_artifact_check.py' in run_texts(s) for st in self.jobs.values() for s in st)
                         + 1, '롬을 받는 잡마다(빌드 잡 + 올리는 잡) ci-roms 를 쓴다')
        for f in (WORKFLOW, GATE):
            self.assertNotIn('ci_gate_setup.sh roms', f.read_text(encoding='utf-8'))
        action = ACTION.read_text(encoding='utf-8')
        self.assertIn('using: composite', action)
        self.assertIn('tools/ci_gate_setup.sh roms', action)

    def test_every_upload_is_checked_first(self):
        uploads = 0
        for name, steps in self.jobs.items():
            for i, step in enumerate(steps):
                if 'actions/upload-artifact@' not in step:
                    continue
                uploads += 1
                path = re.search(r'^\s+path:\s*(\S+)', step, re.M)[1]
                checks = [s for s in steps[:i] if 'tools/ci_artifact_check.py' in run_texts(s)
                          and re.search(rf'ci_artifact_check\.py\s+{re.escape(path)}\s', run_texts(s))]
                self.assertTrue(checks, f'{name}: {path} 를 올리기 전에 ci_artifact_check.py 가 없음')
                sid = re.search(r'^\s+id:\s*(\S+)', checks[-1], re.M)
                self.assertIsNotNone(sid, f'{name}: 검사 단계에 id 가 없음')
                cond = re.search(r'^\s+if:\s*(.+)$', step, re.M)
                self.assertIsNotNone(cond, f'{name}: 올리기 단계가 검사 결과를 보지 않음')
                self.assertIn(f"steps.{sid[1]}.outcome == 'success'", cond[1])
                self.assertNotRegex(path, r'(^|/)rom(/|$)')
        self.assertGreater(uploads, 0)

    def test_plain_cache_holds_no_rom_data(self):
        """평문 actions/cache 는 도구 빌드(gate-tools)와 검사 통과 기록만. 롬에서 나온 것은 enc-cache 로만."""
        steps = [s for st in self.jobs.values() for s in st]
        for f in (SHIP_CACHE, TOOLS_ACTION, ACTION):
            steps += action_steps(f.read_text(encoding='utf-8'))
        seen = 0
        for step in steps:
            if not re.search(r'uses:\s*actions/cache(/restore|/save)?@', step):
                continue
            seen += 1
            for p in cache_paths(step):
                self.assertTrue(p.startswith(PLAIN_CACHE_PATHS), p)
                self.assertNotRegex(p, r'(^|/)(rom|build|ch1|assets|calls|readset|states)(/|$)|\.(sfc|smc|nes|nds|mss)$', p)
        self.assertGreater(seen, 0)

    def test_enc_cache_stores_only_the_encrypted_tar(self):
        steps = action_steps(ENC_CACHE.read_text(encoding='utf-8'))
        caches = [s for s in steps if re.search(r'uses:\s*actions/cache/(restore|save)@', s)]
        self.assertEqual(len(caches), 2)
        for s in caches:
            self.assertEqual(cache_paths(s), ['${{ runner.temp }}/enc-cache/${{ inputs.name }}.age'])
        save = next(s for s in caches if 'actions/cache/save@' in s)
        self.assertIn("steps.pack.outputs.save == 'true'", with_value(save, 'if'))
        pack = next(s for s in steps if re.search(r'^\s+id:\s*pack\b', s, re.M))
        self.assertIn('tools/ci_cache.py pack', pack)
        self.assertIn("age -r", Path(ci_cache.__file__).read_text(encoding='utf-8'))

    def test_rom_derived_folders_go_only_through_enc_cache(self):
        """롬 파생 폴더(work/·assets/·rom/)를 캐시하는 단계는 enc-cache·ship-cache 뿐이다."""
        steps = [s for st in self.jobs.values() for s in st] + action_steps(SHIP_CACHE.read_text(encoding='utf-8'))
        dirs = 0
        for step in steps:
            d = with_value(step, 'dir') or with_value(step, 'calls')
            if not d or 'uses:' not in step:
                continue
            dirs += 1
            self.assertRegex(step, r'uses:\s*\./\.github/actions/(enc-cache|ship-cache)\b', step)
            self.assertIn(with_value(step, 'age_key'), ('${{ secrets.CI_ROM_AGE_KEY }}', '${{ inputs.age_key }}'))
        self.assertGreater(dirs, 0)
        self.assertNotRegex(self.text, r'uses:\s*actions/cache@')

    def test_ship_cache_has_one_chunk_per_stage(self):
        steps = action_steps(SHIP_CACHE.read_text(encoding='utf-8'))
        for op in ('restore', 'save'):
            names = [with_value(s, 'name') for s in steps if with_value(s, 'op') == op]
            self.assertEqual(names, [f'ship-{x}' for x in ci_cache.SHIP_LABELS], op)
            prefixes = [with_value(s, 'prefix') for s in steps if with_value(s, 'op') == op]
            # 한 접두어가 다른 접두어로 시작하면 restore-keys 가 남의 묶음을 잡는다
            self.assertFalse([a for a in prefixes for b in prefixes if a != b and (b + '-').startswith(a + '-')])

    def test_release_gate_caches_only_when_rehearsing(self):
        gate = GATE.read_text(encoding='utf-8')
        self.assertIn('cache: ${{ inputs.rehearse }}', gate)
        self.assertRegex(gate, r'rehearse:\n\s+description:[^\n]*\n\s+type: boolean\n\s+default: false')
        self.assertRegex(self.text, r'cache:\n\s+description:[^\n]*(\n\s+[^\n]+)*?\n\s+type: boolean\n\s+default: false')

    def test_secrets_only_through_env_or_with(self):
        for name, steps in self.jobs.items():
            for step in steps:
                self.assertNotIn('secrets.', run_texts(step), f'{name}: run 안에서 시크릿을 바로 씀')
                self.assertNotRegex(run_texts(step), r'set\s+-[a-z]*x', f'{name}: set -x')
                for line in run_texts(step).splitlines():
                    self.assertFalse(prints_secret(line), f'{name}: 시크릿을 찍음: {line.strip()}')

    def test_setup_script_and_action_never_print_secrets(self):
        for f in (SETUP, *ALL_ACTIONS, ROOT / 'tools' / 'ci_cache.py'):
            text = f.read_text(encoding='utf-8')
            self.assertNotRegex(text, r'(?m)^\s*set\s+-[a-z]*x')
            for line in text.splitlines():
                self.assertFalse(prints_secret(line), f'{f.name}: {line.strip()}')
        for f in ALL_ACTIONS:
            action = f.read_text(encoding='utf-8')
            self.assertNotRegex(action, r'run:[^\n]*\$\{\{\s*(inputs|steps)\.', f'{f.parent.name}: 입력을 run 에 바로 끼움')
            for block in re.split(r'\n    - ', action):
                if 'run:' in block:
                    self.assertNotIn('${{ inputs.', block.split('run:', 1)[1], f'{f.parent.name}: 입력을 run 안에서 바로 씀')

    def test_setup_script_masks_the_key(self):
        self.assertIn('::add-mask::', SETUP.read_text(encoding='utf-8'))

    def test_secret_check_helper(self):
        self.assertTrue(prints_secret('echo "$CI_ROM_AGE_KEY"'))
        self.assertTrue(prints_secret('printf "%s" "${CI_ROM_TOKEN}"'))
        self.assertTrue(prints_secret('echo "k=$CI_ROM_TOKEN" >> "$GITHUB_ENV"'))
        self.assertFalse(prints_secret('printf "%s\\n" "$CI_ROM_AGE_KEY" >"$key"'))
        self.assertFalse(prints_secret('echo "::error::secret CI_ROM_TOKEN is not set"'))

    def test_guards_run_without_cache_and_local_needs_are_excluded(self):
        """캐시 없는 실행이 기본(inputs.cache 가 false)이고, 캐시를 쓰는 실행 단계는 inputs.cache 일 때만."""
        runs = [s for s in self.jobs['shard'] if 'tools/guards.py --all' in run_texts(s)]
        plain = [s for s in runs if '--no-cache' in run_texts(s)]
        cached = [s for s in runs if '--no-cache' not in run_texts(s)]
        self.assertEqual((len(plain), len(cached)), (1, 1))
        self.assertRegex(run_texts(plain[0]), r'guards\.py --all ("\$\{only\[@\]\}" )?--run --no-cache')
        self.assertEqual(with_value(plain[0], 'if'), '${{ !inputs.cache }}')
        self.assertEqual(with_value(cached[0], 'if'), 'inputs.cache')
        for s in runs:
            self.assertIn('--exclude-needs "$LOCAL_NEEDS"', run_texts(s))
        self.assertRegex(self.text, r'LOCAL_NEEDS:\s*macos\n')
        build = ''.join(self.jobs['rom'])
        self.assertIn("DQ4_BUILD_CACHE: ${{ inputs.cache && format('{0}/work/cache', github.workspace) || 'off' }}", build)
        for s in self.jobs['rom'] + self.jobs['shard']:
            if 'ship-cache' in s or 'guard-state' in s or 'guard-results-' in s:
                cond = with_value(s, 'if') or ''
                self.assertIn('inputs.cache', cond, s)

    def test_ship_roms_are_built_once_for_every_guard_variant(self):
        """가드가 부르는 dq4build.py 의 인자 조합(--out 빼고)은 모두 rom 잡 행렬에 있고, 조각은 빌드하지 않고
        DQ4_PREBUILT 로 그 롬을 쓴다(guards.with_prebuilt)."""
        rom = ''.join(self.jobs['rom'])
        args = set(re.findall(r'^\s+args:\s*(.*)$', top_block(self.text, 'jobs') and '\n'.join(top_block(self.text, 'jobs')), re.M))
        args = {a.strip().strip("'") for a in args}
        used = set()
        for toml in list(ROOT.glob('*/*/guards.toml')) + [ROOT / 'sfc' / 'dq4' / 'release.toml']:
            for m in re.finditer(r'dq4build\.py --out \S+((?: --[\w-]+)*)', toml.read_text(encoding='utf-8')):
                used.add(m[1].strip())
        self.assertTrue(used)
        self.assertLessEqual(used, args)
        self.assertIn('tools/ci_cache.py ship-build', rom)
        shard = ''.join(self.jobs['shard'])
        self.assertNotIn('dq4build.py', shard)
        self.assertNotIn('ship-build', shard)
        self.assertIn('DQ4_PREBUILT=', shard)

    def test_mesence_unpacks_its_libraries_before_guards(self):
        """리눅스 MesenCE 는 처음 뜰 때 MesenCore.so 를 실행 파일 옆에 푼다. 처음 뜨는 것이 여럿 함께면 서로 덮어써
        Bus error 로 죽어(dq4-npc-walk 시드 기록이 빔), 셋업이 MESENCE 를 잡 환경에 넘기기 전에 한 번 띄워 둔다."""
        text = SETUP.read_text(encoding='utf-8')
        unzip = text.index('unzip -q -o "$mzip" -d "$TOOLS/mesence"')
        warm = text.index('sfc/dq4/tools/dq4mesen.py', unzip)
        check = text.index('MesenCore.so" ]', warm)
        self.assertLess(check, text.index('echo "MESENCE=', check))

    def test_banned_suffixes_cover_rom_and_save_kinds(self):
        for ext in ('.sfc', '.smc', '.nes', '.nds', '.ml1', '.sav', '.mss', '.ips'):
            self.assertIn(ext, ci_artifact_check.BANNED)


if __name__ == '__main__':
    unittest.main()
