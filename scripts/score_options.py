"""Criteria-weighted subjective comparison, not voting on factual truth."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import sys

def number(x, name):
    if isinstance(x, bool) or not isinstance(x, (float, int)):
        raise ValueError(name + ' must be numeric')
    n = Decimal(str(x))
    if not n.is_finite():
        raise ValueError(name + ' must be finite')
    return n

def score(d):
    if not isinstance(d, dict):
        raise ValueError('Decision matrix must be an object')
    if d.get('mode') not in ['decision', 'creative']:
        raise ValueError('Do not score factual truth; this matrix is for decision/creative criteria')
    criteria = d.get('criteria')
    options = d.get('options')
    if not isinstance(criteria, list) or not criteria or not isinstance(options, list) or not options:
        raise ValueError('Nonempty criteria and options are required')
    weights = {}
    for c in criteria:
        if not isinstance(c, dict):
            raise ValueError('Criteria rows must be objects')
        key = c.get('id')
        if not isinstance(key, str) or not key or key in weights:
            raise ValueError('Criteria need unique IDs')
        w = number(c.get('weight'), 'weight')
        if w <= 0:
            raise ValueError('Weights must be positive')
        weights[key] = w
    total = sum(weights.values())
    rows, exact, seen = [], {}, set()
    for o in options:
        if not isinstance(o, dict):
            raise ValueError('Option rows must be objects')
        key = o.get('id')
        if not isinstance(key, str) or not key or key in seen:
            raise ValueError('Options need unique IDs')
        seen.add(key)
        scores = o.get('scores')
        if not isinstance(scores, dict) or set(scores) != set(weights):
            raise ValueError('Every criterion must have an explicit score; missing is not zero')
        ns = {c: number(scores[c], 'score') for c in weights}
        if any(v < 0 or v > 10 for v in ns.values()):
            raise ValueError('Scores must be between 0 and 10')
        if not isinstance(o.get('excluded', False), bool):
            raise ValueError('excluded must be boolean')
        excluded = o.get('excluded', False)
        reason = o.get('exclusion_reason', '')
        if excluded and (not isinstance(reason, str) or not reason.strip()):
            raise ValueError('Exclusion requires a reason')
        numerator = sum(weights[c] * ns[c] for c in weights)
        exact[key] = numerator / total
        rows.append({'id': key, 'score': float(exact[key].quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)),
                     'weighted_numerator': str(numerator), 'weight_total': str(total),
                     'excluded': excluded, 'exclusion_reason': reason,
                     'evidence_ids': o.get('evidence_ids', [])})
    eligible = [r['id'] for r in rows if not r['excluded']]
    best = max((exact[k] for k in eligible), default=None)
    winners = [k for k in eligible if exact[k] == best]
    return {'scores': rows, 'top_options': winners, 'exact_tie': len(winners) > 1,
            'ranking': sorted(eligible, key=lambda k: exact[k], reverse=True),
            'interpretation': 'Subjective criteria scores, not probability or factual validity',
            'tie_break': 'Requires an explicit reason; none applied by this script'}

if __name__ == '__main__':
    try:
        print(json.dumps(score(json.load(open(sys.argv[1], encoding='utf-8'))), ensure_ascii=False, indent=2))
    except (ValueError, TypeError, KeyError, OSError, IndexError, InvalidOperation) as e:
        print(json.dumps({'error': str(e)}, ensure_ascii=False))
        sys.exit(2)
