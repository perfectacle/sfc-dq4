"""MesenCE 사용자 설정 파일(settings.json)의 자리와 해시. 읽은 바이트 캐시(sfc/dq4/tools/dq4readset.py)와 회귀 가드의
검사 단위 캐시(tools/guards.py)가 같은 것을 키에 넣는다. 명령줄로 고정하지 않은 설정(콜백 시간 제한 등)도 결과에 닿는다."""
import hashlib
import os
import sys
from pathlib import Path


def settings_path(mesence):
    """MesenCE 가 읽는 settings.json. 실행 파일 옆에 있으면 포터블 모드라 그것을, 아니면 사용자 설정 폴더의 것을 읽는다.
    MESENCE_SAVES 는 배터리 기록을 찾는 곳일 뿐 MesenCE 의 설정 위치를 바꾸지 않아 보지 않는다."""
    portable = Path(mesence).resolve().parent / 'settings.json'
    if portable.is_file():
        return portable
    home = Path.home()
    if sys.platform == 'darwin':
        return home / 'Library/Application Support/MesenCE/settings.json'
    if sys.platform == 'win32':
        return Path(os.environ.get('APPDATA', home)) / 'MesenCE/settings.json'
    return Path(os.environ.get('XDG_CONFIG_HOME', home / '.config')) / 'MesenCE/settings.json'


def settings_digest(mesence):
    """설정 파일 원 바이트의 SHA-256. 파일이 없으면 None."""
    p = settings_path(mesence)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
