"""ci.yml 의 PR 가드 잡이 롬 묶음 시크릿을 같은 저장소 브랜치의 PR 과 main push(머지 뒤 캐시 데우기)에만 넘기는 꼴인지 지킨다.

pr-guards 잡은 guard-shards.yml 을 부르며 CI_ROM_TOKEN·CI_ROM_AGE_KEY 를 넘긴다. 포크 PR 의 코드가 시크릿과 함께 돌면
안 되고(pull_request 는 포크에 시크릿을 주지 않지만, 조건이 빠지면 같은 저장소 판정도 사라진다), pull_request_target 처럼
base 의 권한으로 PR 코드를 돌리는 트리거도 안 된다. 시크릿을 쓰는 잡은 같은 커밋의 보호 테스트(이 파일과
test_release_gate_workflow)가 먼저 통과해야 돈다 — 워크플로를 고치다 키를 찍는 실수를 시크릿 앞에서 잡는다.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_release_gate_workflow import WORKFLOWS, jobs, run_texts, top_block, triggers, with_value  # noqa: E402

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
        self.assertIn('[ "$EVENT" = pull_request ] && [ "$SAME_REPO" != true ]', script)
        self.assertRegex(script, r'exit 1\s*$')
        self.assertEqual(with_value(self.steps['pr-guards-result'][0], 'SAME_REPO'), f'${{{{ {SAME_REPO} }}}}')

    def test_required_checks_asks_forks_for_every_line(self):
        script = run_texts(self.steps['required-checks'][-1])
        self.assertIn('scope=(--local-only)', script)
        self.assertIn('[ "$SAME_REPO" = true ]', script)

    def test_local_needs_has_one_source(self):
        """로컬 몫 이름은 guard-shards.yml 의 LOCAL_NEEDS 하나에서만 읽는다(ci.yml 에 따로 두지 않음)."""
        self.assertIsNone(re.search(r'LOCAL_NEEDS\s*:', self.text), 'ci.yml 에 LOCAL_NEEDS 를 따로 정의함')
        self.assertTrue(guards.ci_local_needs())


if __name__ == '__main__':
    unittest.main()
