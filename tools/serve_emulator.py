"""
로컬 에뮬레이터 서버
====================

사용법:
  python3 tools/serve_emulator.py [--port 9801] [--no-open]

emulator/ 를 정적 서빙하고 인덱스 페이지를 브라우저로 자동 연다.
번역 에디터(tools/editor.py, 포트 8182)와는 별개 — 그쪽은 번역·빌드/번들/배포용,
이건 결과물을 실제로 눈으로 확인하는 용도.
"""

import argparse
import functools
import http.server
import os
import sys
import threading
import webbrowser

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMULATOR_DIR = os.path.join(PROJECT_ROOT, 'emulator')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=9801)  # PC-9801
    ap.add_argument('--no-open', action='store_true')
    args = ap.parse_args()

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=EMULATOR_DIR)
    try:
        server = http.server.HTTPServer(('127.0.0.1', args.port), handler)
    except OSError as e:
        print(f'포트 {args.port} 를 열 수 없습니다: {e}')
        print('이미 에뮬레이터 서버가 떠 있지 않은지 확인하세요.')
        sys.exit(1)

    url = f'http://localhost:{args.port}/'
    print(f'에뮬레이터: {url}')
    print('종료: Ctrl+C')

    # 서버를 백그라운드로 먼저 띄운다 — serve_forever() 전에 브라우저를 열면
    # 연결 거부를 맞는다 (editor.py 와 동일 패턴).
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f'(브라우저 자동 실행 실패 — 직접 열어주세요: {e})')

    try:
        server_thread.join()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
