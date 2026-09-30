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
from validate_artifacts import validate

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

    def test_mapper_xml_is_fingerprinted_and_marks_sql_risk(self):
        self.init_git()
        name = 'src/main/resources/mapper/Orders.xml'
        self.put(name, '<mapper namespace="demo.Orders"><select id="find">SELECT id FROM orders</select></mapper>')
        self.put('src/main/resources/unrelated.xml', '<settings/>')
        self.commit()
        before = inspect(self.root)
        self.put(name, '<mapper namespace="demo.Orders"><select id="find">SELECT id FROM orders WHERE tenant_id = #{tenant}</select></mapper>')
        after = inspect(self.root)
        self.assertIn(name, before['fingerprints'])
        self.assertNotEqual(before['fingerprints'][name], after['fingerprints'][name])
        self.assertIn({'path': name, 'indicators': ['sql-mapping']}, after['risk_indicators'])
        self.assertIn(name, after['signals']['mybatis'])
        self.assertNotIn('src/main/resources/unrelated.xml', after['fingerprints'])

    def test_gradle_literal_consumers_are_transitive(self):
        for dsl in ('groovy', 'kotlin'):
            with self.subTest(dsl=dsl):
                root = self.root / dsl
                root.mkdir()
                suffix = '.kts' if dsl == 'kotlin' else ''
                self.put(dsl + '/settings.gradle' + suffix, 'include("common", "service", "api")')
                for module, provider in [('common', None), ('service', 'common'), ('api', 'service')]:
                    dependency = '' if not provider else ('dependencies { implementation(project(path = ":' + provider + '")) }' if dsl == 'kotlin' else 'dependencies { implementation project(path: ":' + provider + '") }')
                    self.put(dsl + '/' + module + '/build.gradle' + suffix, dependency)
                subprocess.check_call(['git', 'init', '-q', str(root)])
                subprocess.check_call(['git', '-C', str(root), 'add', '.'])
                subprocess.check_call(['git', '-C', str(root), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture'])
                self.put(dsl + '/common/src/main/java/Common.java', 'class Common {}')
                result = inspect(root)
                self.assertEqual(result['change']['impacted_modules_hint'], ['api', 'common', 'service'])
                self.assertEqual(result['change']['confidence'], 'LOW')

    def test_gradle_project_directory_override_and_unresolved_reference(self):
        self.init_git()
        self.put('settings.gradle', "include ':shared', ':api'\nproject(':shared').projectDir = file('libs/core')")
        self.put('libs/core/build.gradle', '')
        self.put('api/build.gradle', "dependencies { implementation project(':shared'); implementation project(':unknown') }")
        self.commit()
        self.put('libs/core/src/main/java/Core.java', 'class Core {}')
        result = inspect(self.root)
        self.assertEqual(result['change']['impacted_modules_hint'], ['api', 'libs/core'])
        self.assertEqual(result['module_edges'], [{'consumer': 'api', 'provider': 'libs/core', 'confidence': 'MEDIUM', 'source': 'api/build.gradle'}])
        self.assertTrue(any('Unresolved Gradle project' in warning for warning in result['warnings']))

    def test_gradle_dynamic_directory_does_not_guess_an_edge(self):
        self.put('settings.gradle', "include ':shared', ':api'\nproject(':shared').projectDir = findSharedDirectory()")
        self.put('shared/build.gradle', '')
        self.put('api/build.gradle', "dependencies { implementation project(':shared') }")
        result = inspect(self.root)
        self.assertEqual(result['module_edges'], [])
        self.assertTrue(any('Gradle projectDir' in warning for warning in result['warnings']))

    def test_gradle_consumer_of_root_project_and_comment_only_mapper(self):
        self.init_git()
        self.put('settings.gradle', "include ':api'")
        self.put('build.gradle', '')
        self.put('api/build.gradle', "dependencies { implementation project(':') }")
        self.put('src/main/resources/settings.xml', '<settings><!-- <mapper namespace="demo"/> --></settings>')
        self.commit()
        self.put('src/main/java/Root.java', 'class Root {}')
        result = inspect(self.root)
        self.assertEqual(result['change']['impacted_modules_hint'], ['.', 'api'])
        self.assertNotIn('src/main/resources/settings.xml', result['fingerprints'])

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

    def test_compile_only_run_does_not_require_test_report(self):
        date = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat()
        manifest = {'schema_version': 1, 'required_run_ids': ['compile'], 'blockers': [], 'runs': [
            {'id': 'compile', 'kind': 'compile', 'requires_test_report': False,
             'argv': ['./mvnw', '-DskipTests', 'compile'], 'exit_code': 0,
             'started_at': date(self.started), 'finished_at': date(self.finished), 'reports': []}]}
        result = self.result(manifest)
        self.assertEqual(result['status'], 'EVIDENCE_PASS')
        self.assertEqual(result['counts']['tests'], 0)
        self.assertEqual(result['runs'][0]['kind'], 'compile')

    def test_compile_failure_still_blocks_without_test_report(self):
        date = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat()
        manifest = {'schema_version': 1, 'required_run_ids': ['compile'], 'blockers': [], 'runs': [
            {'id': 'compile', 'kind': 'compile', 'requires_test_report': False,
             'argv': ['./mvnw', '-DskipTests', 'compile'], 'exit_code': 1,
             'started_at': date(self.started), 'finished_at': date(self.finished), 'reports': []}]}
        self.assertEqual(self.result(manifest)['status'], 'NOT_VERIFIED')

    def test_required_test_run_without_report_is_not_verified(self):
        date = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat()
        manifest = {'schema_version': 1, 'required_run_ids': ['unit'], 'blockers': [], 'runs': [
            {'id': 'unit', 'kind': 'test', 'requires_test_report': True,
             'argv': ['./mvnw', 'test'], 'exit_code': 0,
             'started_at': date(self.started), 'finished_at': date(self.finished), 'reports': []}]}
        result = self.result(manifest)
        self.assertEqual(result['status'], 'NOT_VERIFIED')
        self.assertIn('NO_REQUIRED_REPORT_GROUP', {i['type'] for i in result['issues']})
        self.assertIn('ZERO_TESTS', {i['type'] for i in result['issues']})

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

    def test_generic_agent_explicit_destination_and_repeat_install(self):
        parent = self.root / 'custom-agent-skills'
        command = [sys.executable, str(ROOT / 'tools/install_skill.py'), '--dest', str(parent)]
        first = json.loads(subprocess.check_output(command))
        self.assertEqual(first['status'], 'INSTALLED')
        self.assertTrue((parent / 'smart-test/references/test-design.md').is_file())
        self.assertEqual(json.loads(subprocess.check_output(command))['status'], 'UNCHANGED')
        self.assertEqual(installer.contents(parent / 'smart-test'), installer.contents(installer.SOURCE))

    def test_generic_agent_requires_destination_and_dry_run_writes_nothing(self):
        command = [sys.executable, str(ROOT / 'tools/install_skill.py'), '--host', 'generic']
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--dest', json.loads(result.stdout)['error'])
        parent = self.root / 'custom-agent-skills'
        result = subprocess.check_output(command + ['--dest', str(parent), '--dry-run'])
        self.assertEqual(json.loads(result)['status'], 'DRY_RUN')
        self.assertFalse(parent.exists())

    def test_generic_agent_replace_preserves_customized_installation(self):
        parent = self.root / 'custom-agent-skills'
        command = [sys.executable, str(ROOT / 'tools/install_skill.py'), '--dest', str(parent)]
        subprocess.check_output(command)
        target = parent / 'smart-test'
        (target / 'SKILL.md').write_text('local customization')
        refused = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(refused.returncode, 2)
        self.assertEqual((target / 'SKILL.md').read_text(), 'local customization')
        updated = json.loads(subprocess.check_output(command + ['--replace']))
        self.assertEqual((Path(updated['backup']) / 'SKILL.md').read_text(), 'local customization')
        self.assertNotEqual(Path(updated['backup']).parent, parent)
        self.assertEqual(installer.contents(target), installer.contents(installer.SOURCE))

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


class ArtifactTests(Workspace):
    def put_json(self, name, value):
        return self.put('.smart-test/' + name, json.dumps(value))

    def test_validates_traceability_fields(self):
        self.put_json('business-oracle.json', {'entries': [
            {'business_truth': True, 'source': 'docs/approval.md', 'claim': 'Rejected state is REJECTED'}]})
        self.put_json('test-plan.json', {'items': [{
            'id': 'ST-1', 'target': 'OrderService#reject', 'risk': 'HIGH', 'suite': 'unit',
            'required': True, 'assertions': ['state is REJECTED'],
            'oracle': {'business_truth': True, 'source': 'docs/approval.md', 'claim': 'Rejected state'}}]})
        self.put_json('status.json', {'status': 'READY', 'blocking_ids': []})
        result = validate(self.root, required=['business-oracle.json', 'test-plan.json', 'status.json'])
        self.assertEqual(result['status'], 'VALID')

    def test_rejects_untraceable_oracle_and_pass_with_blockers(self):
        self.put_json('business-oracle.json', {'entries': [{'business_truth': True}]})
        self.put_json('status.json', {'status': 'PASS', 'blocking_ids': ['DB-1']})
        result = validate(self.root, required=['business-oracle.json', 'status.json'])
        self.assertEqual(result['status'], 'INVALID')
        self.assertIn('BUSINESS_TRUTH_SOURCE_MISSING', {i['type'] for i in result['issues']})
        self.assertIn('PASS_WITH_BLOCKERS', {i['type'] for i in result['issues']})

    def test_rejects_business_truth_without_claim(self):
        self.put_json('business-oracle.json', {'entries': [
            {'business_truth': True, 'source': 'docs/approval.md'}]})
        result = validate(self.root, required=['business-oracle.json'])
        self.assertEqual(result['status'], 'INVALID')
        self.assertIn('BUSINESS_TRUTH_CLAIM_MISSING', {i['type'] for i in result['issues']})

    def test_rejects_incomplete_required_test_plan_item(self):
        self.put_json('test-plan.json', {'items': [{'required': True, 'id': 'ST-1'}]})
        result = validate(self.root, required=['test-plan.json'])
        self.assertEqual(result['status'], 'INVALID')
        kinds = {i['type'] for i in result['issues']}
        self.assertIn('REQUIRED_ITEM_TARGET_MISSING', kinds)
        self.assertIn('REQUIRED_ITEM_ORACLE_MISSING', kinds)

    def test_accepts_minimum_test_policy(self):
        self.put_json('test-policy.json', {
            'required_suites': ['unit'],
            'verification': {'required': True},
            'environment': {'database': 'isolated'},
            'coverage': {
                'mode': 'UNSPECIFIED', 'metric': 'LINE', 'threshold': None,
                'scope': {'type': 'REPOSITORY'}, 'baseline': None,
            },
            'production_code_modify': False,
        })
        result = validate(self.root, required=['test-policy.json'])
        self.assertEqual(result['status'], 'VALID')

    def test_rejects_malformed_test_policy(self):
        self.put_json('test-policy.json', {
            'required_suites': 'unit',
            'coverage': {'mode': 'FULL', 'threshold': 101},
            'production_code_modify': 'no',
        })
        result = validate(self.root, required=['test-policy.json'])
        self.assertEqual(result['status'], 'INVALID')
        kinds = {i['type'] for i in result['issues']}
        self.assertIn('REQUIRED_SUITES_INVALID', kinds)
        self.assertIn('COVERAGE_MODE_INVALID', kinds)
        self.assertIn('COVERAGE_THRESHOLD_INVALID', kinds)
        self.assertIn('PRODUCTION_CODE_MODIFY_INVALID', kinds)

    def test_blocked_status_with_blockers_is_valid(self):
        self.put_json('status.json', {'status': 'BLOCKED', 'blocking_ids': ['DB-1']})
        result = validate(self.root, required=['status.json'])
        self.assertEqual(result['status'], 'VALID')

    def test_pass_status_without_blockers_is_valid(self):
        self.put_json('status.json', {'status': 'PASS', 'blocking_ids': []})
        self.assertEqual(validate(self.root, ['status.json'])['status'], 'VALID')

    def test_pass_cannot_hide_blockers_behind_empty_blocking_ids(self):
        self.put_json('status.json', {'status': 'PASS', 'blocking_ids': [], 'blockers': ['DB-1']})
        self.assertEqual(validate(self.root, ['status.json'])['status'], 'INVALID')

    def test_each_required_plan_field_is_checked(self):
        item = {'id': 'ST-1', 'target': 'Payment#pay', 'risk': 'HIGH', 'suite': 'unit',
                'required': True, 'assertions': ['confirmed amount'],
                'oracle': {'business_truth': True, 'source': 'contract.md', 'claim': 'confirmed amount'}}
        for key in ('id', 'target', 'risk', 'suite', 'assertions', 'oracle'):
            with self.subTest(key=key):
                incomplete = copy.deepcopy(item)
                del incomplete[key]
                self.put_json('test-plan.json', {'items': [incomplete]})
                result = validate(self.root, ['test-plan.json'])
                self.assertEqual(result['status'], 'INVALID')
                self.assertIn('REQUIRED_ITEM_' + key.upper() + '_MISSING',
                              {i['type'] for i in result['issues']})

    def test_policy_rejects_invalid_shapes_and_field_types(self):
        invalid = [[], None, {}, {'hello': 'world'},
                   {'required_suites': [1]}, {'required_suites': [' ']},
                   {'verification': []}, {'environment': 'isolated'},
                   {'production_change_boundary': False}, {'coverage': []}]
        for field, values in {
            'mode': ['FULL', [], None], 'metric': ['COUNT', {}, None],
            'threshold': [-1, 101, True, '80', float('nan'), float('inf')],
            'scope': [[], 'repository'], 'baseline': [1, [], ' '],
        }.items():
            invalid.extend({'coverage': {field: value}} for value in values)
        for policy in invalid:
            with self.subTest(policy=policy):
                self.put_json('test-policy.json', policy)
                self.assertEqual(validate(self.root, ['test-policy.json'])['status'], 'INVALID')

    def test_policy_allows_optional_fields_and_coverage_boundaries(self):
        valid = [{'required_suites': ['unit', {'suite': 'integration'}]},
                 {'production_code_modify': False}, {'production_change_boundary': {}}]
        valid.extend({'coverage': {'mode': mode, 'metric': metric, 'threshold': threshold,
                                  **({'baseline': 'origin/main'} if mode in ('INCREMENTAL', 'BOTH') else {})}}
                     for mode in ('UNSPECIFIED', 'REPORT_ONLY', 'OVERALL', 'INCREMENTAL', 'BOTH')
                     for metric in ('LINE', 'BRANCH', 'INSTRUCTION', 'METHOD', 'CLASS')
                     for threshold in (None, 0, 80.5, 100))
        for policy in valid:
            with self.subTest(policy=policy):
                self.put_json('test-policy.json', policy)
                self.assertEqual(validate(self.root, ['test-policy.json'])['status'], 'VALID')

    def test_incremental_coverage_requires_an_explicit_baseline(self):
        for mode in ('INCREMENTAL', 'BOTH'):
            for baseline in (None, '', ' '):
                with self.subTest(mode=mode, baseline=baseline):
                    self.put_json('test-policy.json', {'coverage': {'mode': mode, 'threshold': 80, 'baseline': baseline}})
                    result = validate(self.root, ['test-policy.json'])
                    self.assertEqual(result['status'], 'INVALID')
                    self.assertIn('COVERAGE_BASELINE_REQUIRED', {i['type'] for i in result['issues']})
            self.put_json('test-policy.json', {'coverage': {'mode': mode, 'threshold': 80}})
            self.assertEqual(validate(self.root, ['test-policy.json'])['status'], 'INVALID')

    def test_coverage_supports_distinct_thresholds_without_accepting_bad_values(self):
        coverage = {'mode': 'BOTH', 'baseline': 'origin/main', 'threshold': {'overall': 75, 'incremental': 80}}
        self.put_json('test-policy.json', {'coverage': coverage})
        self.assertEqual(validate(self.root, ['test-policy.json'])['status'], 'VALID')
        for threshold in ({}, {'overall': 75}, {'overall': 75, 'incremental': True},
                          {'overall': -1, 'incremental': 80}, {'overall': 75, 'incremental': float('nan')},
                          {'overall': 75, 'incremental': 80, 'other': 70}):
            with self.subTest(threshold=threshold):
                self.put_json('test-policy.json', {'coverage': {**coverage, 'threshold': threshold}})
                self.assertEqual(validate(self.root, ['test-policy.json'])['status'], 'INVALID')

    def test_all_artifacts_require_object_roots(self):
        for name in ('business-oracle.json', 'test-plan.json', 'effective-context.json',
                     'test-policy.json', 'status.json'):
            with self.subTest(name=name):
                self.put_json(name, [])
                result = validate(self.root, [name])
                self.assertEqual(result['issues'][0]['type'], 'ROOT_OBJECT_REQUIRED')

    def test_validator_cli_reports_invalid_without_modifying_artifact(self):
        path = self.put_json('test-policy.json', {'coverage': {'mode': []}})
        before = path.read_bytes()
        result = subprocess.run([sys.executable, str(SCRIPTS / 'validate_artifacts.py'),
                                 '--repo', str(self.root), '--require', 'test-policy.json'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['status'], 'INVALID')
        self.assertEqual(before, path.read_bytes())

    def test_rejects_invalid_json(self):
        self.put('.smart-test/status.json', '{not-json')
        result = validate(self.root, required=['status.json'])
        self.assertEqual(result['status'], 'INVALID')
        self.assertEqual(result['issues'][0]['type'], 'INVALID_JSON')

    def test_example_artifact_is_not_valid_evidence(self):
        self.put_json('test-policy.json', {'example_only': True, 'required_suites': ['unit']})
        result = validate(self.root, required=['test-policy.json'])
        self.assertEqual(result['status'], 'INVALID')
        self.assertIn('EXAMPLE_ARTIFACT', {i['type'] for i in result['issues']})

    def test_malformed_plan_shapes_are_rejected(self):
        cases = [
            {'items': ['malformed required item']},
            {'items': ['bad', {'required': False}]},
            {'test_plan': 'oops'},
            {},
        ]
        for plan in cases:
            with self.subTest(plan=plan):
                self.put_json('test-plan.json', plan)
                result = validate(self.root, required=['test-plan.json'])
                self.assertEqual(result['status'], 'INVALID')

    def test_missing_and_malformed_plan_items_report_distinct_issues(self):
        self.put_json('test-plan.json', {'items': ['bad']})
        kinds = {i['type'] for i in validate(self.root, ['test-plan.json'])['issues']}
        self.assertEqual(kinds, {'TEST_PLAN_ITEM_INVALID'})
        self.put_json('test-plan.json', {})
        kinds = {i['type'] for i in validate(self.root, ['test-plan.json'])['issues']}
        self.assertEqual(kinds, {'TEST_PLAN_ITEMS_MISSING'})

    def test_malformed_oracle_entries_are_rejected(self):
        self.put_json('business-oracle.json', {'entries': ['not-an-object', {'business_truth': True}]})
        result = validate(self.root, required=['business-oracle.json'])
        self.assertEqual(result['status'], 'INVALID')
        kinds = {i['type'] for i in result['issues']}
        self.assertIn('ORACLE_ENTRY_INVALID', kinds)
        self.assertIn('BUSINESS_TRUTH_SOURCE_MISSING', kinds)

    def test_missing_required_artifact_is_invalid(self):
        result = validate(self.root, required=['test-plan.json'])
        self.assertEqual(result['status'], 'INVALID')
        self.assertEqual(result['issues'][0]['type'], 'MISSING_REQUIRED_ARTIFACT')

if __name__ == '__main__':
    unittest.main()
