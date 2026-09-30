"""Shared, stable names used by the smart_test workflow and reports.

Keeping these names in one small module prevents the CLI helpers and feedback
exporter from silently drifting apart. The values are intentionally plain
Python objects so the skill remains Python 3.9+ and dependency-free.
"""

WORKFLOWS = ('help', 'init', 'scan', 'changes', 'check', 'pipeline', 'update')

HOSTS = frozenset({'codex', 'claude-code', 'other', 'unknown'})

FEEDBACK_TYPES = frozenset({
    'FALSE_PASS', 'FALSE_BLOCKED', 'WRONG_STRATEGY', 'WRONG_SCOPE',
    'ORACLE_ERROR', 'DIRECTIVE_IGNORED', 'MISSING_CAPABILITY',
    'UX_CONFUSION', 'PERFORMANCE', 'OTHER',
})

STATUSES = frozenset({
    'NOT_STARTED', 'PROPOSED', 'READY', 'PARTIAL', 'BLOCKED', 'FAILED',
    'PASS', 'STALE', 'NOT_VERIFIED', 'UNKNOWN', 'NOT_APPLICABLE',
    'NOT_RUN', 'EVIDENCE_PASS', 'VALID', 'INVALID', 'DISCOVERED',
})

SUITES = frozenset({'unit', 'slice', 'integration', 'contract', 'e2e', 'critical-flow'})

SIGNALS = frozenset({
    'spring-boot', 'mybatis', 'jpa', 'mysql', 'postgresql', 'h2', 'redis',
    'kafka', 'rocketmq', 'rabbitmq', 'flyway', 'liquibase', 'security',
    'http-client', 'rpc', 'junit5', 'junit4', 'testng', 'mockito', 'assertj',
    'spring-test', 'testcontainers', 'jacoco', 'pact', 'pitest', 'surefire',
    'failsafe', 'transaction', 'authorization', 'concurrency',
    'sql-mapping', 'database-migration',
})

# All artifacts that may be exported as sanitized feedback. The validator has
# a narrower set because project-profile is intentionally agent-reviewed.
ARTIFACTS = (
    'project-profile.json', 'effective-context.json', 'business-oracle.json',
    'test-policy.json', 'test-plan.json', 'status.json',
)

VALIDATED_ARTIFACTS = (
    'business-oracle.json', 'effective-context.json', 'test-policy.json',
    'test-plan.json', 'status.json',
)
