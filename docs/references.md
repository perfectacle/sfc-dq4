# 참고 자료

`refs/` 에 받아 두고 읽는다(커밋하지 않음).

| 대상 | 자료 | 받는 법 |
| --- | --- | --- |
| DQ5 SFC 구조체·텍스트(허프만)·인카운트·몬스터 | showa-yojyo「ドラクエ命」 https://showa-yojyo.github.io/dqbook/dq5.html | `git clone https://github.com/showa-yojyo/dqbook.git` |
| DQ5 SFC 압축·RAM | DQバイナリ改造 @Wiki https://w.atwiki.jp/dq_binary/pages/29.html , https://w.atwiki.jp/dq_binary/pages/23.html | 웹 |
| DQ4 FC(북미판) 전체 디스어셈블리·에셋 추출 | https://github.com/TheAnsarya/dragon-warrior-4-info | `git clone` |
| DQ4 FC(북미판) 바이트 단위 디스어셈블리 | https://github.com/JEschete/DW4_Disassembly | `git clone` |
| SFC 이식 시도(DQ3 엔진, 초기 단계) | https://github.com/TheAnsarya/dq4r-info | `git clone` |
| DQ6 기반 5장 해킹(아이디어만 참고, 데이터 미사용) | https://ameblo.jp/lockandload1326/entry-12885189324.html | 웹 |

DQ4 디스어셈블리는 북미판 기준이다. 일본판은 텍스트·폰트·일부 주소가 다르므로 구조만 참고하고 주소는 일본판에서 다시 찾는다.

## 도구

- 어셈블러: asar(https://github.com/RPGHacker/asar) 소스 빌드
- 에뮬레이터: Mesen2(디버거·트레이스 로그)
- 공통 도구: kr-patch-toolkit(65c816 디스어셈블러, 타일 렌더링, 헤드리스 테스트)
