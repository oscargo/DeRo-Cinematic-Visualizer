import json,tempfile,unittest
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
from lyric_sites import FavoriteSites,checked_site,site_search_url

class LyricSitesTests(unittest.TestCase):
    def test_maker_favorites_migrate_without_modifying_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);legacy=root/'maker.json';own=root/'visualizer.json'
            saved=[{'name':'My site','url':'https://genius.com'}];legacy.write_text(json.dumps(saved))
            store=FavoriteSites(own,legacy);self.assertEqual(store.load(),saved)
            changed=[checked_site('AZLyrics','https://www.azlyrics.com'),*saved];store.save(changed)
            self.assertEqual(store.load(),changed);self.assertEqual(json.loads(legacy.read_text()),saved)
            store.save([]);self.assertEqual(store.load(),[])
    def test_search_encodes_proper_artist_and_song_and_other_sites_stay_manual(self):
        text='Earth, Wind & Fire September'
        url,direct=site_search_url(checked_site('AZLyrics','https://www.azlyrics.com'),text)
        self.assertTrue(direct);self.assertEqual(parse_qs(urlsplit(url).query)['q'],[text])
        url,direct=site_search_url(checked_site('Genius','https://genius.com'),text)
        self.assertFalse(direct);self.assertEqual(url,'https://genius.com')
    def test_invalid_sites_and_bad_documents_are_rejected(self):
        for url in ('javascript:alert(1)','file:///tmp/private','https://','https://user:password@example.com'):
            with self.assertRaises(ValueError):checked_site('Site',url)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'sites.json';path.write_text('{}')
            with self.assertRaises(ValueError):FavoriteSites(path,path).load()
