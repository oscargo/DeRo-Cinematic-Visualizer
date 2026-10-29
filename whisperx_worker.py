"""Isolated WhisperX worker; original pasted words remain authoritative."""
import json,math,re,sys
from pathlib import Path
from lyric_alignment import *
APP_BUILD='Cinematic-Visualizer-0.1.34'

def align_exact_lyrics(source, lyrics, requested_language, emit):
    import whisperx, torch
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    compute = 'float16' if device == 'cuda' else 'int8'
    emit('Alignment device: '+('NVIDIA GPU (CUDA)' if device=='cuda' else 'CPU'))
    emit('Loading WhisperX audio…')
    audio = whisperx.load_audio(source)
    recognition_model = 'small'
    batch_size = 8
    emit(f'Loading {recognition_model} speech recognition model…')
    model = whisperx.load_model(recognition_model, device, compute_type=compute)
    if requested_language in ('en', 'es'):
        language = requested_language
        emit('Song language selected: ' + ('English' if language == 'en' else 'Spanish') + ' (automatic detection bypassed)')
        result = model.transcribe(audio, batch_size=batch_size, language=language)
        detected_language = 'manual:' + language
        language_source = 'manual'
    else:
        result = model.transcribe(audio, batch_size=batch_size)
        detected_language = str(result.get('language') or 'unknown').lower().strip()
        language = detected_language
        language_source = 'automatic'
        if language not in ('en', 'es'):
            import unicodedata
            tokens = [unicodedata.normalize('NFKD', w).casefold().strip('.,!?¿¡:;()[]"\'') for line in lyrics for w in line.split()]
            english = {'the', 'and', 'you', 'your', 'i', 'me', 'my', 'we', 'are', 'is', 'it', 'to', 'of', 'in', 'that', 'for', 'with', 'love', 'dont', 'not', 'on', 'this', 'be', 'was', 'can', 'have'}
            spanish = {'que', 'de', 'la', 'el', 'los', 'las', 'yo', 'tu', 'te', 'mi', 'me', 'es', 'en', 'un', 'una', 'con', 'por', 'para', 'como', 'pero', 'si', 'amor', 'corazon', 'quiero', 'estoy', 'eres', 'tengo'}
            english_score = sum((w in english for w in tokens))
            spanish_score = sum((w in spanish for w in tokens))
            language = 'es' if spanish_score > english_score else 'en'
            language_source = 'lyrics_fallback'
            emit('Detected unsupported/uncertain language ' + detected_language + '. Pasted-lyrics clue: ' + ('Spanish' if language == 'es' else 'English') + '.')
            emit('Retrying transcription as ' + language + '; pasted lyrics will not be modified.')
            result = model.transcribe(audio, batch_size=batch_size, language=language)
    del model
    if device == 'cuda':
        torch.cuda.empty_cache()
    emit('Alignment language: ' + language + ' (detected: ' + detected_language + '; source: ' + language_source + ') — matching pasted words')
    recognized = [seg for seg in result.get('segments', []) if str(seg.get('text', '')).strip()]
    if not recognized:
        raise RuntimeError('No speech was recognized. Try using a vocal stem.')

    def normalize(word):
        return re.sub('[^\\w]+', '', word.casefold(), flags=re.UNICODE)
    emit('Finding word-level anchors in the recognized vocals…')
    align_model, metadata = whisperx.load_align_model(language_code=language, device=device)
    recognized_alignment = whisperx.align(recognized, align_model, metadata, audio, device, return_char_alignments=False)
    recognized_aligned = recognized_alignment.get('segments', [])
    ref = []
    for seg in recognized_aligned:
        for word in seg.get('words', []):
            try:
                token = str(word.get('word', '')).strip()
                a = float(word['start'])
                b = float(word['end'])
                if normalize(token) and math.isfinite(a) and math.isfinite(b) and (b > a):
                    ref.append((normalize(token), a, b))
            except (KeyError, TypeError, ValueError):
                continue
    flat = [(i, token) for i, line in enumerate(lyrics) for token in line.split()]
    anchors = monotonic_word_anchors([token for _, token in flat], ref, normalize)
    candidate_anchor_count = len(anchors)
    if not ref:
        raise RuntimeError('No recognized words to use as timing anchors')
    if not anchors:
        raise RuntimeError('No pasted lyric words matched the recognized word timestamps')
    minimum_words = min(len(flat), max(8, math.ceil(len(flat) * 0.2)))
    minimum_anchors = min(len(flat), max(4, math.ceil(len(flat) * 0.08)))
    if len(ref) < minimum_words or len(anchors) < minimum_anchors:
        raise RuntimeError(f'Automatic synchronization stopped: WhisperX recognized only {len(ref)} timed words and matched {len(anchors)} of {len(flat)} pasted words. Minimum required for this song: {minimum_words} recognized and {minimum_anchors} matching words. No lyrics or existing word timings were replaced. Check that the isolated vocal stem contains clear singing; try a better vocal separation or a stronger Whisper model.')
    line_counts = [len(line.split()) for line in lyrics]
    alignment_windows, anchors = prepare_alignment_windows(line_counts, anchors)
    segments = [{'start': a, 'end': b, 'text': line} for line, (a, b) in zip(lyrics, alignment_windows)]
    emit('Aligning exact pasted lyrics with WhisperX…')
    aligned = whisperx.align(segments, align_model, metadata, audio, device, return_char_alignments=False)
    returned_aligned_segments = aligned.get('segments', [])
    aligned_segments = reconcile_alignment_segments(segments, returned_aligned_segments, normalize)
    missing_segment_count = sum((seg is None for seg in aligned_segments))
    if missing_segment_count:
        emit(f'WhisperX omitted {missing_segment_count} lyric line(s); using local anchor windows for those lines.')
    output = []
    wordmap = {}
    statuses = {}
    scores = {}
    reasons = {}
    matched_counts = {}
    direct_anchor_counts = {}
    offset = 0
    for i, line in enumerate(lyrics):
        seg = aligned_segments[i]
        segment_missing = seg is None
        seg = seg or {}
        exact = line.split()
        input_a = float(segments[i]['start'])
        input_b = float(segments[i]['end'])
        a = float(seg.get('start', input_a))
        b = float(seg.get('end', input_b))
        candidates = [w for w in seg.get('words', []) if str(w.get('word', '')).strip()]
        recovered, word_scores, matched_count, valid_count = recover_line_timings(exact, candidates, a, b, normalize)
        reliable, quality_reason = forced_alignment_quality(exact, recovered, word_scores)
        if segment_missing:
            reliable = False
            quality_reason = 'whisperx_segment_missing'
        direct_count = sum((offset + j in anchors for j in range(len(exact))))
        if reliable:
            output.append([round(a, 3), round(max(a + 0.1, b), 3), line])
            wordmap[str(i)] = recovered
        else:
            output.append([round(input_a, 3), round(max(input_a + 0.1, input_b), 3), line])
            wordmap[str(i)] = estimate_line_timings(exact, input_a, input_b)
        scores[str(i)] = word_scores
        direct_anchor_counts[str(i)] = direct_count
        if not reliable and exact:
            statuses[str(i)] = 'estimated'
            reasons[str(i)] = quality_reason
        elif direct_count == 0 and exact:
            statuses[str(i)] = 'estimated'
            reasons[str(i)] = 'no_direct_transcript_support'
        elif matched_count == len(exact) and direct_count >= max(1, math.ceil(len(exact) * 0.4)):
            statuses[str(i)] = 'aligned'
            reasons[str(i)] = 'all_words_text_matched_to_whisperx_timestamps'
        elif matched_count > 0:
            statuses[str(i)] = 'partial'
            reasons[str(i)] = f'{matched_count}_of_{len(exact)}_words_timed_from_whisperx'
        else:
            statuses[str(i)] = 'estimated' if exact else 'failed'
            reasons[str(i)] = 'no_matching_timestamped_words' if exact else 'empty_line'
        matched_counts[str(i)] = matched_count
        offset += len(exact)
    trusted_lines = sum((status in ('aligned', 'partial') for status in statuses.values()))
    if trusted_lines == 0 or trusted_lines < min(len(lyrics), max(2, math.ceil(len(lyrics) * 0.1))):
        raise RuntimeError(f'Automatic sync rejected: only {trusted_lines} of {len(lyrics)} lines have any supported alignment; the remainder are estimated. Existing word timings have NOT been replaced. Please review the vocals stem and recognition quality before retrying.')
    inspector = {'schema': 3, 'build': APP_BUILD, 'recognition_model': recognition_model, 'detected_language': detected_language, 'language': language, 'requested_language': requested_language, 'language_source': language_source, 'recognized_segments': [{'start': seg.get('start'), 'end': seg.get('end'), 'text': seg.get('text', '')} for seg in recognized], 'recognized_words': [{'token': token, 'start': a, 'end': b} for token, a, b in ref], 'recognized_word_anchors': len(ref), 'candidate_anchor_words': candidate_anchor_count, 'reliable_anchor_words': len(anchors), 'returned_alignment_segments': len(returned_aligned_segments), 'missing_alignment_segments': missing_segment_count, 'direct_anchor_counts': direct_anchor_counts, 'alignment_inputs': [{'start': seg['start'], 'end': seg['end'], 'text': seg['text']} for seg in segments], 'raw_aligned_segments': [{'missing': seg is None, 'start': (seg or {}).get('start'), 'end': (seg or {}).get('end'), 'text': (seg or {}).get('text', ''), 'words': [{'word': w.get('word', ''), 'start': w.get('start'), 'end': w.get('end'), 'score': w.get('score')} for w in (seg or {}).get('words', [])]} for seg in aligned_segments]}
    summary = {'build': APP_BUILD, 'recognition_model': recognition_model, 'detected_language': detected_language, 'language': language, 'requested_language': requested_language, 'language_source': language_source, 'total_lines': len(lyrics), 'recognized_segments': len(recognized), 'recognized_tokens': len(ref), 'pasted_tokens': len(flat), 'candidate_anchor_tokens': candidate_anchor_count, 'anchored_tokens': len(anchors), 'returned_alignment_segments': len(returned_aligned_segments), 'missing_alignment_segments': missing_segment_count, 'line_details': [{'line_index': i + 1, 'status': statuses[str(i)], 'reason': reasons[str(i)], 'word_count': len(lyrics[i].split()), 'direct_anchor_words': direct_anchor_counts[str(i)], 'review_confidence': 'high' if direct_anchor_counts[str(i)] >= max(1, math.ceil(len(lyrics[i].split()) * 0.6)) else 'medium' if direct_anchor_counts[str(i)] else 'review', 'scored_words': sum((isinstance(v, (int, float)) for v in scores[str(i)])), 'matched_timed_words': matched_counts[str(i)]} for i in range(len(lyrics))], 'note': 'No lyric text or audio included. Timing behavior is restored to the verified 0.1.0.31 path. Missing WhisperX result segments use their anchored local window instead of aborting the whole song.'}
    return (output, wordmap, language, statuses, scores, summary, inspector)

def main():
    request=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    result=align_exact_lyrics(request['source'],request['lines'],request['language'],lambda text:print(text,flush=True))
    Path(sys.argv[2]).write_text(json.dumps(result,ensure_ascii=False,allow_nan=False),encoding='utf-8')

if __name__=='__main__':main()
