import argparse
import copy
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills' / 'smart-test' / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from inspect_repo import inspect
from state import apply, initial, active_directives
from collect_reports import collect

spec = importlib.util.spec_from_file_location('installer', ROOT / 'tools' / 'install_skill.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class Workspace(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def put(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.DEVNULL)

    def init_git(self):
        self.git('init', '-q')

    def commit(self):
        self.git('add', '.')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')


class InspectorTests(Workspace):
    def test_four_repository_profiles(self):
        cases = [
            ('a', 'pom.xml', '<project><artifactId>a</artifactId><dependencies><dependency><artifactId>spring-boot-starter</artifactId></dependency><dependency><artifactId>mybatis-spring-boot-starter</artifactId></dependency><dependency><artifactId>mysql-connector-j</artifactId></dependency></dependencies></project>', {'spring-boot', 'mybatis', 'mysql'}),
            ('b', 'pom.xml', '<project><artifactId>b</artifactId><dependencies><dependency><artifactId>spring-boot-starter-data-jpa</artifactId></dependency><dependency><artifactId>postgresql</artifactId></dependency></dependencies></project>', {'spring-boot', 'jpa', 'postgresql'}),
            ('c', 'build.gradle.kts', 'plugins { id("org.springframework.boot") }\ndependencies { implementation("org.springframework.boot:spring-boot-starter-data-redis"); implementation("org.springframework.kafka:spring-kafka") }', {'spring-boot', 'redis', 'kafka'}),
            ('d', 'pom.xml', '<project><artifactId>d</artifactId><dependencies><dependency><groupId>junit</groupId><artifactId>junit</artifactId></dependency></dependencies></project>', {'junit4'}),
        ]
        for directory, name, content, expected in cases:
            with self.subTest(directory=directory):
                self.put(directory + '/' + name, content)
                result = inspect(self.root / directory)
                self.assertTrue(expected <= set(result['signals']))
                self.assertEqual(result['status'], 'DISCOVERED')
                if directory == 'd':
                    self.assertNotIn('junit5', result['signals'])

    def test_multimodule_transitive_consumers(self):
        self.init_git()
        for module, dependency in [('common', None), ('service', 'common'), ('api', 'service')]:
            dep = '' if not dependency else '<dependencies><dependency><groupId>demo</groupId><artifactId>' + dependency + '</artifactId></dependency></dependencies>'
            self.put(module + '/pom.xml', '<project><groupId>demo</groupId><artifactId>' + module + '</artifactId>' + dep + '</project>')
        self.put('common/src/main/java/Common.java', 'class Common {}')
        self.commit()
        self.put('common/src/main/java/Common.java', 'class Common { int value; }')
        result = inspect(self.root)
        self.assertEqual(result['change']['impacted_modules_hint'], ['api', 'common', 'service'])
        self.assertEqual(result['change']['confidence'], 'LOW')

    def test_diff_staged_unstaged_and_untracked(self):
        self.init_git()
        self.put('A.java', 'class A {}')
        self.put('Delete.java', 'class Delete {}')
        self.commit()
        self.put('A.java', 'class A { int x; }')
        self.git('add', 'A.java')
        self.put('A.java', 'class A { int x; int y; }')
        (self.root / 'Delete.java').unlink()
        self.put('New File.java', 'class New {}')
        files = {f['path']: f['status'] for f in inspect(self.root)['change']['files']}
        self.assertEqual(files, {'A.java': 'M', 'Delete.java': 'D', 'New File.java': '?'})
        staged = inspect(self.root, staged=True)['change']['files']
        self.assertEqual([f['path'] for f in staged], ['A.java'])

    def test_base_uses_merge_base_and_includes_worktree(self):
        self.init_git()
        self.put('A.java', 'class A {}')
        self.commit()
        self.git('branch', 'baseline')
        self.put('B.java', 'class B {}')
        self.commit()
        self.put('C.java', 'class C {}')
        result = inspect(self.root, base='baseline')['change']
        self.assertEqual([f['path'] for f in result['files']], ['B.java', 'C.java'])
        self.assertTrue(result['merge_base'])

    def test_unborn_git(self):
        self.init_git()
        self.put('A.java', 'class A {}')
        self.git('add', 'A.java')
        self.put('B.java', 'class B {}')
        result = inspect(self.root)['change']
        self.assertIsNone(result['head'])
        self.assertEqual(len(result['files']), 2)

    def test_read_only_ignores_secrets_and_generated_files(self):
        self.init_git()
        self.put('.gitignore', 'ignored/\n')
        self.put('ignored/Leak.java', 'class Leak {}')
        self.put('.env', 'TOKEN=DO_NOT_OUTPUT')
        self.put('target/Generated.java', 'class Generated {}')
        self.put('src/main/resources/application.yml', 'spring: jdbc:mysql://user:DO_NOT_OUTPUT@host/db')
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*'))
        output = json.dumps(inspect(self.root))
        after = sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*'))
        self.assertEqual(before, after)
        self.assertNotIn('DO_NOT_OUTPUT', output)
        self.assertNotIn('Leak.java', output)
        self.assertNotIn('Generated.java', output)
        self.assertIn('mysql', output)

    def test_symlink_is_not_followed(self):
        outside = self.put('outside/pom.xml', '<project/>')
        self.root.joinpath('linked-pom.xml').symlink_to(outside)
        result = inspect(self.root)
        self.assertNotIn('linked-pom.xml', result['fingerprints'])

    def test_limit_and_invalid_ref_fail_honestly(self):
        self.put('A.java', 'class A {}')
        self.put('B.java', 'class B {}')
        self.assertTrue(inspect(self.root, limit=1)['incomplete'])
        self.init_git()
        with self.assertRaises(ValueError):
            inspect(self.root, base='ref-that-does-not-exist')


class StateTests(Workspace):
    def setUp(self):
        super().setUp()
        self.state = initial()
        self.put('pom.xml', '<project/>')

    def action(self, command, payload=None, **kwargs):
        return apply(self.state, self.root, argparse.Namespace(command=command, **kwargs), payload)

    def proposal(self, identity='DEC-UNIT', topics=None, deps=None, paths=None):
        return {'id': identity, 'kind': 'strategy', 'summary': 'Use the existing test stack',
                'topics': topics or ['unit'], 'evidence_paths': paths if paths is not None else ['pom.xml'],
                'depends_on': deps or []}

    def effective(self, identity='DEC-UNIT', topics=None, deps=None, paths=None):
        self.action('propose', self.proposal(identity, topics, deps, paths))
        self.action('resolve', id=identity, action='confirm', source='user', evidence='Actual user message authorizing this test strategy')

    def directive(self, identity='DIR-1', lifecycle='PROJECT', binding=None):
        return {'id': identity, 'category': 'technical', 'level': 'REQUIRED', 'statement': 'No Docker',
                'source': 'Actual user message', 'scope': {'test_type': ['integration']},
                'lifecycle': lifecycle, 'binding': binding or {}, 'topics': ['integration'], 'status': 'ACTIVE'}

    def test_proposal_cannot_self_approve(self):
        item = self.proposal()
        item['status'] = 'EFFECTIVE'
        item['approval'] = {'type': 'user'}
        self.action('propose', item)
        decision = self.state['decisions'][0]
        self.assertEqual(decision['status'], 'PROPOSED')
        self.assertNotIn('approval', decision)

    def test_reuse_unchanged_decision(self):
        self.effective()
        before = copy.deepcopy(self.state)
        self.action('propose', self.proposal())
        self.assertEqual(before, self.state)

    def test_file_change_invalidates_only_affected_chain(self):
        self.put('unit.json', '{}')
        self.effective(paths=['unit.json'])
        self.effective('DEC-DB', ['integration'])
        self.effective('DEC-CI', ['ci'], ['DEC-DB'], [])
        self.put('pom.xml', '<project><artifactId>changed</artifactId></project>')
        result = self.action('reconcile')
        self.assertEqual(result['invalidated'], ['DEC-CI', 'DEC-DB'])
        self.assertEqual(self.state['decisions'][0]['status'], 'EFFECTIVE')

    def test_directive_invalidates_integration_and_ci_not_unit(self):
        self.effective()
        self.effective('DEC-DB', ['integration'])
        self.effective('DEC-CI', ['ci'], ['DEC-DB'], [])
        result = self.action('directive', self.directive())
        self.assertEqual(result['invalidated'], ['DEC-CI', 'DEC-DB'])
        self.assertEqual(self.state['decisions'][0]['status'], 'EFFECTIVE')

    def test_rejected_proposal_cannot_be_confirmed_without_revision(self):
        self.action('propose', self.proposal())
        self.action('resolve', id='DEC-UNIT', action='reject', evidence='User rejected this proposal')
        with self.assertRaises(ValueError):
            self.action('resolve', id='DEC-UNIT', action='confirm', source='user', evidence='Old approval')
        self.action('propose', self.proposal())
        self.assertEqual(self.state['decisions'][0]['version'], 2)

    def test_lifecycle_bindings_do_not_leak(self):
        self.action('directive', self.directive('session', 'SESSION', {'session': 'one'}))
        self.action('directive', self.directive('change', 'CHANGE', {'change': 'change-one'}))
        self.action('directive', self.directive('project'))
        result = active_directives(self.state, session='two', change='change-two')
        self.assertEqual([d['id'] for d in result['active_directives']], ['project'])
        with self.assertRaises(ValueError):
            self.action('directive', self.directive('invalid', 'SESSION'))

    def test_scope_is_matched_when_context_is_explicit(self):
        directive = self.directive('order-db')
        directive['scope'] = {'module': ['order*'], 'test_type': ['integration']}
        self.action('directive', directive)
        integration = active_directives(self.state, module='order-service', test_type='integration')
        self.assertEqual([d['id'] for d in integration['active_directives']], ['order-db'])
        unit = active_directives(self.state, module='order-service', test_type='unit')
        self.assertEqual(unit['active_directives'], [])
        self.assertEqual(unit['excluded_directives'][0]['id'], 'order-db')
        unresolved = active_directives(self.state, test_type='integration')
        self.assertEqual(unresolved['unresolved_directives'][0]['id'], 'order-db')

    def test_one_time_consumption(self):
        self.action('directive', self.directive('once', 'ONE_TIME', {'session': 'one'}))
        self.action('consume', id='once', evidence='Completed the one authorized action')
        self.assertFalse(active_directives(self.state, session='one')['active_directives'])
        with self.assertRaises(ValueError):
            self.action('consume', id='once', evidence='second use')

    def test_changed_proposal_evidence_cannot_receive_old_approval(self):
        self.action('propose', self.proposal())
        self.put('pom.xml', '<changed/>')
        with self.assertRaises(ValueError):
            self.action('resolve', id='DEC-UNIT', action='confirm', source='user', evidence='Approval of original proposal')

    def test_path_traversal_and_symlink_evidence_rejected(self):
        with self.assertRaises(ValueError):
            self.action('propose', self.proposal(paths=['../outside']))
        self.root.joinpath('link').symlink_to(self.root / 'pom.xml')
        with self.assertRaises(ValueError):
            self.action('propose', self.proposal(paths=['link']))

    def test_dependency_cycle_is_rejected_without_changing_decisions(self):
        self.effective('A')
        self.effective('B', deps=['A'])
        before = copy.deepcopy(self.state)
        with self.assertRaises(ValueError):
            self.action('propose', self.proposal('A', deps=['B']))
        self.assertEqual(self.state, before)

    def test_cli_dry_run_no_files_and_init_is_idempotent(self):
        command = [sys.executable, str(SCRIPTS / 'state.py'), '--repo', str(self.root)]
        subprocess.check_output(command + ['--dry-run', 'init'])
        self.assertFalse((self.root / '.smart-test').exists())
        subprocess.check_output(command + ['init'])
        path = self.root / '.smart-test/state.json'
        before = path.read_bytes()
        subprocess.check_output(command + ['init'])
        self.assertEqual(before, path.read_bytes())

    def test_cli_lock_and_invalid_payload_preserve_ledger(self):
        command = [sys.executable, str(SCRIPTS / 'state.py'), '--repo', str(self.root)]
        subprocess.check_output(command + ['init'])
        path = self.root / '.smart-test/state.json'
        before = path.read_bytes()
        lock = self.put('.smart-test/state.lock', 'other-process')
        result = subprocess.run(command + ['init'], capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertTrue(lock.exists())
        lock.unlink()
        payload = self.put('bad.json', '{}')
        result = subprocess.run(command + ['directive', '--input', str(payload)], capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(before, path.read_bytes())
        self.assertFalse(lock.exists())


class ReportTests(Workspace):
    def setUp(self):
        super().setUp()
        self.started = time.time() - 2
        self.report = self.put('target/surefire-reports/TEST-Demo.xml', '<testsuite tests="1"><testcase classname="Demo" name="works"/></testsuite>')
        self.finished = time.time() + 2

    def manifest(self):
        date = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat()
        return {'schema_version': 1, 'required_run_ids': ['unit'], 'blockers': [], 'runs': [
            {'id': 'unit', 'argv': ['./mvnw', 'test'], 'exit_code': 0,
             'started_at': date(self.started), 'finished_at': date(self.finished),
             'reports': [{'pattern': 'target/surefire-reports/TEST-*.xml', 'required': True,
                          'expected_test_ids': ['Demo#works']}]}]}

    def result(self, manifest=None):
        return collect(self.root, manifest or self.manifest())

    def test_fresh_success_is_execution_evidence_only(self):
        result = self.result()
        self.assertEqual(result['status'], 'EVIDENCE_PASS')
        self.assertEqual(result['counts']['tests'], 1)

    def test_missing_zero_and_stale_reports_never_pass(self):
        os.utime(self.report, (self.started - 100, self.started - 100))
        self.assertEqual(self.result()['status'], 'NOT_VERIFIED')
        self.report.unlink()
        self.assertEqual(self.result()['status'], 'NOT_VERIFIED')
        self.put('target/surefire-reports/TEST-Demo.xml', '<testsuite tests="0"/>')
        self.assertEqual(self.result()['status'], 'NOT_VERIFIED')

    def test_failure_even_with_exit_zero_and_skip(self):
        for child in ('<failure/>', '<error/>', '<skipped/>'):
            with self.subTest(child=child):
                self.report.write_text('<testsuite tests="1"><testcase classname="Demo" name="works">' + child + '</testcase></testsuite>')
                self.assertEqual(self.result()['status'], 'NOT_VERIFIED')

    def test_nonzero_command_or_missing_required_run(self):
        m = self.manifest()
        m['runs'][0]['exit_code'] = 1
        self.assertEqual(self.result(m)['status'], 'NOT_VERIFIED')
        m = self.manifest()
        m['required_run_ids'].append('integration')
        self.assertEqual(self.result(m)['status'], 'NOT_VERIFIED')

    def test_nested_suites_and_duplicate_report_references(self):
        self.report.write_text('<testsuites tests="1"><testsuite tests="1"><testcase classname="Demo" name="works"/></testsuite></testsuites>')
        self.assertEqual(self.result()['counts']['tests'], 1)
        m = self.manifest()
        m['runs'][0]['reports'].append(copy.deepcopy(m['runs'][0]['reports'][0]))
        result = self.result(m)
        self.assertEqual(result['status'], 'NOT_VERIFIED')
        self.assertEqual(result['counts']['tests'], 1)

    def test_malformed_or_declared_only_xml_does_not_pass(self):
        for content in ('<broken', '<testsuite tests="5"/>', '<!DOCTYPE x><testsuite/>'):
            with self.subTest(content=content):
                self.report.write_text(content)
                self.assertEqual(self.result()['status'], 'NOT_VERIFIED')

    def test_blocker_and_missing_expected_test(self):
        m = self.manifest()
        m['blockers'] = ['PRODUCT_DEFECT']
        self.assertEqual(self.result(m)['status'], 'NOT_VERIFIED')
        m = self.manifest()
        m['runs'][0]['reports'][0]['expected_test_ids'] = ['Demo#another']
        self.assertEqual(self.result(m)['status'], 'NOT_VERIFIED')

    def test_secret_log_content_and_args_not_emitted(self):
        self.report.write_text('<testsuite tests="1"><testcase classname="Demo" name="works"/><system-out>SECRET_VALUE</system-out></testsuite>')
        m = self.manifest()
        m['runs'][0]['argv'].append('-Dpassword=SECRET_VALUE')
        self.assertNotIn('SECRET_VALUE', json.dumps(self.result(m)))

    def test_report_outside_repository_is_rejected(self):
        m = self.manifest()
        m['runs'][0]['reports'][0]['pattern'] = '../*.xml'
        with self.assertRaises(ValueError):
            self.result(m)

    def test_expected_test_must_execute_even_if_other_skips_allowed(self):
        self.report.write_text('<testsuite tests="2"><testcase classname="Demo" name="works"><skipped/></testcase><testcase classname="Demo" name="another"/></testsuite>')
        m = self.manifest()
        m['runs'][0]['reports'][0]['allow_skipped'] = True
        self.assertEqual(self.result(m)['status'], 'NOT_VERIFIED')

    def test_example_manifest_is_not_execution_evidence(self):
        m = self.manifest()
        m['example_only'] = True
        with self.assertRaises(ValueError):
            self.result(m)


class InstallTests(Workspace):
    def test_install_reinstall_and_non_overwrite(self):
        parent = self.root / 'skills'
        self.assertEqual(installer.install(parent)['status'], 'INSTALLED')
        self.assertEqual(installer.install(parent)['status'], 'UNCHANGED')
        target = parent / 'smart-test'
        (target / 'SKILL.md').write_text('user customization')
        with self.assertRaises(ValueError):
            installer.install(parent)
        result = installer.install(parent, replace=True)
        backup = Path(result['backup'])
        self.assertEqual((backup / 'SKILL.md').read_text(), 'user customization')
        self.assertNotEqual(backup.parent, parent)
        self.assertEqual(installer.contents(target), installer.contents(installer.SOURCE))

    def test_dry_run_creates_nothing(self):
        result = installer.install(self.root / 'new', dry_run=True)
        self.assertEqual(result['status'], 'DRY_RUN')
        self.assertFalse((self.root / 'new').exists())

    def test_symlink_destination_is_rejected(self):
        parent = self.root / 'skills'
        parent.mkdir()
        (parent / 'smart-test').symlink_to(self.root)
        with self.assertRaises(ValueError):
            installer.install(parent)

    def test_both_project_install_paths(self):
        for host, directory in [('codex', '.agents'), ('claude', '.claude')]:
            with self.subTest(host=host):
                subprocess.check_output([sys.executable, str(ROOT / 'tools/install_skill.py'),
                                         '--host', host, '--scope', 'project', '--project', str(self.root)])
                self.assertTrue((self.root / directory / 'skills/smart-test/SKILL.md').is_file())

    def test_installed_read_only_helpers_do_not_write_bytecode(self):
        parent = self.root / '.agents/skills'
        installer.install(parent)
        installed = parent / 'smart-test/scripts'
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*'))
        env = dict(os.environ)
        env.pop('PYTHONDONTWRITEBYTECODE', None)
        subprocess.check_output([sys.executable, str(installed / 'inspect_repo.py'), '--repo', str(self.root)], env=env)
        subprocess.check_output([sys.executable, str(installed / 'state.py'), '--repo', str(self.root), '--dry-run', 'init'], env=env)
        after = sorted(str(p.relative_to(self.root)) for p in self.root.rglob('*'))
        self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()
