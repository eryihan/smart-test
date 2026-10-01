"""Shared, stable names used by the smart_test workflow and reports.

Keeping these names in one small module prevents the CLI helpers and feedback
exporter from silently drifting apart. The values are intentionally plain
Python objects so the skill remains Python 3.9+ and dependency-free.
"""

WORKFLOWS = ('help', 'init', 'scan', 'changes', 'check', 'pipeline', 'status', 'update', 'uninstall')

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
