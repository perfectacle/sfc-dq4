"""DQ5(SFC) 보행 모드 메시지 디코더. 형식은 sfc/dq5/docs/dq5-text-format.md.

24:8BAF 가 메시지 번호를 받아 24:AF1E 색인(16개마다 3바이트)으로 시작 비트를 찾고, 24:9E02 허프만 디코더로
문자 코드(13비트)를 하나씩 꺼낸다. 번호 하위 4비트만큼은 끝 코드(1001·1010·1018)까지 읽어 건너뛴다.

제어 코드(1000~101D, 1100~1118)는 24:819D 가 24:8204·24:8240 점프 표로 처리한다. 이름·숫자 변수의 인자는 메시지가 아니라
$F5~$F8 대기열에서 꺼낸다(24:889F). 메뉴 창 문자열은 04:EB48 창 표가 가리키는 레코드 안에 1바이트 부호로 있다.

사용:
  python sfc/dq5/tools/dq5text.py rom/dq5.sfc 129                 # 메시지 0x129 를 글자로
  python sfc/dq5/tools/dq5text.py rom/dq5.sfc 129 --codes --n 64  # 끝 코드와 상관없이 코드 64개(24:8B98 처럼)
  python sfc/dq5/tools/dq5text.py rom/dq5.sfc --controls          # 제어 코드 처리기 주소와 뜻
  python sfc/dq5/tools/dq5text.py rom/dq5.sfc --window 1          # 창 1(명령 창) 레코드와 항목 문자열
  python sfc/dq5/tools/dq5text.py rom/dq5.sfc --hangul-test       # 새 글자 코드 3DB 에 「한」 을 넣는 실험 ROMPATCH
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from dq5map import Rom  # noqa: E402

INDEX = 0x24AF1E
# 24:9E02. 노드는 2바이트, bit15 면 잎(값 & 1FFF 가 문자 코드), 아니면 (값 & 1FFF) * 2 가 다음 노드 오프셋.
NODES_1 = 0x248CB6
NODES_0 = 0x249472
ROOT = 0x07BA
ENDS = (0x1001, 0x1010, 0x1018)
# 글자 코드 000~3DA 의 글자. 24:B176 폰트를 그려 읽고, 이름 입력 글자 목록인 메시지 061 의 순서로 가나를 맞췄다.
# 모양이 같은 쌍(へ/ヘ, ぺ/ペ, 二/ニ, 一/ー, 口/ロ, 夕/タ, が/ガ)은 그 메시지와 문맥으로 갈랐다. 000 은 공백.
CHARS = (
    '　園馬平閉辺飛匹ぷ亡不風間囲因院'  # 000
    '下化可果回灰開階間ガグサネピホヤ'  # 010
    'ヴ兄穴元幻器帰記起局故語国困苦具'  # 020
    '空面恩両再山世星生声石仕士思指止'  # 030
    '死車囚上冗心図天田同要愛悪安暗案'  # 040
    '闇影栄永英宴演炎煙遠派破敗杯背配'  # 050
    '倍売漠箱畑発抜判半反帆板犯晩番兵'  # 060
    '別変返便勉妃彼悲扉疲秘非備美必姫'  # 070
    '百氷表評描病品貧歩募墓母報宝抱放'  # 080
    '方法訪豊坊忘房望防北本付夫婦敷普'  # 090
    '浮父負附武舞部封復服福腹払物分文'  # 0A0
    '以位偉意移違井育印飲何夏嫁家歌火'  # 0B0
    '花苛荷華我会解快怪梅改海界皆絵外'  # 0C0
    '格確覚学楽恰活寒完官感換汗甘看肝'  # 0D0
    '館丸岩顔願刑形恵敬景系経継計軽決'  # 0E0
    '結件剣堅建権犬研見険験原現言限危'  # 0F0
    '奇寄希忌期機気祈季貴儀技犠議客久'  # 100
    '休急救求泣究去許供競共叫強教橋胸'  # 110
    '鏡業曲禁筋近金古呼庫湖雇後御護交'  # 120
    '光功効向好幸広抗攻港考航荒行降高'  # 130
    '合豪告酷黒獄腰骨頃今婚根句屈君訓'  # 140
    '魔埋妹枚毎末満命迷鳴味未密妙民眠'  # 150
    '戻問紋門夢無娘内謎南熱年念尼任認'  # 160
    '悩能農奥押横黄屋音来頼絡落令冷礼'  # 170
    '歴列恋練連利理陸率立流留竜旅料良'  # 180
    '量淋輪路労牢老録涙砂座最妻才細在'  # 190
    '材罪財作昨札殺参散産残征性成晴清'  # 1A0
    '牲精聖誓青静税昔責赤切節説雪絶先'  # 1B0
    '専川戦泉潜船選前善然全使史始姉姿'  # 1C0
    '子志私系紙至詩試飼事似字持時次治'  # 1D0
    '耳式失室実舎捨者謝邪若弱主取守手'  # 1E0
    '酒受呪樹収修拾終習舟集住十重宿祝'  # 1F0
    '出春準盾純処初所暑緒書助女勝商小'  # 200
    '少承招焼照章笑粧証丈乗城場嬢情条'  # 210
    '杖状色食信寝新森深真神親身進祖素'  # 220
    '僧倉秦捜早争相草荘装走送騒像憎側'  # 230
    '即息束足族続存孫尊村吹水酔数他多'  # 240
    '太打体対待泰袋貸退代台大第題滝誰'  # 250
    '単探誕団断段男談亭帝底庭弟敵的鉄'  # 260
    '店点伝殿値知地置茶着中仲忠昼注虫'  # 270
    '兆帳張挑朝町調長頂鳥直沈渡途都度'  # 280
    '土奴倒冬凍塔島投東盗湯灯等答統逃'  # 290
    '頭闘働動導洞道得特毒読突追通右運'  # 2A0
    '雲和話惑腕夜野役約薬予余与預幼妖'  # 2B0
    '様溶用羊葉踊養欲油勇友有由裕遊雄'  # 2C0
    '夕０２３４５６７８９＄トリ１ＡＨ'  # 2D0
    'ＫＱＴＶｈきそちはまもらるろをん'  # 2E0
    'ノヒレワＢＥＦＬＯＰＳｂｄうくさ'  # 2F0
    'しじとよりミヲＣＤＧ＊メＭＷＸＹ'  # 300
    '＋ざぢどねひふぶみめれわセムル血'  # 310
    '玉口王皿正西Ｕあえおかけすせただ'  # 320
    'なべむやゆアシツテラ日ａｏっゃゅ'  # 330
    'ァｃｅｉｌｊ“”ｍｎｕｐこｒｓｔ'  # 340
    '々ｖヨｗつエ。、・？！＃＠ウカ〓'  # 350
    'ー｛｝「―へ…＜＞％ぺ医オキケチ'  # 360
    'ナ月巨入乙臣人＆イクタド買泊罰冒'  # 370
    '員引加賀枯后名明力師消刃当届白目'  # 380
    '呂占自申ぁォッャいのハモ二がぱぴ'  # 390
    'ぽギゲゴザズゾダヂヅバパビブプベ'  # 3A0
    'ボポ温ぎぐごずぞづぬばびぼジゼデ'  # 3B0
    'げぜでてマンにほコスソヌフロょィ'  # 3C0
    '暮一ェニユヘペ滅猛ュョ'  # 3D0
)
# 24:A609. 5바이트 항목이 같은 크기 글자의 묶음: [개수 12비트 | 폭 4비트][시작 주소 16비트][bit0-1 뱅크-7, bit2-5 높이].
# 묶음 안 글자는 폭×높이 비트씩 이어 붙은 1bpp 그림이고, 줄마다 폭 비트를 LSB 쪽부터 읽어 높은 비트가 왼쪽 점이다.
FONT_GROUPS = 0x24B176
GLYPHS = 0x3DB
# 24:A7B6. 이름 문자열(1바이트 부호)을 글자 코드로. 보통 바이트 b 는 24:B270 + b*2, 84 xx 는 24:AE9A 에서 xx 를 찾은 순번 i 로
# 24:B36E + i*2(탁점 글자), 83 xx 는 같은 표의 28 번째부터 찾는다(반탁점 글자). 01 은 공백.
STRING_CODES = 0x24B270
MARK_KEYS = 0x24AE9A
MARK_CODES = 0x24B36E
# 21:955D. 이름 표 번호($43)마다 [길이][바이트…] 가 이어진 문자열 목록의 시작.
STRING_TABLES = 0x21959B
# 끝 코드와 줄바꿈. 나머지 제어 코드는 {XXXX} 로 둔다(sfc/dq5/docs/dq5-text-format.md 의 「제어 코드」).
CONTROL = {0x1000: '\n', 0x1001: '{end}', 0x1010: '{end}', 0x1018: '{end}'}
# 24:819D. 코드 & FF 를 색인으로 1000~101D 는 24:8204, 1100~1118 은 24:8240 의 처리기로 간다(16비트 주소, 뱅크 24).
CONTROL_TABLES = ((0x1000, 0x248204, 0x1E), (0x1100, 0x248240, 0x19))
# 뜻. 「실측」 은 sfc/dq5/docs/dq5-text-format.md 의 「제어 코드」 에 적은 실험으로 확인한 것, 나머지는 코드 읽기.
CONTROL_MEANING = {
    0x1000: '줄바꿈(실측)',
    0x1001: '메시지 끝: 줄을 내리고 앞 메시지들의 줄을 밀어 올려 이 메시지만 창 위에 남김, 버튼 대기 없음(실측)',
    0x1002: '▼ 버튼 대기 뒤 앞 줄들을 밀어 올려 새 쪽(실측)',
    0x1003: '말하는 사람 대사: ＊「 를 붙이지 않고 다음 줄부터 들여 씀. 24:8AF9 가 줄 첫머리에서 먹음(실측)',
    0x1004: '숫자: $F5~$F7 24비트(실측)',
    0x1005: '일행이 둘 이상이면 「たち」',
    0x1006: '서술문: ＊「 도 들여쓰기도 없음. 24:8AF9 가 먹음(실측)',
    0x1007: '들여쓰기 끄기(실측)',
    0x1008: '이름: $F5 한 바이트. bit7=0 일행 슬롯 & 0F(bit6 이면 「たち」), FF「まもののむれ」, 그 밖 bit7 은 전투 몬스터(실측 일부)',
    0x1009: '몬스터 이름(이름 표 4, $F5, 실측). 메시지에 쓰이지 않아 허프만 트리에 없음',
    0x100A: '물건 이름(이름 표 5, $F5, 실측)',
    0x100B: '주문 이름(이름 표 3, $F5, 실측)',
    0x100C: '이름 표 7($F5). 표 7 은 30:8000 으로 롬 밖이라 아무것도 찍히지 않음(실측). 트리에 없음',
    0x100D: '31프레임 멈춤(실측)',
    0x100E: '아무것도 하지 않음(실측). 트리에 없음',
    0x100F: '몬스터 이름(이름 표 4, $F5) + 7E:1005,[7E:0F23] 이 0·1 이면 Ａ·Ｂ, 음수면 없음(실측)',
    0x1010: '메시지 끝: 1001 과 같이 밀어 올린 뒤 ▼ 버튼 대기(실측)',
    0x1011: '일행 슬롯 0 의 이름(실측: 주인공)',
    0x1012: '주인공 이름 7E:2001(실측)',
    0x1013: '일행 레코드(7E:2040 + 2A*i) 8개 중 인물 번호(+0)가 80 인 동료의 이름. 없으면 빈칸(실측)',
    0x1014: '이름 표 6(작전·마을, $F5, 실측). 트리에 없음',
    0x1015: '신부 이름: 7E:21B3 & 08 이면 ビアンカ, 아니면 フローラ(실측)',
    0x1016: '아들 이름 7E:2009(실측)',
    0x1017: '딸 이름 7E:2011(실측)',
    0x1018: '메시지 끝: 줄만 하나 내리고 밀어 올리지 않음. 다음 메시지가 아랫줄에 이어짐(실측)',
    0x1019: '101A 까지 글자를 기다림 없이 한 번에 찍음(실측)',
    0x101A: '1019·101C 를 끔',
    0x101B: '주인공(일행 레코드 0)이 살아 있으면 1012, 아니면 1011(실측). 트리에 없음',
    0x101C: '느리게: 글자마다 3프레임, 밀어 올리기 1점씩(실측)',
    0x101D: '스크립트가 7E:0F13 에 넣어 둔 루틴 호출',
}
# 1100~1118 은 말하는 인물(7E:0F1E 슬롯)의 동작과 창·화면 효과. 7E:31E0 은 방향(88 위·44 아래·22 왼쪽·11 오른쪽),
# 7E:3260 은 bit7 이 켜지면 아래 니블의 방향(8 위·4 아래·2 왼쪽·1 오른쪽) 모양으로 그린다. 「실측」 은 선실 파파스로 띄워 본 것.
for _c in range(0x1100, 0x1119):
    CONTROL_MEANING[_c] = '말하는 인물 동작. 메시지에 쓰이지 않아 트리에 없음'
CONTROL_MEANING.update({
    0x1100: '창이 커졌다 돌아옴(7E:0A43~0A46, 「わっ！」, 실측)',
    0x1101: '고개를 좌우로: 3260 = 81·02·82·02 를 3프레임마다(실측)',
    0x1103: '두리번거림: 3260 = 82·81 을 10프레임마다, 뒤 31E0 = 22·44(실측)',
    0x1104: '두 번 뛰어오름: 7E:3080 을 ±1 씩 31프레임(실측)',
    0x1105: '창이 흔들림(7E:0750·0752, 실측)',
    0x1106: '위를 봄(31E0 = 88, 실측)', 0x1107: '아래를 봄(31E0 = 44, 실측)',
    0x1108: '왼쪽을 봄(31E0 = 22, 트리에 없음)', 0x1109: '오른쪽을 봄(31E0 = 11, 트리에 없음)',
    0x110A: '위 모양(3260 = 88, 실측)', 0x110B: '아래 모양(3260 = 84, 실측)',
    0x110C: '왼쪽 모양(3260 = 82, 실측)', 0x110D: '오른쪽 모양(3260 = 81, 트리에 없음)',
    0x110E: '31E0 = 주인공 방향 & F0(실측: 80)', 0x110F: '3260 = 02 로 되돌림(실측)',
    0x1110: '한 바퀴 돌기: 31E0 = 11·88·22·44 를 3프레임마다(실측)',
    0x1112: '몸 떨기: 7E:3000+슬롯 을 20·00 으로 2프레임마다 8번(「さぶい」, 실측)',
    0x1113: '고개를 좌우로 천천히 두 번: 1101 을 10프레임 간격으로(실측)',
    0x1114: '기침: 7E:3180+슬롯(세로 어긋남) = FF 를 3프레임씩 두 번(「ごほん」, 실측)',
    0x1115: '주인공을 마주 보는 모양: 주인공 31E0 이 위면 3260 = 84 등(실측)',
    0x1116: '화면을 어둡게(03:A6CB, 실측)', 0x1117: '화면을 되돌림(03:A73D, 실측)',
    0x1118: '딸꾹질: 7E:3180+슬롯 = 01 을 3프레임(「ヒック」, 실측)',
})
# 04:9C40. 창 번호 * 2 → 뱅크 04 의 창 레코드. 레코드의 항목 문자열은 FE 로 시작하고 FF 가 줄 끝.
# 창 문자열 바이트는 BG3 타일 번호로 그대로 쓰인다(04:B235). 타일 01~8A 는 04:E528 의 1bpp 글자.
WINDOWS = 0x04EB48
# 04:ACC8. 창 제목 문자열 목록(FF 로 나뉨). 머리 +4 아래 4비트가 0 이 아니면 +5 가 이 목록의 번호. 탁점 접두는 92·93.
WINDOW_TITLES = 0x04AD78


class BitReader:
    """24:8C8D·24:9E02. 24비트 값의 하위 3비트가 비트 위치, 나머지가 바이트 주소. 비트는 LSB 부터 읽는다."""

    def __init__(self, rom, value):
        self.rom, self.addr, self.bit = rom, value >> 3, value & 7

    def read(self):
        b = (self.rom.u8(self.addr) >> self.bit) & 1
        self.bit += 1
        if self.bit == 8:
            self.bit = 0
            # 24:9E2F: 16비트 주소가 0 으로 넘어가면 다음 뱅크의 $8000.
            self.addr += 1
            if self.addr & 0xFFFF == 0:
                self.addr |= 0x8000
        return b


def next_code(rom, br):
    x = ROOT
    while True:
        v = rom.u16((NODES_1 if br.read() else NODES_0) + x)
        if v & 0x8000:
            return v & 0x1FFF
        x = (v & 0x1FFF) << 1


def reader(rom, msg):
    """24:8BAF: msg 번호의 첫 코드를 가리키는 BitReader."""
    br = BitReader(rom, rom.u24(INDEX + (msg >> 4) * 3))
    for _ in range(msg & 0xF):
        while next_code(rom, br) not in ENDS:
            pass
    return br


def message(rom, msg, n=None):
    """끝 코드까지(끝 코드 포함) 또는 n 개의 문자 코드."""
    br, out = reader(rom, msg), []
    while True:
        c = next_code(rom, br)
        out.append(c)
        if (n is None and c in ENDS) or (n is not None and len(out) == n):
            return out


def font_groups(rom):
    out, a, start = [], FONT_GROUPS, 0
    while start < GLYPHS:
        count = rom.u16(a) & 0xFFF
        b4 = rom.u8(a + 4)
        out.append((start, count, rom.u8(a + 1) >> 4, (b4 >> 2) & 0xF, ((b4 & 3) + 7) << 16 | rom.u16(a + 2)))
        start += count
        a += 5
    return out


def glyph(rom, code, groups=None):
    """24:A631~A793. 글자 code 의 (폭, 높이, 줄마다 점 목록). 000 은 공백(24:A623, 폭 8)."""
    if code == 0:
        return 8, 1, [[0] * 8]
    for start, count, w, h, base in groups or font_groups(rom):
        if start <= code < start + count:
            break
    rows = []
    for r in range(h):
        bit = (code - start) * w * h + r * w
        a = base + (bit >> 3)
        v = (rom.u8(a) | rom.u8(a + 1) << 8 | rom.u8(a + 2) << 16) >> (bit & 7)
        rows.append([(v >> (w - 1 - x)) & 1 for x in range(w)])
    return w, h, rows


def string_codes(rom, data):
    out, i = [], 0
    while i < len(data):
        b = data[i]
        if b in (0x83, 0x84):
            i += 1
            k = 0x28 if b == 0x83 else 0
            while rom.u8(MARK_KEYS + k) != data[i]:
                k += 1
            out.append(rom.u16(MARK_CODES + k * 2))
        elif b == 0x01:
            out.append(0)
        else:
            out.append(rom.u16(STRING_CODES + b * 2))
        i += 1
    return out


def string(rom, table, n):
    """21:955D. 이름 표 table 의 n 번째 문자열 바이트."""
    a = rom.u24(STRING_TABLES + table * 3)
    for _ in range(n):
        a += rom.u8(a) + 1
    return bytes(rom.u8(a + 1 + i) for i in range(rom.u8(a)))


def text(codes):
    out = []
    for c in codes:
        if c in CONTROL:
            out.append(CONTROL[c])
        elif c < len(CHARS):
            out.append(CHARS[c])
        else:
            out.append(f'{{{c:04X}}}')
    return ''.join(out)


def controls(rom):
    """(코드, 처리기 주소) 목록. 24:81AD~81DB."""
    out = []
    for base, table, count in CONTROL_TABLES:
        for i in range(count):
            out.append((base + i, 0x240000 | rom.u16(table + i * 2)))
    return out


def window(rom, n):
    """04:9C40. 창 n 레코드의 주소와, 다음 레코드 시작까지의 바이트(창 레코드는 주소 순으로 이어져 있다)."""
    first = rom.u16(WINDOWS)
    starts = sorted({rom.u16(WINDOWS + i * 2) for i in range((first - (WINDOWS & 0xFFFF)) // 2)})
    a = rom.u16(WINDOWS + n * 2)
    end = next((s for s in starts if s > a), a + 0x40)
    return 0x040000 | a, bytes(rom.u8(0x040000 | a + i) for i in range(end - a))


def window_header(data):
    """창 레코드 머리. +0 아래 5비트 X(bit6 을 끄면 일행 창이 한 줄만, bit7 을 켜면 안 뜸), +1 Y, +2 너비, +3 아래 4비트 높이(타일)·bit7 줄 간격 16점·bit5(명령 창에서 끄면 안 뜸, 상태 창은 꺼진 채 뜸).
    +4 아래 4비트가 0 이면 +5 가 줄 수. 0 이 아니면 그 값이 제목의 가로 자리(타일), +5 가 제목 번호(WINDOW_TITLES),
    +6(+4 bit6-7 만큼 뒤로 밀림)이 줄 수이고, 그 bit7 이면 일행 수만큼 되풀이(아래 비트 = 사람마다 줄 수). 줄 수 바로 뒤부터가 줄 내용.
    +4 bit6-7 은 제목 뒤 건너뛸 바이트 수, +2 bit6-7 은 상태에 따른 글자 색(1·3 글자만, 2 테두리까지)."""
    h = {'x': data[0] & 0x1F, 'x_flags': data[0] & 0xE0, 'y': data[1] & 0x1F, 'w': data[2] & 0x1F, 'h': data[3] & 0x0F, 'color_by_state': data[2] >> 6, 'tall_rows': bool(data[3] & 0x80),
         'bit5': bool(data[3] & 0x20)}
    if data[4] & 0x0F:
        k = 6 + (data[4] >> 6)                                    # 제목 뒤 건너뛸 바이트(+4 bit6-7) 다음이 줄 수
        h.update(title=data[5], title_x=data[4] & 0x0F, title_skip=data[4] >> 6, rows=data[k] & 0x7F,
                 per_member=bool(data[k] & 0x80))
    else:
        h.update(title=None, rows=data[5])
    return h


def window_title(rom, n):
    """04:ACC8. 제목 n 의 바이트(92·93 은 탁점·반탁점 접두)."""
    a = WINDOW_TITLES
    for _ in range(n):
        while rom.u8(a) != 0xFF:
            a += 1
        a += 1
    out = bytearray()
    while rom.u8(a) != 0xFF:
        out.append(rom.u8(a))
        a += 1
    return bytes(out)


def window_items(rom, data):
    """창 레코드의 첫 FE 부터를 항목 문자열로. FE = 항목 시작, FF = 줄 끝."""
    k = data.find(b'\xfe')
    if k < 0:
        return ''
    out, i = [], k
    while i < len(data):
        b = data[i]
        if i > k and data[i - 1] == 0xFF and b != 0xFE:
            break
        if b == 0xFE:
            out.append('|')
        elif b == 0xFF:
            out.append('\n')
        else:
            n = 2 if b in (0x83, 0x84) else 1
            out.append(text(string_codes(rom, data[i:i + n])))
            i += n - 1
        i += 1
    return ''.join(out)


# 폰트 묶음 표를 읽는 명령의 피연산자(24:B176·B178·B17A 를 long 주소로 읽음). 표를 옮기려면 넷을 모두 고친다.
FONT_TABLE_OPERANDS = ((0x24A63C, 0), (0x24A660, 0), (0x24A6C2, 2), (0x24A673, 4))
# 표를 옮겨 볼 빈 곳(0B:FB99~, 0 이 1,127바이트)과, 메시지에 쓰이지 않는 글자 2E0~2E2(ＫＱＴ) 그림 자리(07:CA9F~, 36바이트).
FREE_TABLE = 0x0BFB99
FREE_GLYPH = 0x07CA9F
HANGUL_TEST = ('...#.....#.', '.#####...#.', '..###....#.', '.#...#...##', '.#...#...#.', '..###....#.', '.........#.',
               '..#......#.', '..#........', '..#........', '..#######..', '...........', '...........')


def leaf_address(rom, code):
    """허프만 트리에서 글자 code 의 잎(값 8000 | code)이 있는 노드 주소. 없으면 None."""
    for base in (NODES_0, NODES_1):
        for x in range(0, NODES_0 - NODES_1, 2):
            if rom.u16(base + x) == 0x8000 | code:
                return base + x
    return None


def hangul_test_patch(rom, replace=0x399):
    """폰트 묶음 표를 FREE_TABLE 로 옮겨 51번째 묶음(글자 1개, 11×13)을 더하고, 그 글자(코드 3DB)를 FREE_GLYPH 에 그린 뒤
    트리 잎 replace(기본 の)를 3DB 로 바꾸는 (파일 오프셋, 바이트) 목록."""
    from dq5map import lorom
    w, h = len(HANGUL_TEST[0]), len(HANGUL_TEST)
    data = bytearray((w * h + 7) // 8)
    for y, row in enumerate(HANGUL_TEST):
        for x, c in enumerate(row):
            if c == '#':
                i = y * w + w - 1 - x
                data[i >> 3] |= 1 << (i & 7)
    n = len(font_groups(rom))
    table = bytes(rom.u8(FONT_GROUPS + i) for i in range(n * 5))
    table += bytes((1, w << 4, FREE_GLYPH & 0xFF, FREE_GLYPH >> 8 & 0xFF, (FREE_GLYPH >> 16) - 7 | h << 2))
    out = [(lorom(FREE_GLYPH), bytes(data)), (lorom(FREE_TABLE), table)]
    for a, k in FONT_TABLE_OPERANDS:
        t = FREE_TABLE + k
        out.append((lorom(a), bytes((t & 0xFF, t >> 8 & 0xFF, t >> 16))))
    out.append((lorom(leaf_address(rom, replace)), (0x8000 | GLYPHS).to_bytes(2, 'little')))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('msg', nargs='?', type=lambda s: int(s, 16))
    ap.add_argument('--n', type=int)
    ap.add_argument('--codes', action='store_true', help='글자 대신 코드를 찍음')
    ap.add_argument('--controls', action='store_true', help='제어 코드 처리기와 뜻')
    ap.add_argument('--window', type=lambda s: int(s, 16), help='창 레코드(04:EB48)')
    ap.add_argument('--hangul-test', action='store_true', help='새 글자 코드에 「한」 을 넣는 실험 ROMPATCH')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    if args.hangul_test:
        print(';'.join(f'{o:X}={b.hex().upper()}' for o, b in hangul_test_patch(rom)))
        return 0
    if args.controls:
        for c, a in controls(rom):
            print(f'{c:04X} {a >> 16:02X}:{a & 0xFFFF:04X} {CONTROL_MEANING.get(c, "")}')
        return 0
    if args.window is not None:
        a, data = window(rom, args.window)
        print(f'window {args.window:02X} at {a >> 16:02X}:{a & 0xFFFF:04X}: {data.hex(" ")}')
        if not data[0] & 0x80:
            h = window_header(data)
            print(' '.join(f'{k}={v}' for k, v in h.items()))
            if h['title'] is not None:
                t = window_title(rom, h['title']).replace(b'\x92', b'\x84').replace(b'\x93', b'\x83')
                print('title:', text(string_codes(rom, bytes(b for b in t if b < 0xE0))))
        print(window_items(rom, data))
        return 0
    codes = message(rom, args.msg, args.n)
    print(' '.join(f'{c:04X}' for c in codes) if args.codes else text(codes))
    return 0


if __name__ == '__main__':
    sys.exit(main())
