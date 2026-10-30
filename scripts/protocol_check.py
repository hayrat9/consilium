"""Validate recorded protocol 1.2 data; never judges evidence or calls models."""
import json
from pathlib import Path
from blind_review import checked_mapping, join


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def strings(value, allow_empty=False):
    return isinstance(value, list) and (bool(value) or allow_empty) and all(nonempty(x) for x in value)


def artifact(directory, name):
    if directory is None:
        raise ValueError('Protocol 1.2 review artifacts need the session directory')
    if not nonempty(name):
        raise ValueError('Review artifact reference is missing')
    rel = Path(name)
    if rel.is_absolute() or '..' in rel.parts:
        raise ValueError('Review artifacts must be relative paths inside the session directory')
    root = Path(directory).resolve()
    target = root / rel
    if any((root / Path(*rel.parts[:i])).is_symlink() for i in range(1, len(rel.parts) + 1)):
        raise ValueError('Review artifact references cannot follow symlinks')
    if not target.resolve().is_relative_to(root):
        raise ValueError('Review artifact escapes the session directory')
    with target.open(encoding='utf-8') as handle:
        return json.load(handle)


def review_check(d, r2, directory, errors):
    blind = d.get('blind_review')
    if not isinstance(blind, dict):
        errors.append('Protocol 1.2 completed R2 requires a blind_review object')
        return
    status = blind.get('status')
    if status not in ('complete', 'skipped_no_eligible'):
        errors.append('Protocol 1.2 completed R2 requires completed review or a no-eligible exception')
        return
    if status == 'complete' and blind.get('blinding') not in ('metadata_only', 'fresh_contexts'):
        errors.append('Completed review needs metadata_only or fresh_contexts blinding')
    try:
        mapping = artifact(directory, blind.get('mapping_file'))
        assignments = checked_mapping(mapping)
        scoped = {c['role_id'] for c in r2.get('cards', []) if isinstance(c, dict) and isinstance(c.get('role_id'), str)}
        if set(assignments) != scoped:
            raise ValueError('Reviewers must match the recorded R2 scope')
        eligible = any(a['aliases'] for a in assignments.values())
        if status == 'skipped_no_eligible':
            if not nonempty(blind.get('exception_reason')) or eligible:
                raise ValueError('No-eligible exception requires a reason and no eligible assignments')
            return
        if not eligible:
            raise ValueError('No eligible assessments: record the explicit no-eligible exception')
        reviews = artifact(directory, blind.get('reviews_file'))
        saved = artifact(directory, blind.get('results_file'))
        result = join(mapping, reviews)
        if not isinstance(saved, dict) or any(saved.get(k) != result[k]
                for k in ('status', 'assessments', 'missing', 'skipped_reviewers')):
            raise ValueError('Saved review result must match recomputed assessments and coverage')
    except (ValueError, TypeError, KeyError, OSError) as exc:
        errors.append('Review artifacts: ' + str(exc))


def validate(d, artifact_dir=None):
    errors, warnings = [], []
    protocol = d.get('protocol_version')
    if protocol in (None, '1.0', '1.1'):
        warnings.append('Legacy session: protocol 1.2 outcome and review-artifact gates are not applied; history is unchanged')
        return errors, warnings
    if protocol != '1.2':
        return ['Unsupported protocol_version'], warnings
    mode = d.get('mode')
    if mode not in ('decision', 'creative', 'research', 'explanation'):
        errors.append('Unknown protocol 1.2 mode')
    phase = d.get('phase')
    ready = phase in ('ready', 'round1', 'round2', 'round3', 'complete')
    decision = mode in ('decision', 'creative')
    contract = d.get('decision_contract')
    if ready and decision:
        if (not isinstance(contract, dict) or contract.get('stage') not in ('explore', 'test', 'act')
                or not strings(contract.get('acceptance_criteria'))):
            errors.append('Decision contract needs stage and acceptance criteria before R1')
    rounds = d.get('rounds', [])
    if not isinstance(rounds, list) or not all(isinstance(r, dict) for r in rounds):
        return errors, warnings
    r2 = next((r for r in rounds if r.get('number') == 2), None)
    if r2 and r2.get('status', 'complete') == 'complete':
        review_check(d, r2, artifact_dir, errors)
        critical = d.get('critical_check')
        if not isinstance(critical, dict) or not all(nonempty(critical.get(k)) for k in (
                'assumption_and_refutation', 'simpler_or_no_action', 'strongest_objection', 'response')):
            errors.append('Completed R2 needs recorded refutation, simpler path, objection and response')
    if phase != 'complete':
        return errors, warnings
    result = d.get('result')
    if not isinstance(result, dict):
        return errors, warnings  # The base checker reports this error.
    outcome = result.get('outcome')
    if outcome not in ('analysis', 'candidate_for_test', 'action_supported', 'no_option_passed', 'insufficient_evidence'):
        errors.append('Result needs an explicit outcome')
    if mode in ('research', 'explanation') and outcome not in ('analysis', 'insufficient_evidence'):
        errors.append('Research or explanation does not select a test or action; use decision or creative')
    if decision and outcome == 'analysis':
        errors.append('A decision result must state its decision outcome')
    selected = result.get('selected_options')
    if not strings(selected, allow_empty=True):
        errors.append('selected_options must be a list of option IDs')
    elif outcome in ('candidate_for_test', 'action_supported') and not selected:
        errors.append('A selected test or action needs at least one option ID')
    elif outcome in ('no_option_passed', 'insufficient_evidence', 'analysis') and selected:
        errors.append('A result without a selected option cannot declare a winner')
    if outcome == 'action_supported' and (not isinstance(contract, dict) or contract.get('stage') != 'act'):
        errors.append('Action support requires the act stage; a test is not proven readiness')
    if not nonempty(result.get('basis')) or not strings(result.get('limits')):
        errors.append('Result needs its basis and limits')
    if r2 is None:
        if not nonempty(d.get('stop_reason')) or outcome not in ('analysis', 'insufficient_evidence'):
            errors.append('Stopping before R2 requires a reason and a non-recommendation outcome')
        warnings.append('Stopped before R2: no peer review is claimed')
    claims = d.get('claims')
    if not isinstance(claims, list):
        errors.append('claims must be a list')
    elif not claims:
        if outcome in ('candidate_for_test', 'action_supported') or not nonempty(d.get('claims_not_applicable_reason')):
            errors.append('Key claims or a concrete not-applicable reason are required')
    else:
        ids = []
        for row in claims:
            if not isinstance(row, dict):
                errors.append('Claim records must be objects'); continue
            cid = row.get('id'); ids.append(cid)
            if not nonempty(cid) or not nonempty(row.get('text')) or not nonempty(row.get('limits')):
                errors.append('Claim needs id, text and limits')
            if row.get('kind') not in ('observation', 'inference', 'hypothesis', 'preference'):
                errors.append('Unknown claim kind')
            support = row.get('support')
            if support not in ('supported', 'partial', 'unknown', 'contradicted', 'not_applicable'):
                errors.append('Unknown evidence support; hypothesis and verified are not support levels')
            if support == 'not_applicable' and row.get('kind') != 'preference':
                errors.append('Only a preference can have support not_applicable')
            refs = row.get('evidence_refs')
            if not strings(refs, allow_empty=True) or (support in ('supported', 'partial', 'contradicted') and not refs):
                errors.append('Supported or contradicted claims need evidence references')
            if 'verification' in row:
                v = row['verification']
                if not isinstance(v, dict) or not all(nonempty(v.get(k)) for k in ('method', 'result', 'checked_at', 'scope')):
                    errors.append('Verification needs method, observed result, date and scope')
        if all(isinstance(x, str) for x in ids) and len(ids) != len(set(ids)):
            errors.append('Claim IDs must be unique')
    changes = d.get('position_changes', [])
    if not isinstance(changes, list) or not all(isinstance(x, dict) and all(nonempty(x.get(k))
            for k in ('from', 'to', 'reason')) for x in changes):
        errors.append('Position changes need the original view, new view and a substantive reason')
    warnings.append('Recorded claims and review artifacts are not proof of truthful execution or decision quality')
    return errors, warnings
