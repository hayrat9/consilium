"""Behavioral checks for masked packets, provenance, view safety and mode gates."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from blind_review import prepare, join
from render_rounds import render
from session_check import check
from self_test import approved

ROOT = Path(__file__).resolve().parents[1]


def sample():
    return {'criteria': [{'id': 'proof', 'question': 'Does evidence support the claim?'}],
            'reviewers': ['R1', 'R2', 'R3', 'R4'],
            'submissions': [{'id': f'S{i}', 'authors': [f'R{i}'], 'model': 'HIDDEN_MODEL',
                             'content': f'Claim {i} with limits', 'source_ids': [f'E{i}']}
                            for i in range(1, 5)]}


def reviews(pack):
    return [{'reviewer_id': p['reviewer_id'], 'assessments': [
        {'alias': c['alias'], 'verdict': 'amend', 'reason': 'Check the cited source before deciding.'}
        for c in p['prompt']['candidates']]} for p in pack['panels']]


class ReviewTests(unittest.TestCase):
    def test_no_self_review_and_only_prompt_fields_reach_reviewers(self):
        pack = prepare(sample(), 17)
        for panel, mapping in zip(pack['panels'], pack['mapping']['assignments']):
            self.assertEqual(set(panel['prompt']), {'criteria', 'candidates'})
            self.assertEqual(len(panel['prompt']['candidates']), 3)
            for card in panel['prompt']['candidates']:
                self.assertEqual(set(card), {'alias', 'content', 'source_ids'})
                self.assertNotIn(panel['reviewer_id'], mapping['aliases'][card['alias']]['authors'])
            self.assertNotIn('HIDDEN_MODEL', json.dumps(panel['prompt']))

    def test_all_coauthors_excluded_and_origins_retained(self):
        d = sample(); d['submissions'].append({'id': 'combined', 'authors': ['R1', 'R2'],
                                             'content': 'Combined mechanism'})
        pack = prepare(d, 3)
        for assignment in pack['mapping']['assignments']:
            ids = [v['submission_id'] for v in assignment['aliases'].values()]
            self.assertEqual('combined' in ids, assignment['reviewer_id'] not in ('R1', 'R2'))
        result = join(pack['mapping'], reviews(pack))
        self.assertTrue(any(r['authors'] == ['R1', 'R2'] for r in result['assessments']))

    def test_repeatable_seed_and_order_is_not_always_original(self):
        data = sample(); original = deepcopy(data)
        pack = prepare(data, 42)
        self.assertEqual(pack, prepare(data, 42))
        self.assertEqual(data, original)
        observed = []
        for seed in range(12):
            a = prepare(data, seed)['mapping']['assignments'][0]
            observed.append(tuple(v['submission_id'] for v in a['aliases'].values()))
        self.assertGreater(len(set(observed)), 1)
        self.assertNotEqual(pack, prepare(data, 43))

    def test_join_requires_all_expected_and_keeps_partial(self):
        pack = prepare(sample(), 5); rr = reviews(pack)
        rr[0]['assessments'].pop()
        with self.assertRaises(ValueError): join(pack['mapping'], rr)
        partial = join(pack['mapping'], rr, True)
        self.assertEqual(partial['status'], 'in_progress')
        self.assertEqual(len(partial['missing']), 1)
        self.assertEqual(join(pack['mapping'], reviews(pack))['status'], 'complete')

    def test_join_rejects_unknown_duplicate_and_empty_assessments(self):
        pack = prepare(sample(), 5)
        for mutate in (
            lambda r: r.append(deepcopy(r[0])),
            lambda r: r[0]['assessments'].append(deepcopy(r[0]['assessments'][0])),
            lambda r: r[0].update(reviewer_id='outsider'),
            lambda r: r[0]['assessments'][0].update(alias='A999'),
            lambda r: r[0]['assessments'][0].update(reason='  '),
            lambda r: r[0]['assessments'][0].update(verdict='winner')):
            rr = reviews(pack); mutate(rr)
            with self.assertRaises(ValueError): join(pack['mapping'], rr)

    def test_tampered_map_cannot_assign_self_or_omit_eligible_item(self):
        pack = prepare(sample(), 5)
        for kind in ('self', 'omit', 'wrong_origin'):
            mapping = deepcopy(pack['mapping']); a = mapping['assignments'][0]
            first = next(iter(a['aliases']))
            if kind == 'self': a['aliases'][first] = {'submission_id': 'S1', 'authors': ['R1']}
            elif kind == 'omit': a['aliases'].pop(first)
            else: a['aliases'][first]['authors'] = ['R4']
            with self.assertRaises(ValueError): join(mapping, [], True)

    def test_losing_a_nonauthor_reviewer_is_not_silent_completion(self):
        d = sample(); d['reviewers'].append('observer')
        pack = prepare(d, 19)
        mapping = deepcopy(pack['mapping'])
        mapping['assignments'] = [a for a in mapping['assignments'] if a['reviewer_id'] != 'observer']
        rr = [r for r in reviews(pack) if r['reviewer_id'] != 'observer']
        with self.assertRaises(ValueError): join(mapping, rr)
        partial = join(pack['mapping'], rr, True)
        self.assertEqual(partial['status'], 'in_progress')
        self.assertEqual(len(partial['missing']), 4)
        self.assertEqual(join(pack['mapping'], reviews(pack))['status'], 'complete')

    def test_single_role_is_explicitly_skipped(self):
        d = sample(); d['reviewers'] = ['R1']; d['submissions'] = d['submissions'][:1]
        pack = prepare(d, 9)
        self.assertEqual(pack['panels'][0]['status'], 'skipped_no_eligible')
        result = join(pack['mapping'], [])
        self.assertEqual(result['skipped_reviewers'], ['R1'])
        self.assertEqual(result['assessments'], [])

    def test_invalid_provenance_is_rejected(self):
        for mutate in (
            lambda d: d['submissions'][0].update(authors=[]),
            lambda d: d['submissions'][0].update(authors=['outside']),
            lambda d: d['submissions'].append(deepcopy(d['submissions'][0])),
            lambda d: d['reviewers'].append('R1')):
            d = sample(); mutate(d)
            with self.assertRaises(ValueError): prepare(d)

    def test_cli_creates_only_prompts_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder); source = base/'in.json'; out = base/'pack'
            source.write_text(json.dumps(sample()), encoding='utf-8')
            command = [sys.executable, '-B', str(ROOT/'scripts/blind_review.py'), 'prepare',
                       str(source), '--output-dir', str(out), '--seed', '7']
            first = subprocess.run(command, capture_output=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            panel = json.loads((out/'panel-001.json').read_text())
            self.assertEqual(set(panel), {'criteria', 'candidates'})
            before = (out/'mapping.json').read_bytes()
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)
            self.assertEqual((out/'mapping.json').read_bytes(), before)
            pack = prepare(sample(), 7); rr = base/'reviews.json'; result = base/'result.json'
            rr.write_text(json.dumps(reviews(pack)))
            joined = subprocess.run([sys.executable, '-B', str(ROOT/'scripts/blind_review.py'),
                                     'join', str(out/'mapping.json'), str(rr), '--output', str(result)], capture_output=True)
            self.assertEqual(joined.returncode, 0, joined.stderr)
            self.assertEqual(json.loads(result.read_text())['status'], 'complete')


class ModeViewTests(unittest.TestCase):
    def test_legacy_session_keeps_approval_gate_and_template_is_readable(self):
        d = approved()
        for field in ('schema_version', 'depth', 'research', 'blind_review', 'execution'):
            d.pop(field, None)
        self.assertTrue(check(d)['can_run_rounds'])
        d['scope_approval']['status'] = 'pending'
        self.assertFalse(check(d)['valid'])

    def test_light_needs_reason_to_skip_freshness_but_not_scope(self):
        d = approved(); d['depth'] = 'light'; d['research'] = {'policy': 'not_applicable'}
        self.assertFalse(check(d)['valid'])
        d['research']['rationale'] = 'Compare wording against an immutable supplied document.'
        self.assertTrue(check(d)['valid'])
        d['scope_approval']['status'] = 'pending'
        self.assertFalse(check(d)['valid'])

    def test_full_retains_last30_and_bad_config_fails(self):
        d = approved(); d['research'] = {'policy': 'targeted'}
        self.assertFalse(check(d)['valid'])
        for field in ('research', 'execution', 'blind_review'):
            d = approved(); d[field] = []
            self.assertFalse(check(d)['valid'])

    def test_multi_model_requires_permission_available_models_and_card_origin(self):
        d = approved(); ex = d['execution']; ex['strategy'] = 'multi_model'
        self.assertFalse(check(d)['valid'])
        ex.update(model_change_authorized=True, models=['p/m1', 'p/m2'], availability='verified',
                  authorization={'source': 'user', 'turn_id': 'test', 'text': 'Use these models'})
        self.assertTrue(check(d)['valid'])
        d['phase'] = 'round1'; d['rounds'] = [{'number': 1, 'cards': [
            {'role_id': r['id'], 'content': 'Recorded argument'} for r in d['roles']]}]
        self.assertFalse(check(d)['valid'])
        for i, card in enumerate(d['rounds'][0]['cards']): card['model'] = ex['models'][i]
        self.assertTrue(check(d)['valid'])
        ex['models'] = ['p/m1', 'p/m1']; self.assertFalse(check(d)['valid'])

    def test_html_escapes_untrusted_text_and_shows_partial_and_missing_cards(self):
        d = approved(); d['phase'] = 'round1'; d['topic'] = '<script>alert(1)</script>'
        d['rounds'] = [{'number': 1, 'status': 'in_progress', 'cards': [
            {'role_id': 'r0', 'content': '<img src=x onerror=alert(1)>', 'amendment': 'Keep this correction'}]}]
        html = render(d)
        self.assertNotIn('<script>', html); self.assertNotIn('<img', html)
        self.assertIn('&lt;script&gt;', html); self.assertIn('&lt;img', html)
        self.assertIn('in_progress', html); self.assertIn('No recorded card', html)
        self.assertIn('Keep this correction', html)
        self.assertNotIn('<script src=', html); self.assertNotIn('<link ', html)

    def test_complete_cannot_hide_open_reviews(self):
        d = approved(); d['phase'] = 'complete'; d['max_rounds'] = 1
        d['rounds'] = [{'number': 1, 'cards': [{'role_id': r['id'], 'content': 'Recorded'} for r in d['roles']]}]
        d['result'] = {'conclusion': 'Conditional conclusion'}
        d['blind_review']['status'] = 'in_progress'
        self.assertFalse(check(d)['valid'])
        d['blind_review']['status'] = 'complete'
        self.assertTrue(check(d)['valid'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
