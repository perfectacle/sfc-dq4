"""음 목록을 오선 악보 MusicXML(3.1 partwise)로 쓰고, verovio 로 SVG 를 그린다. 게임과 무관한 부분이다.

- 시간 단위는 틱이고 4분음표 = PPQ 틱(MusicXML divisions 도 PPQ). 틱이 정수라 음 길이는 그대로 담기고 따로 양자화하지 않는다.
- 마디를 넘는 음은 붙임줄로 나누고, 한 조각은 2진 음표(점 하나까지)와 셋잇단(3:2) 음표의 합으로 가른다.
- 같은 입력이면 같은 바이트가 나온다(시각·임의 id 없음, verovio 는 xmlIdSeed 고정).
"""
from xml.sax.saxutils import escape

STEPS = [('C', 0), ('C', 1), ('D', 0), ('D', 1), ('E', 0), ('F', 0), ('F', 1), ('G', 0), ('G', 1), ('A', 0), ('A', 1), ('B', 0)]
DRUM_DISPLAY = {36: ('F', 4), 38: ('C', 5), 42: ('G', 5)}


def pieces(ppq):
    """(틱, 종류, 점, 셋잇단) — 긴 것부터. 2진은 점 하나까지, 셋잇단은 2진 값의 2/3."""
    base = [('whole', 4), ('half', 2), ('quarter', 1), ('eighth', 0.5), ('16th', 0.25), ('32nd', 0.125), ('64th', 0.0625)]
    out = []
    for name, q in base:
        t = q * ppq
        if t * 1.5 == int(t * 1.5) and t >= 1:
            out.append((int(t * 1.5), name, True, False))
        if t == int(t) and t >= 1:
            out.append((int(t), name, False, False))
        tt = t * 2 / 3
        if tt == int(tt) and tt >= 1:
            out.append((int(tt), name, False, True))
    return sorted(out, key=lambda p: (-p[0], p[3], not p[2]))


def split(d, ppq):
    """길이 d 틱을 음표 조각 목록으로(탐욕). 1 틱까지 나눌 수 있어야 한다."""
    out = []
    for t, name, dot, trip in pieces(ppq):
        while d >= t:
            out.append((t, name, dot, trip))
            d -= t
    assert d == 0, d
    return out


def pitch_xml(m):
    step, alter = STEPS[m % 12]
    oct_ = m // 12 - 1
    return (f'<pitch><step>{step}</step>' + (f'<alter>{alter}</alter>' if alter else '')
            + f'<octave>{oct_}</octave></pitch>')


def note_xml(kind, key, d, name, dot, trip, tie_start, tie_stop, tuplet=None, voice=1):
    """kind: 'pitch'·'drum'·'rest'."""
    x = ['<note>']
    if kind == 'rest':
        x.append('<rest/>')
    elif kind == 'drum':
        st, oc = DRUM_DISPLAY.get(key, ('C', 5))
        x.append(f'<unpitched><display-step>{st}</display-step><display-octave>{oc}</display-octave></unpitched>')
    else:
        x.append(pitch_xml(key))
    x.append(f'<duration>{d}</duration>')
    if tie_stop:
        x.append('<tie type="stop"/>')
    if tie_start:
        x.append('<tie type="start"/>')
    x.append(f'<voice>{voice}</voice><type>{name}</type>')
    if dot:
        x.append('<dot/>')
    if trip:
        x.append('<time-modification><actual-notes>3</actual-notes><normal-notes>2</normal-notes></time-modification>')
    if kind == 'drum' and key == 42:
        x.append('<notehead>x</notehead>')
    if tie_start or tie_stop or tuplet:
        x.append('<notations>' + ('<tied type="stop"/>' if tie_stop else '') + ('<tied type="start"/>' if tie_start else '')
                 + (f'<tuplet type="{tuplet}"/>' if tuplet else '') + '</notations>')
    x.append('</note>')
    return ''.join(x)


def musicxml(title, parts, end, ppq, bar, tempos, loop=None, subtitle=''):
    """parts: [(이름, 'treble'|'bass'|'perc', [(시작 틱, 길이, 음 번호)])], 음은 채널마다 겹치지 않게 정렬돼 있어야 한다.
    end: 마지막 틱, bar: 마디 틱 수(96 = 4/4, 72 = 3/4), tempos: [(틱, 4분음표 BPM)], loop: (시작 틱, 끝 틱) 또는 None.
    되풀이 시작·끝이 마디 경계면 도돌이표, 아니면 그 자리에 글자 표시를 둔다."""
    beats = bar // ppq
    nbars = max(1, -(-end // bar))
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" '
           '"http://www.musicxml.org/dtds/partwise.dtd">',
           '<score-partwise version="3.1">',
           f'<work><work-title>{escape(title)}</work-title></work>',
           '<identification><encoding><software>sfc-dq4 fc/dq4/tools/dq4score.py</software></encoding></identification>']
    if subtitle:
        out.append(f'<credit page="1"><credit-type>subtitle</credit-type><credit-words>{escape(subtitle)}</credit-words></credit>')
    out.append('<part-list>')
    for i, (name, _, _) in enumerate(parts):
        out.append(f'<score-part id="P{i + 1}"><part-name>{escape(name)}</part-name></score-part>')
    out.append('</part-list>')
    marks = {}
    if loop:
        ls, le = loop
        marks.setdefault(ls, []).append('start')
        marks.setdefault(le, []).append('end')
    for i, (name, clef, notes) in enumerate(parts):
        out.append(f'<part id="P{i + 1}">')
        # 음을 마디 경계로 나눈 (시작, 길이, 음 또는 None) 목록
        events, t = [], 0
        for s, d, key in notes:
            s, d = max(s, t), min(s + d, end) - max(s, t)
            if d <= 0:
                continue
            if s > t:
                events.append((t, s - t, None))
            events.append((s, d, key))
            t = s + d
        if t < nbars * bar:
            events.append((t, nbars * bar - t, None))
        by_bar = [[] for _ in range(nbars)]
        for s, d, key in events:
            first = True
            while d > 0:
                b = s // bar
                take = min(d, (b + 1) * bar - s)
                by_bar[b].append((s, take, key, not first, d > take))
                s, d, first = s + take, d - take, False
        for b in range(nbars):
            m0 = b * bar
            out.append(f'<measure number="{b + 1}">')
            if 'start' in marks.get(m0, []):
                out.append('<barline location="left"><bar-style>heavy-light</bar-style><repeat direction="forward"/></barline>')
            if b == 0:
                cl = {'treble': ('G', 2), 'bass': ('F', 4), 'perc': ('percussion', 2)}[clef]
                out.append(f'<attributes><divisions>{ppq}</divisions><key><fifths>0</fifths></key>'
                           f'<time><beats>{beats}</beats><beat-type>4</beat-type></time>'
                           f'<clef><sign>{cl[0]}</sign><line>{cl[1]}</line></clef></attributes>')
            if i == 0:
                for tt, bpm in tempos:
                    if m0 <= tt < m0 + bar:
                        off = tt - m0
                        out.append('<direction placement="above"><direction-type><metronome><beat-unit>quarter</beat-unit>'
                                   f'<per-minute>{bpm:.1f}</per-minute></metronome></direction-type>'
                                   + (f'<offset>{off}</offset>' if off else '') + f'<sound tempo="{bpm:.2f}"/></direction>')
                for tt, kinds in sorted(marks.items()):
                    if m0 <= tt < m0 + bar and not (tt == m0 and kinds == ['start']) and tt != (b + 1) * bar:
                        off = tt - m0
                        words = ' / '.join('되풀이 시작' if k == 'start' else '되풀이 끝' for k in kinds)
                        out.append(f'<direction placement="above"><direction-type><words>{words}</words></direction-type>'
                                   + (f'<offset>{off}</offset>' if off else '') + '</direction>')
            items = []
            for s, d, key, tie_stop, tie_start in by_bar[b]:
                ps = split(d, ppq)
                for j, (pd, name, dot, trip) in enumerate(ps):
                    kind = 'rest' if key is None else 'drum' if clef == 'perc' else 'pitch'
                    items.append([kind, key or 0, pd, name, dot, trip, key is not None and (tie_start or j < len(ps) - 1),
                                  key is not None and (tie_stop or j > 0), None])
            # 같은 종류의 셋잇단 셋이 이어지면(2진 음표 둘 자리) 셋잇단 묶음으로 표시
            j = 0
            while j < len(items):
                run = items[j:j + 3]
                if len(run) == 3 and all(it[5] and it[3] == run[0][3] and not it[4] for it in run):
                    run[0][8], run[2][8] = 'start', 'stop'
                    j += 3
                else:
                    j += 1
            for it in items:
                out.append(note_xml(*it))
            if 'end' in marks.get((b + 1) * bar, []):
                out.append('<barline location="right"><bar-style>light-heavy</bar-style><repeat direction="backward"/></barline>')
            elif b == nbars - 1:
                out.append('<barline location="right"><bar-style>light-heavy</bar-style></barline>')
            out.append('</measure>')
        out.append('</part>')
    out.append('</score-partwise>')
    return '\n'.join(out) + '\n'


def svg_pages(xml):
    """verovio 로 MusicXML → SVG 쪽 목록."""
    import verovio
    tk = verovio.toolkit()
    tk.setOptions({'xmlIdSeed': 1, 'pageWidth': 2100, 'pageHeight': 2970, 'scale': 40, 'adjustPageHeight': True,
                   'footer': 'none', 'header': 'auto', 'breaks': 'auto'})
    if not tk.loadData(xml):
        raise ValueError('verovio 가 MusicXML 을 읽지 못함')
    return [tk.renderToSVG(p) for p in range(1, tk.getPageCount() + 1)]
