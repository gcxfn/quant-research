#!/usr/bin/env python3
"""Offline evidence-file checker. NOT a trading validator or approval system.

Reads JSON/XML and hashes local files. Never runs supplied commands, accesses
networks, or changes repository content. Python 3.10+; standard library only.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
STAGES = {f"C{i}" for i in range(10)}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def local_file(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError('evidence path must be a nonempty relative path')
    # Reject Windows absolute paths even when this checker runs on Linux.
    if re.match(r'^[A-Za-z]:', value) or value.startswith(('\\', '/')):
        raise ValueError('absolute evidence paths are not allowed')
    parts = value.replace('\\', '/').split('/')
    if '..' in parts:
        raise ValueError('parent traversal is not allowed')
    path = root.joinpath(*parts).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('evidence path escapes supplied root (including symlinks)')
    if not path.is_file():
        raise ValueError(f'evidence is not an existing file: {value}')
    return path


def read_json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('JSON evidence too large; split the evidence manifest')
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError('JSON root must be an object')
    return data


def check_junit(path: Path) -> tuple[list[str], dict[str, int]]:
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('JUnit XML too large; supply scoped evidence')
    raw = path.read_bytes()
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('DTD/entity declarations are not allowed')
    tree = ET.fromstring(raw)
    cases = list(tree.iter('testcase'))
    counts = {'tests':len(cases), 'failures':0, 'errors':0, 'skipped':0}
    for case in cases:
        for key, tag in [('failures','failure'),('errors','error'),('skipped','skipped')]:
            counts[key] += int(case.find(tag) is not None)
    errors = []
    if not cases:
        errors.append('JUnit has no actual testcase elements')
    if counts['failures'] or counts['errors']:
        errors.append('JUnit contains failures/errors')
    return errors, counts


def verify(report: dict[str, Any], root: Path, allow_skip: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    cautions: list[str] = [
        'This checks file presence, byte identity and basic evidence consistency only.',
        'It does not authenticate users/reviewers or prove that logs are genuine.',
        'It does not validate market rules, accounting, strategy edge or grant approval.'
    ]
    if report.get('schema_version') != '1.0':
        errors.append('schema_version must be 1.0')
    stage = report.get('stage_id')
    if stage not in STAGES:
        errors.append('stage_id must be C0..C9')
    if report.get('engineering_state') not in {'pending', 'accepted', 'rejected', 'blocked'}:
        errors.append('engineering_state is invalid')
    if report.get('run_state') != 'completed':
        errors.append('delivery is not marked completed; template/incomplete evidence cannot pass')
    if not report.get('implementer_id'):
        errors.append('implementer_id missing')
    if not report.get('authorization_reference'):
        errors.append('authorization_reference missing (presence is not authenticity)')
    if not re.fullmatch(r'[0-9a-fA-F]{40}', str(report.get('code_commit', ''))):
        errors.append('code_commit must be the complete 40-hex Git commit identity')
    if not HEX64.fullmatch(str(report.get('contract_sha256', ''))):
        errors.append('contract_sha256 must be a SHA256 hex digest')

    entries = report.get('evidence', [])
    if not isinstance(entries, list) or not entries:
        errors.append('nonempty evidence list required')
        entries = []
    verified: dict[str, tuple[Path, str]] = {}
    junit_summary = []
    for entry in entries:
        try:
            if not isinstance(entry, dict):
                raise ValueError('evidence entry must be an object')
            eid = entry.get('id')
            if not isinstance(eid, str) or not eid or eid in verified:
                raise ValueError('evidence id missing or duplicated')
            path = local_file(root, entry.get('path'))
            expected = entry.get('sha256')
            if not isinstance(expected, str) or not HEX64.fullmatch(expected):
                raise ValueError(f'{eid}: SHA256 missing/invalid')
            if digest(path).lower() != expected.lower():
                raise ValueError(f'{eid}: file SHA256 does not match')
            kind = str(entry.get('kind', ''))
            verified[eid] = (path, kind)
            if kind == 'junit':
                je, counts = check_junit(path)
                errors.extend(f'{eid}: {e}' for e in je)
                junit_summary.append({'evidence_id':eid, **counts})
                if counts['skipped']:
                    if not allow_skip:
                        errors.append(f'{eid}: skipped tests require explicit independent treatment')
                    else:
                        cautions.append(f'{eid}: {counts["skipped"]} skipped; core gates still must not be skipped')
        except (ValueError, OSError, ET.ParseError) as exc:
            errors.append(str(exc))

    checks = report.get('checks', [])
    # This package's baseline is eight gates per stage. A revised approved
    # matrix requires a versioned checker change; never silently omit gates.
    expected_gates = {f'{stage}-{i:02}' for i in range(1,9)} if stage in STAGES else set()
    seen_gates = set()
    if not isinstance(checks, list):
        errors.append('checks must be a list')
        checks = []
    for c in checks:
        if not isinstance(c, dict):
            errors.append('check entry must be an object'); continue
        gid = c.get('gate_id')
        if gid in seen_gates:
            errors.append(f'duplicate gate {gid}')
        seen_gates.add(gid)
        if c.get('status') != 'PASS':
            errors.append(f'{gid}: gate is not PASS')
        refs = c.get('evidence_ids')
        if not isinstance(refs, list) or not refs or any(x not in verified for x in refs):
            errors.append(f'{gid}: missing/unverified evidence reference')
    if seen_gates != expected_gates:
        errors.append('gate IDs do not exactly match this package stage matrix')

    for issue in report.get('open_issues', []):
        if not isinstance(issue, dict):
            errors.append('issue entry must be an object'); continue
        if issue.get('severity') in {'CRITICAL','MAJOR'} and issue.get('status') != 'closed':
            errors.append(f'unclosed blocker: {issue.get("issue_id")}')

    run_refs = report.get('run_records', [])
    if stage not in {'C0'} and not run_refs:
        errors.append('non-C0 completed stage requires run-record evidence')
    for ref in run_refs:
        try:
            if ref not in verified or verified[ref][1] != 'run_record':
                raise ValueError(f'{ref}: run_record evidence reference invalid')
            run = read_json(verified[ref][0])
            if run.get('status') != 'completed' or type(run.get('exit_code')) is not int or run['exit_code'] != 0:
                raise ValueError(f'{ref}: run did not complete with integer exit_code 0')
            if not isinstance(run.get('command'), list) or not run['command']:
                raise ValueError(f'{ref}: actual command missing')
            t0=datetime.fromisoformat(str(run.get('started_at_utc','')).replace('Z','+00:00'))
            t1=datetime.fromisoformat(str(run.get('ended_at_utc','')).replace('Z','+00:00'))
            if t0.tzinfo is None or t1.tzinfo is None or t1 < t0:
                raise ValueError(f'{ref}: invalid timezone-aware start/end')
            for prefix in ('code','config'):
                before=run.get(f'{prefix}_sha256_at_start')
                after=run.get(f'{prefix}_sha256_at_end')
                if not HEX64.fullmatch(str(before or '')) or before != after:
                    raise ValueError(f'{ref}: {prefix} start/end identity mismatch')
            if set(run.get('expected_arms', [])) != set(run.get('actual_arms', [])):
                raise ValueError(f'{ref}: missing or unregistered output arms')
        except (ValueError, OSError, TypeError) as exc:
            errors.append(str(exc))

    review_ref = report.get('independent_review_evidence_id')
    if report.get('engineering_state') == 'accepted':
        if not report.get('reviewer_id') or report.get('reviewer_id') == report.get('implementer_id'):
            errors.append('accepted requires a different named reviewer (identity still externally verified)')
        if review_ref not in verified or verified[review_ref][1] != 'independent_review':
            errors.append('accepted requires hashed independent_review evidence')
    else:
        cautions.append('No engineering approval inferred; pending/rejected/blocked remains unchanged.')
    if report.get('next_stage_authorized'):
        cautions.append('Next-stage authorization is NOT validated by this tool; verify externally.')
    return {'status':'EVIDENCE_FILES_OK' if not errors else 'EVIDENCE_CHECK_FAILED',
            'stage_id':stage,'errors':errors,'cautions':cautions,
            'verified_file_count':len(verified),'junit_summary':junit_summary,
            'engineering_approval_granted':False,'research_validated':False}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True, help='Evidence root, not a remote URL')
    parser.add_argument('--allow-noncritical-skips', action='store_true')
    args=parser.parse_args()
    try:
        if not args.root.is_dir():
            raise ValueError('--root must be an existing directory')
        result=verify(read_json(args.report), args.root.resolve(), args.allow_noncritical_skips)
    except (ValueError, OSError, TypeError, json.JSONDecodeError) as exc:
        result={'status':'EVIDENCE_CHECK_FAILED','errors':[str(exc)],'engineering_approval_granted':False}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status']=='EVIDENCE_FILES_OK' else 2

if __name__ == '__main__':
    raise SystemExit(main())
