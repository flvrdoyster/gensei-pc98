"""
빌드·번들·배포 공용 파이프라인
==============================

editor.py(타이틀별 번역 에디터)와 dashboard 모드가 공유하는 순수 함수 모음.
전부 title 인자를 받고 dict를 반환한다 — HTTP 응답은 호출자(editor.py Handler)가 쓴다.

파이프라인 4단계:
  translation/<t>/translation.json
    → build/<t>/<disks>            (build)
      → emulator/rom/<disks> + emulator/<t>.data   (bundle)
        → docs/<t>.data             (deploy — tools/deploy-docs.sh, 전 타이틀 공용)
"""

import filecmp
import os
import re
import shutil
import subprocess
import sys
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lint  # noqa: E402  (빌드 시 검수 통합)

TITLES = {
    'hukyou':   '환세풍광전',
    'kaitou':   '환세쾌도전',
    'torimono': '환세포물장',
    'kitan':    '환세희담',
}

# 타이틀별 번들에 포함되는 디스크 (emulator/rom/ 에 복사되는 파일명)
TITLE_DISKS = {
    'hukyou':   ('hukyou_kr.fdi',),
    'kaitou':   ('kaitou_kr.fdi',),
    'torimono': ('torimono_kr.hdi',),
    'kitan':    ('kitan-system.fdi', 'kitan-data.fdi', 'kitan-demo.fdi'),
}

# emsdk file_packager.py 경로 (번들 재생성용)
FILE_PACKAGER = os.path.expanduser(
    '~/GitHub/emsdk/upstream/emscripten/tools/file_packager.py'
)


def has_inserter(title):
    return os.path.exists(os.path.join(PROJECT_ROOT, 'tools', f'{title}_inserter.py'))


def has_emulator(title):
    return os.path.exists(os.path.join(PROJECT_ROOT, 'emulator', f'{title}.js'))


def translation_path(title):
    return os.path.join(PROJECT_ROOT, 'translation', title, 'translation.json')


# ── 빌드 ──────────────────────────────────────────────────────────────

def build(title):
    """인서터 실행 → translation.json 을 원본 디스크에 삽입 (build/<title>/).
    반환: {ok, message, output, warnings}"""
    game_dir = os.path.join(PROJECT_ROOT, 'original', title)
    inserter = os.path.join(PROJECT_ROOT, 'tools', f'{title}_inserter.py')
    try:
        proc = subprocess.run(
            ['python3', inserter, game_dir],
            capture_output=True, text=True, timeout=60,
            cwd=PROJECT_ROOT,
        )
    except Exception as e:
        return {'ok': False, 'message': str(e), 'output': '', 'warnings': []}

    output = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 0:
        last = output.splitlines()[-1] if output else '빌드 실패'
        return {'ok': False, 'message': f'빌드 실패: {last}', 'output': output, 'warnings': []}

    lines = output.splitlines()
    n_trunc = sum(1 for l in lines if '초과, 잘림' in l)
    # 인서터별 출력 형식이 달라 두 가지 모두 인식:
    #  hukyou/kitan: "<file>: N건 교체, ..." (파일별 여러 줄)
    #  kaitou:       "패치: N줄 / M청크, ..."
    file_lines = [l for l in lines if '건 교체' in l]
    if file_lines:
        n_files = len(file_lines)
        n_items = sum(int(l.split('건 교체')[0].split()[-1]) for l in file_lines)
        msg = f'빌드 완료 — {n_files}개 파일 {n_items}건 교체'
    elif (m := re.search(r'패치:\s*(\d+)줄\s*/\s*(\d+)청크', output)):
        msg = f'빌드 완료 — {m.group(2)}개 청크 {m.group(1)}줄 교체'
    else:
        msg = '빌드 완료 (교체 항목 없음)'

    warnings = []
    if n_trunc:
        msg += f' · ⚠ {n_trunc}줄 길이초과 잘림'
        warnings.append(f'{n_trunc}줄 길이초과 잘림')

    # 검수 lint 통합 (빠른 검사 — 무거운 offset 검사는 제외).
    # 깨진문자·잘림은 버그라 warn=True, 일관성은 정보만.
    warn = n_trunc > 0
    try:
        lr = lint.analyze(title, check_offset=False)
        parts = []
        if lr.get('broken'):
            parts.append(f"깨진문자 {len(lr['broken'])}")
            warn = True
        if lr.get('conflicts'):
            parts.append(f"일관성 {len(lr['conflicts'])}")
        if parts:
            msg += ' · lint: ' + ' / '.join(parts)
            warnings.extend(parts)
    except Exception:
        pass

    return {'ok': not warn, 'message': msg, 'output': output, 'warnings': warnings}


# ── 번들 ──────────────────────────────────────────────────────────────

def _repackage_bundle(title, fdi_names):
    """공통 번들 재생성: emulator/bios + 지정 FDI들 → file_packager로 묶고
    emulator/<title>.js의 loadPackage 메타데이터 갱신. data_size 반환.
    실패 시 RuntimeError raise."""
    emulator_dir = os.path.join(PROJECT_ROOT, 'emulator')
    rom_dir      = os.path.join(emulator_dir, 'rom')
    bios_dir     = os.path.join(emulator_dir, 'bios')
    data_path    = os.path.join(emulator_dir, f'{title}.data')
    js_path      = os.path.join(emulator_dir, f'{title}.js')

    if not os.path.exists(FILE_PACKAGER):
        raise RuntimeError(f'file_packager.py 없음: {FILE_PACKAGER}')

    tmpdir = tempfile.mkdtemp(prefix=f'{title}-bundle-')
    loader_js = os.path.join(tmpdir, 'loader.js')
    try:
        tmp_bios = os.path.join(tmpdir, 'bios')
        tmp_rom  = os.path.join(tmpdir, 'rom')
        os.makedirs(tmp_bios)
        os.makedirs(tmp_rom)
        # font_jp.bmp: 미지 반각 코드 글리프 판독용 로컬 참고 자료일 뿐, 번들에는 불필요
        # (게임은 font.bmp만 참조 — 번들에 넣으면 524KB 낭비)
        for f in os.listdir(bios_dir):
            if not f.startswith('.') and f != 'font_jp.bmp':
                shutil.copy2(os.path.join(bios_dir, f), tmp_bios)
        for fdi in fdi_names:
            src = os.path.join(rom_dir, fdi)
            if os.path.exists(src):
                shutil.copy2(src, tmp_rom)

        proc = subprocess.run(
            ['python3', FILE_PACKAGER, data_path,
             '--js-output=' + loader_js,
             '--preload', 'bios@/emulator/np2kai',
             '--preload', 'rom@/rom'],
            capture_output=True, text=True, timeout=120, cwd=tmpdir,
        )
        if proc.returncode != 0:
            raise RuntimeError(f'file_packager 실패: {proc.stderr.strip()[-300:]}')

        with open(loader_js, 'r') as f:
            loader_content = f.read()
        meta_match = re.search(r'"files":\s*(\[.*?\]),\s*"remote_package_size":\s*(\d+)', loader_content)
        if not meta_match:
            raise RuntimeError('메타데이터 추출 실패')
        new_files = meta_match.group(1)
        new_size  = meta_match.group(2)

        with open(js_path, 'r') as f:
            js_content = f.read()
        js_content = re.sub(
            r'loadPackage\(\{(?:"files"|files):\s*\[.*?\],\s*(?:"remote_package_size"|remote_package_size):\s*\d+\}\)',
            f'loadPackage({{"files":{new_files},"remote_package_size":{new_size}}})',
            js_content,
        )
        with open(js_path, 'w') as f:
            f.write(js_content)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return os.path.getsize(data_path)


def _build_disk_full_paths(title):
    """(필수 디스크 경로 목록, 선택 디스크 경로 목록). 선택 = 희담 데모(오프닝 미번역이면
    없을 수 있음 — 빌드 실패로 보지 않는다)."""
    if title == 'kitan':
        core = [os.path.join(PROJECT_ROOT, 'build', 'kitan', n)
                 for n in ('kitan-system.fdi', 'kitan-data.fdi')]
        optional = [os.path.join(PROJECT_ROOT, 'build', 'kitan-demo', 'kitan-demo.fdi')]
        return core, optional
    build_dir = os.path.join(PROJECT_ROOT, 'build', title)
    core = [os.path.join(build_dir, n) for n in TITLE_DISKS[title]]
    return core, []


def _bundle_shared_input_paths():
    """모든 타이틀 번들에 공통으로 들어가는 입력(폰트 등 emulator/bios/*) —
    _repackage_bundle 의 복사 대상 필터와 반드시 동일해야 한다. 이 목록이 번들 신선도
    판정에서 빠지면, 폰트만 바뀌고 어떤 타이틀의 build/ 디스크도 안 바뀐 경우 —
    실제로는 모든 타이틀의 .data 가 구식 폰트를 담은 채인데도 '번들됨'으로 잘못 표시된다."""
    bios_dir = os.path.join(PROJECT_ROOT, 'emulator', 'bios')
    if not os.path.isdir(bios_dir):
        return []
    return [
        os.path.join(bios_dir, f) for f in os.listdir(bios_dir)
        if not f.startswith('.') and f != 'font_jp.bmp'
    ]


def bundle(title):
    """build/ 의 패치 디스크를 emulator/rom/ 에 복사하고 emulator/<title>.data 재생성.
    희담은 데모 디스크 패치를 먼저 시도(실패해도 계속 진행 — 오프닝 미번역이면 정상).
    반환: {ok, message, output, warnings, data_size}"""
    warnings = []
    output = ''

    if title == 'kitan':
        build_dir = os.path.join(PROJECT_ROOT, 'build', 'kitan')
        for fdi_name in ('kitan-system.fdi', 'kitan-data.fdi'):
            p = os.path.join(build_dir, fdi_name)
            if not os.path.exists(p):
                return {'ok': False, 'code': 400,
                        'message': f'빌드 결과 없음: {p} — 먼저 빌드하세요.',
                        'output': '', 'warnings': []}

        demo_inserter = os.path.join(PROJECT_ROOT, 'tools', 'kitan_demo_inserter.py')
        demo_game_dir = os.path.join(PROJECT_ROOT, 'original', 'kitan', 'data')
        try:
            proc = subprocess.run(['python3', demo_inserter, demo_game_dir],
                                   capture_output=True, text=True, timeout=60, cwd=PROJECT_ROOT)
            output = (proc.stdout + proc.stderr).strip()
            if proc.returncode != 0:
                warnings.append('데모 디스크 스킵됨 (kitan_demo_inserter 실패)')
        except Exception as e:
            warnings.append(f'데모 디스크 스킵됨 ({e})')

        rom_dir = os.path.join(PROJECT_ROOT, 'emulator', 'rom')
        demo_build = os.path.join(PROJECT_ROOT, 'build', 'kitan-demo', 'kitan-demo.fdi')
        try:
            shutil.copy(os.path.join(build_dir, 'kitan-system.fdi'), rom_dir)
            shutil.copy(os.path.join(build_dir, 'kitan-data.fdi'), rom_dir)
            if os.path.exists(demo_build):
                shutil.copy(demo_build, rom_dir)
            elif '데모 디스크 스킵됨' not in ' '.join(warnings):
                warnings.append('데모 디스크 없음 — 번들에서 제외')
        except Exception as e:
            return {'ok': False, 'code': 500, 'message': f'디스크 복사 실패: {e}',
                    'output': output, 'warnings': warnings}

        try:
            data_size = _repackage_bundle('kitan',
                ('kitan-system.fdi', 'kitan-data.fdi', 'kitan-demo.fdi'))
        except Exception as e:
            return {'ok': False, 'code': 500, 'message': f'번들 재생성 실패: {e}',
                    'output': output, 'warnings': warnings}

        msg = f'에뮬레이터 업데이트 완료 — 번들 재생성 ({data_size:,} bytes)'
        return {'ok': True, 'message': msg, 'output': output, 'warnings': warnings, 'data_size': data_size}

    # hukyou / kaitou / torimono — 단일/복수 디스크 공통
    disk_names = TITLE_DISKS[title]
    build_dir = os.path.join(PROJECT_ROOT, 'build', title)
    rom_dir   = os.path.join(PROJECT_ROOT, 'emulator', 'rom')

    for disk_name in disk_names:
        build_disk = os.path.join(build_dir, disk_name)
        if not os.path.exists(build_disk):
            return {'ok': False, 'code': 400,
                    'message': f'빌드 결과 없음: {build_disk} — 먼저 빌드하세요.',
                    'output': '', 'warnings': []}

    try:
        for disk_name in disk_names:
            shutil.copy(os.path.join(build_dir, disk_name), os.path.join(rom_dir, disk_name))
    except Exception as e:
        return {'ok': False, 'code': 500, 'message': f'디스크 복사 실패: {e}',
                'output': '', 'warnings': []}

    try:
        data_size = _repackage_bundle(title, disk_names)
    except Exception as e:
        return {'ok': False, 'code': 500, 'message': f'번들 재생성 실패: {e}',
                'output': '', 'warnings': []}

    msg = f'에뮬레이터 업데이트 완료 — 번들 재생성 ({data_size:,} bytes)'
    return {'ok': True, 'message': msg, 'output': '', 'warnings': [], 'data_size': data_size}


# ── 배포 ──────────────────────────────────────────────────────────────

def deploy(force=False):
    """tools/deploy-docs.sh 실행 (emulator→docs 동기화 + 정합 검사). 커밋·버전 미변경.
    반환: {ok, message, output}"""
    script = os.path.join(PROJECT_ROOT, 'tools', 'deploy-docs.sh')
    args = ['bash', script]
    if force:
        args.append('-f')
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=60, cwd=PROJECT_ROOT,
        )
    except Exception as e:
        return {'ok': False, 'message': str(e), 'output': ''}

    out = (proc.stdout + proc.stderr).strip()
    if proc.returncode == 0:
        return {'ok': True, 'message': 'docs 동기화·정합 검사 통과', 'output': out}
    bad = [l.strip() for l in out.splitlines()
           if any(s in l for s in ('⚠', '✗', '실패', '의심'))]
    msg = ' / '.join(bad) if bad else (out.splitlines()[-1] if out else 'docs 배포 실패')
    return {'ok': False, 'message': 'docs 배포: ' + msg, 'output': out}


def predict_deploy_block(title):
    """deploy-docs.sh 0단계(빌드 신선도)를 그대로 재현: json·데이터가 둘 다 git clean이면
    스킵(통과), 아니면 mtime 비교. True = 이 타이틀 때문에 배포가 막힘."""
    json_path = translation_path(title)
    data_path = os.path.join(PROJECT_ROOT, 'emulator', f'{title}.data')
    if not os.path.exists(json_path) or not os.path.exists(data_path):
        return False
    try:
        clean = subprocess.run(
            ['git', 'diff', '--quiet', 'HEAD', '--', json_path, data_path],
            cwd=PROJECT_ROOT, capture_output=True,
        ).returncode == 0
    except Exception:
        clean = False
    if clean:
        return False
    return os.path.getmtime(json_path) > os.path.getmtime(data_path)


# ── 상태 ──────────────────────────────────────────────────────────────

def _stage(path_a_list, path_b):
    """path_a_list(선행 산출물들) → path_b(후행 산출물) mtime 비교.
    'missing'(b 없음) / 'stale'(a가 더 최신) / 'ok'"""
    if not os.path.exists(path_b):
        return 'missing'
    existing_a = [p for p in path_a_list if os.path.exists(p)]
    if not existing_a:
        return 'missing'
    if max(os.path.getmtime(p) for p in existing_a) > os.path.getmtime(path_b):
        return 'stale'
    return 'ok'


def _synced(src, dst):
    """emulator/<f> ↔ docs/<f> 동기 여부. 'missing' / 'stale' / 'ok'.
    deploy-docs.sh 는 `cp -r` 로 복사하므로 동기 상태면 dst mtime ≥ src mtime 이다 —
    크기+mtime 으로 먼저 걸러 수 MB 짜리 .data 전수 비교를 대부분 피한다."""
    if not os.path.exists(src) or not os.path.exists(dst):
        return 'missing'
    try:
        s_st, d_st = os.stat(src), os.stat(dst)
        if s_st.st_size != d_st.st_size:
            return 'stale'
        if d_st.st_mtime >= s_st.st_mtime:
            return 'ok'
        return 'ok' if filecmp.cmp(src, dst, shallow=False) else 'stale'
    except Exception:
        return 'stale'


def _iter_rel_files(root):
    """root 아래 전체 파일의 상대경로. 숨김 파일·디렉토리(.DS_Store 포함) 제외 —
    deploy-docs.sh 의 `diff --exclude='.DS_Store'` 와 기준을 맞춘다."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        for fn in filenames:
            if fn.startswith('.'):
                continue
            yield os.path.relpath(os.path.join(dirpath, fn), root)


def shared_status():
    """타이틀별 <t>.data/<t>.js 를 뺀 **나머지 emulator/ 전체**의 docs/ 동기 여부.
    version.js·audio.js·bios/ 등은 어느 타이틀에도 안 묶이는데 deploy-docs.sh 는
    `cp -r emulator/*` 로 통째로 복사한다 — 이걸 안 보면 버전만 올린 배포를 놓친다.
    반환: {'state': 'ok'|'stale'|'missing', 'files': [상대경로...]}"""
    emulator_dir = os.path.join(PROJECT_ROOT, 'emulator')
    docs_dir = os.path.join(PROJECT_ROOT, 'docs')
    per_title = {f'{t}{ext}' for t in TITLES for ext in ('.data', '.js')}

    out_of_sync = []
    state = 'ok'
    for rel in _iter_rel_files(emulator_dir):
        if rel in per_title:
            continue
        st = _synced(os.path.join(emulator_dir, rel), os.path.join(docs_dir, rel))
        if st != 'ok':
            out_of_sync.append(rel)
            state = 'missing' if st == 'missing' and state != 'stale' else 'stale'
    return {'state': state, 'files': sorted(out_of_sync)[:20]}


def title_status(title):
    """title 하나의 4단계 상태. 반환:
    {build, bundle, deploy, deploy_blocked, demo(kitan만)}"""
    core, optional = _build_disk_full_paths(title)
    json_path = translation_path(title)
    data_path = os.path.join(PROJECT_ROOT, 'emulator', f'{title}.data')

    if not all(os.path.exists(p) for p in core):
        build_stage = 'missing'
    else:
        # 같은 빌드 실행에서 나온 파일들이라 mtime이 사실상 동일 — 가장 오래된
        # 산출물을 기준으로 비교(보수적 판정).
        oldest_build_mtime = min(os.path.getmtime(p) for p in core)
        build_stage = 'stale' if os.path.getmtime(json_path) > oldest_build_mtime else 'ok'

    # 번들 비교엔 존재하는 선택 디스크(희담 데모) + 공용 입력(폰트 등 bios/*)도 포함 —
    # 데모만 새로 빌드됐거나, 어느 타이틀 build/ 도 안 바뀌었지만 폰트만 바뀐 경우를 놓치지 않게.
    bundle_stage = _stage(
        core + [p for p in optional if os.path.exists(p)] + _bundle_shared_input_paths(),
        data_path,
    )

    # 배포는 <t>.data 와 <t>.js(loadPackage 메타) 둘 다 봐야 한다.
    js_path = os.path.join(PROJECT_ROOT, 'emulator', f'{title}.js')
    docs_dir = os.path.join(PROJECT_ROOT, 'docs')
    deploy_parts = [
        _synced(data_path, os.path.join(docs_dir, f'{title}.data')),
        _synced(js_path, os.path.join(docs_dir, f'{title}.js')),
    ]
    if 'stale' in deploy_parts:
        deploy_stage = 'stale'
    elif 'missing' in deploy_parts:
        deploy_stage = 'missing'
    else:
        deploy_stage = 'ok'

    result = {
        'build': build_stage,
        'bundle': bundle_stage,
        'deploy': deploy_stage,
        'deploy_blocked': predict_deploy_block(title),
    }
    if title == 'kitan':
        result['demo'] = 'ok' if os.path.exists(optional[0]) else 'missing'
    return result


def status():
    """전 타이틀 상태 + 공용 파일 상태.
    {'titles': {t: {...}}, 'shared': {'state', 'files'}}"""
    titles = {}
    for title, title_kr in TITLES.items():
        s = title_status(title)
        s['title_kr'] = title_kr
        s['has_inserter'] = has_inserter(title)
        s['has_emulator'] = has_emulator(title)
        titles[title] = s
    return {'titles': titles, 'shared': shared_status()}


# ── 커밋 ──────────────────────────────────────────────────────────────

# 대시보드 커밋의 범위. tools/ 등 이 파이프라인과 무관한 작업 중인 코드 변경은
# 절대 안 건드린다 — 번역 커밋에 무관한 코드가 쓸려 들어가면 안 되므로.
COMMIT_SCOPE = ('translation', 'emulator', 'docs')

_PER_TITLE_SUFFIXES = ('.data', '.js')


def _title_of_path(rel_path):
    """commit_status() 의 상대경로 하나가 어느 타이틀 소관인지: 'json'|'bundle'|'docs'|None."""
    for t in TITLES:
        if rel_path.startswith(f'translation/{t}/'):
            return t, 'json'
        if rel_path in (f'emulator/{t}{ext}' for ext in _PER_TITLE_SUFFIXES):
            return t, 'bundle'
        if rel_path in (f'docs/{t}{ext}' for ext in _PER_TITLE_SUFFIXES):
            return t, 'docs'
    return None, None


def _draft_commit_message(files):
    """변경 파일 목록에서 커밋 메시지 초안 생성. 사용자가 대시보드에서 그대로 쓰거나
    고쳐 쓴다 — 완벽할 필요는 없고 출발점만 되면 된다."""
    paths = [f['path'] for f in files]
    stage = {}  # title -> 'docs' > 'bundle' > 'json' (가장 진행된 단계로 표시)
    rank = {'json': 0, 'bundle': 1, 'docs': 2}
    shared = []

    for p in paths:
        t, kind = _title_of_path(p)
        if t is None:
            shared.append(p)
            continue
        if t not in stage or rank[kind] > rank[stage[t]]:
            stage[t] = kind

    by_stage = {'json': [], 'bundle': [], 'docs': []}
    for t, kind in stage.items():
        by_stage[kind].append(TITLES[t])

    parts = []
    if by_stage['docs']:
        parts.append(f"{'·'.join(by_stage['docs'])} 번역 반영 및 배포")
    if by_stage['bundle']:
        parts.append(f"{'·'.join(by_stage['bundle'])} 빌드 갱신")
    if by_stage['json']:
        parts.append(f"{'·'.join(by_stage['json'])} 번역 작업")
    if shared:
        parts.append('공용 리소스 갱신' if parts else '웹 에뮬 공용 리소스 갱신')

    return ' / '.join(parts) if parts else '번역 작업'


def commit_status():
    """COMMIT_SCOPE 안의 git 변경 파일 + 자동 커밋 메시지 초안.
    반환: {'files': [{'path','status'}...], 'message': str}"""
    try:
        proc = subprocess.run(
            ['git', 'status', '--porcelain', '--'] + list(COMMIT_SCOPE),
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=15,
        )
    except Exception as e:
        return {'files': [], 'message': '', 'error': str(e)}

    files = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        st = line[:2].strip()
        path = line[3:].strip()
        if ' -> ' in path:  # rename: "old -> new"
            path = path.split(' -> ', 1)[1]
        files.append({'path': path, 'status': st})

    return {'files': files, 'message': _draft_commit_message(files)}


def commit(message):
    """COMMIT_SCOPE 를 git add 후 커밋. 스코프 밖(tools/ 등)은 절대 add 하지 않는다.
    반환: {ok, message, output}"""
    message = (message or '').strip()
    if not message:
        return {'ok': False, 'message': '커밋 메시지가 비어 있습니다.'}

    try:
        add_proc = subprocess.run(
            ['git', 'add', '--'] + list(COMMIT_SCOPE),
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30,
        )
        if add_proc.returncode != 0:
            return {'ok': False, 'message': f'git add 실패: {add_proc.stderr.strip()}'}

        # 스테이징된 게 없으면(다른 세션이 먼저 커밋했거나 이미 clean) 빈 커밋 방지.
        staged = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=PROJECT_ROOT)
        if staged.returncode == 0:
            return {'ok': False, 'message': '커밋할 변경사항이 없습니다.'}

        commit_proc = subprocess.run(
            ['git', 'commit', '-m', message],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30,
        )
        out = (commit_proc.stdout + commit_proc.stderr).strip()
        if commit_proc.returncode != 0:
            return {'ok': False, 'message': f'커밋 실패: {out[-300:]}', 'output': out}
        return {'ok': True, 'message': '커밋 완료', 'output': out}
    except Exception as e:
        return {'ok': False, 'message': str(e)}
