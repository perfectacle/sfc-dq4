"""dq4libretro 의 리눅스 데이터 세그먼트 찾기. 이것이 빈 목록이면 bsnes 는 WRAM 을 직렬화로만 읽고 써서 타이밍이 바뀌고,
리눅스 러너(CI 배포 관문)에서 호환성 걷기가 첫 구간부터 어긋난다."""
import os
import tempfile
import unittest
from pathlib import Path

import dq4libretro


class LinuxSegmentsTest(unittest.TestCase):
    def maps(self, lib, text):
        d = tempfile.mkdtemp()
        f = Path(d) / 'maps'
        f.write_text(text.replace('LIB', lib))
        return f

    def test_lib_rw_and_following_bss(self):
        with tempfile.NamedTemporaryFile(suffix='.so') as so:
            lib = os.path.realpath(so.name)
            f = self.maps(lib, '\n'.join([
                '1000-2000 r-xp 00000000 08:01 1 LIB',
                '2000-3000 r--p 00001000 08:01 1 LIB',
                '3000-4000 rw-p 00002000 08:01 1 LIB',
                '4000-9000 rw-p 00000000 00:00 0 ',
                '9000-a000 rw-p 00000000 00:00 0 ',
                'b000-c000 rw-p 00000000 00:00 0 ',
                'c000-d000 rw-p 00000000 08:01 2 /usr/lib/other.so',
                'd000-e000 rw-p 00000000 00:00 0 [heap]',
            ]) + '\n')
            self.assertEqual(dq4libretro.linux_segments(so.name, f),
                             [(0x3000, 0x1000), (0x4000, 0x5000), (0x9000, 0x1000)])

    def test_unknown_lib_or_missing_maps(self):
        f = self.maps('/x/a.so', '3000-4000 rw-p 00002000 08:01 1 LIB\n')
        self.assertEqual(dq4libretro.linux_segments('/nowhere/b.so', f), [])
        self.assertEqual(dq4libretro.linux_segments('/nowhere/b.so', '/nonexistent/maps'), [])


if __name__ == '__main__':
    unittest.main()
