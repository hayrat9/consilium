"""Behavioral invariants for approval, retained coverage and arithmetic."""
from copy import deepcopy
from pathlib import Path
import json
import unittest
from session_check import check
from estimate_resources import estimate
from score_options import score

ROOT = Path(__file__).resolve().parents[1]

def approved(n=2):
    d = json.loads((ROOT/'assets/session.template.json').read_text())
    d.update(topic='Выбор способа очистки воды', phase='ready')
    d['disciplines'] = [dict(id=f'd{i}', name=f'Область{i}', question='Как меняется ответ?',
                              contribution='Отдельный аспект') for i in range(n)]
    d['scope_approval'] = dict(status='approved', version=1, source='user', turn_id='test-user-turn',
                               text='Утверждаю выбранные области', discipline_ids=[x['id'] for x in d['disciplines']])
    d['roles'] = [dict(id=f'r{i}', kind='professional', discipline_ids=[f'd{i}']) for i in range(n)]
    return d

class SessionTests(unittest.TestCase):
    def test_new_template_waits_for_user(self):
        r = check(json.loads((ROOT/'assets/session.template.json').read_text()))
        self.assertTrue(r['valid'])
        self.assertFalse(r['can_select_personas'])
        self.assertFalse(r['can_run_rounds'])

    def test_pending_cannot_run_even_with_selected_roles(self):
        d = approved(); d['scope_approval']['status'] = 'pending'
        d['phase'] = 'round1'
        self.assertFalse(check(d)['valid'])

    def test_scope_version_change_invalidates_old_approval(self):
        d = approved(); d['scope_version'] = 2
        self.assertFalse(check(d)['can_run_rounds'])

    def test_material_quote_is_not_user_approval(self):
        d = approved(); d['scope_approval']['source'] = 'document'
        self.assertFalse(check(d)['valid'])

    def test_many_approved_disciplines_are_not_silently_removed(self):
        d = approved(15)
        self.assertTrue(check(d)['can_run_rounds'])
        d['roles'].pop()
        self.assertFalse(check(d)['valid'])

    def test_named_role_needs_materials_and_limits(self):
        d = approved(); d['roles'][0]['kind'] = 'named_persona'
        self.assertFalse(check(d)['valid'])
        d['roles'][0].update(profile_basis='read', source_ids=['E1'], limits=['Ограниченная симуляция'])
        self.assertTrue(check(d)['valid'])

    def test_rounds_keep_all_roles_and_stop_at_completion(self):
        d = approved(); d['phase'] = 'complete'
        d['rounds'] = [{'number': 1, 'cards': [{'role_id': r['id'], 'content': 'Публичный аргумент роли'} for r in d['roles']]}]
        d['result'] = {'conclusion': 'Недостаточно данных;нужен контрольный замер'}
        d['stop_reason'] = 'Источники исчерпаны,новый раунд не добавит данных'
        self.assertTrue(check(d)['valid'])
        self.assertFalse(check(d)['can_run_rounds'])
        d['rounds'][0]['cards'].pop()
        self.assertFalse(check(d)['valid'])

    def test_round_limit_and_bad_root(self):
        d = approved(); d['phase'] = 'round2'; d['max_rounds'] = 1
        d['rounds'] = [{'number': i, 'cards': [{'role_id': r['id'], 'content': 'Аргумент роли'} for r in d['roles']]} for i in (1, 2)]
        self.assertIn('More rounds than planned', check(d)['errors'])
        self.assertFalse(check([])['valid'])

    def test_partial_wave_can_resume_without_losing_approved_coverage(self):
        d = approved(15); d['phase'] = 'round1'
        d['rounds'] = [{'number': 1, 'scope_version': 1, 'status': 'in_progress',
                        'cards': [{'role_id': f'r{i}', 'content': 'Первичная позиция'} for i in range(4)]}]
        self.assertTrue(check(d)['can_run_rounds'])
        d['rounds'][0]['status'] = 'complete'
        self.assertFalse(check(d)['valid'])

    def test_approved_new_scope_keeps_historical_round_unchanged(self):
        old = approved(2); d = approved(3)
        d['scope_version'] = 2; d['scope_approval']['version'] = 2; d['phase'] = 'round2'
        d['scope_history'] = [{'version': 1, 'discipline_ids': ['d0', 'd1'], 'role_ids': ['r0', 'r1'],
                              'approval': old['scope_approval']}]
        d['rounds'] = [{'number': 1, 'scope_version': 1, 'status': 'complete',
                        'cards': [{'role_id': f'r{i}', 'content': 'Сохранённый аргумент'} for i in range(2)]}]
        historical = deepcopy(d['rounds'])
        self.assertTrue(check(d)['can_run_rounds'])
        self.assertEqual(d['rounds'], historical)
        d['rounds'][0]['scope_version'] = 2
        self.assertFalse(check(d)['valid'])

    def test_cannot_jump_to_round3_or_complete_an_empty_shell(self):
        d = approved(); d['phase'] = 'round3'
        self.assertFalse(check(d)['valid'])
        d['phase'] = 'complete'; d['max_rounds'] = 1
        d['rounds'] = [{'number': 1, 'cards': [{'role_id': r['id']} for r in d['roles']]}]
        d['result'] = {'conclusion': 'Некоторый вывод'}
        self.assertFalse(check(d)['valid'])
        for c in d['rounds'][0]['cards']: c['content'] = 'Аргумент с указанными ограничениями'
        self.assertTrue(check(d)['valid'])
        d['result'] = None
        self.assertFalse(check(d)['valid'])

class EstimateTests(unittest.TestCase):
    def setUp(self):
        self.d = json.loads((ROOT/'assets/estimate.example.json').read_text())

    def test_baseline_is_exactly_100_and_not_actual_usage(self):
        out = estimate(self.d)
        self.assertEqual(out['formats'][0]['tokens_percent_of_baseline'], [100, 100])
        self.assertEqual(out['formats'][0]['minutes_percent_of_baseline'], [100, 100])
        self.assertFalse(out['is_actual_usage'])
        self.assertEqual(out['basis'], 'illustrative')

    def test_shared_analysis_percentage_and_separate_render(self):
        d = dict(basis='planning', assumptions=['Known example'], analysis_tokens=[100, 200],
                 analysis_minutes=[10, 20], baseline='text', formats=[
                 dict(id='text', extra_tokens=[10, 10], extra_minutes=[1, 1]),
                 dict(id='video', extra_tokens=[20, 20], extra_minutes=[2, 2], render_minutes=[30, 30])])
        v = estimate(d)['formats'][1]
        self.assertEqual(v['tokens_percent_of_baseline'], [104.8, 109.1])
        self.assertEqual(v['total_active_minutes'], [42, 52])
        self.assertEqual(v['total_tokens'], [120, 220])
        self.assertEqual(v['external_cost'], 'не оценено')

    def test_invalid_ranges_duplicate_and_zero_denominator_rejected(self):
        for value in [[-1, 2], [3, 1], [True, 3], [1, float('inf')]]:
            d = deepcopy(self.d); d['analysis_tokens'] = value
            with self.assertRaises(ValueError): estimate(d)
        d = deepcopy(self.d); d['formats'].append(d['formats'][0])
        with self.assertRaises(ValueError): estimate(d)
        d = deepcopy(self.d); d['analysis_tokens'] = [0, 0]; d['formats'][0]['extra_tokens'] = [0, 0]
        with self.assertRaises(ValueError): estimate(d)

class ScoreTests(unittest.TestCase):
    def setUp(self):
        self.d = dict(mode='decision', criteria=[dict(id='benefit', weight=3), dict(id='risk', weight=1)],
                      options=[dict(id='A', scores=dict(benefit=8, risk=4)),
                               dict(id='B', scores=dict(benefit=7, risk=7))])

    def test_exact_tie_preserved(self):
        out = score(self.d)
        self.assertTrue(out['exact_tie'])
        self.assertEqual(out['top_options'], ['A', 'B'])
        self.assertEqual([x['score'] for x in out['scores']], [7, 7])

    def test_rounding_does_not_create_false_tie(self):
        d = deepcopy(self.d); d['options'][0]['scores']['benefit'] = 8.01
        out = score(d)
        self.assertFalse(out['exact_tie'])
        self.assertEqual(out['top_options'], ['A'])
        self.assertEqual([x['score'] for x in out['scores']], [7, 7])

    def test_missing_score_is_not_zero(self):
        self.d['options'][0]['scores'].pop('risk')
        with self.assertRaises(ValueError): score(self.d)

    def test_hard_constraint_overrides_top_score(self):
        self.d['options'][0].update(scores=dict(benefit=10, risk=10), excluded=True, exclusion_reason='Не проходит обязательное условие')
        self.assertEqual(score(self.d)['top_options'], ['B'])

    def test_research_truth_not_voted_and_boolean_score_rejected(self):
        d = deepcopy(self.d); d['mode'] = 'research'
        with self.assertRaises(ValueError): score(d)
        self.d['options'][0]['scores']['risk'] = True
        with self.assertRaises(ValueError): score(self.d)

if __name__ == '__main__':
    unittest.main(verbosity=2)
