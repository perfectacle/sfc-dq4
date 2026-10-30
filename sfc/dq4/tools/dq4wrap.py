"""메시지 창 줄바꿈. 대사를 쓸 때 줄 자리를 신경 쓰지 않도록 낱말(띄어쓰기) 단위로 칸을 세어 나눈다."""


def wrap(text, width, cols, first=0, page_lines=None):
    """text 를 줄 목록으로. '/' 는 그 자리에서 억지로 줄을 바꾼다(없어도 된다).

    width(s): s 가 차지하는 칸. first: 쪽 첫 줄에서 말하는 이 이름이 더 차지하는 칸.
    page_lines 가 있으면 쪽이 바뀔 때마다 첫 줄에 first 를 다시 뺀다.
    """
    lines = []

    def room(n):
        top = n == 0 if page_lines is None else n % page_lines == 0
        return cols - (first if top else 0)

    for segment in text.split('/'):
        cur = ''
        for word in segment.split(' '):
            cand = f'{cur} {word}' if cur else word
            if cur and width(cand) > room(len(lines)):
                lines.append(cur)
                cur = word
            else:
                cur = cand
        lines.append(cur)
    for n, line in enumerate(lines):
        if width(line) > room(n):
            raise ValueError(f'낱말 하나가 한 줄({room(n)}칸)보다 김: {line}')
    return lines
