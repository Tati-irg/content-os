#!/usr/bin/env python3
"""Проверка голоса на штампы (D-38, VOICE_PROFILE §19). Тата 2.11.2026: «посты шаблонные и скучные».

Ловит по словам то, что делает текст «ботаническим»:
  - «не X, а Y» больше одного раза на текст;
  - шаблонные хвосты: «Листай, там…», «Как вам кажется…», «Как вам такая/такой…», «Сохрани и перешли…»;
  - её фирменные фразы, если их больше одной на текст («есть один нюанс», «так вот», «смотри, что получается»);
  - стоп-лист §10 (самое частое);
  - длинные тире;
  - мат: больше одной точки на текст.
Ровность абзацев тоже меряет: если все абзацы почти одной длины, предупреждает.

Её собственный авторский текст скриптом не правим (§17.23): у неё «Знакомо?» живое.
Скрипт не судит смысл и юмор. Есть ли абсурдная картинка «до точки» и второй слой, смотрит Claude по §19.

Примеры:
  python3 voice/voice_check.py runs/2026-W46/07_TEXTS.md          # по разделам «## …»
  python3 voice/voice_check.py runs/2026-W45/captions/ig2.txt
  python3 voice/voice_check.py runs/2026-W45/captions/            # все .txt в папке
"""
import re, sys
from pathlib import Path

NE_A = re.compile(r'\bне\s+[^.!?\n]{1,60}?,\s*(а|это)\s', re.I)
NE_A2 = re.compile(r'\b(дело|вопрос|это)\s+не\s+в\s+[^.!?\n]{1,50}?[.,]\s*(дело|вопрос)?\s*в\s', re.I)

TAILS = {
    '«Листай, там…»': r'листай,? там',
    '«Как вам кажется…»': r'как вам кажется',
    '«Как вам такая/такой…»': r'как вам так(ая|ой|ое)',
    '«Как вы на это смотрите?»': r'как вы на это смотрите',
    '«Сохрани и перешли…»': r'сохрани\w* и (перешли|подкинь|отправь)',
}
SIGNATURE = {
    '«есть один нюанс»': r'(есть )?один нюанс',
    '«так вот»': r'\bтак вот\b',
    '«смотри, что получается»': r'смотри,? что (получается|происходит)',
    '«и да, и нет»': r'и да,? и нет',
}
STOPLIST = [
    r'знакомо\?', r'узнал[аи]? себя\?', r'спойлер', r'плот-твист', r'правда в том, что', r'вот в ч[её]м штука',
    r'ключевой момент', r'давай разбер[её]мся', r'давай честно', r'важно понимать', r'\bпомни:', r'\bглавное:',
    r'таким образом', r'именно поэтому', r'в заключение', r'подводя итог', r'ты заслуживаешь',
    r'безусловно', r'в современном мире', r'в наше время', r'трансформаци', r'экологичн', r'ресурсн',
    r'наполнен', r'валидн', r'глубинн', r'бережно', r'обнимаю', r'береги себя',
]
MAT = re.compile(r'\b(х[уе][йяеию]\w*|херн\w*|хрен\w*|бля\w*|пизд\w*|еба\w*|ёба\w*|съеба\w*|сыкл\w*|охуе\w*|офиге\w*|насрать|говн\w*)', re.I)


def units_of(path):
    p = Path(path)
    if p.is_dir():
        for f in sorted(p.glob('*.txt')):
            yield f.name, f.read_text(encoding='utf-8')
        return
    text = p.read_text(encoding='utf-8')
    if p.suffix != '.md' or '\n## ' not in '\n' + text:
        yield p.name, text
        return
    title, buf = None, []
    for line in text.splitlines():
        if line.startswith('## '):
            if title and ''.join(buf).strip():
                yield title, '\n'.join(buf)
            title, buf = line[3:].strip(), []
        else:
            buf.append(line)
    if title and ''.join(buf).strip():
        yield title, '\n'.join(buf)


def check(text):
    t = text.lower().replace('ё', 'е')
    body = re.sub(r'#\S+', '', t)
    out = []
    ne_a = [m.group(0) for m in NE_A.finditer(body)] + [m.group(0) for m in NE_A2.finditer(body)]
    if len(ne_a) > 1:
        out.append(('ПЕРЕПИСАТЬ', f'«не X, а Y» {len(ne_a)} раз (можно 1): ' + ' | '.join(s[:50] for s in ne_a[:4])))
    for name, rx in TAILS.items():
        if re.search(rx, body):
            out.append(('ХВОСТ', f'{name}: шаблонный зачин. Финал сильной фразой; если это кейс или дилемма и вопрос нужен (D-37), задать его своими словами, без этой формулы'))
    sig = [name for name, rx in SIGNATURE.items() if re.search(rx, body)]
    if len(sig) > 1:
        out.append(('ПЕРЕПИСАТЬ', 'фирменных фраз больше одной: ' + ', '.join(sig)))
    elif sig:
        out.append(('СВЕРИТЬ', f'{sig[0]}: не чаще раза в неделю на все площадки (§19.3)'))
    for rx in STOPLIST:
        m = re.search(rx, body)
        if m:
            out.append(('СТОП-ЛИСТ', f'«{m.group(0)}» (§10)'))
    if '—' in text:
        out.append(('ПЕРЕПИСАТЬ', f'длинное тире {text.count("—")} раз'))
    mats = MAT.findall(body)
    if len(mats) > 1:
        out.append(('ПЕРЕПИСАТЬ', f'мат {len(mats)} раз, можно одну точку: ' + ', '.join(mats)))
    paras = [p for p in re.split(r'\n\s*\n', re.sub(r'#\S+', '', text)) if len(p.split()) >= 8]
    if len(paras) >= 4:
        lens = [len(p.split()) for p in paras]
        avg = sum(lens) / len(lens)
        if max(lens) - min(lens) <= avg * 0.5:
            out.append(('СВЕРИТЬ', f'абзацы одной длины ({min(lens)}–{max(lens)} слов): нужен перепад, длинная мысль и короткий удар'))
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    bad = 0
    for path in sys.argv[1:]:
        for title, text in units_of(path):
            res = check(text)
            print(f'\n=== {title[:90]}')
            if not res:
                print('  чисто')
            for level, msg in res:
                print(f'  {level}: {msg}')
            bad += sum(l in ('ПЕРЕПИСАТЬ', 'ХВОСТ', 'СТОП-ЛИСТ') for l, _ in res)
    print(f'\nИтог: {"замечаний " + str(bad) if bad else "чисто"}')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
