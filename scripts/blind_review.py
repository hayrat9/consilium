"""Prepare masked review packets and join assessments offline; never calls models."""
import argparse
import json
from pathlib import Path
import random
import secrets


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def unique_strings(value, label, allow_empty=False):
    if (not isinstance(value, list) or (not value and not allow_empty)
            or not all(nonempty(x) for x in value) or len(set(value)) != len(value)):
        raise ValueError(label + ' must be a list of unique nonempty strings')
    return value


def prepare(data, seed=None):
    if not isinstance(data, dict):
        raise ValueError('Input must be an object')
    reviewers = unique_strings(data.get('reviewers'), 'reviewers')
    criteria = data.get('criteria')
    if (not isinstance(criteria, list) or not criteria
            or not all(isinstance(c, dict) and nonempty(c.get('id'))
                       and nonempty(c.get('question')) for c in criteria)
            or len({c['id'] for c in criteria}) != len(criteria)):
        raise ValueError('criteria need unique IDs and substantive questions')
    clean_criteria = [{'id': c['id'], 'question': c['question']} for c in criteria]
    rows = data.get('submissions')
    if not isinstance(rows, list) or not rows:
        raise ValueError('submissions must be a nonempty list')
    normalized, ids = [], set()
    for row in rows:
        if not isinstance(row, dict) or not nonempty(row.get('id')) or row['id'] in ids:
            raise ValueError('Submissions need unique nonempty IDs')
        ids.add(row['id'])
        authors = unique_strings(row.get('authors'), 'authors')
        if not set(authors).issubset(reviewers):
            raise ValueError('Every author must be listed in reviewers')
        if not nonempty(row.get('content')):
            raise ValueError('Submission content must be substantive')
        sources = unique_strings(row.get('source_ids', []), 'source_ids', allow_empty=True)
        normalized.append({'id': row['id'], 'authors': list(authors),
                           'content': row['content'], 'source_ids': list(sources)})
    if seed is None:
        seed = secrets.randbits(128)
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError('seed must be an integer')
    rng = random.Random(seed)
    panels, assignments = [], []
    for reviewer in reviewers:
        eligible = [s for s in normalized if reviewer not in s['authors']]
        rng.shuffle(eligible)
        candidates, aliases = [], {}
        for index, row in enumerate(eligible, 1):
            alias = f'A{index:02}'
            candidates.append({'alias': alias, 'content': row['content'],
                               'source_ids': list(row['source_ids'])})
            aliases[alias] = {'submission_id': row['id'], 'authors': list(row['authors'])}
        status = 'ready' if candidates else 'skipped_no_eligible'
        panels.append({'reviewer_id': reviewer, 'status': status,
                       'prompt': {'criteria': clean_criteria, 'candidates': candidates}})
        assignments.append({'reviewer_id': reviewer, 'status': status, 'aliases': aliases})
    return {'panels': panels, 'mapping': {
        'schema_version': '1.1', 'seed': seed, 'criteria': clean_criteria,
        'reviewers': list(reviewers),
        'submissions': [{'id': s['id'], 'authors': s['authors']} for s in normalized],
        'assignments': assignments,
        'limits': 'Metadata masking only; text identity clues and fresh contexts need human/agent checks'}}


def checked_mapping(mapping):
    """Reject damaged maps, including omissions and self-review assignments."""
    if not isinstance(mapping, dict) or mapping.get('schema_version') != '1.1':
        raise ValueError('Unsupported mapping')
    reviewers = unique_strings(mapping.get('reviewers'), 'mapped reviewers')
    submissions = mapping.get('submissions')
    assignments = mapping.get('assignments')
    if not isinstance(submissions, list) or not submissions or not isinstance(assignments, list):
        raise ValueError('Mapping requires submissions and assignments')
    by_id = {}
    for row in submissions:
        if not isinstance(row, dict) or not nonempty(row.get('id')) or row['id'] in by_id:
            raise ValueError('Invalid mapping submission')
        by_id[row['id']] = unique_strings(row.get('authors'), 'mapped authors')
    seen, authors = set(), {a for row in by_id.values() for a in row}
    for assignment in assignments:
        if not isinstance(assignment, dict):
            raise ValueError('Invalid assignment')
        rid, aliases = assignment.get('reviewer_id'), assignment.get('aliases')
        if not nonempty(rid) or rid in seen or not isinstance(aliases, dict):
            raise ValueError('Mapping reviewers must be unique with alias objects')
        seen.add(rid)
        mapped = []
        for alias, item in aliases.items():
            if not nonempty(alias) or not isinstance(item, dict):
                raise ValueError('Invalid alias')
            sid = item.get('submission_id')
            if not isinstance(sid, str) or sid not in by_id or item.get('authors') != by_id[sid]:
                raise ValueError('Alias provenance does not match submission')
            if rid in by_id[sid]:
                raise ValueError('Self/coauthor review is forbidden')
            mapped.append(sid)
        expected = {sid for sid, aa in by_id.items() if rid not in aa}
        if len(mapped) != len(set(mapped)) or set(mapped) != expected:
            raise ValueError('Mapping must cover exactly the eligible submissions')
        if assignment.get('status') != ('ready' if expected else 'skipped_no_eligible'):
            raise ValueError('Incorrect assignment status')
    if not assignments or not authors.issubset(seen) or seen != set(reviewers):
        raise ValueError('Mapping must retain exactly all declared reviewers, including nonauthors')
    return {a['reviewer_id']: a for a in assignments}


def join(mapping, reviews, allow_partial=False):
    assignments = checked_mapping(mapping)
    if not isinstance(reviews, list):
        raise ValueError('Reviews must be a list')
    seen, records = set(), []
    for review in reviews:
        if not isinstance(review, dict) or not isinstance(review.get('reviewer_id'), str):
            raise ValueError('Invalid review')
        rid = review['reviewer_id']
        if rid not in assignments or rid in seen:
            raise ValueError('Unknown or duplicate reviewer')
        seen.add(rid)
        assessments = review.get('assessments')
        if not isinstance(assessments, list):
            raise ValueError('assessments must be a list')
        found = set()
        for item in assessments:
            if not isinstance(item, dict) or not isinstance(item.get('alias'), str):
                raise ValueError('Invalid assessment')
            alias = item['alias']
            if alias not in assignments[rid]['aliases'] or alias in found:
                raise ValueError('Unknown or duplicate alias for reviewer')
            if item.get('verdict') not in ('support', 'amend', 'challenge', 'unclear') or not nonempty(item.get('reason')):
                raise ValueError('Assessment requires verdict and substantive reason')
            found.add(alias)
            records.append({'reviewer_id': rid, 'alias': alias,
                            **assignments[rid]['aliases'][alias],
                            'verdict': item['verdict'], 'reason': item['reason']})
    done = {(r['reviewer_id'], r['alias']) for r in records}
    missing = [{'reviewer_id': rid, 'alias': alias} for rid, a in assignments.items()
               for alias in a['aliases'] if (rid, alias) not in done]
    if missing and not allow_partial:
        raise ValueError('Missing assessments; resume saved packets or use --allow-partial')
    skipped = [rid for rid, a in assignments.items() if not a['aliases']]
    return {'status': 'in_progress' if missing else 'complete', 'assessments': records,
            'missing': missing, 'skipped_reviewers': skipped,
            'limits': 'Completeness of assessments is not truth, independence or completed R2 role cards'}


def write_new(path, data):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='operation', required=True)
    p = subs.add_parser('prepare')
    p.add_argument('input', type=Path)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--seed', type=int)
    j = subs.add_parser('join')
    j.add_argument('mapping', type=Path)
    j.add_argument('reviews', type=Path)
    j.add_argument('--output', type=Path, required=True)
    j.add_argument('--allow-partial', action='store_true')
    args = parser.parse_args()
    try:
        if args.operation == 'prepare':
            pack = prepare(json.loads(args.input.read_text(encoding='utf-8')), args.seed)
            args.output_dir.mkdir(mode=0o700, exist_ok=False)
            manifest = []
            for index, panel in enumerate(pack['panels'], 1):
                name = f'panel-{index:03}.json'
                write_new(args.output_dir / name, panel['prompt'])
                manifest.append({'reviewer_id': panel['reviewer_id'], 'file': name, 'status': panel['status']})
            write_new(args.output_dir / 'manifest.json', manifest)
            write_new(args.output_dir / 'mapping.json', pack['mapping'])
            print(json.dumps({'directory': str(args.output_dir), 'reviewers': len(manifest)}))
        else:
            result = join(json.loads(args.mapping.read_text(encoding='utf-8')),
                          json.loads(args.reviews.read_text(encoding='utf-8')), args.allow_partial)
            write_new(args.output, result)
            print(json.dumps({'output': str(args.output), 'status': result['status']}))
    except (ValueError, TypeError, OSError) as error:
        parser.exit(2, str(error) + '\n')


if __name__ == '__main__':
    main()
