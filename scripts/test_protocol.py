"""Checks for explicit outcomes and recorded review coverage in protocol 1.2."""
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
from blind_review import prepare, join
from self_test import approved
from session_check import check


def finished(root, count=2):
    d = approved(count)
    d.update(protocol_version='1.2', phase='complete', mode='decision')
    d['decision_contract'] = {'stage': 'test', 'acceptance_criteria': ['A reversible test with no claim of proven demand']}
    d['claims'] = [{'id': 'C1', 'text': 'H1 may be worth testing', 'kind': 'hypothesis',
                    'support': 'unknown', 'evidence_refs': [], 'limits': 'No sales observed'}]
    d['critical_check'] = {'assumption_and_refutation': 'Price is not evidence of purchases.',
                           'simpler_or_no_action': 'One customer interview before building.',
                           'strongest_objection': 'Demand may not exist.', 'response': 'Only a bounded test is proposed.'}
    d['rounds'] = [{'number': n, 'scope_version': 1, 'status': 'complete',
                    'cards': [{'role_id': r['id'], 'content': 'Recorded argument with limits.'} for r in d['roles']]}
                   for n in (1, 2, 3)]
    d['result'] = {'conclusion': 'Test H1, demand remains unknown.', 'outcome': 'candidate_for_test',
                   'selected_options': ['H1'], 'basis': 'Reversible low-cost learning.', 'limits': ['No proven demand.']}
    ids = [r['id'] for r in d['roles']]
    pack = prepare({'criteria': [{'id': 'proof', 'question': 'What is supported?'}], 'reviewers': ids,
                    'submissions': [{'id': f'S{i}', 'authors': [rid], 'content': 'Position with limits.'}
                                    for i, rid in enumerate(ids)]}, 12)
    rr = [{'reviewer_id': panel['reviewer_id'], 'assessments': [
        {'alias': c['alias'], 'verdict': 'amend', 'reason': 'The conclusion must retain uncertainty.'}
        for c in panel['prompt']['candidates']]} for panel in pack['panels']]
    for name, obj in [('mapping.json', pack['mapping']), ('reviews.json', rr), ('results.json', join(pack['mapping'], rr))]:
        (root/name).write_text(json.dumps(obj))
    d['blind_review'].update(status='complete', blinding='metadata_only', mapping_file='mapping.json',
                             reviews_file='reviews.json', results_file='results.json')
    return d


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.d = finished(self.root)

    def check(self, d=None):
        return check(self.d if d is None else d, artifact_dir=self.root)

    def test_marked_complete_without_started_review_is_rejected(self):
        self.d['blind_review']['status'] = 'not_started'
        self.assertFalse(check(self.d)['valid'])

    def test_recorded_complete_review_and_bounded_test_pass(self):
        self.assertTrue(self.check()['valid'])

    def test_complete_flag_without_artifacts_is_not_enough(self):
        (self.root/'reviews.json').unlink()
        self.assertFalse(self.check()['valid'])
        self.assertFalse(check(self.d)['valid'])

    def test_missing_assessment_cannot_be_hidden_by_complete_result(self):
        rr = json.loads((self.root/'reviews.json').read_text()); rr[0]['assessments'].clear()
        (self.root/'reviews.json').write_text(json.dumps(rr))
        self.assertFalse(self.check()['valid'])

    def test_saved_result_must_match_recomputed_coverage(self):
        r = json.loads((self.root/'results.json').read_text()); r['assessments'][0]['reason'] = 'Changed after join'
        (self.root/'results.json').write_text(json.dumps(r))
        self.assertFalse(self.check()['valid'])

    def test_reviewers_must_match_the_completed_R2_scope(self):
        self.d['roles'][0]['id'] = 'replacement'
        for row in self.d['rounds']: row['cards'][0]['role_id'] = 'replacement'
        self.assertFalse(self.check()['valid'])

    def test_artifact_paths_cannot_escape_session_directory(self):
        self.d['blind_review']['reviews_file'] = '../outside.json'
        self.assertFalse(self.check()['valid'])
        self.d['blind_review']['reviews_file'] = str(self.root/'reviews.json')
        self.assertFalse(self.check()['valid'])

    def test_single_role_has_recorded_no_eligible_exception(self):
        d = finished(self.root, 1); d['blind_review'].update(status='skipped_no_eligible', exception_reason='Only one author; no independent peer.')
        self.assertTrue(self.check(d)['valid'])
        d['blind_review']['exception_reason'] = ''
        self.assertFalse(self.check(d)['valid'])

    def test_exception_cannot_skip_existing_eligible_reviewers(self):
        self.d['blind_review'].update(status='skipped_no_eligible', exception_reason='Saving tokens')
        self.assertFalse(self.check()['valid'])

    def test_stop_before_R2_requires_reason_and_cannot_claim_action(self):
        self.d['rounds'] = self.d['rounds'][:1]
        self.d['blind_review']['status'] = 'not_started'
        self.d['stop_reason'] = 'No additional evidence; stop before peer review.'
        self.d['result'].update(outcome='insufficient_evidence', selected_options=[])
        self.assertTrue(self.check()['valid'])
        self.d['result'].update(outcome='candidate_for_test', selected_options=['H1'])
        self.assertFalse(self.check()['valid'])

    def test_early_stop_after_R2_still_requires_completed_review(self):
        self.d['rounds'] = self.d['rounds'][:2]; self.d['stop_reason'] = 'No further useful information.'
        self.assertTrue(self.check()['valid'])
        self.d['blind_review']['status'] = 'not_started'
        self.assertFalse(self.check()['valid'])

    def test_unknown_or_failed_options_do_not_require_a_winner(self):
        for outcome in ('insufficient_evidence', 'no_option_passed'):
            self.d['result'].update(outcome=outcome, selected_options=[])
            self.assertTrue(self.check()['valid'])
        self.d['result']['selected_options'] = ['H1']
        self.assertFalse(self.check()['valid'])

    def test_action_requires_the_action_stage_and_declared_basis(self):
        self.d['result']['outcome'] = 'action_supported'
        self.assertFalse(self.check()['valid'])
        self.d['decision_contract']['stage'] = 'act'
        self.assertTrue(self.check()['valid'])
        self.d['result']['basis'] = ''
        self.assertFalse(self.check()['valid'])

    def test_hypothesis_type_can_have_support_but_needs_evidence(self):
        c = self.d['claims'][0]; c['support'] = 'supported'
        self.assertFalse(self.check()['valid'])
        c['evidence_refs'] = ['bounded-local-observation']
        self.assertTrue(self.check()['valid'])
        c['support'] = 'VERIFIED'
        self.assertFalse(self.check()['valid'])

    def test_verification_records_result_time_and_scope(self):
        self.d['claims'][0]['verification'] = {'method': 'Downloaded the page'}
        self.assertFalse(self.check()['valid'])
        self.d['claims'][0]['verification'].update(result='Price present, no purchase evidence.', checked_at='2026-10-30', scope='Published price only')
        self.assertTrue(self.check()['valid'])

    def test_critical_check_not_replaced_by_a_winner_score(self):
        self.d['critical_check'] = None
        self.assertFalse(self.check()['valid'])

    def test_research_can_finish_without_selecting_an_option(self):
        self.d['mode'] = 'research'; self.d['decision_contract'] = None
        self.d['result'].update(outcome='analysis', selected_options=[])
        self.assertTrue(self.check()['valid'])

    def test_old_session_is_read_with_warning_and_not_rewritten(self):
        self.d.pop('protocol_version'); self.d['blind_review']['status'] = 'not_started'
        before = deepcopy(self.d); result = self.check()
        self.assertTrue(result['valid']); self.assertEqual(self.d, before)
        self.assertTrue(any('Legacy' in x for x in result['warnings']))

    def test_missing_blind_block_cannot_bypass_R2_gate(self):
        self.d.pop('blind_review')
        self.assertFalse(self.check()['valid'])

    def test_unknown_mode_is_not_silently_research(self):
        self.d.update(mode='decison', decision_contract=None)
        self.d['result'].update(outcome='analysis', selected_options=[])
        self.assertFalse(self.check()['valid'])

    def test_complete_review_needs_an_actual_blinding_mode(self):
        self.d['blind_review']['blinding'] = 'not_started'
        self.assertFalse(self.check()['valid'])

    def test_research_mode_cannot_declare_a_selected_test_or_action(self):
        self.d.update(mode='research', decision_contract=None)
        self.assertFalse(self.check()['valid'])

    def test_unknown_protocol_is_not_silently_legacy(self):
        self.d['protocol_version'] = 'future'
        self.assertFalse(self.check()['valid'])


if __name__ == '__main__': unittest.main(verbosity=2)
