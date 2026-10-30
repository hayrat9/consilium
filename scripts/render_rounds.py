"""Render recorded session cards to standalone HTML; no network and no model calls."""
import argparse
from html import escape
import json
from pathlib import Path
from session_check import check


def render(data, *, artifact_dir=None):
    validation = check(data, artifact_dir=artifact_dir)
    if not validation['valid']:
        raise ValueError('; '.join(validation['errors']))
    def pretty(value):
        return escape(json.dumps(value, ensure_ascii=False, indent=2))
    def card_html(card):
        labels = {'content': 'Позиция / Position', 'position': 'Позиция / Position',
                  'arguments': 'Аргументы / Arguments', 'vote': 'Поддержка / Support',
                  'reason': 'Основания / Reasons', 'accepted_argument': 'Принятый довод / Accepted argument',
                  'amendment': 'Поправка / Amendment', 'amendments': 'Поправки / Amendments',
                  'remaining_disagreement': 'Разногласие / Disagreement',
                  'what_changes_my_view': 'Что изменит мнение / What changes the view',
                  'source_ids': 'Источники / Sources', 'model': 'Модель / Model'}
        blocks = []
        for key, label in labels.items():
            if key not in card:
                continue
            value = card[key]
            text = escape(value) if isinstance(value, str) else pretty(value)
            blocks.append('<div class="argument"><strong>' + label + '</strong><div class="text">' + text + '</div></div>')
        blocks.append('<details><summary>Все поля / All fields</summary><pre>' + pretty(card) + '</pre></details>')
        return ''.join(blocks)
    rounds = data.get('rounds', [])
    role_names = {r['id']: r.get('name', r['id']) for r in data.get('roles', [])}
    role_ids = list(role_names)
    for row in rounds:
        for card in row.get('cards', []):
            if card['role_id'] not in role_ids:
                role_ids.append(card['role_id'])
    headers = ''.join('<th scope="col">R' + str(r['number']) + '<br>'
                      + escape(str(r.get('status', 'complete'))) + '<br>scope '
                      + escape(str(r.get('scope_version', data.get('scope_version')))) + '</th>' for r in rounds)
    rows = []
    for rid in role_ids:
        cells = []
        for row in rounds:
            card = next((c for c in row.get('cards', []) if c['role_id'] == rid), None)
            cells.append('<td>' + card_html(card) + '</td>' if card is not None
                         else '<td>Нет записанной карточки / No recorded card</td>')
        rows.append('<tr><th scope="row">' + escape(str(role_names.get(rid, rid)))
                    + '<br>' + escape(rid) + '</th>' + ''.join(cells) + '</tr>')
    details = ''.join('<details><summary>R' + str(row['number']) + ' — полная запись / record</summary><pre>'
                      + pretty(row) + '</pre></details>' for row in rounds)
    return '''<!doctype html><html lang="ru"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Consilium — раунды / rounds</title>
<style>body{font:16px/1.5 system-ui,sans-serif;color:#202938;background:#f6f7fb;margin:0;padding:24px}
main{max-width:1500px;margin:auto}h1{font-size:1.7rem}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.55 ui-monospace,monospace}
section,details,.table{background:white;border:1px solid #d8dce5;border-radius:10px;padding:16px;margin:16px 0}
.table{overflow:auto}table{border-collapse:collapse;min-width:760px;width:100%;table-layout:fixed}th,td{border:1px solid #d8dce5;padding:12px;vertical-align:top;overflow-wrap:anywhere}
th{background:#eef2fa}thead th:first-child{width:15%}.argument{margin-bottom:16px}.argument strong{font-size:13px;color:#506078}.text{white-space:pre-wrap;overflow-wrap:anywhere;margin-top:4px}td details{padding:8px;margin:8px 0}summary{cursor:pointer}small{color:#506078}@media(max-width:600px){body{padding:12px}}
</style><main><h1>''' + escape(data.get('topic') or 'Consilium') + '''</h1>
<p>Фаза / phase: <strong>''' + escape(str(data.get('phase'))) + '''</strong> · depth: ''' + escape(str(data.get('depth', 'full'))) + '''</p>
<small>Только записанные публичные аргументы. Отсутствующие позиции не восстановлены.
AI-перспективы, не заседание людей. Только для просмотра после закрытия анонимных оценок.</small>
<section><h2>Итог / Result</h2><pre>''' + pretty(data.get('result')) + '''</pre></section>
<div class="table"><table><thead><tr><th scope="col">Роль / Role</th>''' + headers + '''</tr></thead><tbody>''' + ''.join(rows) + '''</tbody></table></div>''' + details + '''
<details><summary>Состав, исполнение и пределы / Scope, execution and limits</summary><pre>''' + pretty({
        k: data.get(k) for k in ('scope_version', 'scope_approval', 'scope_history', 'disciplines',
                                  'roles', 'execution', 'research', 'blind_review', 'unresolved', 'stop_reason',
                                  'protocol_version', 'decision_contract', 'claims', 'critical_check', 'position_changes')}) + '''</pre></details>
</main></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        html = render(json.loads(args.session.read_text(encoding='utf-8')), artifact_dir=args.session.resolve().parent)
        with args.output.open('x', encoding='utf-8') as output:
            output.write(html)
        print(args.output)
    except (ValueError, TypeError, OSError) as error:
        parser.exit(2, str(error) + '\n')


if __name__ == '__main__':
    main()
