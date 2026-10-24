"""DQ5(SFC) 보행 모드 메시지 디코더. 형식은 docs/dq5-text-format.md.

24:8BAF 가 메시지 번호를 받아 24:AF1E 색인(16개마다 3바이트)으로 시작 비트를 찾고, 24:9E02 허프만 디코더로
문자 코드(13비트)를 하나씩 꺼낸다. 번호 하위 4비트만큼은 끝 코드(1001·1010·1018)까지 읽어 건너뛴다.

사용:
  python tools/dq5text.py rom/dq5.sfc 129                 # 메시지 0x129 를 글자로
  python tools/dq5text.py rom/dq5.sfc 129 --codes --n 64  # 끝 코드와 상관없이 코드 64개(24:8B98 처럼)
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
# 끝 코드와 줄바꿈. 나머지 제어 코드는 {XXXX} 로 둔다(docs/dq5-text-format.md 의 「제어 코드」).
CONTROL = {0x1000: '\n', 0x1001: '{end}', 0x1010: '{end}', 0x1018: '{end}'}


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('msg', type=lambda s: int(s, 16))
    ap.add_argument('--n', type=int)
    ap.add_argument('--codes', action='store_true', help='글자 대신 코드를 찍음')
    args = ap.parse_args()
    rom = Rom(open(args.rom, 'rb').read())
    codes = message(rom, args.msg, args.n)
    print(' '.join(f'{c:04X}' for c in codes) if args.codes else text(codes))
    return 0


if __name__ == '__main__':
    sys.exit(main())
