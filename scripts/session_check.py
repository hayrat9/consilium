"""Check session structure and phase gates; does not authenticate user approval."""
import json
import sys
from pathlib import Path
from protocol_check import validate as validate_protocol

PHASES = ['planning', 'awaiting_scope', 'approved', 'ready', 'round1', 'round2', 'round3', 'complete']

def check(d, *, artifact_dir=None):
    if not isinstance(d, dict):
        return {'valid': False, 'can_select_personas': False, 'can_run_rounds': False,
                'errors': ['Session must be an object'], 'warnings': []}
    errors, warnings = [], []
    phase = d.get('phase')
    if phase not in PHASES:
        return {'valid': False, 'can_select_personas': False, 'can_run_rounds': False,
                'errors': ['Unknown phase'], 'warnings': []}
    stage = PHASES.index(phase)
    # Optional 1.1 fields leave historical 1.0 sessions readable without migration.
    depth = d.get('depth', 'full')
    if depth not in ('full', 'light'):
        errors.append('depth must be full or light')
    research = d.get('research', {})
    if not isinstance(research, dict):
        errors.append('research must be an object')
    else:
        policy = research.get('policy', 'last30' if depth == 'full' else 'targeted')
        if policy not in ('last30', 'targeted', 'not_applicable'):
            errors.append('Unknown research policy')
        if depth == 'full' and policy != 'last30':
            errors.append('Full depth retains the last30 research policy')
        if policy == 'not_applicable' and not (isinstance(research.get('rationale'), str)
                                               and research['rationale'].strip()):
            errors.append('Skipping freshness requires a concrete rationale')
    execution = d.get('execution', {})
    if not isinstance(execution, dict):
        errors.append('execution must be an object')
    elif execution.get('strategy', 'single_model') not in ('single_model', 'multi_model'):
        errors.append('Unknown execution strategy')
    elif execution.get('strategy') == 'multi_model' and stage >= 3:
        authorization = execution.get('authorization')
        if (execution.get('model_change_authorized') is not True
                or not isinstance(authorization, dict) or authorization.get('source') != 'user'
                or not isinstance(authorization.get('turn_id'), str) or not authorization['turn_id'].strip()
                or not isinstance(authorization.get('text'), str) or not authorization['text'].strip()):
            errors.append('Multi-model execution requires recorded explicit user authorization')
        models = execution.get('models')
        if (not isinstance(models, list) or len(models) < 2
                or not all(isinstance(x, str) and x.strip() for x in models)
                or (all(isinstance(x, str) for x in models) and len(set(models)) != len(models))):
            errors.append('Multi-model execution requires at least two distinct actual model IDs')
        if execution.get('availability') != 'verified':
            errors.append('Multi-model availability must be checked before readiness')
    blind = d.get('blind_review', {})
    if not isinstance(blind, dict):
        errors.append('blind_review must be an object')
    else:
        if blind.get('status', 'not_started') not in ('not_started', 'in_progress', 'complete', 'skipped_no_eligible'):
            errors.append('Unknown blind review status')
        if blind.get('blinding', 'not_started') not in ('not_started', 'metadata_only', 'fresh_contexts'):
            errors.append('Unknown blinding mode')
        if phase == 'complete' and blind.get('status') == 'in_progress':
            errors.append('Cannot complete while anonymous assessments are in progress')
    version = d.get('scope_version')
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        errors.append('scope_version must be a positive integer')
    ds, roles, rounds = d.get('disciplines', []), d.get('roles', []), d.get('rounds', [])
    if not all(isinstance(x, list) for x in [ds, roles, rounds]):
        return {'valid': False, 'can_select_personas': False, 'can_run_rounds': False,
                'errors': errors + ['disciplines, roles and rounds must be lists'], 'warnings': []}
    if not all(isinstance(x, dict) for x in ds + roles + rounds):
        return {'valid': False, 'can_select_personas': False, 'can_run_rounds': False,
                'errors': errors + ['Session rows must be objects'], 'warnings': []}
    dids = [x.get('id') for x in ds]
    rids = [x.get('id') for x in roles]
    for name, ids in [('discipline', dids), ('role', rids)]:
        if any(not isinstance(x, str) or not x.strip() for x in ids):
            errors.append(name + ' IDs must be nonempty strings')
        elif len(set(ids)) != len(ids):
            errors.append('Duplicate ' + name + ' IDs')
    if any(not isinstance(x, str) for x in dids + rids):
        return {'valid': False, 'can_select_personas': False, 'can_run_rounds': False,
                'errors': errors, 'warnings': warnings}
    approval = d.get('scope_approval', {})
    if not isinstance(approval, dict):
        approval = {}
        errors.append('scope_approval must be an object')
    status = approval.get('status', 'pending')
    if status not in ['pending', 'approved']:
        errors.append('Unknown scope approval status')
    approved = status == 'approved'
    if approved:
        if stage < 2:
            errors.append('Recorded approval requires an approved or later phase')
        if approval.get('version') != version:
            errors.append('Approval is for another scope version')
        if approval.get('source') != 'user':
            errors.append('Approval must refer to an actual user decision')
        for k in ['turn_id', 'text']:
            if not isinstance(approval.get(k), str) or not approval[k].strip():
                errors.append('Approval requires ' + k)
        approved_ids = approval.get('discipline_ids')
        if not isinstance(approved_ids, list) or not all(isinstance(x, str) for x in approved_ids):
            errors.append('Approval discipline_ids must be a string list')
        elif len(set(approved_ids)) != len(approved_ids) or set(approved_ids) != set(dids):
            errors.append('Approval must cover exactly the selected disciplines')
        if not ds:
            errors.append('Cannot approve an empty scope')
    elif stage >= 2 or roles or rounds:
        errors.append('User scope approval is required before selecting roles or running rounds')
    if stage >= 2:
        if not isinstance(d.get('topic'), str) or not d['topic'].strip():
            errors.append('Approved session requires a topic')
        for x in ds:
            for k in ['name', 'question', 'contribution']:
                if not isinstance(x.get(k), str) or not x[k].strip():
                    errors.append('Discipline ' + x['id'] + ' requires ' + k)
    history = d.get('scope_history', [])
    snapshots = {}
    if not isinstance(history, list) or not all(isinstance(x, dict) for x in history):
        errors.append('scope_history must contain version snapshots')
        history = []
    for snapshot in history:
        v, ids = snapshot.get('version'), snapshot.get('role_ids')
        hds, ha = snapshot.get('discipline_ids'), snapshot.get('approval', {})
        if (not isinstance(v, int) or isinstance(v, bool) or not isinstance(version, int)
                or v < 1 or v >= version or v in snapshots):
            errors.append('Historical scope versions must be unique earlier positive integers')
            continue
        if (not isinstance(ids, list) or not ids or not all(isinstance(x, str) and x for x in ids)
                or len(set(ids)) != len(ids)):
            errors.append('Historical scope requires unique role_ids')
            continue
        if (not isinstance(hds, list) or not hds or not all(isinstance(x, str) and x for x in hds)
                or len(set(hds)) != len(hds)):
            errors.append('Historical scope requires unique discipline_ids')
        if (not isinstance(ha, dict) or ha.get('source') != 'user'
                or not isinstance(ha.get('turn_id'), str) or not ha['turn_id'].strip()
                or not isinstance(ha.get('text'), str) or not ha['text'].strip()):
            errors.append('Historical scope requires its recorded user approval')
        snapshots[v] = set(ids)
    covered = set()
    for r in roles:
        rd = r.get('discipline_ids', [])
        if not isinstance(rd, list) or not all(isinstance(x, str) for x in rd):
            errors.append('Role discipline_ids must be a string list')
            continue
        if not rd or not set(rd).issubset(dids):
            errors.append('Role ' + r['id'] + ' has missing or unapproved disciplines')
        covered.update(rd)
        if r.get('kind') not in ['named_persona', 'professional', 'stakeholder']:
            errors.append('Unknown role kind for ' + r['id'])
        if r.get('kind') == 'named_persona':
            if r.get('profile_basis') not in ['read', 'partial'] or not r.get('source_ids'):
                errors.append('Named role ' + r['id'] + ' lacks a read profile basis')
            if not r.get('limits'):
                errors.append('Named role ' + r['id'] + ' requires explicit limits')
            if r.get('profile_basis') == 'partial':
                warnings.append('Partial profile for ' + r['id'])
    if stage >= 3:
        if not roles or covered != set(dids):
            errors.append('Every approved discipline must remain represented')
    maximum = d.get('max_rounds', 3)
    if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 1:
        errors.append('max_rounds must be a positive planned integer')
    elif len(rounds) > maximum:
        errors.append('More rounds than planned')
    round_states = []
    for i, row in enumerate(rounds, 1):
        if row.get('number') != i:
            errors.append('Round numbers must be sequential')
        cards = row.get('cards', [])
        if not isinstance(cards, list) or not all(isinstance(x, dict) for x in cards):
            errors.append('Round cards must be objects')
            continue
        rv = row.get('scope_version', version)
        expected = set(rids) if rv == version else snapshots.get(rv) if isinstance(rv, int) else None
        if expected is None:
            errors.append('Round ' + str(i) + ' needs a saved snapshot for its scope_version')
            continue
        status = row.get('status', 'complete')
        if status not in ['in_progress', 'complete']:
            errors.append('Unknown round status')
        round_states.append(status)
        ids = [x.get('role_id') for x in cards]
        valid_ids = all(isinstance(x, str) for x in ids)
        if (not valid_ids or len(set(ids)) != len(ids) or not set(ids).issubset(expected)
                or (status == 'complete' and set(ids) != expected)):
            errors.append('Round ' + str(i) + ' must retain its scoped roles; partial cards need in_progress')
        for card in cards:
            if (isinstance(execution, dict) and execution.get('strategy') == 'multi_model'
                    and (not isinstance(card.get('model'), str)
                         or card['model'] not in (execution.get('models') if isinstance(execution.get('models'), list) else []))):
                errors.append('Multi-model cards must identify their actual declared model')
            text = card.get('content')
            position, arguments = card.get('position'), card.get('arguments')
            reason, vote = card.get('reason'), card.get('vote')
            has_text = isinstance(text, str) and bool(text.strip())
            has_argument = (isinstance(position, str) and bool(position.strip())
                            and isinstance(arguments, list) and bool(arguments)
                            and all(isinstance(x, str) and x.strip() for x in arguments))
            has_vote = (vote in ['Endorse', 'Endorse with amendment', 'Dissent']
                        and isinstance(reason, str) and bool(reason.strip()))
            if not (has_text or has_argument or has_vote):
                errors.append('Round card must contain public arguments, not only role_id')
        if status == 'in_progress':
            if i != len(rounds) or phase != 'round' + str(i):
                errors.append('Only the current last round may be in_progress')
    if rounds and stage < 4:
        errors.append('Round data before round phase')
    if phase.startswith('round'):
        current = int(phase[-1])
        if len(rounds) < current - 1 or len(rounds) > current:
            errors.append('Round phase requires all earlier round records and no future round')
        if any(s != 'complete' for s in round_states[:current - 1]):
            errors.append('Earlier rounds must be complete before the next round')
    if phase == 'complete':
        if not rounds or any(s != 'complete' for s in round_states):
            errors.append('Completed council requires finished public round records')
        if rounds and rounds[-1].get('scope_version', version) != version:
            errors.append('Current approved scope must appear in the final completed round')
        result = d.get('result')
        if (not isinstance(result, dict) or not isinstance(result.get('conclusion'), str)
                or not result['conclusion'].strip()):
            errors.append('Completed council requires a substantive result.conclusion')
        if isinstance(maximum, int) and len(rounds) < maximum:
            if not isinstance(d.get('stop_reason'), str) or not d['stop_reason'].strip():
                errors.append('Finishing before the planned round count requires stop_reason')
    protocol_errors, protocol_warnings = validate_protocol(d, artifact_dir)
    errors.extend(protocol_errors)
    warnings.extend(protocol_warnings)
    warnings.append('This validates recorded structure, not authenticity of approval or truth of sources')
    return {'valid': not errors, 'phase': phase,
            'can_select_personas': approved and 2 <= stage < 7 and not errors,
            'can_run_rounds': approved and 3 <= stage < 7 and not errors,
            'errors': errors, 'warnings': warnings}

if __name__ == '__main__':
    try:
        result = check(json.load(open(sys.argv[1], encoding='utf-8')), artifact_dir=Path(sys.argv[1]).resolve().parent)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result['valid'] else 2)
    except (ValueError, TypeError, KeyError, OSError, IndexError) as e:
        print(json.dumps({'valid': False, 'error': str(e)}, ensure_ascii=False))
        sys.exit(2)
