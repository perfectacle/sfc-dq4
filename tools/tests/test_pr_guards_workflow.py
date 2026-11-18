"""ci.yml 의 PR 가드 잡이 롬 묶음 시크릿을 같은 저장소 브랜치의 PR 과 main push(머지 뒤 캐시 데우기)에만 넘기는 꼴인지 지킨다.

pr-guards 잡은 guard-shards.yml 을 부르며 CI_ROM_TOKEN·CI_ROM_AGE_KEY 를 넘긴다. 포크 PR 의 코드가 시크릿과 함께 돌면
안 되고(pull_request 는 포크에 시크릿을 주지 않지만, 조건이 빠지면 같은 저장소 판정도 사라진다), pull_request_target 처럼
base 의 권한으로 PR 코드를 돌리는 트리거도 안 된다. 이 저장소는 포크 PR 을 받지 않는다: 사용자 소유 퍼블릭 저장소는
포크 자체를 끌 수 없어서, 포크에서 온 PR 은 ci-ok 가 실패해 머지되지 못하게 한다. 시크릿을 쓰는 잡은 같은 커밋의 보호 테스트(이 파일과
test_release_gate_workflow)가 먼저 통과해야 돈다 — 워크플로를 고치다 키를 찍는 실수를 시크릿 앞에서 잡는다.
"""
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_release_gate_workflow import GATE, WARM, WORKFLOWS, jobs, run_texts, top_block, triggers, with_value  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import guards  # noqa: E402

CI = WORKFLOWS / 'ci.yml'
SAME_REPO = 'github.event.pull_request.head.repo.full_name == github.repository'
SECRETS = ('CI_ROM_TOKEN', 'CI_ROM_AGE_KEY')
MAIN_PUSH = "github.event_name == 'push' && github.ref == 'refs/heads/main'"
PR_GUARDS_IF = (f"needs.guard-plan.outputs.guards != '' && (github.event_name == 'pull_request' && {SAME_REPO}"
                f" || {MAIN_PUSH})")


def job_texts(text):
    """{잡 이름: 잡 글 전부}(jobs() 는 단계만 보므로 잡 자리의 uses·with·secrets 는 여기서)."""
    out, job = {}, None
    for line in top_block(text, 'jobs'):
        m = re.match(r'^  ([A-Za-z0-9_-]+):\s*$', line)
        if m:
            job = m[1]
            out[job] = ''
        elif job:
            out[job] += line + '\n'
    return out


def job_key(text, key):
    m = re.search(rf'^    {key}:\s*(.+)$', text, re.M)
    return m[1].strip() if m else None


class PrGuardsWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.text = CI.read_text(encoding='utf-8')
        self.jobs = job_texts(self.text)
        self.steps = jobs(self.text)

    def test_no_privileged_triggers(self):
        self.assertTrue({'pull_request'} <= triggers(self.text))
        for bad in ('pull_request_target', 'workflow_run', 'issue_comment'):
            self.assertNotRegex(self.text, rf'\b{bad}\b')
        self.assertNotRegex(self.text, r'secrets:\s*inherit')

    def test_newer_push_cancels_older_run(self):
        # PR 과 main push 는 ref 하나에 그룹 하나라 새 푸시가 앞 run 을 끊는다. 손으로 띄운 run 은 run 마다 그룹이 달라 끝까지 돈다.
        block = '\n'.join(top_block(self.text, 'concurrency'))
        group = re.search(r'group: (.+)', block)[1]
        self.assertIn("format('{0}-{1}', github.event_name, github.ref)", group)
        self.assertIn("github.event_name == 'workflow_dispatch' && format('dispatch-{0}', github.run_id)", group)
        self.assertNotIn('github.sha', group)
        self.assertIn("cancel-in-progress: ${{ github.event_name != 'workflow_dispatch' }}", block)

    def test_gate_and_warm_never_cancel(self):
        # 관문은 손으로 띄운 결과를 끝까지 봐야 하고, 데우기는 관문과 그룹을 나눠 겹치지 않을 뿐 끊기면 안 된다.
        for wf in (GATE, WARM):
            block = '\n'.join(top_block(wf.read_text(encoding='utf-8'), 'concurrency'))
            self.assertRegex(block, r'group: release-gate-', wf.name)
            self.assertRegex(block, r'cancel-in-progress: false\b', wf.name)

    def test_only_pr_guards_touches_secrets(self):
        for name, body in self.jobs.items():
            if name != 'pr-guards':
                self.assertNotIn('secrets.', body, f'{name}: 시크릿은 pr-guards 잡만')
        callers = [n for n, b in self.jobs.items() if 'guard-shards.yml' in (job_key(b, 'uses') or '')]
        self.assertEqual(callers, ['pr-guards'])

    def test_pr_guards_runs_only_for_same_repo_prs(self):
        job = self.jobs['pr-guards']
        # 같은 저장소 브랜치 PR 또는 main 에 push(머지 뒤 캐시 데우기)뿐. 조건을 넓히려면 이 글자를 고쳐야 한다
        self.assertEqual(job_key(job, 'if'), PR_GUARDS_IF)
        self.assertEqual(job_key(job, 'needs'), 'guard-plan')
        self.assertRegex(job, r'uses:\s*\./\.github/workflows/guard-shards\.yml')
        self.assertRegex(job, r'\n      mode: pr\n')
        self.assertRegex(job, r'\n      cache: true\n')
        for s in SECRETS:
            self.assertIn(f'{s}: ${{{{ secrets.{s} }}}}', job)
        self.assertEqual(len(re.findall(r'secrets\.', job)), len(SECRETS))

    def test_plan_reads_the_guard_table_of_the_commit_the_shards_check_out(self):
        """guard-plan 이 뽑은 검사 이름은 guard-shards 가 `ref` 로 받는 PR 머리 커밋의 표에서 읽혀야 한다. 기본 체크아웃
        (refs/pull/N/merge)은 가지를 딴 뒤 main 에 새로 생긴 가드까지 이름으로 뽑아, 그 가드가 없는 머리 커밋을 받은
        조각이 「--only: 모르는 검사」 로 멈춘다. required-checks 도 같은 표로 본문 결과 줄을 요구한다."""
        head = 'ref: ${{ github.event.pull_request.head.sha || github.sha }}'
        passed = re.search(r'\n      ref: (.+)\n', self.jobs['pr-guards'])[1].strip()
        self.assertEqual(f'ref: {passed}', head)
        for name in ('guard-plan', 'required-checks'):
            checkouts = [s for s in self.steps[name] if 'actions/checkout@' in s]
            self.assertEqual(len(checkouts), 1, name)
            self.assertIn(head, checkouts[0], f'{name} 가 PR 머리 커밋을 받지 않음')

    def test_plan_runs_protection_tests_first(self):
        steps = self.steps['guard-plan']
        tests = [i for i, s in enumerate(steps) if 'test_release_gate_workflow.py' in run_texts(s)
                 and 'test_pr_guards_workflow.py' in run_texts(s)]
        plan = [i for i, s in enumerate(steps) if '--plan' in run_texts(s)]
        self.assertEqual(len(tests), 1)
        self.assertEqual(len(plan), 1)
        self.assertLess(tests[0], plan[0])
        self.assertEqual(job_key(self.jobs['guard-plan'], 'if'), f"github.event_name == 'pull_request' || {MAIN_PUSH}")
        # 권한은 읽기만
        self.assertNotRegex(self.text, r':\s*write\b')

    def test_verdict_job_gates_ci_ok(self):
        ok = self.jobs['ci-ok']
        needs = job_key(ok, 'needs')
        for n in ('required-checks', 'pr-guards-result'):
            self.assertIn(n, needs)
        verdict = self.jobs['pr-guards-result']
        self.assertEqual(job_key(verdict, 'if'), 'always()')
        self.assertIn('guard-plan', job_key(verdict, 'needs'))
        self.assertIn('pr-guards', job_key(verdict, 'needs'))
        script = run_texts(self.steps['pr-guards-result'][0])
        self.assertIn('"$RESULT" = success', script)
        self.assertNotIn('관리자가 확인', script)
        self.assertRegex(script, r'exit 1\s*$')
        self.assertEqual(with_value(self.steps['pr-guards-result'][0], 'SAME_REPO'), f'${{{{ {SAME_REPO} }}}}')

    def run_step(self, step, **env):
        r = subprocess.run(['bash', '-c', run_texts(step)], env={**os.environ, **env},
                           capture_output=True, text=True, timeout=10)
        return r.returncode, r.stdout + r.stderr

    def test_ci_ok_rejects_fork_prs(self):
        first = self.steps['ci-ok'][0]
        self.assertNotRegex(first, r'^\s+if:', 'ci-ok 의 포크 거부 단계는 조건 없이 늘 돈다')
        self.assertEqual(with_value(first, 'SAME_REPO'), f'${{{{ {SAME_REPO} }}}}')
        self.assertEqual(with_value(first, 'EVENT'), '${{ github.event_name }}')
        code, out = self.run_step(first, EVENT='pull_request', SAME_REPO='false')
        self.assertEqual(code, 1)
        self.assertIn('이 저장소는 포크 PR 을 받지 않는다', out)
        for event, same in (('pull_request', 'true'), ('push', 'false'), ('workflow_dispatch', 'false')):
            self.assertEqual(self.run_step(first, EVENT=event, SAME_REPO=same)[0], 0, (event, same))

    def test_verdict_rejects_fork_prs_before_any_pass(self):
        code, out = self.run_step(self.steps['pr-guards-result'][0], EVENT='pull_request', SAME_REPO='false',
                                  PLAN='success', GUARDS='', LOCAL='', RESULT='skipped')
        self.assertEqual(code, 1)
        self.assertIn('이 저장소는 포크 PR 을 받지 않는다', out)

    def test_required_checks_asks_only_local_lines(self):
        step = self.steps['required-checks'][-1]
        self.assertIn('--local-only', run_texts(step))
        self.assertNotIn('SAME_REPO', step)

    def test_local_needs_has_one_source(self):
        """로컬 몫 이름은 guard-shards.yml 의 LOCAL_NEEDS 하나에서만 읽는다(ci.yml 에 따로 두지 않음)."""
        self.assertIsNone(re.search(r'LOCAL_NEEDS\s*:', self.text), 'ci.yml 에 LOCAL_NEEDS 를 따로 정의함')
        self.assertTrue(guards.ci_local_needs())


if __name__ == '__main__':
    unittest.main()
