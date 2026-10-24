# 참고 자료

저장소에는 링크만 둡니다. 내려받은 사본은 `refs/` 에 두면 커밋되지 않습니다.

## DQ5(SFC)

| 자료 | 다루는 것 |
| --- | --- |
| [「ドラクエ命」 SFC 版ドラクエ 5](https://showa-yojyo.github.io/dqbook/dq5.html) ([소스](https://github.com/showa-yojyo/dqbook)) | 구조체, 텍스트(허프만 부호), 인카운트, 몬스터, 상점 |
| [DQバイナリ改造 @Wiki: 圧縮 - SFC-DQ5](https://w.atwiki.jp/dq_binary/pages/29.html) | 스프라이트·몬스터 그래픽 압축 |
| [DQバイナリ改造 @Wiki: 解析（RAM） - SFC-DQ5](https://w.atwiki.jp/dq_binary/pages/23.html) | RAM 주소(파티, 이벤트 플래그, 인물 데이터) |

atwiki 는 스크립트 접근을 막을 때가 있어 [Wayback Machine](https://web.archive.org/web/2024/https://w.atwiki.jp/dq_binary/pages/29.html) 사본으로 읽었습니다.
RAM 페이지의 「`7EFC00-` マップデータ」는 실제와 다릅니다([dq5-map-format.md](dq5-map-format.md#위키와-다른-점)).

## DQ4(FC)

| 자료 | 다루는 것 |
| --- | --- |
| [TheAnsarya/dragon-warrior-4-info](https://github.com/TheAnsarya/dragon-warrior-4-info) | 북미판 전체 디스어셈블리, 에셋 추출, 편집기 |
| [JEschete/DW4_Disassembly](https://github.com/JEschete/DW4_Disassembly) | 북미판 바이트 단위 디스어셈블리 |

둘 다 북미판(Dragon Warrior IV) 기준입니다. 일본판은 텍스트·폰트·일부 주소가
다르므로 구조만 참고하고, 주소는 일본판에서 다시 찾습니다.

### DQ4 포팅용 그래픽

| 자료 | 참고한 것 |
| --- | --- |
| [Realm of Darkness: NES DQ4 sprites](https://www.realmofdarkness.net/dq/nes-dw4-sprites/) | 원작 인물의 윤곽·비율과 타일의 조밀한 무늬 |
| [Realm of Darkness: Nintendo DS DQ4 sprites](https://www.realmofdarkness.net/dq/ds-dq4-sprites/) | 라이안·호이미 슬라임의 색 구분과 특징 |
| [Realm of Darkness: SFC DQ5 sprites](https://www.realmofdarkness.net/dq/snes-dq5-sprites/) | 이식 대상 엔진의 인물 표현 참고 |

사용자가 제공한 Nintendo DS DQ4 타이틀 화면은 하늘·용·로고의 색감 참고로 사용했습니다. 지형 표현은 저장소의 [DQ5 맵 비교 그림](images/dq5-map-0206-compare.webp)과 [낮·밤 그림](images/dq5-map-0206-day-night.webp)도 참고했습니다. 자료의 픽셀 데이터를 제작물에 복사하지 않았으며, 외부 참고 이미지 사본은 배포하지 않습니다. 제작 원본과 변환 규격은 [dq4-graphics.md](dq4-graphics.md)에 있습니다.

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
