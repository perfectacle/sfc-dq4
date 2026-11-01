"""이벤트 스크립트 블록 나무·함수 명령 읽기, 명령 풀이, ARM 분기표 읽기를 합성 스크립트로 검사한다."""
import contextlib
import io
import os
import struct
import tempfile
import unittest

import ndsscript as sc


def block(name, secs):
    """이름 16바이트, 칸 수, 머리 크기, 표 크기, 0, (오프셋, 크기) 표, 칸 자료(4바이트 맞춤)."""
    n = len(secs)
    tsize = (n * 8 + 15) // 16 * 16
    head = 0x20 + tsize
    table, body = bytearray(), bytearray()
    for s in secs:
        table += struct.pack("<2I", len(body), len(s))
        body += s
        body += bytes(-len(body) % 4)
    table += bytes(tsize - len(table))
    return name.encode().ljust(16, b"\0") + struct.pack("<4I", n, head, tsize, 0) + bytes(table) + bytes(body)


def func(name, cmds):
    """함수 블록: 깊이 바이트들, 명령 시작 오프셋(명령 수 + 1), 코드. cmds: [(깊이, [낱말…])]."""
    depths = bytes(d for d, _ in cmds)
    offs, code = [0], bytearray()
    for _d, words in cmds:
        code += struct.pack(f"<{len(words)}I", *words)
        offs.append(len(code))
    # functions 는 깊이 칸의 크기를 명령 수로 읽는다
    return block(name, [depths, struct.pack(f"<{len(offs)}I", *offs), bytes(code)])


def script(objects):
    """script → scriptgroup → scriptobject(머리 0x30, initialize, execute, terminate)."""
    objs = []
    for head, init, exe, term in objects:
        objs.append(block("scriptobject", [head, func("initialize", init), func("execute", exe),
                                           func("terminate", term)]))
    return block("script", [block("scriptgroup", objs)])


def obj_head(model, facing, x, y, z):
    return struct.pack("<I2I3i", 0, model, facing, int(x * 4096), int(y * 4096), int(z * 4096)).ljust(0x30, b"\0")


SAMPLE = script([
    (obj_head(0x12, 2, 1.5, 0, -3), [(0, [0x86, 5])],
     [(0, [0x18, 0, 0x2A, 1]), (1, [0x05, 1001, 2]), (1, [0x62, 300]),
      (0, [0x1F, 0x31666163, 0, 1, 2, 4096, 0, -8192 & 0xFFFFFFFF, 7, 8])],
     []),
])


class BlockTests(unittest.TestCase):
    def test_tree_depths_and_names(self):
        tree = [(d, n) for d, n, _o, _s in sc.blocks(SAMPLE)]
        self.assertEqual(tree, [(0, "script"), (1, "scriptgroup"), (2, "scriptobject"), (3, "initialize"),
                                (3, "execute"), (3, "terminate")])

    def test_rejects_bad_header(self):
        bad = bytearray(SAMPLE)
        struct.pack_into("<I", bad, 24, 0x30)       # 표 크기와 맞지 않는 머리 크기
        with self.assertRaises(ValueError):
            sc.blocks(bytes(bad))

    def test_functions_split_commands_by_offsets(self):
        fs = sc.functions(SAMPLE)
        self.assertEqual([n for n, _o, _i in fs], ["initialize", "execute", "terminate"])
        self.assertEqual(fs[0][2], [(0, (0x86, 5))])
        ins = fs[1][2]
        self.assertEqual([d for d, _ in ins], [0, 1, 1, 0])
        self.assertEqual(ins[1][1], (0x05, 1001, 2))
        self.assertEqual(len(ins[3][1]), 10)
        self.assertEqual(fs[2][2], [])

    def test_object_head(self):
        _d, _n, _o, secs = sc.blocks(SAMPLE)[2]
        self.assertEqual(sc.object_head(SAMPLE, secs[0][0]), (0x12, 2, 1.5, 0.0, -3.0))


class DescribeTests(unittest.TestCase):
    def test_known_forms(self):
        msgs = {1001: "こんにちは\nせかい"}
        self.assertEqual(sc.describe((0x05, 1001, 2), msgs), "005 대사 이어서(마을): 1001「こんにちは/せかい」 2")
        self.assertEqual(sc.describe((0x18 | 3 << 16, 2, 0x2A, 1), {}), "018.3 깃발이면: 맵[2A]=1")
        self.assertEqual(sc.describe((0x1F, 0x31666163, 0, 1, 2, 4096, 0, -8192 & 0xFFFFFFFF, 7, 8), {}),
                         "01F 맵 이동(자리): caf1 1 2 1 0 -2 7 8")
        self.assertEqual(sc.describe((0x04, 0, 5, 0, 0, 0, 0, 0, 0), {}), "004 대사 목록: 5")   # 0 은 빈 칸
        self.assertEqual(sc.describe((0x0D, 3), {}), "00D 화면 어둡게(끝): 3")              # 인자가 모자라면 멈춤
        self.assertEqual(sc.describe((0x86, 5, 0xAB), {}), "086 곡 틀기: 5 AB")             # 남는 인자는 16진
        self.assertEqual(sc.describe((0x51, 0xFF), {}), "051 감정 표시: FF")

    def test_unknown_op_and_names(self):
        self.assertEqual(sc.describe((0x1FF, 10, 11), {}), "1FF A B")
        self.assertEqual(sc.word_name(0x31666163), "caf1")
        self.assertIsNone(sc.word_name(0))
        self.assertIsNone(sc.word_name(0x01020304))
        self.assertEqual(sc.describe((0x20, 0, 0, 1, 2, 3, 4), {}), "020 맵 이동(입구): 0 1 2 3 4")


def arm9_with_dispatch(targets, default):
    """분기표 자리(DISPATCH - 4 부터)에 `b` 명령을 둔 arm9 이미지."""
    d = bytearray(sc.DISPATCH - sc.ARM9 + 4 * (sc.NOPS + 1))

    def b(at, to):
        return 0xEA000000 | (((to - at - 8) >> 2) & 0xFFFFFF)
    struct.pack_into("<I", d, sc.DISPATCH - 4 - sc.ARM9, b(sc.DISPATCH - 4, default))
    for k in range(sc.NOPS):
        at = sc.DISPATCH + 4 * k
        struct.pack_into("<I", d, at - sc.ARM9, b(at, targets.get(k, default)))
    return bytes(d)


class DispatchTests(unittest.TestCase):
    def test_branch_forward_and_backward(self):
        arm9 = arm9_with_dispatch({0: sc.DISPATCH + 0x1000, 5: 0x02000100}, 0x02010000)
        hs = sc.handlers(arm9)
        self.assertEqual(len(hs), sc.NOPS)
        self.assertEqual(hs[0], sc.DISPATCH + 0x1000)
        self.assertEqual(hs[5], 0x02000100)          # 뒤로 뛰는 분기(부호 있는 24비트)
        self.assertEqual(hs[1], 0x02010000)
        self.assertEqual(sc.branch(arm9, sc.DISPATCH - 4), 0x02010000)

    def test_groups_have_no_duplicates(self):
        seen = [op for ops in sc.GROUPS.values() for op in ops]
        self.assertEqual(len(seen), len(set(seen)))
        self.assertTrue(all(op < sc.NOPS for op in seen + list(sc.OPS)))


class CliTests(unittest.TestCase):
    def test_tree_dump_stats_ops(self):
        with tempfile.TemporaryDirectory() as d:
            sdir = os.path.join(d, "SCRIPT")
            os.makedirs(sdir)
            path = os.path.join(sdir, "caf1.bin")
            with open(path, "wb") as f:
                f.write(SAMPLE)
            arm9 = os.path.join(d, "arm9.bin")
            with open(arm9, "wb") as f:
                f.write(arm9_with_dispatch({0x86: 0x02020000}, 0x02010000))
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                sc.main(["tree", path])
                sc.main(["dump", path])
                sc.main(["stats", sdir])
                sc.main(["ops", arm9, sdir])
            out = buf.getvalue()
        self.assertIn("scriptobject", out)
        self.assertIn("모습 0x12 방향 2 자리 (1.5, 0, -3)", out)
        self.assertIn("062 효과음: 300", out)
        self.assertIn("파일 1, 함수 3, 명령 5", out)
        self.assertIn("086\t02020000\t1\t1\t소리\t곡 틀기", out)
        self.assertIn("087\t02010000\t0\t-\t소리\t(처리 없음)", out)
        with self.assertRaises(SystemExit):
            sc.main(["x"])
        with self.assertRaises(SystemExit):
            sc.main(["nope", "y"])


if __name__ == "__main__":
    unittest.main()
