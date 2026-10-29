"""App-wide favorite lyric websites, with migration from Maker Lite preferences."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit,urlencode

DEFAULT_SITES=[{'name':'AZLyrics','url':'https://www.azlyrics.com'},
               {'name':'Genius','url':'https://genius.com'},
               {'name':'SongLyrics','url':'https://www.songlyrics.com'}]

def checked_site(name,url):
    name=str(name).strip();url=str(url).strip()
    parsed=urlsplit(url)
    if not name or parsed.scheme.lower() not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Enter a site name and a full http:// or https:// website URL.')
    return {'name':name,'url':url}

class FavoriteSites:
    def __init__(self,path=None,legacy=None):
        self.path=Path(path) if path is not None else Path.home()/'.dero_cinematic_visualizer'/'favorite_lyrics_sites.json'
        self.legacy=Path(legacy) if legacy is not None else Path.home()/'.karaoke_maker_lite'/'favorite_lyrics_sites.json'
    def load(self):
        source=self.path if self.path.exists() else self.legacy
        if not source.exists():return [dict(item) for item in DEFAULT_SITES]
        data=json.loads(source.read_text(encoding='utf-8'))
        if not isinstance(data,list):raise ValueError('Favorite lyrics sites must be a list.')
        result=[]
        for item in data[:200]:
            if not isinstance(item,dict):continue
            try:result.append(checked_site(item.get('name',''),item.get('url','')))
            except ValueError:continue
        return result
    def save(self,sites):
        if len(sites)>200:raise ValueError('You can save up to 200 favorite sites.')
        sites=[checked_site(item['name'],item['url']) for item in sites]
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temporary=self.path.with_suffix('.tmp')
        try:
            temporary.write_text(json.dumps(sites,ensure_ascii=False,indent=2),encoding='utf-8')
            os.replace(temporary,self.path)
        finally:
            if temporary.exists():temporary.unlink()

def site_search_url(site,artist_song):
    """Only AZLyrics has a configured direct search, matching Maker Lite."""
    host=urlsplit(site['url']).hostname.lower()
    if host in ('azlyrics.com','www.azlyrics.com','search.azlyrics.com'):
        return 'https://search.azlyrics.com/search.php?'+urlencode({'q':artist_song,'w':'lyrics'}),True
    return site['url'],False
