"""Conservative name suggestions. File tags are evidence, not identification."""
from dataclasses import dataclass
import re
import html
import unicodedata
from audio_io import read_metadata


@dataclass(frozen=True)
class SongSuggestion:
    title: str
    artist: str
    source: str


def clean_text(text):
    return ' '.join(unicodedata.normalize('NFC',html.unescape(str(text or ''))).split())


def clean_title(text):
    text=clean_text(text)
    noise={'official','music','video','audio','lyric','lyrics','hd','hq','4k','1080p','visualizer','visualiser','youtube'}
    while True:
        match=re.search(r'\s*[\[(]([^\[\]()]+)[\])]\s*$',text)
        bracket=match is not None
        if match is None:match=re.search(r'\s+[-–—|]\s+([^|]+)$',text)
        if match is None:break
        suffix=match.group(1)
        words=set(re.findall(r'[\w]+',suffix.casefold()))
        promotional=bool(words and words<=noise and words-{'music'})
        youtube_id=(bracket and re.fullmatch(r'[A-Za-z0-9_-]{11}',suffix) is not None
                    and any(c.isdigit() or c in '_-' for c in suffix)
                    and text[match.start():].lstrip().startswith('['))
        if not promotional and not youtube_id:break
        text=text[:match.start()].strip()
    return text


def _artist_key(text):
    # Honorifics can differ between a filename/title prefix and the artist tag.
    # Normalize only for comparison; never remove them from the displayed artist.
    name=re.sub(r'^(?:ms|mrs|mr|miss|dr)\.?\s+','',clean_text(text),flags=re.IGNORECASE)
    return ''.join(c for c in name.casefold() if c.isalnum())


def filename_names(path):
    filename=re.split(r'[/\\]',str(path))[-1]
    stem=filename.rsplit('.',1)[0] if '.' in filename else filename
    stem=clean_title(stem)
    track=re.match(r'^\d{1,3}\s*[-.]\s*(.+)$',stem)
    if track and re.search(r'\s+[-–—]\s+',track.group(1)):stem=track.group(1)
    parts=re.split(r'\s+[-–—]\s+',stem,maxsplit=1)
    if len(parts)==2:return clean_text(parts[0]),clean_title(parts[1])
    return '',stem


def suggest_names(path,cancel=None):
    tags=read_metadata(path,cancel=cancel)
    artist=clean_title(tags.get('artist',''))
    artist=re.sub(r'\s+-\s+Topic$','',artist,flags=re.IGNORECASE)
    title=clean_title(tags.get('title',''))
    file_artist,file_title=filename_names(path)
    result=[]
    if title or artist:
        title=title or file_title
        parts=re.split(r'\s+[-–—]\s+',title,maxsplit=1)
        if len(parts)==2:
            if artist and _artist_key(parts[0])==_artist_key(artist):title=clean_title(parts[1])
            elif not artist and file_artist and _artist_key(parts[0])==_artist_key(file_artist):
                artist=clean_text(parts[0]);title=clean_title(parts[1])
        artist=artist or file_artist
        result.append(SongSuggestion(title,artist,'File tags' if tags.get('title') and tags.get('artist') else 'File tags and filename'))
    candidate=SongSuggestion(file_title,file_artist,'Filename (unverified)')
    if file_title and not any((s.title,s.artist)==(candidate.title,candidate.artist) for s in result):result.append(candidate)
    return result


# MusicBrainz public recording search: no key, media upload, or fingerprinting.
import json
import threading
import time
from urllib.error import HTTPError,URLError
from urllib.parse import urlencode
from urllib.request import Request,urlopen

_request_lock=threading.Lock()
_last_request=0.


def _wait_for_musicbrainz(cancel):
    global _last_request
    with _request_lock:
        delay=max(0,1.1-(time.monotonic()-_last_request))
        if cancel is not None:
            if cancel.event.wait(delay):cancel.check()
        elif delay:time.sleep(delay)
        _last_request=time.monotonic()


def search_musicbrainz(artist,title,cancel=None):
    title=clean_title(title)
    if not title:return []
    def quote(text):return '"'+text.replace('\\','\\\\').replace('"','\\"')+'"'
    query='recording:'+quote(title)
    if artist:query+=' AND artist:'+quote(clean_text(artist))
    url='https://musicbrainz.org/ws/2/recording/?'+urlencode({'query':query,'fmt':'json','limit':10})
    _wait_for_musicbrainz(cancel)
    if cancel is not None:cancel.check()
    request=Request(url,headers={'User-Agent':'DeRoCinematicVisualizer/0.1.33 (https://github.com/oscargo/DeRo-Cinematic-Visualizer)',
                                 'Accept':'application/json'})
    with urlopen(request,timeout=10) as response:
        raw=response.read(2_000_001)
    if cancel is not None:cancel.check()
    if len(raw)>2_000_000:raise ValueError('Online response too large')
    document=json.loads(raw)
    suggestions=[]
    for recording in document.get('recordings',[]):
        try:score=int(recording.get('score',0))
        except (TypeError,ValueError):continue
        if score<80:continue
        credits=recording.get('artist-credit',[])
        artist_name=''.join(clean_text(c.get('artist',{}).get('name') or c.get('name',''))+c.get('joinphrase','')
                            for c in credits if isinstance(c,dict)).strip()
        song=clean_title(recording.get('title',''))
        parts=re.split(r'\s+[-–—]\s+',song,maxsplit=1)
        if len(parts)==2 and _artist_key(parts[0])==_artist_key(artist_name):song=clean_title(parts[1])
        if not song or not artist_name:continue
        key=(song.casefold(),artist_name.casefold())
        if any((s.title.casefold(),s.artist.casefold())==key for s in suggestions):continue
        suggestions.append(SongSuggestion(song,artist_name,'MusicBrainz'))
    return suggestions


def find_names(path,cancel=None):
    """Tags first, then online search; return local evidence when offline/no match."""
    local=suggest_names(path,cancel=cancel)
    if not local:return [],'No title was found. Enter the names manually.'
    first=local[0]
    seeds=[(first.artist,first.title)]
    file_artist,file_title=filename_names(path)
    if first.artist:seeds.append(('',first.title))
    elif (file_artist,file_title)!=seeds[0] and file_title:seeds.append((file_artist,file_title))
    online=[];notice='No confident online match was found. Review the file information or enter the names manually.'
    try:
        for artist,title in list(dict.fromkeys(seeds))[:2]:
            online=search_musicbrainz(artist,title,cancel=cancel)
            if online:break
        if online:notice='Online matches found. Check the artist and song before applying them.'
    except HTTPError as exc:
        notice=('The music database is busy. Try again later; file suggestions are shown below.' if exc.code in (429,503) else
                'Online lookup was blocked. File suggestions are shown below.')
    except (URLError,TimeoutError,OSError):
        notice='Online lookup is unavailable. Check your internet connection; file suggestions are shown below.'
    except (ValueError,TypeError,AttributeError):
        notice='The music database returned an unreadable response. File suggestions are shown below.'
    result=online[:]
    for suggestion in local:
        if not any((s.title.casefold(),s.artist.casefold())==(suggestion.title.casefold(),suggestion.artist.casefold()) for s in result):
            result.append(suggestion)
    return result,notice


def review_names(title,artist):
    title=clean_title(title);artist=clean_title(artist)
    parts=re.split(r'\s+[-–—]\s+',title,maxsplit=1)
    if len(parts)==2 and artist and _artist_key(parts[0])==_artist_key(artist):title=clean_title(parts[1])
    return title,artist
