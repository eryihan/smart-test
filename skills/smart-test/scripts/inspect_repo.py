#!/usr/bin/env python3
"""Read-only repository evidence; deliberately not a Java/Gradle semantic parser."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
from common import EXCLUDED, digest, emit, git, relative_file, safe_name

SIGNALS = {
    'spring-boot': r'spring-boot|org\.springframework\.boot',
    'mybatis': r'mybatis', 'jpa': r'starter-data-jpa|hibernate-core',
    'mysql': r'mysql-connector|jdbc:mysql:',
    'postgresql': r'org\.postgresql|<artifactId>postgresql</artifactId>|jdbc:postgresql:',
    'h2': r'com\.h2database|jdbc:h2:', 'redis': r'starter-data-redis|jedis|lettuce',
    'kafka': r'spring-kafka|kafka-clients', 'rocketmq': r'rocketmq',
    'rabbitmq': r'starter-amqp|rabbitmq', 'flyway': r'flyway', 'liquibase': r'liquibase',
    'security': r'starter-security|spring-security',
    'http-client': r'openfeign|okhttp|httpclient|WebClient|RestTemplate',
    'rpc': r'dubbo|grpc', 'junit5': r'junit-jupiter|org\.junit\.jupiter',
    'junit4': r'<artifactId>junit</artifactId>|junit:junit|org\.junit\.Test',
    'testng': r'testng', 'mockito': r'mockito', 'assertj': r'assertj',
    'spring-test': r'starter-test|spring-test', 'testcontainers': r'testcontainers',
    'jacoco': r'jacoco', 'pact': r'pact-jvm|au\.com\.dius\.pact',
    'pitest': r'pitest', 'surefire': r'maven-surefire-plugin',
    'failsafe': r'maven-failsafe-plugin',
}
BUILD_NAMES = {'pom.xml', 'build.gradle', 'build.gradle.kts', 'settings.gradle',
               'settings.gradle.kts', 'gradle.properties', 'libs.versions.toml'}


def inventory(root):
    warnings = []
    try:
        top = Path(os.fsdecode(git(root, 'rev-parse', '--show-toplevel')).strip()).resolve()
        if top != root:
            raise ValueError('pass the Git repository root with --repo')
        names = [os.fsdecode(n) for n in git(root, 'ls-files', '-z', '--cached',
                 '--others', '--exclude-standard').split(b'\0') if n]
        is_git = True
    except (ValueError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        if 'pass the Git' in str(exc):
            raise
        is_git = False
        warnings.append('No Git inventory; filesystem scan may include untracked local files.')
        names = []
        for directory, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED
                             and not Path(directory, d).is_symlink())
            names.extend(str(Path(directory, n).relative_to(root)) for n in files)
    result = []
    for name in sorted(set(names)):
        if not safe_name(name):
            continue
        try:
            path = relative_file(root, name)
        except ValueError:
            warnings.append('Skipped symlink: ' + name)
            continue
        if path.is_file():
            result.append(name)
    return result, is_git, warnings


def changes(root, is_git, staged=False, base=None):
    if not is_git:
        if staged or base:
            raise ValueError('Git diff mode requires a Git repository')
        return {'available': False, 'confidence': 'LOW', 'files': []}
    try:
        head = os.fsdecode(git(root, 'rev-parse', '--verify', 'HEAD')).strip()
    except ValueError:
        head = None
    merge_base = None
    if base:
        ref = os.fsdecode(git(root, 'rev-parse', '--verify', '--end-of-options',
                             base + '^{commit}')).strip()
        merge_base = os.fsdecode(git(root, 'merge-base', 'HEAD', ref)).strip()
        args = ['diff', '--name-status', '-z', '--no-renames', merge_base, '--']
    elif staged:
        args = ['diff', '--cached', '--name-status', '-z', '--no-renames', '--']
    elif head:
        args = ['diff', '--name-status', '-z', '--no-renames', 'HEAD', '--']
    else:
        args = None
    found = {}
    if args:
        parts = git(root, *args).split(b'\0')
        for i in range(0, len(parts) - 1, 2):
            found[os.fsdecode(parts[i + 1])] = os.fsdecode(parts[i])
    else:
        for part in git(root, 'ls-files', '-z', '--cached').split(b'\0'):
            if part:
                found[os.fsdecode(part)] = 'A'
    if not staged:
        for part in git(root, 'ls-files', '-z', '--others', '--exclude-standard').split(b'\0'):
            if part:
                found[os.fsdecode(part)] = '?'
    return {'available': True, 'head': head, 'base': base, 'merge_base': merge_base,
            'mode': 'staged' if staged else ('base-to-worktree' if base else 'worktree'),
            'files': [{'path': n, 'status': s} for n, s in sorted(found.items())
                      if safe_name(n)],
            'renames': 'reported as delete + add; inspect both sides'}


def pom_info(path):
    tree = ET.fromstring(path.read_bytes())
    for element in tree.iter():
        element.tag = element.tag.rsplit('}', 1)[-1]
    value = lambda key: tree.findtext(key)
    return {
        'artifact': value('artifactId'),
        'group': value('groupId') or value('parent/groupId'),
        'version': value('version') or value('parent/version'),
        'parent': {'artifact': value('parent/artifactId'), 'version': value('parent/version')},
        'java': value('properties/java.version') or value('properties/maven.compiler.release')
                or value('properties/maven.compiler.source'),
        'declared_modules': [n.text for n in tree.findall('modules/module') if n.text],
        'dependencies': [{'group': d.findtext('groupId'), 'artifact': d.findtext('artifactId')}
                         for d in tree.findall('dependencies/dependency')],
    }


def gradle_edges(root, modules, settings, warnings):
    """Resolve literal root-settings paths only; dynamic Gradle stays unresolved."""
    consumers = [m for m in modules if m.get('project_refs')]
    if not consumers:
        return []
    if len(settings) != 1:
        warnings.append('Unresolved Gradle project graph: one root settings file is required for literal hints.')
        return []
    settings_path, text = settings[0]
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    paths = {':': '.'}
    for match in re.finditer(r'(?m)^\s*include\b\s*(?:\(([^)]*)\)|([^\n]+))', text):
        expression = match.group(1) if match.group(1) is not None else match.group(2)
        literals = re.findall(r'[\'"]([^\'"]+)[\'"]', expression)
        remainder = re.sub(r'[\'"][^\'"]+[\'"]|[\s,;]', '', expression)
        if remainder or not literals:
            warnings.append('Unresolved Gradle include expression: ' + settings_path)
            continue
        for project in literals:
            identity = ':' + project.lstrip(':')
            paths[identity] = project.lstrip(':').replace(':', '/')
    overrides = list(re.finditer(
        r'project\s*\(\s*[\'"](:[^\'"]+)[\'"]\s*\)\s*\.projectDir\s*=\s*file\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)', text))
    if len(re.findall(r'\.projectDir\b', text)) != len(overrides):
        warnings.append('Unresolved Gradle projectDir expression: ' + settings_path)
        return []  # Do not attach a default-directory edge when a remap is unknown.
    for match in overrides:
        if match.group(1) in paths:
            paths[match.group(1)] = match.group(2)
    by_directory = {}
    for module in modules:
        if module['tool'] == 'gradle':
            by_directory.setdefault(module['directory'], []).append(module)
    providers = {}
    for identity, directory in paths.items():
        try:
            if '$' in directory:
                raise ValueError('dynamic path')
            path = root if directory == '.' else relative_file(root, directory)
            candidates = by_directory.get(str(path.relative_to(root)), [])
            if len(candidates) == 1:
                providers[identity] = candidates[0]
        except ValueError:
            warnings.append('Unresolved Gradle project directory: ' + identity)
    edges = []
    for consumer in consumers:
        for reference in consumer['project_refs']:
            provider = providers.get(reference)
            if provider is None:
                warnings.append('Unresolved Gradle project ' + reference + ': ' + consumer['path'])
            elif provider['directory'] != consumer['directory']:
                edges.append({'consumer': consumer['directory'], 'provider': provider['directory'],
                              'confidence': 'MEDIUM', 'source': consumer['path']})
    return edges


def inspect(root, staged=False, base=None, limit=20000, paths=None):
    root = Path(root).resolve()
    names, is_git, warnings = inventory(root)
    scopes = []
    for name in paths or []:
        path = root if name == '.' else relative_file(root, name)
        if not path.exists():
            raise ValueError('query scope does not exist')
        scopes.append(path.relative_to(root).as_posix())
    if scopes and '.' not in scopes:
        # Keep build declarations for consumer hints; source reads stay scoped.
        names = [n for n in names if Path(n).name in BUILD_NAMES or
                 any(n == scope or n.startswith(scope + '/') for scope in scopes)]
    truncated = len(names) > limit
    if truncated:
        warnings.append('File limit reached; broaden scope manually. Inventory is incomplete.')
        names = names[:limit]
    found = {name: [] for name in SIGNALS}
    fingerprints, builds, modules, sources, tests, docs, ci, risks = {}, [], [], [], [], [], [], []
    gradle_settings = []
    for name in names:
        path = root / name
        is_build = path.name in BUILD_NAMES
        is_java = path.suffix == '.java'
        is_doc = (path.suffix in {'.md', '.adoc', '.proto', '.graphql'}
                  or 'openapi' in path.name.lower() or 'swagger' in path.name.lower())
        is_migration = (path.suffix == '.sql' or 'db/migration/' in name
                        or 'db/changelog/' in name)
        is_config = path.name.startswith('application') and path.suffix in {'.yml', '.yaml', '.properties'}
        is_ci = name.startswith('.github/workflows/') or path.name in {'.gitlab-ci.yml', 'Jenkinsfile'}
        is_xml = path.suffix.lower() == '.xml'
        if is_java:
            (tests if '/src/test/' in '/' + name or '/src/integrationTest/' in '/' + name else sources).append(name)
        if is_doc:
            docs.append(name)
        if is_ci:
            ci.append(name)
        selected = is_build or is_java or is_doc or is_migration or is_config or is_ci
        if not (selected or is_xml):
            continue
        if path.stat().st_size > 2_000_000:
            warnings.append('Skipped large file: ' + name)
            continue
        content = path.read_text(encoding='utf-8', errors='replace')
        is_mapper = is_xml and bool(re.search(r'<mapper(?:\s|>)', re.sub(r'<!--.*?-->', '', content, flags=re.S)))
        if not selected and not is_mapper:
            continue
        fingerprints[name] = digest(path)
        if is_mapper:
            found['mybatis'].append(name)
        if is_build or is_java or is_config:
            for signal, pattern in SIGNALS.items():
                if re.search(pattern, content, re.I):
                    found[signal].append(name)
        if is_build:
            builds.append(name)
            if path.name == 'pom.xml':
                try:
                    info = pom_info(path)
                    info.update(path=name, directory=str(path.parent.relative_to(root)), tool='maven')
                    modules.append(info)
                except ET.ParseError:
                    warnings.append('Malformed pom.xml: ' + name)
            elif path.name in {'build.gradle', 'build.gradle.kts'}:
                modules.append({'path': name, 'directory': str(path.parent.relative_to(root)),
                                'tool': 'gradle', 'project_refs': sorted(set(re.findall(
                                    r'project\s*\(\s*(?:path\s*[:=]\s*)?[\'"](:[^\'"]*)', content)))})
            elif name in {'settings.gradle', 'settings.gradle.kts'}:
                gradle_settings.append((name, content))
        indicators = []
        if is_migration:
            indicators.append('database-migration')
        if is_mapper:
            indicators.append('sql-mapping')
        if is_java and name in sources:
            for label, pattern in {'transaction': r'@Transactional', 'authorization': r'@PreAuthorize|@Secured',
                                   'concurrency': r'synchronized|ReentrantLock|compareAndSet',
                                   'sql-mapping': r'@Mapper|@Query|@Select'}.items():
                if re.search(pattern, content):
                    indicators.append(label)
        if indicators:
            risks.append({'path': name, 'indicators': indicators})
    edges = []
    for consumer in modules:
        for dep in consumer.get('dependencies', []):
            for provider in modules:
                if consumer is not provider and dep['group'] and dep['group'] == provider.get('group') and dep['artifact'] == provider.get('artifact'):
                    edges.append({'consumer': consumer['directory'], 'provider': provider['directory'],
                                  'confidence': 'MEDIUM', 'source': consumer['path']})
    edges.extend(gradle_edges(root, modules, gradle_settings, warnings))
    diff = changes(root, is_git, staged, base)
    dirs = sorted((m['directory'] for m in modules), key=len, reverse=True)
    impacted = set()
    for item in diff['files']:
        module = next((d for d in dirs if d == '.' or item['path'].startswith(d + '/')), None)
        item['module'] = module
        if module is not None:
            impacted.add(module)
    while True:
        broadened = impacted | {e['consumer'] for e in edges if e['provider'] in impacted}
        if broadened == impacted:
            break
        impacted = broadened
    diff['impacted_modules_hint'] = sorted(impacted)
    diff['confidence'] = 'LOW'
    diff['fallback'] = 'Run impacted modules and consumers; full verification if graph or dynamic wiring is unresolved.'
    return {'schema_version': 1, 'kind': 'repository-evidence', 'status': 'DISCOVERED',
            'query_scope': scopes or ['.'],
            'root': str(root), 'build_files': builds, 'modules': modules, 'module_edges': edges,
            'signals': {k: v for k, v in found.items() if v}, 'production_sources': sources,
            'test_sources': tests, 'oracle_candidates': docs, 'ci_files': ci,
            'risk_indicators': risks, 'fingerprints': fingerprints, 'change': diff,
            'environment': {'executables': {n: bool(shutil.which(n)) for n in ('java', 'mvn', 'gradle', 'docker')},
                            'wrappers': [n for n in ('mvnw', 'gradlew', 'mvnw.cmd', 'gradlew.bat') if (root / n).is_file()],
                            'docker_daemon': 'UNKNOWN', 'network': 'UNKNOWN', 'external_test_services': 'UNKNOWN'},
            'incomplete': truncated or bool(warnings), 'warnings': warnings,
            'limitations': ['Static candidates, not verified runtime dependencies or business truth.',
                           'Maven inheritance/profiles/properties and Gradle code are not evaluated.',
                           'Gradle edges only resolve literal root-settings includes and file projectDir overrides; other layouts require manual review.',
                           'No complete symbol/call graph; Agent must inspect diff and broaden tests.',
                           'No source/config values or secret-bearing log content are emitted.']}


def query_result(data, query):
    shared = {key: data[key] for key in ('schema_version', 'query_scope', 'incomplete', 'warnings', 'limitations')}
    if query == 'changes':
        return dict(shared, change=data['change'])
    if query == 'build':
        return dict(shared, build_files=data['build_files'], modules=data['modules'],
                    module_edges=data['module_edges'], environment=data['environment'])
    if query == 'tests':
        paths = data['test_sources']
        return dict(shared, test_source_count=len(paths), test_sources=paths[:100],
                    paths_omitted=max(0, len(paths) - 100))
    return dict(shared, build_files=data['build_files'],
                module_count=len(data['modules']), source_count=len(data['production_sources']),
                test_source_count=len(data['test_sources']), ci_files=data['ci_files'],
                signals={key: len(value) for key, value in data['signals'].items()},
                environment=data['environment'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--staged', action='store_true')
    selection.add_argument('--base')
    parser.add_argument('--max-files', type=int, default=20000)
    parser.add_argument('--path', action='append', help='limit source reads to this path; repeat as needed')
    parser.add_argument('--query', choices=['overview', 'changes', 'build', 'tests'], default='overview')
    parser.add_argument('--details', action='store_true', help='detailed static evidence output including fingerprints')
    args = parser.parse_args()
    try:
        if not args.repo.is_dir() or args.max_files < 1:
            raise ValueError('repository must exist and max-files must be positive')
        result = inspect(args.repo.resolve(), args.staged, args.base, args.max_files, args.path)
        emit(result if args.details else query_result(result, args.query))
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        emit({'error': str(exc)})
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
