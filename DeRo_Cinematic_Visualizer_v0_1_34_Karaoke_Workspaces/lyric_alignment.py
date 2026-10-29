"""Toolkit-independent alignment safeguards ported from the supplied DeRo Sync v0.2.0.75."""
import math,re,difflib
from lyric_ass import check_word_timing_integrity

def recover_line_timings(exact, candidates, line_start, line_end, normalize):
    """Preserve only text-matched WhisperX timestamps; estimate gaps explicitly."""
    n = len(exact)
    if not n:
        return ([], [], 0, 0)
    usable = []
    for w in candidates:
        try:
            a = float(w['start'])
            b = float(w['end'])
            if math.isfinite(a) and math.isfinite(b) and (b > a) and normalize(w.get('word', '')):
                usable.append((w, a, b))
        except (KeyError, TypeError, ValueError):
            continue
    pairs = difflib.SequenceMatcher(None, [normalize(t) for t in exact], [normalize(w[0]['word']) for w in usable], autojunk=False)
    anchors = {}
    for block in pairs.get_matching_blocks():
        for k in range(block.size):
            idx = block.a + k
            w, a, b = usable[block.b + k]
            anchors[idx] = (a, b, w.get('score'))
    result = [None] * n
    scores = [None] * n
    for idx, (a, b, score) in anchors.items():
        result[idx] = (a, b)
        scores[idx] = score if isinstance(score, (int, float)) and math.isfinite(score) else None
    for i in range(n):
        if result[i] is not None:
            continue
        left = max((j for j in anchors if j < i), default=None)
        right = min((j for j in anchors if j > i), default=None)
        if left is not None and right is not None:
            lo = anchors[left][1]
            hi = anchors[right][0]
            if hi > lo:
                width = (hi - lo) / (right - left)
                a = lo + width * (i - left - 1)
                b = a + width
            else:
                a = lo
                b = lo + 0.02
        elif left is not None:
            a = anchors[left][1] + 0.18 * (i - left - 1)
            b = a + 0.18
        elif right is not None:
            b = max(0, anchors[right][0] - 0.18 * (right - i - 1))
            a = max(0, b - 0.18)
        else:
            width = max(0.02, (line_end - line_start) / n)
            a = line_start + i * width
            b = a + width
        result[i] = (max(0, a), max(max(0, a) + 0.02, b))
    words = [[round(a, 3), round(max(a + 0.02, b), 3), exact[i]] for i, (a, b) in enumerate(result)]
    return (words, scores, len(anchors), len(usable))

def estimate_line_timings(exact, line_start, line_end):
    """Distribute words across a trusted line window for a safe fallback."""
    if not exact:
        return []
    start = max(0.0, float(line_start))
    end = max(start + 0.02 * len(exact), float(line_end))
    width = (end - start) / len(exact)
    return [[round(start + i * width, 3), round(start + (i + 1) * width, 3), token] for i, token in enumerate(exact)]

def forced_alignment_quality(exact, words, scores):
    """Reject forced-alignment output that is too compressed or unsupported."""
    if not exact or len(words) != len(exact):
        return (False, 'incomplete_word_timing_output')
    try:
        span = float(words[-1][1]) - float(words[0][0])
    except (IndexError, TypeError, ValueError):
        return (False, 'invalid_word_timing_output')
    if not math.isfinite(span) or span <= 0:
        return (False, 'invalid_word_timing_span')
    if check_word_timing_integrity({'word_timings': {'0': words}}):
        return (False, 'invalid_or_overlapping_word_timings')
    if len(exact) >= 2 and span < 0.16 * len(exact):
        return (False, 'implausibly_compressed_word_timing')
    numeric = [float(score) for score in scores if isinstance(score, (int, float)) and math.isfinite(score)]
    if not numeric:
        return (False, 'no_scored_whisperx_word_anchors')
    if numeric:
        average = sum(numeric) / len(numeric)
        low_fraction = sum((score < 0.1 for score in numeric)) / len(numeric)
        if average < 0.15:
            return (False, 'very_low_alignment_confidence')
        if len(numeric) == len(exact) and low_fraction >= 0.5:
            return (False, 'mostly_low_confidence_words')
    return (True, 'forced_alignment_accepted')

def interpolate_anchor_timings(token_count, anchors):
    """Fill missing token spans while preserving real monotonic word anchors."""
    if token_count <= 0:
        return []
    valid = {int(i): (float(v[0]), float(v[1])) for i, v in anchors.items() if 0 <= int(i) < token_count and math.isfinite(float(v[0])) and math.isfinite(float(v[1])) and (float(v[1]) > float(v[0]))}
    if not valid:
        raise ValueError('At least one valid word anchor is required')
    known = sorted(valid)
    starts = [None] * token_count
    ends = [None] * token_count
    for i, (a, b) in valid.items():
        starts[i] = max(0.0, a)
        ends[i] = max(starts[i] + 0.02, b)
    for i in range(token_count):
        if starts[i] is not None:
            continue
        left = max((j for j in known if j < i), default=None)
        right = min((j for j in known if j > i), default=None)
        if left is not None and right is not None:
            starts[i] = starts[left] + (starts[right] - starts[left]) * (i - left) / (right - left)
        elif left is not None:
            starts[i] = starts[left] + (i - left) * 0.22
        else:
            starts[i] = max(0.0, starts[right] - (right - i) * 0.22)
    for i in range(token_count):
        if ends[i] is not None:
            continue
        next_start = starts[i + 1] if i + 1 < token_count else None
        ends[i] = next_start if next_start is not None and next_start > starts[i] else starts[i] + 0.22
    return [(float(starts[i]), float(ends[i])) for i in range(token_count)]

def monotonic_word_anchors(pasted_tokens, recognized_words, normalize):
    """Match repeated lyrics to recognized words without jumping song sections."""
    left = [normalize(token) for token in pasted_tokens]
    right = [normalize(item[0]) for item in recognized_words]
    n = len(left)
    m = len(right)
    if not n or not m:
        return {}
    gap = -1
    match = 3
    mismatch = -2
    previous = [j * gap for j in range(m + 1)]
    moves = [bytearray(m + 1) for _ in range(n + 1)]
    for j in range(1, m + 1):
        moves[0][j] = 2
    for i in range(1, n + 1):
        current = [i * gap] + [0] * m
        moves[i][0] = 1
        for j in range(1, m + 1):
            diagonal = previous[j - 1] + (match if left[i - 1] and left[i - 1] == right[j - 1] else mismatch)
            delete = previous[j] + gap
            insert = current[j - 1] + gap
            best = max(diagonal, delete, insert)
            current[j] = best
            if diagonal == best and left[i - 1] and (left[i - 1] == right[j - 1]):
                moves[i][j] = 0
            elif delete == best:
                moves[i][j] = 1
            elif insert == best:
                moves[i][j] = 2
            else:
                moves[i][j] = 0
        previous = current
    anchors = {}
    i = n
    j = m
    while i or j:
        move = moves[i][j]
        if move == 0:
            if i and j and left[i - 1] and (left[i - 1] == right[j - 1]):
                try:
                    start = float(recognized_words[j - 1][1])
                    end = float(recognized_words[j - 1][2])
                    if math.isfinite(start) and math.isfinite(end) and (end > start):
                        anchors[i - 1] = (start, end)
                except (IndexError, TypeError, ValueError):
                    pass
            i -= 1
            j -= 1
        elif move == 1:
            i -= 1
        else:
            j -= 1
    return anchors

def prepare_alignment_windows(line_token_counts, anchors):
    """Build local lyric-line windows and discard cross-occurrence anchor jumps."""
    filtered = {}
    offset = 0
    for count in line_token_counts:
        entries = [(index, anchors[index]) for index in range(offset, offset + count) if index in anchors]
        clusters = []
        for entry in entries:
            if not clusters or entry[1][0] - clusters[-1][-1][1][1] > 6.0:
                clusters.append([entry])
            else:
                clusters[-1].append(entry)
        if clusters:
            chosen = max(clusters, key=lambda group: (len(group), -(group[-1][1][1] - group[0][1][0])))
            filtered.update(chosen)
        offset += count
    fallback = interpolate_anchor_timings(sum(line_token_counts), filtered)
    windows = []
    offset = 0
    for count in line_token_counts:
        entries = [(index - offset, filtered[index]) for index in range(offset, offset + count) if index in filtered]
        if entries:
            first_index, (first_start, _) = entries[0]
            last_index, (_, last_end) = entries[-1]
            start = max(0.0, first_start - min(1.5, 0.22 * first_index))
            end = last_end + min(1.5, 0.22 * max(0, count - 1 - last_index)) + 0.15
        else:
            spans = fallback[offset:offset + count]
            start = min((x[0] for x in spans))
            end = max((x[1] for x in spans)) + 0.15
        windows.append((start, max(start + 0.1, end)))
        offset += count
    return (windows, filtered)

def reconcile_alignment_segments(inputs, returned, normalize):
    """Map partial WhisperX output back to every requested lyric line."""
    mapped = [None] * len(inputs)
    if not inputs or not returned:
        return mapped
    input_keys = [normalize(item.get('text', '')) for item in inputs]
    returned_keys = [normalize(item.get('text', '')) for item in returned]
    matcher = difflib.SequenceMatcher(None, input_keys, returned_keys, autojunk=False)
    used_inputs = set()
    used_returned = set()
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            ii = block.a + offset
            ri = block.b + offset
            mapped[ii] = returned[ri]
            used_inputs.add(ii)
            used_returned.add(ri)
    pairs = sorted(((ri, ii) for ii, item in enumerate(mapped) if item is not None for ri, returned_item in enumerate(returned) if returned_item is item))

    def number(value, fallback):
        try:
            result = float(value)
            return result if math.isfinite(result) else fallback
        except (TypeError, ValueError):
            return fallback
    for ri, segment in enumerate(returned):
        if ri in used_returned:
            continue
        lower = 0
        upper = len(inputs) - 1
        for known_ri, known_ii in pairs:
            if known_ri < ri:
                lower = max(lower, known_ii + 1)
            elif known_ri > ri:
                upper = min(upper, known_ii - 1)
                break
        candidates = [ii for ii in range(lower, upper + 1) if ii not in used_inputs]
        if not candidates:
            continue
        sa = number(segment.get('start'), 0.0)
        sb = number(segment.get('end'), sa)
        sm = (sa + sb) / 2

        def score(ii):
            item = inputs[ii]
            a = number(item.get('start'), 0.0)
            b = number(item.get('end'), a)
            middle = (a + b) / 2
            text = difflib.SequenceMatcher(None, input_keys[ii], returned_keys[ri], autojunk=False).ratio()
            overlap = max(0.0, min(b, sb) - max(a, sa))
            span = max(0.1, max(b, sb) - min(a, sa))
            return (text * 4 + overlap / span * 2, -abs(middle - sm))
        chosen = max(candidates, key=score)
        mapped[chosen] = segment
        used_inputs.add(chosen)
        pairs.append((ri, chosen))
        pairs.sort()
    return mapped
