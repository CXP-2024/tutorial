#!/usr/bin/env python3
"""Offline preflight, one guarded Volc submission, and read-only recovery.

The tool submits an already reviewed configuration unchanged. It never exports
credentials, grants permissions, modifies mounts, or automatically retries create.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile

import yaml

SELF = Path(__file__).resolve()
STATUSES = 'Queue,Staging,Running,Killing,Success,Failed,Killed,Initialized'
SECRET_KEY = re.compile(r'TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH|(?:^|_)(?:AK|SK|API_KEY|ACCESS_KEY)(?:_|$)', re.I)


class Stop(Exception):
    def __init__(self, code, diagnostic=None):
        super().__init__(code)
        self.code, self.diagnostic = code, diagnostic


def require(ok, code):
    if not ok:
        raise Stop(code)


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def pin(path):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    return {'path': str(path), 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def check(record):
    require(pin(record['path']) == record, 'input_changed')


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value, *, exclusive=False):
    path = Path(path)
    raw = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode()
    if exclusive:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    else:
        fd, temp = tempfile.mkstemp(prefix='.training-state-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp): os.unlink(temp)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def credential_values(env, script=None):
    """Inspect only existing configured sources; never execute a startup script."""
    for names, source in ((('VOLC_ACCESS_KEY_ID', 'VOLC_SECRET_ACCESS_KEY'), 'existing_VOLC_environment'),
                          (('TOS_AK', 'TOS_SK'), 'existing_TOS_environment')):
        if all(env.get(name) for name in names):
            return (env[names[0]], env[names[1]]), {'source': source, 'key_names': list(names), 'caller_identity': 'unknown'}
    if script:
        text = Path(script).read_text()
        values = []
        for name in ('TOS_AK', 'TOS_SK'):
            matches = re.findall(r'(?m)^\s*(?:export\s+)?' + name + r'\s*=\s*(.*)$', text)
            require(bool(matches), 'credential_literal_missing')
            tokens = shlex.split(matches[-1], comments=True)
            require(len(tokens) == 1 and tokens[0] and not any(c in tokens[0] for c in ('$','`')), 'credential_must_be_literal')
            values.append(tokens[0])
        return tuple(values), {'source': 'explicit_script_literals_without_execution',
                               'script': pin(script), 'key_names': ['TOS_AK', 'TOS_SK'], 'caller_identity': 'unknown'}
    return None, {'source': 'existing_cli_configuration_uninspected', 'caller_identity': 'unknown'}


@contextmanager
def cli_environment(region, script=None):
    env = dict(os.environ)
    values, basis = credential_values(env, script)
    basis.update(region=region, credential_values_persisted=False, start_script_executed=False)
    if values:
        # Some CLI builds return before inspecting env if the config file is absent.
        with tempfile.TemporaryDirectory(prefix='volc-auth-') as directory:
            config = Path(directory) / 'config.ini'
            config.write_text('[default]\nregion = ' + region + '\n'); config.chmod(0o600)
            env.update(VOLC_CONFIG_FILE=str(config), VOLC_ACCESS_KEY_ID=values[0],
                       VOLC_SECRET_ACCESS_KEY=values[1], VOLC_REGION=region)
            yield env, basis
    else:
        env['VOLC_REGION'] = region
        yield env, basis


def strings(value):
    if isinstance(value, str): return [value] if len(value) >= 8 else []
    if isinstance(value, dict): return [s for v in value.values() for s in strings(v)]
    if isinstance(value, list): return [s for v in value for s in strings(v)]
    return []


def short_secrets(value, sensitive=False):
    if isinstance(value, str): return [value] if sensitive and value else []
    if isinstance(value, dict):
        return [s for key, child in value.items() for s in short_secrets(child, sensitive or bool(SECRET_KEY.search(str(key))))]
    if isinstance(value, list): return [s for child in value for s in short_secrets(child, sensitive)]
    return []


def safe_paths(config):
    result = set()
    for row in config.get('Storages', []):
        for key in ('MountPath', 'SubPath'):
            value = row.get(key)
            if isinstance(value, str) and '/' in value and re.fullmatch(r'[A-Za-z0-9_./-]+', value):
                result.add(value)
    return result


def diagnostic(result, env, config):
    """Bounded reasons/codes only: no raw output, YAML, env, or exception text."""
    from urllib.parse import quote, quote_plus
    allowed = safe_paths(config)
    secrets = set(strings(config)) - allowed
    secrets.update(short_secrets(config))
    secrets.update(v for k, v in env.items() if SECRET_KEY.search(k) and v)
    variants = {s for v in secrets for s in (v, json.dumps(v)[1:-1], quote(v, safe=''), quote_plus(v)) if s}
    blocked = re.compile(r'\b(envs?|entrypoint|signature|authorization|password|secret|token|credential|access[_ -]?key|api[_ -]?key|storages)\b', re.I)
    code_re = re.compile(r'\b(?:error[_ ]?code|code)["\x27]?\s*[:=]\s*["\x27]?((?:Invalid|AccessDenied|Unauthorized|Forbidden|Resource|Limit|Quota|Internal|Service|Request|Operation|Parameter|NotFound|Conflict|Missing|Unsupported|Expired|Failed|Account|Permission|Authentication|BadRequest|TooManyRequests)[A-Za-z0-9_.-]{0,100})\b', re.I)
    codes, reasons = [], []
    for stream in (result.stderr or '', result.stdout or ''):
        if len(stream) > 1_000_000: continue
        for raw in stream.splitlines():
            line = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', raw).strip()
            for secret in sorted(variants, key=len, reverse=True): line = line.replace(secret, '[REDACTED]')
            line = re.sub(r'https?://[^\s"\x27<>]+', '[URL]', line, flags=re.I)
            if any(ord(c) < 32 for c in line): continue
            found = [c for c in code_re.findall(line) if not c.endswith(('.', '-', '_'))]
            for code in found:
                if code not in codes: codes.append(code)
            if len(raw) > 600 or blocked.search(line): continue
            protected = []
            for value in sorted(set(found) | allowed, key=len, reverse=True):
                if value in line:
                    token = f'[SAFE_{len(protected)}]'
                    line = line.replace(value, token); protected.append((token, value))
            line = re.sub(r'\b(?:glpat|glft)-\S+|\b[A-Za-z0-9_+/=-]{24,}\b', '[REDACTED]', line)
            for token, value in protected: line = line.replace(token, value)
            if len(line) <= 400 and re.search(r'error|fail|invalid|denied|not authorized|unsupported|quota|forbidden|panic|timeout|错误|失败|拒绝|无效|不支持|缺少|超过|权限|不存在', line, re.I):
                if line not in reasons: reasons.append(line)
    return {'returncode': result.returncode, 'codes': codes[:4], 'reasons': reasons[:3], 'raw_output_persisted': False}


def invoke(cli, args, env, config, timeout=120):
    try:
        result = subprocess.run([cli, 'ml_task', *args], env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise Stop('cli_timeout') from None
    except OSError:
        raise Stop('cli_launch_failed') from None
    if result.returncode:
        raise Stop('cli_nonzero_exit', diagnostic(result, env, config))
    return result.stdout


def payload(raw):
    decoder = json.JSONDecoder(); found = []; consumed = -1
    for match in re.finditer(r'(?m)^[ \t]*[\[{]', raw):
        start = match.end() - 1
        if start < consumed: continue
        try: value, end = decoder.raw_decode(raw, start)
        except ValueError: continue
        if isinstance(value, (dict, list)): found.append(value); consumed = end
    require(len(found) == 1, 'ambiguous_or_missing_json')
    return found[0]


def supported_cli(requested):
    candidates = [requested] if requested else [shutil.which('volc'), shutil.which('mlp')]
    if not requested and candidates[0]: candidates.append(str(Path(candidates[0]).parent / 'mlp'))
    for candidate in dict.fromkeys(c for c in candidates if c):
        executable = Path(shutil.which(candidate) or candidate)
        if not executable.is_file(): continue
        checks = []
        for sub, flags in [('submit', ['--conf', '--task_name', '--output']),
                           ('list', ['--status', '--name', '--limit', '--offset', '--output']),
                           ('get', ['--id', '--output'])]:
            try:
                result = subprocess.run([str(executable), 'ml_task', sub, '--help'],
                                        capture_output=True, text=True, timeout=15, check=False)
            except (OSError, subprocess.TimeoutExpired): break
            if result.returncode or not all(flag in result.stdout for flag in flags): break
            checks.append({'subcommand': sub, 'required_flags': flags,
                           'help_sha256': hashlib.sha256(result.stdout.encode()).hexdigest()})
        if len(checks) == 3: return str(executable.resolve()), checks
    raise Stop('cli_subcommands_not_supported')


def check_dependencies(config, requirements):
    mounts = config.get('Storages', [])
    require(isinstance(mounts, list), 'storages_not_a_list')
    roots = []
    for row in mounts:
        path = row.get('MountPath', '')
        require(isinstance(path, str) and Path(path).is_absolute() and '..' not in Path(path).parts, 'invalid_mount_path')
        require('ReadOnly' not in row or isinstance(row['ReadOnly'], bool), 'readonly_must_be_boolean')
        roots.append(Path(path))
    require(len(roots) == len(set(roots)), 'duplicate_mount_path')
    entries = requirements.get('dependencies')
    require(isinstance(entries, list) and entries, 'dependency_inventory_required')
    used, checked = set(), []
    for item in entries:
        path = Path(item['path'])
        require(path.is_absolute() and '..' not in path.parts and item['access'] in ('read', 'write'), 'invalid_dependency')
        candidates = [(i, root) for i, root in enumerate(roots) if path.is_relative_to(root)]
        mount_index = max(candidates, key=lambda pair: len(pair[1].parts))[0] if candidates else None
        local = item.get('storage') == 'container_local'
        require(mount_index is not None or local, 'dependency_without_mount')
        if mount_index is not None:
            used.add(mount_index)
            require(item['access'] != 'write' or not mounts[mount_index].get('ReadOnly', False), 'write_dependency_on_readonly_mount')
        probe = path
        if item['access'] == 'write':
            while not probe.exists() and probe != probe.parent: probe = probe.parent
        require(probe.exists() and os.access(probe, os.R_OK if item['access'] == 'read' else os.W_OK), 'local_dependency_unavailable')
        checked.append({'role': item['role'], 'path': str(path), 'access': item['access'],
                        'mount_index': mount_index, 'container_local': local, 'local_access_checked': True})
    unused = sorted(set(range(len(mounts))) - used)
    if requirements.get('minimum_mount_scope') is True:
        require(not unused, 'declared_minimum_scope_has_unused_mounts')
    summaries = [{k: row[k] for k in ('Type', 'MountPath', 'SubPath', 'VepfsId', 'NasId', 'ReadOnly') if k in row} for row in mounts]
    return {'dependencies': checked, 'mounts': summaries,
            'unused_mount_indices': unused,
            'minimum_mount_scope': requirements.get('minimum_mount_scope') is True,
            'platform_mount_authorization_verified': False, 'future_task_uid_access_verified': False}


def check_training_values(config, task, exp_name, card):
    tokens = shlex.split(config['Entrypoint'], comments=True)
    positions = [i for i, token in enumerate(tokens) if token.endswith('scripts/run/finetune.sh')]
    require(len(positions) == 1 and positions[0] + 1 < len(tokens) and tokens[positions[0] + 1] == task, 'hydra_task_mismatch')
    for key, expected in [('exp_name', exp_name), ('edp.card', card)]:
        values = [token.split('=', 1)[1] for token in tokens if token.lstrip('+').startswith(key + '=')]
        require(values == [expected], 'training_override_mismatch')


def exact_matches(plan, env, config):
    seen, matches = {}, {}
    for offset in range(0, 10000, 100):
        rows = payload(invoke(plan['cli']['path'], ['list', '--status', plan['statuses'], '--name', plan['name'],
            '--limit', '100', '--offset', str(offset), '--output', 'json'], env, config))
        require(isinstance(rows, list) and len(rows) <= 100, 'list_schema_mismatch')
        added = 0
        for row in rows:
            require(isinstance(row, dict) and re.fullmatch(r't-[A-Za-z0-9-]+', str(row.get('JobId', '')))
                    and isinstance(row.get('JobName'), str), 'list_identity_missing')
            identity = row['JobId']
            if identity in seen: require(seen[identity] == row['JobName'], 'list_identity_changed')
            else: added += 1; seen[identity] = row['JobName']
            if row['JobName'] == plan['name']:
                matches[identity] = {key: row[key] for key in ('JobId', 'JobName', 'Status') if key in row}
        if len(rows) < 100: return list(matches.values())
        require(added > 0, 'pagination_did_not_advance')
    raise Stop('pagination_limit_reached')


def verify_plan(path, *, historical=False):
    plan = read(path)
    require(plan['kind'] == 'volc_training_submission_plan' and plan['plan_sha256'] == digest({k:v for k,v in plan.items() if k != 'plan_sha256'}), 'plan_digest_mismatch')
    require(set(STATUSES.split(',')) <= set(plan.get('statuses', '').split(',')), 'all_statuses_required')
    for label, record in plan['inputs'].items():
        if not historical or label == 'tool': check(record)
    check(plan['cli']); require(plan['inputs']['tool'] == pin(SELF), 'tool_version_changed')
    config = ({'Storages': plan['dependencies']['mounts']} if historical else
              yaml.safe_load(Path(plan['inputs']['config']['path']).read_text()))
    return plan, config


def claim_path(plan):
    return Path(plan['journal']) / (digest([plan['region'], plan['name']])[:24] + '.claim.json')


@contextmanager
def claim_lock(plan):
    path = claim_path(plan).with_suffix('.lock')
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        require(os.fstat(fd).st_uid == os.getuid() and not os.fstat(fd).st_mode & 0o077, 'unsafe_claim_lock')
        try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise Stop('same_name_operation_in_progress') from None
        yield
    finally: os.close(fd)


def validate_recovery(plan, claim):
    record = plan['inputs'].get('recovery')
    require(record is not None, 'prior_intent_requires_readonly_recovery')
    check(record); proof = read(record['path'])
    require(proof.get('kind') == 'volc_training_readonly_recovery' and proof.get('exact_matches') == []
            and proof.get('output_exists') is False and proof.get('task_mutations') is False
            and proof.get('name') == plan['name'] and proof.get('region') == plan['region']
            and proof.get('statuses') == plan['statuses'] and proof.get('claim') == pin(claim), 'recovery_does_not_resolve_current_intent')
    check(proof['intent']); old = read(proof['intent']['path'])
    require(read(claim)['intent'] == proof['intent']['path'], 'recovery_intent_not_current_claim')
    require(old['plan_identity'] == [plan['region'], plan['name'], plan['source_id']] and not old.get('JobId'), 'recovery_identity_changed')
    if old['status'] == 'blocked_minimum_mount_acl':
        authorization = read(plan['inputs']['authorization']['path'])
        require(authorization.get('access_restored') is True and authorization.get('access_restored_basis'), 'minimum_mount_acl_needs_external_resolution')


def preflight(args):
    inputs = {label: pin(path) for label, path in [('tool', SELF), ('config', args.config),
              ('authorization', args.authorization), ('requirements', args.requirements)]}
    if args.credential_script: inputs['credential_script'] = pin(args.credential_script)
    if getattr(args, 'entrypoint_file', None): inputs['entrypoint_file'] = pin(args.entrypoint_file)
    if args.recovery: inputs['recovery'] = pin(args.recovery)
    require(re.fullmatch(r'[A-Za-z0-9-]+', args.region), 'invalid_region')
    require(re.fullmatch(r'[A-Za-z0-9_.-]+', args.name) and len(args.name) <= 200, 'invalid_task_name')
    require(re.fullmatch(r't-[A-Za-z0-9-]+', args.source_id), 'invalid_source_id')
    require(re.fullmatch(r'[A-Za-z][A-Za-z0-9]*(?:,[A-Za-z][A-Za-z0-9]*)*', args.statuses)
            and len(args.statuses.split(',')) == len(set(args.statuses.split(','))), 'invalid_status_selection')
    require(set(STATUSES.split(',')) <= set(args.statuses.split(',')), 'all_statuses_required')
    require(not os.stat(args.config).st_mode & 0o077, 'submission_config_must_be_private')
    config = yaml.safe_load(args.config.read_text())
    require(isinstance(config, dict) and not any(re.search(r'\[redacted\]|<redacted>', s, re.I) for s in strings(config)), 'redacted_or_invalid_config')
    require(config.get('TaskName', args.name) == args.name, 'platform_name_mismatch')
    workload = getattr(args, 'workload', 'training')
    if workload == 'command':
        require(getattr(args, 'entrypoint_file', None) is not None, 'command_entrypoint_required')
        expected = args.entrypoint_file.read_text().strip()
        require(bool(expected) and config.get('Entrypoint', '').strip() == expected,
                'command_entrypoint_mismatch')
    else:
        require(bool(args.task), 'training_task_required')
        check_training_values(config, args.task, args.exp_name or args.task.rsplit('/',1)[-1], args.card or args.task.rsplit('/',1)[-1])
    authorization = read(args.authorization)
    require(authorization.get('authorized') is True and authorization.get('actor') == 'user'
            and authorization.get('source_id') == args.source_id and authorization.get('task_name') == args.name
            and authorization.get('basis'), 'existing_user_authorization_required')
    cli, help_checks = supported_cli(args.cli)
    _, auth_basis = credential_values(os.environ, args.credential_script)
    requirements = read(args.requirements)
    dependency_check = check_dependencies(config, requirements)
    require(not os.path.lexists(args.output_path), 'training_output_exists')
    require(any(row['role'] == 'output' and Path(args.output_path).is_relative_to(Path(row['path'])) and row['access'] == 'write'
                for row in dependency_check['dependencies']), 'output_dependency_missing')
    args.journal.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(not args.journal.stat().st_mode & 0o077, 'journal_must_be_private')
    if args.recovery:
        require(bool(args.recovery_reason), 'recovery_needs_concrete_fix_reason')
        from types import SimpleNamespace
        safe = diagnostic(SimpleNamespace(returncode=0, stdout='', stderr='error: ' + args.recovery_reason), os.environ, config)
        args.recovery_reason = safe['reasons'][0].removeprefix('error: ') if safe['reasons'] else '[reason omitted by redaction]'
    plan = {'kind': 'volc_training_submission_plan', 'schema_version': 1, 'created_at_utc': now(),
            'region': args.region, 'name': args.name, 'source_id': args.source_id, 'task': args.task,
            'workload': workload,
            'priority': args.priority, 'statuses': args.statuses, 'output_path': str(args.output_path.absolute()),
            'journal': str(args.journal.resolve()), 'inputs': inputs, 'cli': pin(cli), 'help_checks': help_checks,
            'authentication': auth_basis, 'authentication_verified': False, 'dependencies': dependency_check,
            'recovery_reason': args.recovery_reason,
            'configuration_modified_by_tool': False, 'create_permission_verified': False, 'task_api_calls': 0}
    if claim_path(plan).exists(): validate_recovery(plan, claim_path(plan))
    for record in inputs.values(): check(record)
    plan['plan_sha256'] = digest(plan)
    write(args.record, plan, exclusive=True)
    return {'status': 'offline_preflight_passed', 'record': pin(args.record), 'create_permission_verified': False}


def submit(args):
    plan, config = verify_plan(args.plan)
    state = {'kind': 'volc_training_submission_intent', 'schema_version': 1, 'status': 'preparing',
             'phase': 'guard_created', 'started_at_utc': now(), 'plan': pin(args.plan),
             'plan_identity': [plan['region'], plan['name'], plan['source_id']], 'submission_calls': 0}
    script = plan['inputs'].get('credential_script', {}).get('path')
    with claim_lock(plan):
        claim = claim_path(plan)
        if claim.exists(): validate_recovery(plan, claim)
        require(not os.path.lexists(plan['output_path']), 'training_output_exists')
        write(args.intent, state, exclusive=True)
        write(claim, {'kind': 'volc_training_name_claim', 'intent': str(args.intent.resolve()),
                      'plan_identity': state['plan_identity']}, exclusive=not claim.exists())
        try:
            with cli_environment(plan['region'], script) as (env, basis):
                state['authentication'] = basis
                matches = exact_matches(plan, env, config)
                state.update(exact_matches=matches, all_statuses_checked=plan['statuses'], name_checked_at_utc=now())
                require(not matches, 'exact_name_already_exists')
                verify_plan(args.plan)
                require(not os.path.lexists(plan['output_path']), 'training_output_appeared_before_submit')
                with tempfile.TemporaryDirectory(prefix='volc-submit-') as directory:
                    raw = Path(plan['inputs']['config']['path']).read_bytes()
                    require(hashlib.sha256(raw).hexdigest() == plan['inputs']['config']['sha256'], 'submission_config_changed')
                    private_config = Path(directory) / 'task.yaml'
                    fd = os.open(private_config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(fd, 'wb') as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())
                    state.update(status='submission_outcome_pending', phase='single_submit_call', submission_calls=1)
                    write(args.intent, state)
                    command = ['submit', '--conf', str(private_config), '--task_name', plan['name'], '--output', 'json']
                    if plan['priority'] is not None: command.extend(['--priority', str(plan['priority'])])
                    response = payload(invoke(plan['cli']['path'], command, env, config, timeout=180))
                row = response[0] if isinstance(response, list) and len(response) == 1 else response
                require(isinstance(row, dict), 'submit_response_not_one_task')
                ids = {row[k] for k in ('JobId', 'TaskId', 'task_id', 'Id') if row.get(k)}
                require(len(ids) == 1, 'submit_id_ambiguous')
                identity = next(iter(ids))
                require(isinstance(identity, str) and re.fullmatch(r't-[A-Za-z0-9-]+', identity) and identity != plan['source_id'], 'submit_id_invalid')
                state['JobId'] = identity; state['phase'] = 'read_only_get_confirmation'; write(args.intent, state)
                row = payload(invoke(plan['cli']['path'], ['get', '--id', identity, '--output', 'json'], env, config))
                row = row[0] if isinstance(row, list) and len(row) == 1 else row
                require(isinstance(row, dict) and row.get('JobId') == identity and row.get('JobName') == plan['name'] and isinstance(row.get('Status'), str), 'created_identity_unconfirmed')
                state.update(status='submitted_and_get_verified', phase='complete', platform_status=row['Status'])
        except Exception as exc:
            code = exc.code if isinstance(exc, Stop) else 'local_operation_failed'
            state.update(status='submission_needs_readonly_recovery' if state['submission_calls'] else 'stopped_before_submit', error_code=code)
            if isinstance(exc, Stop) and exc.diagnostic:
                state['diagnostic'] = exc.diagnostic
                reasons = ' '.join(exc.diagnostic['reasons'])
                if state['submission_calls'] and plan['dependencies']['minimum_mount_scope'] and re.search(r'dir:|mount', reasons, re.I) and re.search(r'not authorized|access.?denied|permission.?denied|权限|拒绝', reasons, re.I):
                    state['status'] = 'blocked_minimum_mount_acl'
                    state['resolution'] = 'Existing API principal needs required mount access, or user must supply the correct existing authentication. No automatic resubmission or permission changes.'
        state['finished_at_utc'] = now(); write(args.intent, state)
    return {key: state[key] for key in ('status', 'JobId', 'platform_status', 'submission_calls', 'error_code') if key in state} | {'intent': pin(args.intent)}


def recover(args):
    intent = read(args.intent); check(intent['plan'])
    # Query only the frozen identity. Private submission YAML may already be removed.
    plan, config = verify_plan(intent['plan']['path'], historical=True)
    with claim_lock(plan):
        claim = claim_path(plan); require(read(claim)['intent'] == str(args.intent.resolve()), 'intent_not_current_claim')
        before = pin(args.intent)
        with cli_environment(plan['region'], plan['inputs'].get('credential_script', {}).get('path')) as (env, basis):
            matches = exact_matches(plan, env, config)
        require(pin(args.intent) == before, 'intent_changed_during_recovery')
        record = {'kind': 'volc_training_readonly_recovery', 'schema_version': 1, 'at_utc': now(),
                  'intent': before, 'claim': pin(claim), 'name': plan['name'], 'region': plan['region'],
                  'statuses': plan['statuses'], 'exact_matches': matches, 'output_exists': os.path.lexists(plan['output_path']),
                  'authentication': basis, 'task_mutations': False, 'automatic_resubmission': False}
        write(args.record, record, exclusive=True)
    return {'status': 'readonly_recovery_recorded', 'matches': matches, 'output_exists': record['output_exists'], 'record': pin(args.record)}


def inspect_source(args):
    """Early read-only authentication check; independent of unfinished training data."""
    require(re.fullmatch(r'[A-Za-z0-9-]+', args.region)
            and re.fullmatch(r't-[A-Za-z0-9-]+', args.source_id), 'invalid_source_identity')
    cli, checks = supported_cli(args.cli)
    with cli_environment(args.region, args.credential_script) as (env, basis):
        row = payload(invoke(cli, ['get', '--id', args.source_id, '--output', 'json'], env, {}))
        row = row[0] if isinstance(row, list) and len(row) == 1 else row
        require(isinstance(row, dict) and row.get('JobId') == args.source_id, 'source_identity_unconfirmed')
    result = {'kind': 'volc_training_source_readonly_check', 'at_utc': now(), 'cli': pin(cli),
              'help_checks': checks, 'authentication': basis, 'source_id': args.source_id,
              'source_query_succeeded': True, 'create_permission_verified': False, 'task_mutations': False}
    write(args.record, result, exclusive=True)
    return {'status': 'source_readonly_check_passed', 'record': pin(args.record), 'create_permission_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    inspect = sub.add_parser('inspect-source', help='Early read-only source/auth query; does not create a task')
    inspect.add_argument('--source-id', required=True); inspect.add_argument('--region', required=True)
    inspect.add_argument('--cli'); inspect.add_argument('--credential-script', type=Path)
    inspect.add_argument('--record', required=True, type=Path)
    pre = sub.add_parser('preflight', help='Offline help/auth-origin/config/dependency checks; no task API')
    for flag in ('config', 'authorization', 'requirements', 'output-path', 'journal', 'record'):
        pre.add_argument('--' + flag, type=Path, required=True)
    for flag in ('source-id', 'name', 'region'): pre.add_argument('--' + flag, required=True)
    pre.add_argument('--task')
    pre.add_argument('--workload', choices=('training', 'command'), default='training')
    pre.add_argument('--entrypoint-file', type=Path)
    pre.add_argument('--exp-name'); pre.add_argument('--card'); pre.add_argument('--cli')
    pre.add_argument('--priority', type=int, choices=range(1, 10))
    pre.add_argument('--statuses', default=STATUSES)
    pre.add_argument('--credential-script', type=Path)
    pre.add_argument('--recovery', type=Path); pre.add_argument('--recovery-reason')
    action = sub.add_parser('submit', help='Exactly one guarded create call under existing user authorization')
    action.add_argument('--plan', required=True, type=Path); action.add_argument('--intent', required=True, type=Path)
    action = sub.add_parser('recover', help='Read-only exact-name query; never submits')
    action.add_argument('--intent', required=True, type=Path); action.add_argument('--record', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = {'inspect-source': inspect_source, 'preflight': preflight, 'submit': submit, 'recover': recover}[args.command](args)
    except Exception as exc:
        result = {'status': 'stopped', 'error_code': exc.code if isinstance(exc, Stop) else 'local_operation_failed'}
        if isinstance(exc, Stop) and exc.diagnostic: result['diagnostic'] = exc.diagnostic
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result['status'] in ('source_readonly_check_passed', 'offline_preflight_passed', 'submitted_and_get_verified', 'readonly_recovery_recorded') else 2


if __name__ == '__main__':
    raise SystemExit(main())
