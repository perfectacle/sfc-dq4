# 참고 자료

저장소에는 링크만 둡니다. 내려받은 사본은 `refs/` 에 두면 커밋되지 않습니다.

## DQ5(SFC)

| 자료 | 다루는 것 |
| --- | --- |
| [「ドラクエ命」 SFC 版ドラクエ 5](https://showa-yojyo.github.io/dqbook/dq5.html) ([소스](https://github.com/showa-yojyo/dqbook)) | 구조체, 텍스트(허프만 부호), 인카운트, 몬스터, 상점 |
| [DQバイナリ改造 @Wiki: 圧縮 - SFC-DQ5](https://w.atwiki.jp/dq_binary/pages/29.html) | 스프라이트·몬스터 그래픽 압축 |
| [DQバイナリ改造 @Wiki: 解析（RAM） - SFC-DQ5](https://w.atwiki.jp/dq_binary/pages/23.html) | RAM 주소(파티, 이벤트 플래그, 인물 데이터) |

atwiki 는 스크립트 접근을 막을 때가 있어 [Wayback Machine](https://web.archive.org/web/2024/https://w.atwiki.jp/dq_binary/pages/29.html) 사본으로 읽었습니다.
RAM 페이지의 「`7EFC00-` マップデータ」는 실제와 다릅니다([dq5-map-format.md](dq5-map-format.md#참고와-다른-점)).

## DQ4(FC)

| 자료 | 다루는 것 |
| --- | --- |
| [TheAnsarya/dragon-warrior-4-info](https://github.com/TheAnsarya/dragon-warrior-4-info) | 북미판 전체 디스어셈블리, 에셋 추출, 편집기 |
| [JEschete/DW4_Disassembly](https://github.com/JEschete/DW4_Disassembly) | 북미판 바이트 단위 디스어셈블리 |

둘 다 북미판(Dragon Warrior IV) 기준입니다. 일본판은 텍스트·폰트·일부 주소가
다르므로 구조만 참고하고, 주소는 일본판에서 다시 찾습니다.

## 다른 이식 시도

| 자료 | 내용 |
| --- | --- |
| [TheAnsarya/dq4r-info](https://github.com/TheAnsarya/dq4r-info) | DQ3(SFC) 엔진으로 FC판을 옮기는 프로젝트. 데이터 표 단계 |
| [DQ4^{-}(블로그 글)](https://ameblo.jp/lockandload1326/entry-12885189324.html) | DQ6(SFC) 롬을 고친 5장 해킹. 아이디어만 참고하고 데이터는 쓰지 않음 |

## 도구

| 도구 | 쓰는 곳 |
| --- | --- |
| [MesenCE](https://github.com/nesdev-org/MesenCE) | Mesen 2 후속판. 디버거, `--testrunner` 로 Lua 분석 스크립트 실행([tools/README.md](../tools/README.md)) |
| [kr-patch-toolkit](https://github.com/perfectacle/kr-patch-toolkit) | 65c816 디스어셈블(`krpatch sfc dis`), 타일 렌더링, MesenCE 용 Lua 라이브러리 |
| [asar](https://github.com/RPGHacker/asar) | 65c816 어셈블러 |
