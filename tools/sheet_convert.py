"""
번역 스프레드시트 변환기
========================

사용법:
  python3 tools/sheet_convert.py export    translation.json → TSV (stdout)
  python3 tools/sheet_convert.py import    TSV (stdin) → translation.json 업데이트

예시:
  python3 tools/sheet_convert.py export > translation.tsv
  # 구글 시트에서 편집 후 TSV로 다운로드
  python3 tools/sheet_convert.py import < translation.tsv
"""

import csv
import json
import os
import sys

TRANS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'translation', 'hukyou', 'translation.json',
)


def export_tsv():
    with open(TRANS_PATH, encoding='utf-8') as f:
        data = json.load(f)

    writer = csv.writer(sys.stdout, delimiter='\t', lineterminator='\n')
    writer.writerow(['type', 'file', 'index', 'offset', 'jp', 'kr'])

    for dialog in data['dialogs']:
        for line in dialog['lines']:
            writer.writerow([
                'dialog', dialog['file'], dialog['index'],
                line['offset'], line['jp'], line['kr'],
            ])

    for item in data.get('items', []):
        writer.writerow([
            'item_name', 'MESSAGE.CMD', '',
            item['name']['offset'], item['name']['jp'], item['name']['kr'],
        ])
        if 'stat' in item:
            writer.writerow([
                'item_stat', 'MESSAGE.CMD', '',
                item['stat']['offset'], item['stat']['jp'], item['stat']['kr'],
            ])
        for desc in item['desc']:
            writer.writerow([
                'item_desc', 'MESSAGE.CMD', '',
                desc['offset'], desc['jp'], desc['kr'],
            ])

    for entry in data.get('ui', []):
        writer.writerow([
            'ui', 'GF2.COM', entry.get('category', ''),
            entry['offset'], entry['jp'], entry['kr'],
        ])


def import_tsv():
    with open(TRANS_PATH, encoding='utf-8') as f:
        data = json.load(f)

    kr_map = {}
    reader = csv.reader(sys.stdin, delimiter='\t')
    header = next(reader)
    for row in reader:
        if len(row) < 6:
            continue
        typ, file, index, offset, jp, kr = row[:6]
        kr_map[(typ, int(offset))] = kr

    updated = 0
    for dialog in data['dialogs']:
        for line in dialog['lines']:
            key = ('dialog', line['offset'])
            if key in kr_map:
                if kr_map[key] != line['kr']:
                    line['kr'] = kr_map[key]
                    updated += 1

    for item in data.get('items', []):
        key = ('item_name', item['name']['offset'])
        if key in kr_map and kr_map[key] != item['name']['kr']:
            item['name']['kr'] = kr_map[key]
            updated += 1
        if 'stat' in item:
            key = ('item_stat', item['stat']['offset'])
            if key in kr_map and kr_map[key] != item['stat']['kr']:
                item['stat']['kr'] = kr_map[key]
                updated += 1
        for desc in item['desc']:
            key = ('item_desc', desc['offset'])
            if key in kr_map and kr_map[key] != desc['kr']:
                desc['kr'] = kr_map[key]
                updated += 1

    for entry in data.get('ui', []):
        key = ('ui', entry['offset'])
        if key in kr_map and kr_map[key] != entry['kr']:
            entry['kr'] = kr_map[key]
            updated += 1

    with open(TRANS_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f'{updated}건 업데이트')


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in ('export', 'import'):
        print('usage: python3 tools/sheet_convert.py [export|import]')
        sys.exit(1)

    if sys.argv[1] == 'export':
        export_tsv()
    else:
        import_tsv()
