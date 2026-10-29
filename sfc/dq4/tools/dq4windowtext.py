"""창 글자 한글 표(dq4windowname.asm 의 WnText). dq4windowname.apply 가 부른다.
형식은 sfc/dq4/docs/dq4-window-text-format.md 「창 글자」.

롬의 이름 표(21:955D, BRK 88 2B 가 읽는 표)를 일본어 이름으로 nds/dq4/tables/adopt.tsv 의 DS 일본어와 잇고, 맞는 이름만
Galmuri9 그림으로 바꾼다. 번호가 아니라 이름으로 잇는 것은 DQ4 데이터를 옮겨 번호가 바뀌어도 그대로 쓰기 위해서다.
맞지 않는 이름은 표에 넣지 않아 원래 가나로 찍힌다.

뱅크 TEXT_BANK:
  8000 + 종류 × 200  이름 번호 256개 × 16비트: 그림의 뱅크 안 주소, 0 = 없음. 종류 FIXED_KIND 는 창 고정 문구
  9000               고정 문구 번호 256개 × 16비트: 캔버스 밖 전용 칸의 첫 칸, 0 = 일반 슬롯
  9200~              [열 수][열마다 9바이트: 위 줄 7줄째, 글자 줄 8줄](1bpp, bit7 = 왼쪽 점)
글자의 맨 윗줄이 위 줄 타일의 7줄째, 나머지 여덟 줄이 글자 줄에 온다(상태 창 이름과 같은 배치).
"""
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DQ5_TOOLS = HERE.parents[1] / 'dq5' / 'tools'
ADOPT = ROOT / 'nds' / 'dq4' / 'tables' / 'adopt.tsv'

TEXT_BANK = 0x58
INDEX = 0x8000
SAFE = 0x9000                   # 고정 문구 번호 256개 × 16비트: 캔버스 밖 전용 칸의 첫 칸, 0 = 일반 슬롯
DATA = 0x9200
# 이름 표 번호 → (adopt.tsv 의 표, 창 이름 칸의 최대 열 수, 넘으면 멈출지). 주문 창(28)은 두 칸 넓혀 일곱 칸이고,
# 그보다 긴 이름(몬스터 특기 「얼어붙은 눈보라」)은 가나로 둔다. 전투 몬스터 목록(창 1B)은 이름 아홉 칸이라 넘는 이름은 가나.
KINDS = {5: ('아이템', 10, True), 3: ('주문·특기', 7, False), 4: ('몬스터', 9, False), 6: ('작전', 10, True),
         2: ('성별', 3, True), 1: ('직함', 10, False)}
# adopt.tsv 에 없는 DQ5 고유 이름(빌드가 키를 kana_key 꼴로 바꿈). 작전은 고정 문구 FIXED 와 같은 한글
# 표 2 는 성별 둘(adopt.tsv 능력치·직업 4·5) 뒤에 몬스터 종족이 이어짐. DQ4 동료는 사람뿐이라 성별만 한글로
# 표 1 은 강함 보기의 직함(D2, 사람이면 $43 = 1). DQ5 주인공 직함은 adopt.tsv 에 없어 새로 옮김
EXTRA_NAMES = {6: {'みんながんばれ': '모두 힘내자', 'じゅもんせつやく': '주문 아끼자'}, 2: {'おとこ': '남자', 'おんな': '여자'},
               1: {'パパスのむすこ': '파파스의 아들', 'やどやのむすめ': '여관집 딸', 'ラインハットおうじ': '라인하트 왕자',
                   'しんでんのドレイ': '신전의 노예', 'にげたドレイ': '도망친 노예', 'さすらいのたびびと': '떠돌이 나그네',
                   'モンスターつかい': '몬스터 조련사', 'グランバニアおう': '그란바니아 왕', 'ようせいびと': '요정',
                   'グランバニアへいし': '그란바니아 병사', 'めしつかい': '하인', 'ゆうしゃのちちおや': '용사의 아버지',
                   'でんせつのゆうしゃ': '전설의 용사', 'おとこ': '남자', 'おんな': '여자'}}
# 전투 작전 창(16)은 작전 이름을 넉 자씩 두 줄로 찍는다(04:BB61). 한글은 띄어쓰기 자리에서 나눠 줄마다 고정 문구 하나
TACTIC_LINES = (('한방에', '끝내자구'), ('모두', '힘내자'), ('주문', '아끼자'),
                ('주문을', '쓰지마'), ('생명을', '소중히'), ('명령을', '내려줘'))
# 한글이 없는 이름도 필드에서는 가나 칸을 슬롯으로 돌려 써 원래 가나 타일로 찍으면 깨진다. 필드 창에 나오는 물건 표는
# 원래 가나를 Galmuri9 가나 그림으로 넣는다(창 열 수를 넘는 이름은 뺌). 뱅크가 모자라 주문(3)은 넣지 않는다(한글 없는
# 주문은 DQ5 전용 주문과 몬스터 행동). 몬스터(4)는 전투에서만 나와 가나 칸이 살아 있다
KANA_KINDS = (5,)
SHIFT = 6                       # render 의 띠(한글 윗줄 = 1줄)를 위 줄 7줄로 내림

# 창 레코드의 가나 항목을 접두 9E k(고정 문구 k)로 바꾼다. 이름 표가 쓰지 않는 종류 7 에 그림을 둔다.
FIXED_KIND = 7
FIXED_PREFIX = 0x9E
# 창 번호 → 오른쪽으로 넓힐 칸 수. 명령 창은 한 항목이 네 칸이라 adopt.tsv 의 긴 이름(「강한 정도」·「조사하다」)
# 대신 두 자 낱말로 줄였다. 「どうする」 창은 「건네기」 석 자가 들어가게 한 칸 넓힌다.
# 09 さくせん, 0B つよさ(「강함 보기」 가 들어가게 한 칸 넓힘), 0A·1F 작전(필드·전투, 열 열 「한방에 끝내자구」 가 들어가게 두 칸), 0F 지금 작전(커서 + 이름 열 칸), 19·1A·87·88 전투 첫 창, 1C·1D·1E 전투 명령 창,
# 33 가게, 3C 교회, 51·52·54 맡기는 곳, 32 예/아니요·62 아니요/예(「아니요」 네 열이 들어가게 한 칸), 5A 혼자일 때의 さくせん,
# 4B 쓰기/장비, 4E 보물상자/아이템, 59 동료 맡기는 곳(안쪽 8열이라 짧게), 75 동료 넣고 빼기, 77 기록, 7E 마차 바꾸기(「모두 바꾸기」 가 들어가게 두 칸), 20 그대로/보기/끝
# 코드가 $01~ 버퍼에 베껴 04:B808·04:BC08 로 찍는 문자열 목록(FF 로 끝남). 버퍼 첫 바이트 9E 면 훅이 고정 문구 $02 로
# 그리므로, 자리(표 오프셋)를 지키도록 9E k + 빈칸으로 바꾼다. 04:C2BF 는 04:C25D 가 고르는 장비 비교 라벨
# (첫 「？？？」 는 그대로), 04:C14D 는 04:BA60 이 베끼는 「そうびしない」(04:C14C 의 FE 항목이기도 함)
# 04:C511 은 04:C44D 가 베끼는 가게 동료 창(3A)의 상태 「そうびしている / もっている / そうびできない / もっていない」
INLINE_STRINGS = ((0x04C2C5, 0x04C2E7), (0x04C14D, 0x04C155), (0x04C511, 0x04C536))
FIXED_WINDOWS = {0x01: 0, 0x10: 1, 0x09: 0, 0x0B: 1,
                 0x19: 0, 0x1A: 0, 0x87: 0, 0x88: 0, 0x1C: 0, 0x1D: 0, 0x1E: 0, 0x33: 0,
                 0x0A: 2, 0x1F: 2, 0x0F: 1, 0x3C: 0, 0x51: 0, 0x52: 0, 0x54: 0, 0x32: 1, 0x5A: 0, 0x62: 1,
                 0x4B: 0, 0x4E: 0, 0x59: 0, 0x75: 0, 0x77: 0, 0x7E: 2, 0x20: 0}
FIXED = {
    'はなす': '대화', 'じゅもん': '주문', 'つよさ': '강함', 'どうぐ': '도구',
    'そうび': '장비', 'さくせん': '작전', 'とびら': '문', 'しらべる': '조사',
    'つかう': '쓰기', 'わたす': '건네기', 'すてる': '버리기',
    'ならびかえをする': '대열 바꾸기', 'さくせんをねる': '작전 짜기',
    'ＨＰとＭＰ': 'HP와 MP', 'こうげきカ': '공격력', 'つよさみる': '강함 보기', 'まんたん': '만땅',
    'たたかう': '싸우기', 'いれかえ': '교체', 'にげる': '도망',
    'こうげき': '공격', 'とくぎ': '특기', 'ぼうぎょ': '방어',
    'かいにきた': '사기', 'うりにきた': '팔기', 'やめる': '그만',
    # 작전. adopt.tsv 의 DS 이름(사용자 결정 포함)을 쓰고, DQ5 고유 둘은 DS 의 가까운 작전에 맞춘다
    # (みんながんばれ = DS バッチリがんばれ 「모두 힘내자」, じゅもんせつやく 는 새로 「주문 아끼자」)
    'ガンガンいこうぜ': '한방에 끝내자구', 'みんながんばれ': '모두 힘내자', 'じゅもんせつやく': '주문 아끼자',
    'じゅもんつかうな': '주문을 쓰지마', 'いのちだいじに': '생명을 소중히', 'めいれいさせろ': '명령을 내려줘',
    # 강함 보기의 능력치 라벨(adopt.tsv 능력치·직업 표). DQ5 창은 力 자리에 가타카나 カ 를 씀
    'ちから': '힘', 'すばやさ': '민첩', 'みのまもり': '방어력', 'かしこさ': '현명함', 'うんのよさ': '운',
    'さいだいＨＰ': '최대HP', 'さいだいＭＰ': '최대MP', 'しゅびカ': '수비력', 'せいべつ': '성별',
    # 교회(adopt.tsv 메뉴 202~206 을 전용 칸 48칸에 들어가게 줄임)와 맡기는 곳(300·301)
    'おいのりをする': '기도하기', 'おつげをきく': '계시', 'いきかえらせる': '소생', 'どくのちりょう': '해독',
    'のろいをとく': '저주 풀기', 'あずける': '맡기기', 'ひきだす': '꺼내기', 'もちもの': '소지품', 'おかね': '돈',
    'ぼうぐ': '방어구', 'ぶき': '무기', 'はい': '예', 'いいえ': '아니요',
    # 장비 비교 창의 라벨과 장비 목록 끝 항목(INLINE_STRINGS)
    'こうげきりょく': '공격력', 'しゅびりょく': '수비력', 'そうびしない': '장비 해제',
    # 가게 동료 창의 상태(INLINE_STRINGS). 이름 뒤 빈칸을 문구에 둔다
    '\u3000そうびしている': ' 장비 중', '\u3000\u3000もっている': ' 가짐', '\u3000そうびできない': ' 장비 불가',
    '\u3000もっていない': ' 없음',
    'たからばこ': '보물상자', 'アイテム': '아이템', 'あずけにきた': '맡기기', 'むかえにきた': '데려가기',
    'ようすをみる': '상태 보기', 'わかれにきた': '헤어지기', 'なかまをくわえる': '동료 넣기', 'なかまをはずす': '동료 빼기',
    'ぼうけんのしょに': '모험의 서에', 'キロクする': '기록', 'おはなしのつづきをプレイする': '이야기를 계속한다',
    'いれかえ': '바꾸기', 'そうがえ': '모두 바꾸기', 'みる': '보기', 'そのまま': '그대로', 'おわり': '끝',
    # 한 줄 창(LINE_WINDOWS)은 줄 전체가 문구 하나. 빈칸 01 은 \u3000
    'じゅもんはつかえない': '주문을 못 쓴다', 'じゅもんを\u3000まだ\u3000おぼえていない': '아직 주문을 익히지 않았다',
    'どうぐを\u3000もっていない': '가진 도구가 없다',
}
# 창 제목(04:AD78 목록). 표에 없는 제목(이름 뒤 「の１」, 이름 입력 등)은 가나로 둔다.
TITLES = {
    'コマンド': '명령', 'どうする': '어떻게', 'だれに': '누구에게', 'どこへ': '어디로',
    'ぶき': '무기', 'せんとう': '전투', 'だれの': '누구의', 'だれが': '누가', 'のどうぐ': '의 도구',
    'せんとうじゅもん': '전투 주문', 'のじゅもん': '의 주문', 'しょうひＭＰ': '소비 MP', 'だれを': '누구를',
    'よろい': '갑옷', 'たて': '방패', 'かぶと': '투구', 'レベル': '레벨', 'しゅび': '수비', 'ぼうぐ': '방어구',
    'せんとうとくぎ': '전투 특기', 'のとくぎ': '의 특기', 'だれと': '누구와', 'だれがたたかう': '누가 싸울까',
}
# 메시지 창과 함께 뜨는 창(명령 창 01, 가게 33. 가게 창은 화면 오른쪽 끝이라 넓히지 못해 「그만두기」 를 「그만」 으로)의 문구는
# 걷는 메시지 캔버스(096~17F) 밖 전용 칸 1D0~1FF 에 둔다. 창마다 1D0 부터 채우고, 서로 함께 뜨지 않는 창끼리는 같은 칸을
# 겹쳐 쓴다(창을 그릴 때마다 다시 올림). 메시지와 함께 뜨는 다른 창(예/아니요 32·62, 교회 3C, 맡기는 곳 51·52·54)은 명령 창과
# 함께 뜰 수 있어 전용 칸 대신, 캔버스 밖인 가나 칸 슬롯을 먼저 고르는 일반 슬롯을 쓴다.
SAFE_WINDOWS = {
    0x01: ('はなす', 'じゅもん', 'つよさ', 'どうぐ', 'そうび', 'さくせん', 'とびら', 'しらべる'),
    0x33: ('かいにきた', 'うりにきた', 'やめる'),
}
SAFE_FIRST = 0x1D0
SAFE_TILES = 0x30
# 라벨 창: 줄 머리 빈칸(01) + 가나 + 85(:) 꼴로 오른쪽 정렬된 라벨. 빈칸과 가나를 빈칸 + 9E k 로 바꿔 「:」 자리를 둔다.
# 07 강함 보기 능력치, 06 강함 보기 성별·레벨
LABEL_WINDOWS = (0x07, 0x06)
# 항목 머리 FE 없이 한 줄을 찍는 창. 2D じゅもんはつかえない, 82 じゅもんを まだ おぼえていない, 83 どうぐを もっていない
LINE_WINDOWS = (0x2D, 0x82, 0x83)
TITLE_COUNT = 0x2B              # 제목 2B 부터는 목록 뒤의 코드


def kana_key(text):
    """가타카나를 히라가나로, 빈칸을 빼서 표기 차이를 무시한다."""
    return ''.join(chr(ord(c) - 0x60) if 0x30A1 <= ord(c) <= 0x30F6 else c for c in text if c not in ' 　')


def rom_names(data, table, count=256):
    if str(DQ5_TOOLS) not in sys.path:
        sys.path.insert(0, str(DQ5_TOOLS))
    import dq5text
    from dq5map import Rom
    rom = Rom(bytes(data))
    return [dq5text.text(dq5text.string_codes(rom, dq5text.string(rom, table, n))) for n in range(count)]


def adopted(table):
    with open(ADOPT, encoding='utf-8') as f:
        return {kana_key(r['DS 일본어']): r['채택'] for r in csv.DictReader(f, delimiter='\t')
                if r['표'] == table and r['채택']}


def columns(font, text):
    """한글 문자열 → 열마다 9바이트(위 줄 7줄째 + 글자 줄 8줄). 위 줄의 나머지 일곱 줄은 비어 있어 두지 않는다."""
    import dq4menupatch
    out = []
    for col in dq4menupatch.render(font, text):
        if any(any(row) for row in col[16 - SHIFT:]):
            raise ValueError(f'{text!r}: 글자가 글자 줄 아래로 넘침')
        rows = [[0] * 8] * SHIFT + col[:16 - SHIFT]
        if any(any(row) for row in rows[:7]):
            raise ValueError(f'{text!r}: 글자가 위 줄 7줄째보다 위로 넘침')
        out.append(bytes(int(''.join(map(str, r)), 2) for r in rows[7:]))
    return out


def phrases():
    """고정 문구 [(일본어, 한글, 전용 칸 창 또는 None)]. 번호 k 는 이 순서(FE·FF 를 넘지 않음). SAFE_WINDOWS 의 문구가
    앞에서 창마다 따로 번호를 받고, 같은 낱말이 다른 창·제목에 나오면 뒤에서 일반 번호를 또 받는다(전용 칸의 위 줄 합성은
    그 창 자리에 맞춰져 있음)."""
    out = [(jp, FIXED[jp], w) for w, jps in SAFE_WINDOWS.items() for jp in jps]
    rest = dict(FIXED)
    for jp, ko in TITLES.items():
        rest.setdefault(jp, ko)
    out += [(jp, ko, None) for jp, ko in rest.items()]
    return out + [(f'作戦{n}{half}', ko, None) for n, pair in enumerate(TACTIC_LINES) for half, ko in zip('上下', pair)]


def tactic_first():
    """TACTIC_LINES 의 첫 번호. 작전 n 의 윗줄은 + 2n, 아랫줄은 + 2n + 1."""
    return len(phrases()) - 2 * len(TACTIC_LINES)


def safe_bases(font):
    """번호 k → 전용 칸의 첫 칸. 창마다 SAFE_FIRST 부터 열 수 × 2 칸씩."""
    out, used = {}, {}
    for k, (jp, ko, w) in enumerate(phrases()):
        if w is None:
            continue
        at = used.get(w, 0)
        out[k] = SAFE_FIRST + at
        used[w] = at + 2 * len(columns(font, ko))
        if used[w] > SAFE_TILES:
            raise ValueError(f'창 {w:02X}: 전용 칸 {used[w]}칸이 {SAFE_TILES}칸을 넘음')
    return out


def _runs(rom, rec, i, start_ok, stop=()):
    """rec[i] 부터 가나 한 덩이: (끝, 칸 수, 일본어). 탁점 접두 84·83(제목은 92·93)은 칸을 차지하지 않는다.
    stop 의 부호에서 끊는다."""
    import dq5text
    j, n = i, 0
    while j < len(rec) and 0x02 <= rec[j] < 0xB0 and rec[j] not in stop:
        j += 2 if rec[j] in (0x83, 0x84, 0x92, 0x93) else 1
        n += 1
    raw = rec[i:j].replace(b'\x92', b'\x84').replace(b'\x93', b'\x83')
    return j, n, dq5text.text(dq5text.string_codes(rom, raw))


def fixed_records(data, font):
    """FIXED_WINDOWS 의 창 레코드와 제목 목록을 고쳐 쓴 [(파일 자리, 새 바이트)]와 문구 번호 {일본어: k}.
    가나 n 칸과 그 뒤 빈칸 s 개를 9E k 와 빈칸 (n + s − 한글 열 수) 개로 바꿔, 뒤 항목의 열 자리와
    04:B0F0 의 칸 셈($0ADE)을 원래와 같게 둔다. 창 본문은 항목 머리 FE 바로 뒤만 바꾼다."""
    if str(DQ5_TOOLS) not in sys.path:
        sys.path.insert(0, str(DQ5_TOOLS))
    import dq4menupatch
    import dq5text
    from dq5map import Rom
    rom = Rom(bytes(data))
    table = phrases()
    numbers, safe = {}, {}
    for k, (jp, _, w) in enumerate(table):
        if w is None:
            numbers.setdefault(jp, k)
        else:
            safe[w, jp] = k
    width = {jp: len(columns(font, ko)) for jp, ko, _ in table}
    korean = {jp: ko for jp, ko, _ in table}

    def lorom(addr):
        return ((addr >> 16) & 0x7F) * 0x8000 + (addr & 0x7FFF)

    def window(w):
        # 메뉴와 함께 쓰는 창(dq4menupatch.SHARED)은 창 표가 낮은 WRAM 사본을 가리키므로, 게임 안에서 그 자리로
        # 복사하는 원래 레코드(SHARED_JP)를 고친다
        addr, rec = dq5text.window(rom, w)
        if addr & 0xFFFF >= 0x8000:
            return addr, rec
        addr = dq4menupatch.SHARED_JP + (addr & 0xFFFF) - dq4menupatch.SHARED_WRAM
        rec = bytes(rom.u8(addr + i) for i in range(0x40))
        end = next(i for i in range(1, len(rec)) if rec[i] == 0x80 and rec[i - 1] == 0xFF)
        return addr, rec[:end + 1]

    out = []
    for w, widen in FIXED_WINDOWS.items():
        addr, rec = window(w)
        start = rec.index(0xFE)
        # 한 줄에 항목이 여럿이면(명령 창·전투 작전 창) 열마다 가장 넓은 항목에 맞춰 빈칸을 채워 열을 맞춘다
        # 빈칸 뒤에 가나가 이어지는 줄(77 「ぼうけんのしょに　キロクする」)은 뒤 덩이도 문구로 바꾼다
        parts, row, col, i = [], 0, 0, start
        while i < len(rec):
            head = 0x02 <= rec[i] < 0xB0 and rec[i - 1] == 0xFE
            more = col and 0x10 <= rec[i] <= 0x7A and rec[i - 1] == 0x01
            if not (head or more):
                parts.append(rec[i])
                if rec[i] == 0xFF:
                    row, col = row + 1, 0
                i += 1
                continue
            j, n, jp = _runs(rom, rec, i, True)
            if jp not in FIXED or (w in SAFE_WINDOWS and (w, jp) not in safe):
                raise ValueError(f'창 {w:02X}: 「{jp}」 의 한글 문구가 없음')
            k = safe[w, jp] if w in SAFE_WINDOWS else numbers[jp]
            sp = 0
            while j + sp < len(rec) and rec[j + sp] == 0x01:
                sp += 1
            last = j + sp >= len(rec) or rec[j + sp] == 0xFF
            parts.append((k, jp, max(width[jp], n + sp), col, last))
            col += 1
            i = j + sp
        colw = {}
        for part in parts:
            if isinstance(part, tuple) and not part[4]:
                colw[part[3]] = max(colw.get(part[3], 0), part[2])
        inner = (rec[2] & 0x1F) + widen - 2
        new, used = bytearray(rec[:start]), 0
        for part in parts:
            if isinstance(part, int):
                new.append(part)
                if part == 0xFF:
                    used = 0
                elif part != 0x80:
                    used += 1
                continue
            k, jp, room, c, last = part
            room = room if last else colw[c]
            new += bytes((FIXED_PREFIX, k)) + b'\x01' * (room - width[jp])
            used += room
            if used > inner:
                raise ValueError(f'창 {w:02X}: 「{korean[jp]}」 까지 {used}열, 창 안쪽 {inner}열')
        if len(new) > len(rec):
            raise ValueError(f'창 {w:02X}: 고친 레코드가 원래보다 김')
        new[2] += widen
        o = lorom(addr)
        if bytes(data[o:o + len(rec)]) != rec:
            raise ValueError(f'창 {w:02X}: 레코드 자리가 어긋남')
        out.append((o, bytes(new) + b'\xff' * (len(rec) - len(new))))

    for w in LINE_WINDOWS:
        addr, rec = window(w)
        if dq5text.window_header(rec)['title'] is not None:
            raise ValueError(f'창 {w:02X}: 제목이 있는 한 줄 창')
        end = rec.index(0xFF, 6)
        row = rec[6:end]
        jp = dq5text.text(dq5text.string_codes(rom, row))
        if jp not in numbers:
            raise ValueError(f'창 {w:02X}: 「{jp}」 의 한글 문구가 없음')
        inner = (rec[2] & 0x1F) - 2
        if width[jp] > inner:
            raise ValueError(f'창 {w:02X}: 「{korean[jp]}」 {width[jp]}열, 창 안쪽 {inner}열')
        n = len(row) - sum(b in (0x83, 0x84) for b in row)
        new = rec[:6] + bytes((FIXED_PREFIX, numbers[jp])) + b'\x01' * max(0, n - width[jp]) + rec[end:]
        o = lorom(addr)
        if bytes(data[o:o + len(rec)]) != rec:
            raise ValueError(f'창 {w:02X}: 레코드 자리가 어긋남')
        out.append((o, bytes(new) + b'\xff' * (len(rec) - len(new))))

    for w in LABEL_WINDOWS:
        addr, rec = dq5text.window(rom, w)
        h = dq5text.window_header(rec)
        start = 6 + (rec[4] >> 6) + 1 if h['title'] is not None else 6
        new, i, done = bytearray(rec[:start]), start, 0
        while i < len(rec):
            row = rec.index(0xFF, i) + 1 if 0xFF in rec[i:] else len(rec)
            lead = 0
            while i + lead < row and rec[i + lead] == 0x01:
                lead += 1
            k = i + lead
            if k < row and 0x02 <= rec[k] < 0xB0:
                j, n, jp = _runs(rom, rec, k, False, (0x85, 0x86, 0x87))
                if j < row and rec[j] == 0x85 and jp in numbers:
                    if width[jp] > lead + n:
                        raise ValueError(f'창 {w:02X}: 「{korean[jp]}」 {width[jp]}열, 자리 {lead + n}열')
                    new += b'\x01' * (lead + n - width[jp]) + bytes((FIXED_PREFIX, numbers[jp])) + rec[j:row]
                    i, done = row, done + 1
                    continue
            new += rec[i:row]
            i = row
        if not done:
            raise ValueError(f'창 {w:02X}: 바꾼 라벨이 없음')
        o = lorom(addr)
        out.append((o, bytes(new) + b'\xff' * (len(rec) - len(new))))

    # 제목: 이름 자리(E0~) 없이 가나 한 덩이뿐인 제목만 창 안에서 늘어날 수 있다. 쓰는 창마다 제목 자리 + 열 수 ≤ 너비 − 1
    users = {}
    first = rom.u16(dq5text.WINDOWS)
    for w in range((first - (dq5text.WINDOWS & 0xFFFF)) // 2):
        addr, rec = dq5text.window(rom, w)
        # 메뉴 패치가 낮은 WRAM 으로 돌린 창(공용 창·이름 입력)은 롬에 레코드가 없다
        if addr & 0xFFFF >= 0x8000 and rec and not rec[0] & 0x80 and len(rec) > 6 and rec[4] & 0x0F:
            h = dq5text.window_header(rec)
            users.setdefault(h['title'], []).append((w, h['title_x'], h['w'] + FIXED_WINDOWS.get(w, 0)))
    start = lorom(dq5text.WINDOW_TITLES)
    o, old, new = start, bytearray(), bytearray()
    for t in range(TITLE_COUNT):
        e = data.index(0xFF, o)
        rec = bytes(data[o:e])
        old += rec + b'\xff'
        i, cols = 0, 0
        body = bytearray()
        single = len(rec) > 0 and all(0x02 <= b < 0xB0 for b in rec)
        while i < len(rec):
            if not 0x02 <= rec[i] < 0xB0 or rec[i] == 0x01:
                body.append(rec[i])
                cols += 1
                i += 1
                continue
            j, n, jp = _runs(rom, rec, i, False)
            s = 0
            while j + s < len(rec) and rec[j + s] == 0x01:
                s += 1
            if jp not in numbers or (not single and width[jp] > n + s):
                body += rec[i:j]
                cols += n
                i = j
                continue
            body += bytes((FIXED_PREFIX, numbers[jp])) + b'\x01' * max(0, n + s - width[jp])
            cols += max(width[jp], n + s)
            i = j + s
        for w, x, wd in users.get(t, ()):
            if single and x + cols > wd - 1:
                raise ValueError(f'제목 {t:02X} 「{rec.hex()}」: 창 {w:02X} 너비 {wd} 에 {cols}열이 안 들어감')
        new += body + b'\xff'
        o = e + 1
    if len(new) > len(old):
        raise ValueError('고친 제목 목록이 원래보다 김')
    out.append((start, bytes(new) + b'\xff' * (len(old) - len(new))))

    for a, b in INLINE_STRINGS:
        old = bytes(rom.u8(a + i) for i in range(b - a))
        new, i = bytearray(), 0
        while i < len(old):
            e = old.index(0xFF, i)
            seg = old[i:e]
            jp = dq5text.text(dq5text.string_codes(rom, seg)) if seg else ''
            if jp in FIXED:
                cells = sum(1 for x in seg if x not in (0x83, 0x84))
                if width[jp] > cells or len(seg) < 2:
                    raise ValueError(f'{a:06X}: 「{korean[jp]}」 {width[jp]}열, 자리 {cells}칸')
                seg = bytes((FIXED_PREFIX, numbers[jp])) + b'\x01' * (len(seg) - 2)
            new += seg + b'\xff'
            i = e + 1
        out.append((lorom(a), bytes(new)))
    return out, numbers


def build(data, font):
    """뱅크 TEXT_BANK 의 8000~ 에 넣을 바이트와, 종류마다 (이름 수, 한글로 바꾼 수)."""
    index = bytearray(DATA - INDEX)
    body = bytearray()
    report = {}
    bases = safe_bases(font)
    for k, (jp, ko, _) in enumerate(phrases()):
        index[SAFE - INDEX + k * 2:SAFE - INDEX + k * 2 + 2] = bases.get(k, 0).to_bytes(2, 'little')
        cols = columns(font, ko)
        at = DATA + len(body)
        index[FIXED_KIND * 0x200 + k * 2:FIXED_KIND * 0x200 + k * 2 + 2] = at.to_bytes(2, 'little')
        body += bytes((len(cols),)) + b''.join(cols)
    report[FIXED_KIND] = (len(phrases()), len(phrases()))
    for kind, (table, limit, strict) in KINDS.items():
        korean = adopted(table)
        korean.update({kana_key(jp): ko for jp, ko in EXTRA_NAMES.get(kind, {}).items()})
        names = rom_names(data, kind)
        done = 0
        for n, name in enumerate(names):
            ko = korean.get(kana_key(name))
            if not ko and kind in KANA_KINDS and name and all(0x3041 <= ord(c) <= 0x30FC for c in name):
                ko = name
            if not ko:
                continue
            cols = columns(font, ko)
            if len(cols) > limit:
                if strict and ko != name:
                    raise ValueError(f'{ko!r}: {len(cols)}열, 창은 {limit}열')
                continue
            at = DATA + len(body)
            index[kind * 0x200 + n * 2:kind * 0x200 + n * 2 + 2] = at.to_bytes(2, 'little')
            body += bytes((len(cols),)) + b''.join(cols)
            done += 1
        report[kind] = (len(names), done)
    if DATA + len(body) > 0x10000:
        raise ValueError('창 글자 그림이 뱅크 하나를 넘음')
    return bytes(index + body), report
