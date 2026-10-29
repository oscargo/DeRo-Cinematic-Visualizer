"""DeRo Sync ASS layout/highlighting, adapted to remove the Qt color dependency."""
import math,re
from pathlib import Path

def safe_ass(s):
    return str(s).replace('\\', '\\\\').replace('{', '(').replace('}', ')').replace('\n', ' ')

def ass_timestamp(seconds):
    cs = max(0, round(float(seconds) * 100))
    return f'{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}'

def check_word_timing_integrity(project):
    """Return non-destructive warnings for review; keep overlapping data unchanged."""
    warnings = []
    for key, words in project.get('word_timings', {}).items():
        prev = None
        for i, entry in enumerate(words):
            try:
                start, end, _ = entry
                start = float(start)
                end = float(end)
                if not all(map(math.isfinite, (start, end))) or start < 0 or end <= start:
                    warnings.append(f'Line {key}, word {i + 1}: invalid start/end')
                if prev is not None and start < prev - 0.001:
                    warnings.append(f'Line {key}, word {i + 1}: starts before preceding word ends')
                prev = end
            except (ValueError, TypeError, IndexError):
                warnings.append(f'Line {key}, word {i + 1}: malformed timing')
    return warnings

def ass_file(project, filename, width=1920, height=1080):
    """Render single, preview, or alternating lyrics with exclusive time slots."""
    events = project.get('events', [])
    timings = project.get('word_timings', {})
    lead = max(0.0, min(5.0, float(project.get('lyric_lead_seconds', 2))))
    mode = project.get('lyric_display_mode')
    if mode not in ('single', 'preview', 'alternating', 'classic_flow'):
        mode = 'preview' if project.get('lyric_read_ahead', False) else 'single'
    ahead = mode != 'single'
    flow = mode == 'classic_flow'
    flow_lines = max(2, min(3, int(project.get('classic_flow_lines', 3))))
    flow_fade_in = max(0, min(1500, int(project.get('classic_flow_fade_in', 300))))
    flow_fade_out = max(0, min(2000, int(project.get('classic_flow_fade_out', 400))))
    final_fade = max(0, min(5000, int(project.get('lyric_final_fade_out', 2000))))
    break_bar = bool(project.get('silence_progress_enabled', False))
    break_threshold = max(1.0, min(60.0, float(project.get('silence_progress_threshold', 5.0))))
    flow_hold = max(0.0, min(1.0, float(project.get('lyric_exit_delay', 150)) / 1000.0))
    progress_enabled = bool(project.get('opening_progress_enabled', project.get('lyric_countdown', True)))
    progress_length = max(0.5, min(20.0, float(project.get('opening_progress_duration', 5.0))))
    progress_before = max(0.0, min(30.0, float(project.get('opening_progress_before', 5.0))))
    fontsize = max(24, min(120, int(project.get('lyric_font_size', 72))))
    fontname = str(project.get('lyric_font_family', 'Arial')).replace(',', '').replace('\n', '').strip() or 'Arial'
    bold_ass = -1 if project.get('lyric_font_bold', True) else 0
    outline = max(0, min(8, int(project.get('lyric_outline', 3))))
    vertical = max(12, min(88, int(project.get('lyric_vertical_percent', 53))))
    center_y = round(height * vertical / 100)
    row_gap = round(fontsize * 1.55)
    top_y = max(fontsize, center_y - row_gap // 2) if ahead else center_y
    bottom_y = min(height - fontsize, center_y + row_gap // 2)

    def ass_color(hex_color):
        value = str(hex_color).lstrip('#')
        if not re.fullmatch('[0-9a-fA-F]{6}', value):
            value = 'FFFFFF'
        red, green, blue = (int(value[i:i + 2], 16) for i in (0, 2, 4))
        return f'&H00{blue:02X}{green:02X}{red:02X}'
    color_white = ass_color(project.get('lyric_unsung_color', '#EAF3FF'))
    color_pink = ass_color(project.get('lyric_sung_color', '#31B9FF'))
    header = f'[Script Info]\nTitle: Karaoke Maker Lite - Configurable Lyric Rows\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Active,{fontname},{fontsize},{color_pink},{color_white},&H00000000,&H80000000,{bold_ass},0,0,0,100,100,0,0,1,{outline},1,5,90,90,0,1\nStyle: Next,{fontname},{fontsize},{color_white},{color_white},&H00000000,&H80000000,{bold_ass},0,0,0,100,100,0,0,1,{outline},1,5,90,90,0,1\nStyle: Progress,Arial,18,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
    out = [header]
    parsed = []
    for i, event in enumerate(events):
        try:
            a, b, t = event
            a = float(a)
            b = float(b)
            if b <= a or not str(t).strip():
                continue
            parsed.append((i, a, b, str(t)))
        except (TypeError, ValueError):
            continue
    parsed.sort(key=lambda x: (x[1], x[0]))
    if not parsed:
        Path(filename).write_text(header, encoding='utf-8-sig')
        return
    opening_bar_end = min(parsed[0][1], max(0.0, parsed[0][1] - progress_before) + progress_length) if progress_enabled and progress_before > 0 else -1.0

    def add(a, b, style, lyric, layer=0, y=None, fade_out=0):
        if b > a + 0.01:
            prefix = '{\\an5\\pos(' + str(width // 2) + ',' + str(y if y is not None else top_y) + ')}'
            if fade_out:prefix += r'{\fad(0,'+str(fade_out)+')}'
            out.append(f'Dialogue: {layer},{ass_timestamp(a)},{ass_timestamp(b)},{style},,0,0,0,,{prefix}{lyric}\n')

    def text_units(value):
        return sum((0.35 if ch.isspace() else 0.95 if ch in 'MW@#%&' else 0.58 for ch in str(value)))

    def line_layout(text):
        """Preserve the chosen font size by wrapping once before shrinking."""
        words = str(text).split()
        available = max(160.0, width - 180.0)
        if not words:
            return (fontsize, (), words)
        total = text_units(' '.join(words))
        if total * fontsize <= available:
            return (fontsize, (), words)
        if len(words) == 1:
            return (max(24, min(fontsize, int(available / max(1.0, total)))), (), words)
        choices = []
        for split in range(1, len(words)):
            left = text_units(' '.join(words[:split]))
            right = text_units(' '.join(words[split:]))
            choices.append((max(left, right), abs(left - right), split))
        largest, _imbalance, split = min(choices)
        fitted = max(24, min(fontsize, int(available / max(1.0, largest))))
        return (fitted, (split,), words)

    def line_override(text):
        fitted, _breaks, _words = line_layout(text)
        return '{\\q2\\fs' + str(fitted) + '}'

    def plain_text(text):
        fitted, breaks, words = line_layout(text)
        if not words:
            return '{\\q2\\fs' + str(fitted) + '}'
        rendered = []
        for position, word in enumerate(words, 1):
            rendered.append(safe_ass(word))
            if position < len(words):
                rendered.append('\\N' if position in breaks else ' ')
        return '{\\q2\\fs' + str(fitted) + '}' + ''.join(rendered)

    def layout_rows(text):
        fitted, breaks, _words = line_layout(text)
        return (fitted, len(breaks) + 1)

    def stack_positions(texts):
        metrics = [layout_rows(text) for text in texts]
        heights = [max(1, round(size * 1.18 * rows)) for size, rows in metrics]
        gap = round(fontsize * 0.48)
        total = sum(heights) + gap * max(0, len(heights) - 1)
        top = max(10.0, min(height - total - 10.0, center_y - total / 2))
        positions = []
        cursor = top
        for block_height in heights:
            positions.append(round(cursor + block_height / 2))
            cursor += block_height + gap
        return positions

    def word_text(idx, a, b, text):
        """ASS progressive fills follow absolute word ONSETS, not summed word lengths.

  ASS karaoke-tag durations are sequential. Duration-to-next-onset preserves the saved
  word start positions even when a word's stored end overlaps the next word.
  Sequential karaoke tags cannot show simultaneous words;
  the next onset takes precedence and overlapping intervals are flagged in QA.
  """
        ww = timings.get(str(idx), [])
        if not ww:
            return plain_text(text)
        clean = []
        for entry in ww:
            try:
                wa, wb, word = entry
                wa = float(wa)
                wb = float(wb)
                if not math.isfinite(wa) or not math.isfinite(wb) or (not str(word).strip()):
                    continue
                clean.append((max(a, min(b, wa)), str(word)))
            except (TypeError, ValueError):
                continue
        if not clean:
            return plain_text(text)
        expected = [re.sub('[^\\w]+', '', token.casefold(), flags=re.UNICODE) for token in str(text).split()]
        timed = [re.sub('[^\\w]+', '', word.casefold(), flags=re.UNICODE) for _, word in clean]
        if expected != timed:
            return plain_text(text)
        starts = []
        last = a
        display_words = str(text).split()
        for (wa, _timed_word), display_word in zip(clean, display_words):
            last = max(last, wa)
            starts.append((last, display_word))
        fitted, breaks, _words = line_layout(text)
        pieces = ['{\\q2\\fs' + str(fitted) + '}']
        if starts[0][0] > a + 0.005:
            pieces.append('{\\k' + str(max(0, round((starts[0][0] - a) * 100))) + '}' + '\\h')
        for j, (onset, word) in enumerate(starts):
            next_onset = starts[j + 1][0] if j + 1 < len(starts) else b
            centiseconds = max(0, round((max(onset, next_onset) - onset) * 100))
            separator = '\\N' if j + 1 in breaks else ' '
            pieces.append('{\\kf' + str(centiseconds) + '}' + safe_ass(word) + (separator if j + 1 < len(starts) else ''))
        return ''.join(pieces) or plain_text(text)

    def add_opening_progress_bar():
        """One centered ASS vector progress bar, shown only before first sung lyric.

  Duration and start-before-first-lyric are independent settings. A bar that
  would extend into singing is truncated to avoid covering active lyrics.
  """
        if not progress_enabled or not parsed or progress_before <= 0:
            return
        first_start = max(0.0, float(parsed[0][1]))
        begin = max(0.0, first_start - progress_before)
        end = min(first_start, begin + progress_length)
        if end <= begin + 0.02:
            return
        bar_width = max(120, int(width * 0.48))
        bar_height = max(13, int(height * 0.022))
        left = (width - bar_width) // 2
        right = left + bar_width
        top = (height - bar_height) // 2
        bottom = top + bar_height

        def rect(x1, y1, x2, y2):
            return f'm {x1} {y1} l {x2} {y1} {x2} {y2} {x1} {y2}'

        def shape(a, b, layer, fill, geometry):
            tags = '{\\an7\\pos(0,0)\\bord0\\shad0\\1c&H' + fill + '&\\p1}'
            out.append(f'Dialogue: {layer},{ass_timestamp(a)},{ass_timestamp(b)},Progress,,0,0,0,,{tags}{geometry}' + '{\\p0}' + '\n')
        shape(begin, end, 5, '334158', rect(left - 4, top - 4, right + 4, bottom + 4))
        shape(begin, end, 6, '18121E', rect(left, top, right, bottom))
        count = max(2, min(100, int((end - begin) * 20)))
        for step in range(count):
            a = begin + (end - begin) * step / count
            b = begin + (end - begin) * (step + 1) / count
            fill_end = left + max(1, round(bar_width * (step + 1) / count))
            shape(a, b, 7, 'FFB975', rect(left, top, fill_end, bottom))

    def add_silence_progress_bars():
        if not break_bar or len(parsed) < 2:
            return
        bar_width = max(120, int(width * 0.48))
        bar_height = max(10, int(height * 0.018))
        left = (width - bar_width) // 2
        top = (height - bar_height) // 2

        def rect(x1, y1, x2, y2):
            return f'm {x1} {y1} l {x2} {y1} {x2} {y2} {x1} {y2}'

        def shape(a, b, layer, fill, geometry):
            if b <= a + 0.015:
                return
            tags = '{\\an7\\pos(0,0)\\bord0\\shad0\\1c&H' + fill + '&\\p1}'
            out.append(f'Dialogue: {layer},{ass_timestamp(a)},{ass_timestamp(b)},Progress,,0,0,0,,{tags}{geometry}' + '{\\p0}' + '\n')
        for pos in range(len(parsed) - 1):
            idx, a, b, _ = parsed[pos]
            next_start = parsed[pos + 1][1]
            ends = []
            for entry in timings.get(str(idx), []):
                try:
                    end = float(entry[1])
                    if math.isfinite(end):
                        ends.append(end)
                except (TypeError, ValueError, IndexError):
                    pass
            sung_end = max(ends) if ends else b
            begin = max(0.0, sung_end + flow_hold + min(flow_fade_out / 1000.0, 0.5))
            finish = next_start
            if finish - sung_end < break_threshold or finish - begin <= 0.08:
                continue
            shape(begin, finish, 5, '334158', rect(left - 4, top - 4, left + bar_width + 4, top + bar_height + 4))
            shape(begin, finish, 6, '18121E', rect(left, top, left + bar_width, top + bar_height))
            count = max(2, min(160, int((finish - begin) * 15)))
            for step in range(count):
                ta = begin + (finish - begin) * step / count
                tb = begin + (finish - begin) * (step + 1) / count
                shape(ta, tb, 7, 'FFB975', rect(left, top, left + max(1, round(bar_width * (step + 1) / count)), top + bar_height))
    if flow:
        spacing = round(fontsize * 1.55)
        first_y = max(fontsize + 12, min(height - fontsize * 3, center_y - spacing))

        def dialogue_flow(a, b, style, content, y, layer=0, fade_in=0, fade_out=0, move=False):
            if b <= a + 0.02:
                return
            duration_ms = int((b - a) * 1000)
            fi = min(fade_in, duration_ms // 3)
            fo = min(fade_out, duration_ms // 2)
            effect = '{\\an5\\move(' + str(width // 2) + ',' + str(y + round(fontsize * 0.18)) + ',' + str(width // 2) + ',' + str(y) + ',0,' + str(min(300, duration_ms // 2)) + ')}' if move else '{\\an5\\pos(' + str(width // 2) + ',' + str(y) + ')}'
            if fi or fo:
                effect += '{\\fad(' + str(fi) + ',' + str(fo) + ')}'
            out.append(f'Dialogue: {layer},{ass_timestamp(a)},{ass_timestamp(b)},{style},,0,0,0,,{effect}{content}\n')

        def line_sung_end(idx, fallback):
            ends = []
            for entry in timings.get(str(idx), []):
                try:
                    value = float(entry[1])
                    if math.isfinite(value):
                        ends.append(value)
                except (TypeError, ValueError, IndexError):
                    pass
            return max(ends) if ends else float(fallback)
        previous_page_end = 0.0
        for page_pos in range(0, len(parsed), flow_lines):
            page = parsed[page_pos:page_pos + flow_lines]
            page_start = max(0.0, page[0][1] - lead, previous_page_end, opening_bar_end if page_pos == 0 else 0.0)
            sung_ends = [line_sung_end(item[0], item[2]) for item in page]
            last_word_end = max(sung_ends)
            this_fade = final_fade if page_pos + flow_lines >= len(parsed) else flow_fade_out
            page_end = max(page_start + 0.03, last_word_end) + flow_hold + this_fade / 1000.0
            page_fade_in = min(flow_fade_in, int((page_end - page_start) * 1000) // 3)
            page_fade_out = min(this_fade, int((page_end - page_start) * 1000) // 2)
            positions = stack_positions([item[3] for item in page])
            first_y = positions[0]
            for row, (idx, a, b, lyric) in enumerate(page):
                y = positions[row]
                sung_end = max(a + 0.02, sung_ends[row])
                if a > page_start:
                    dialogue_flow(page_start, min(a, page_end), 'Next', plain_text(lyric), y, 1, page_fade_in, 0, True)
                active_start = max(page_start, a)
                if page_end > active_start:
                    dialogue_flow(active_start, page_end, 'Active', word_text(idx, active_start, sung_end, lyric), y, 3, page_fade_in if active_start == page_start else 0, page_fade_out)
            previous_page_end = page_end
        add_opening_progress_bar()
        add_silence_progress_bars()
        Path(filename).write_text(''.join(out), encoding='utf-8-sig')
        return
    for pos, (idx, a, b, text) in enumerate(parsed):
        previous_end = min(parsed[pos - 1][2], a) if pos else 0.0
        next_start = parsed[pos + 1][1] if pos + 1 < len(parsed) else float('inf')
        slot_start = max(0.0, a - lead, previous_end, opening_bar_end if pos == 0 else 0.0)
        exit_ms=int(project.get('lyric_exit_duration',450)) if project.get('lyric_exit','Fade Out')!='None' else 0
        hold_ms=int(project.get('lyric_exit_delay',150))
        slot_end = min(b+(hold_ms+exit_ms)/1000, next_start)
        if slot_end <= slot_start:
            continue
        if ahead and pos + 1 < len(parsed):
            pair_positions = stack_positions([text, parsed[pos + 1][3]])
            active_y, next_y = pair_positions
            if mode == 'alternating' and pos % 2:
                active_y, next_y = (next_y, active_y)
        else:
            active_y = center_y
            next_y = bottom_y
        if slot_start < a:
            add(slot_start, min(a, slot_end), 'Active', plain_text(text), 1, active_y)
        if slot_end > a:
            add(a, slot_end, 'Active', word_text(idx, a, b, text), 1, active_y, min(exit_ms,round(max(0,slot_end-b)*1000)))
        if ahead and pos + 1 < len(parsed):
            next_text = parsed[pos + 1][3]
            add(slot_start, slot_end, 'Next', plain_text(next_text), 0, next_y)
    add_opening_progress_bar()
    add_silence_progress_bars()
    Path(filename).write_text(''.join(out), encoding='utf-8-sig')
