"""Scenario arithmetic for one shared analysis and alternative output formats."""
import json
import math
import sys

def interval(v, name):
    if not isinstance(v, list) or len(v) != 2:
        raise ValueError(name + ' must be [low, high]')
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0 for x in v):
        raise ValueError(name + ' must contain finite nonnegative numbers')
    if v[0] > v[1]:
        raise ValueError(name + ' low exceeds high')
    return v

def plus(a, b):
    return [a[0] + b[0], a[1] + b[1]]

def percent(shared, extra, baseline):
    # Same analysis in numerator and denominator: correlated across formats.
    if shared[0] + baseline[0] <= 0:
        raise ValueError('Baseline must have positive cost for percentage comparison')
    candidates = [(a + e) / (a + b) * 100 for a in shared for e in extra for b in baseline]
    return [round(min(candidates), 1), round(max(candidates), 1)]

def estimate(d):
    if not isinstance(d, dict):
        raise ValueError('Estimate input must be an object')
    basis = d.get('basis')
    if basis not in ['illustrative', 'planning', 'measured']:
        raise ValueError('basis must be illustrative, planning or measured')
    if not isinstance(d.get('assumptions'), list) or not d['assumptions']:
        raise ValueError('Explicit assumptions are required')
    at = interval(d.get('analysis_tokens'), 'analysis_tokens')
    am = interval(d.get('analysis_minutes'), 'analysis_minutes')
    formats = d.get('formats')
    if not isinstance(formats, list) or not formats:
        raise ValueError('Nonempty formats are required')
    by_id = {}
    for f in formats:
        if not isinstance(f, dict) or not isinstance(f.get('id'), str) or not f['id'] or f['id'] in by_id:
            raise ValueError('Formats need unique nonempty IDs')
        by_id[f['id']] = {
            'id': f['id'], 'label': f.get('label', f['id']),
            'extra_tokens': interval(f.get('extra_tokens'), 'extra_tokens'),
            'extra_minutes': interval(f.get('extra_minutes'), 'extra_minutes'),
            'render_minutes': interval(f.get('render_minutes', [0, 0]), 'render_minutes'),
            'external_cost': f.get('external_cost', 'не оценено')}
    baseline = d.get('baseline')
    if baseline not in by_id:
        raise ValueError('Baseline format not found')
    base = by_id[baseline]
    base_minutes = plus(base['extra_minutes'], base['render_minutes'])
    if at[0] + base['extra_tokens'][0] <= 0 or am[0] + base_minutes[0] <= 0:
        raise ValueError('Baseline tokens and minutes must be positive')
    rows = []
    for key, f in by_id.items():
        minutes = plus(f['extra_minutes'], f['render_minutes'])
        pt = [100.0, 100.0] if key == baseline else percent(at, f['extra_tokens'], base['extra_tokens'])
        pm = [100.0, 100.0] if key == baseline else percent(am, minutes, base_minutes)
        rows.append({**f, 'total_tokens': plus(at, f['extra_tokens']),
                     'total_active_minutes': plus(am, minutes),
                     'tokens_percent_of_baseline': pt, 'minutes_percent_of_baseline': pm,
                     'additional_tokens_percent': [round(x - 100, 1) for x in pt],
                     'additional_minutes_percent': [round(x - 100, 1) for x in pm]})
    return {'basis': basis, 'is_actual_usage': False, 'baseline': baseline,
            'assumptions': d['assumptions'], 'formats': rows,
            'limitations': ['Scenario, not a promise or automatic monetary estimate',
                            'Shared analysis is the same across alternative formats',
                            'Sequential stage model; user waiting excluded',
                            'Text tokens do not include unknown media-service billing']}

if __name__ == '__main__':
    try:
        print(json.dumps(estimate(json.load(open(sys.argv[1], encoding='utf-8'))), ensure_ascii=False, indent=2))
    except (ValueError, TypeError, KeyError, OSError, IndexError) as e:
        print(json.dumps({'error': str(e)}, ensure_ascii=False))
        sys.exit(2)
