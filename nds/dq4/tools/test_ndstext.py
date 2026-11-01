"""MPT0 대사 파일 읽기(색인 위치·번호), 한글 글리프 표 바꾸기, 이름 표 꼴, 동료 대화 표, Shift_JIS 문자열 찾기를 합성 파일로 검사한다."""
import contextlib
import io
import os
import struct
import tempfile
import unittest

import ndstext as nt


def mpt(first, msgs):
    """MPT0: 머리 32바이트 + 색인(번호, 길이, 위치/4) + 4바이트 맞춘 본문. msgs: [(색인 번호, 글)]."""
    body, index = bytearray(), bytearray()
    for num, text in msgs:
        raw = text.encode("utf-8")
        index += struct.pack("<3H", num, len(raw), len(body) // 4)
        body += raw + bytes(-len(raw) % 4 or 4)
    table = bytes(index) + b"\0\0"
    table += bytes(-len(table) % 4)
    size = 0x20 + len(table) + len(body)
    head = struct.pack("<8I", 0x3054504D, size, first, first + len(msgs), len(msgs), 0x20, len(index) + 2, len(body))
    return head + table + bytes(body)


def put(root, rel, data):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


class ReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_index_offsets_and_full_numbers(self):
        p = put(self.root, "a.mpt", mpt(5000, [(0, "あ"), (3, "いうえお\nか"), (4, "")]))
        self.assertEqual(nt.read(p), [(0, "あ"), (3, "いうえお\nか"), (4, "")])
        self.assertEqual([n for n, _ in nt.read(p, full=True)], [5000, 5003, 5004])

    def test_rejects_wrong_size_or_magic(self):
        raw = mpt(0, [(0, "x")])
        p = put(self.root, "b.mpt", raw + b"\0")
        with self.assertRaises(ValueError):
            nt.read(p)
        p = put(self.root, "c.mpt", b"XPT0" + raw[4:])
        with self.assertRaises(ValueError):
            nt.read(p)

    def test_messages_merge_files(self):
        put(self.root, "data/data/MESS/ja/b0001000.mpt", mpt(1000, [(0, "一"), (1, "二")]))
        put(self.root, "data/data/MESS/ja/b0002000.mpt", mpt(2000, [(0, "三")]))
        put(self.root, "data/data/MESS/ja/readme.txt", b"x")
        self.assertEqual(nt.messages(self.root), {1000: "一", 1001: "二", 2000: "三"})


class TableTests(unittest.TestCase):
    def test_kr_table_and_decode(self):
        t = nt.kr_table()
        self.assertEqual(t["Ё"], "이")
        self.assertEqual(nt.decode_kr("ЁX", t), "이X")

    def test_adopt_table(self):
        a = nt.adopt_table()
        self.assertEqual(a["아이템", 1][1], "곤봉")

    def test_label_and_kana_key(self):
        self.assertEqual(nt.label("@1ソ;ロ@"), "ソロ")
        self.assertEqual(nt.label("@0m@2the@3a@4Hero@5x@"), "Hero")
        self.assertEqual(nt.label("@plain@"), "plain")
        self.assertEqual(nt.kana_key("ひの き;のぼう"), "ヒノキノボウ")
        self.assertEqual(nt.kana_key("ゖ"), "ヶ")
        self.assertEqual(nt.kana_key("ゝ"), "ゝ")   # 가나 범위 밖은 그대로


class TalkTests(unittest.TestCase):
    def test_records_follow_head(self):
        with tempfile.TemporaryDirectory() as root:
            recs = b""
            for k in range(2):
                r = bytearray(nt.TALK_SIZE)
                struct.pack_into("<H", r, 0, 0x10 + k)
                struct.pack_into("<I", r, 16, 7000 + k)
                recs += bytes(r)
            put(root, "data/data/PARAM/param_player_talk3.dat", b"HEAD" + recs + b"tail")
            out = nt.talk_records(root, 3)
        self.assertEqual([m for m, _ in out], [7000, 7001])
        self.assertEqual(out[1][1][0], 0x11)
        self.assertEqual(out[0][1][8:10], (7000, 0))   # +16 u32 은 u16 칸 8·9


class SjisTests(unittest.TestCase):
    def test_aligned_terminated_kana_only(self):
        d = bytearray(64)
        d[0:7] = "あいう".encode("cp932") + b"\0"
        d[8:13] = "漢字".encode("cp932") + b"\0"
        d[16:19] = b"ab\0"
        d[21:26] = "かき".encode("cp932") + b"\0"          # 4바이트 맞춤이 아님
        d[28:34] = "ｱｲｳ".encode("cp932").ljust(5, b"\0") + b"\0"   # 반각 가나는 뺀다
        d[36:43] = "さ\nし".encode("cp932") + b"\0"
        d[44:49] = "え".encode("cp932") + b"\x01\x02\0"     # 제어 문자는 뺀다
        got = nt.sjis_strings(bytes(d))
        self.assertEqual(got, [(0, "あいう"), (36, "さ\nし")])
        self.assertIn((8, "漢字"), nt.sjis_strings(bytes(d), kanji=True))

    def test_modules_and_cmd_sjis_pointers(self):
        with tempfile.TemporaryDirectory() as jp, tempfile.TemporaryDirectory() as kr:
            a9 = bytearray(64)
            a9[0:7] = "あいう".encode("cp932") + b"\0"
            a9[8:13] = "漢字".encode("cp932") + b"\0"
            struct.pack_into("<2I", a9, 32, 0x02000000, 0x02000008)    # 두 문자열을 가리키는 표
            put(jp, "arm9.bin", bytes(a9))
            ov = bytearray(40)
            ov[0:5] = "えお".encode("cp932") + b"\0"
            y9 = struct.pack("<8I", 0, 0x02100000, 0, 0, 0, 0, 0, 0) * 2
            put(jp, "y9.bin", y9)
            put(jp, "overlay9/overlay_0000.bin", bytes(ov))
            put(jp, "overlay9/overlay_0001.bin", bytes(8))         # 32바이트 이하는 건너뜀
            kr_a9 = bytearray(a9)
            kr_a9[0:2] = "Ё".encode("cp932")              # 한글 패치는 코드는 두고 글리프만 바꿨다
            put(kr, "arm9.bin", bytes(kr_a9))
            put(kr, "y9.bin", y9)
            put(kr, "overlay9/overlay_0000.bin", bytes(ov))
            put(kr, "overlay9/overlay_0001.bin", bytes(8))
            mods = list(nt.modules(jp))
            self.assertEqual([(n, a) for n, a, _ in mods], [("arm9", 0x02000000), ("overlay_0000", 0x02100000)])
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                nt.cmd_sjis(jp, kr)
                nt.cmd_sjis(jp, None, kanji=True)
            lines = buf.getvalue().splitlines()
        # 가나 모드에서는 漢字 가 찾은 문자열이 아니므로 표가 한 칸짜리로 끊긴다
        self.assertIn("arm9\t000000\t02000000\tarm9:20\tあいう\t" + nt.decode_kr("Ёいう", nt.kr_table()), lines)
        self.assertIn("overlay_0000\t000000\t02100000\t-\tえお\t", lines)
        self.assertIn("arm9\t000008\t02000008\tarm9:24\t漢字\t", lines)
        self.assertEqual(sum("あいう" in x for x in lines), 1)   # kanji 모드는 가나 있는 문자열을 내지 않는다


def name_root(root, lang, files):
    for f, msgs in files.items():
        put(root, f"data/data/MESS/{lang}/{f}.mpt", mpt(0, msgs))


class CommandTests(unittest.TestCase):
    def test_names_glossary_stats_forms_talk_dump(self):
        with tempfile.TemporaryDirectory() as jp, tempfile.TemporaryDirectory() as kr:
            for f in nt.NAME_FILES:
                name_root(jp, "ja", {f: [(0, "@1ひのきのぼう@"), (1, "@1こんぼう@"), (2, "@1こんぼう@")]})
                name_root(jp, "en", {f: [(0, "@4Cypress stick@"), (1, "@4Club|x@")]})
                name_root(kr, "ja", {f: [(0, "@1Ё@")]})
            put(jp, "data/data/MESS/ja/b0100000.mpt", mpt(100000, [(0, "%a01002 と %a01012 @c1@")]))
            put(jp, "data/data/PARAM/param_player_talk1.dat",
                b"HEAD" + struct.pack("<16xI24x", 100000))
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                nt.cmd_names(jp, kr)
                nt.cmd_glossary(jp, kr, os.path.join(jp, "none.nes"))
                nt.cmd_stats(jp)
                nt.cmd_forms(jp)
                nt.cmd_forms(jp, 1)
                nt.main(["talk", jp, "1", "--kr", kr])
                nt.main(["dump", os.path.join(jp, "data/data/MESS/ja/b1000000.mpt"), "--kr"])
            out = buf.getvalue()
        self.assertIn("아이템\tb1000000:0\tひのきのぼう\tCypress stick\t이", out)
        self.assertIn("<!-- FC 이름을 읽지 못함", out)
        self.assertIn("| 0 | ひのきのぼう |  | Cypress stick | 이 | 노송나무 막대 |", out)
        self.assertEqual(out.count("| 2 | こんぼう"), 0)      # 같은 (일본어, 한글) 은 한 번만
        self.assertIn("Club/x", out)                         # 표 칸을 깨는 | 는 바꾼다
        self.assertIn("ja\t파일 9\t문자열 25", out)
        self.assertIn("ja\t01\t2\t0:1 1:1", out)
        self.assertIn("ja\t01\t1\t1:1", out)
        self.assertIn("1\t100000\t", out)
        self.assertIn("\n0\t@1" + nt.decode_kr("ひのきのぼう", nt.kr_table()) + "@\n", out)

    def test_main_usage(self):
        with self.assertRaises(SystemExit):
            nt.main([])
        with self.assertRaises(SystemExit):
            nt.main(["what"])


if __name__ == "__main__":
    unittest.main()
