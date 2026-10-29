import unittest
from unittest.mock import patch
from song_identity import clean_title,filename_names,suggest_names


class SongIdentityTests(unittest.TestCase):
    def test_screenshot_case_removes_artist_prefix_and_video_suffix(self):
        tags={'title':'Earth, Wind & Fire - September (Official HD Video)','artist':'Earth Wind & Fire'}
        with patch('song_identity.read_metadata',return_value=tags):
            suggestions=suggest_names('Earth, Wind & Fire - September (Official HD Video).mp3')
        self.assertEqual(suggestions[0].title,'September')
        self.assertEqual(suggestions[0].artist,'Earth Wind & Fire')
        self.assertEqual(suggestions[0].source,'File tags')

    def test_names_and_meaningful_versions_keep_original_spelling(self):
        self.assertEqual(clean_title('iPhone Song (Live at Wembley)'), 'iPhone Song (Live at Wembley)')
        self.assertEqual(clean_title('Song (2024 Remaster)'), 'Song (2024 Remaster)')
        self.assertEqual(clean_title('Song (Official Audio) [dQw4w9WgXcQ]'),'Song')
        self.assertEqual(filename_names(r'C:\Music\01 - AC_DC - Song (Live).mp3'),('AC_DC','Song (Live)'))

    def test_filename_is_marked_unverified_and_missing_artist_is_not_invented(self):
        with patch('song_identity.read_metadata',return_value={'title':'','artist':''}):
            one=suggest_names('Artist - Song [Official Video].mp3')[0]
            two=suggest_names('Song.mp3')[0]
        self.assertEqual((one.artist,one.title),('Artist','Song'))
        self.assertIn('unverified',one.source)
        self.assertEqual(two.artist,'')

    def test_valid_tags_take_priority_over_unrelated_filename(self):
        with patch('song_identity.read_metadata',return_value={'title':'Actual Song','artist':'will.i.am'}):
            suggestions=suggest_names('Wrong - Filename.mp3')
        self.assertEqual((suggestions[0].title,suggestions[0].artist),('Actual Song','will.i.am'))
        self.assertEqual(suggestions[1].source,'Filename (unverified)')

    def test_artist_topic_suffix_and_incomplete_tags(self):
        with patch('song_identity.read_metadata',return_value={'title':'Song (Official Audio)','artist':'Artist - Topic'}):
            self.assertEqual(suggest_names('Artist - Song.mp3')[0].artist,'Artist')
        with patch('song_identity.read_metadata',return_value={'title':'','artist':'Artist'}):
            self.assertEqual(suggest_names('Artist - Song.mp3')[0].title,'Song')

    def test_online_canonical_names_preserve_punctuation_and_exclude_extra_fields(self):
        import json
        from song_identity import search_musicbrainz
        from unittest.mock import Mock
        response={'recordings':[
            {'title':'September','score':100,'artist-credit':[{'name':'Earth Wind and Fire',
             'artist':{'name':'Earth, Wind & Fire','id':'not-for-fields'}}],'id':'recording-id','disambiguation':'not-for-fields'},
            {'title':'September','score':99,'artist-credit':[{'artist':{'name':'Earth, Wind & Fire'}}]},
            {'title':'Wrong','score':20,'artist-credit':[{'artist':{'name':'Other'}}]}]}
        stream=Mock();stream.__enter__=Mock(return_value=stream);stream.__exit__=Mock(return_value=False)
        stream.read.return_value=json.dumps(response).encode()
        with patch('song_identity._wait_for_musicbrainz'),patch('song_identity.urlopen',return_value=stream) as request:
            result=search_musicbrainz('Earth Wind & Fire','September')
        self.assertEqual(len(result),1)
        self.assertEqual((result[0].artist,result[0].title),('Earth, Wind & Fire','September'))
        self.assertNotIn('not-for-fields',result[0].artist+result[0].title)
        self.assertEqual(request.call_args.kwargs['timeout'],10)
        self.assertIn('https://musicbrainz.org/ws/2/recording/',request.call_args.args[0].full_url)

    def test_metadata_precedes_online_and_online_names_take_priority(self):
        from song_identity import find_names,SongSuggestion
        canonical=SongSuggestion('September','Earth, Wind & Fire','MusicBrainz')
        with patch('song_identity.read_metadata',return_value={'title':'Earth, Wind & Fire - September (Official HD Video)','artist':'Earth Wind & Fire'}),patch('song_identity.search_musicbrainz',return_value=[canonical]) as search:
            result,notice=find_names('Earth, Wind & Fire - September.mp3')
        self.assertEqual(search.call_args.args,('Earth Wind & Fire','September'))
        self.assertEqual(result[0],canonical)
        self.assertIn('Online matches found',notice)

    def test_offline_keeps_local_suggestions_and_reports_failure(self):
        from urllib.error import URLError
        from song_identity import find_names
        with patch('song_identity.read_metadata',return_value={'title':'Song','artist':'Artist'}),patch('song_identity.search_musicbrainz',side_effect=URLError('offline')):
            result,notice=find_names('Artist - Song.mp3')
        self.assertEqual((result[0].artist,result[0].title),('Artist','Song'))
        self.assertIn('unavailable',notice)

    def test_online_artist_credit_joinphrase_preserved(self):
        import json
        from song_identity import search_musicbrainz
        from unittest.mock import Mock
        response={'recordings':[{'title':'Don’t Stop','score':100,'artist-credit':[
            {'artist':{'name':'AC/DC'},'joinphrase':' & '},{'artist':{'name':'P!nk'}}]}]}
        stream=Mock();stream.__enter__=Mock(return_value=stream);stream.__exit__=Mock(return_value=False)
        stream.read.return_value=json.dumps(response).encode()
        with patch('song_identity._wait_for_musicbrainz'),patch('song_identity.urlopen',return_value=stream):
            result=search_musicbrainz('AC/DC','Don’t Stop')
        self.assertEqual(result[0].artist,'AC/DC & P!nk')
        self.assertEqual(result[0].title,'Don’t Stop')

    def test_cleanup_does_not_damage_legitimate_names_or_numeric_artists(self):
        self.assertEqual(filename_names('311 - Love Song.mp3'),('311','Love Song'))
        self.assertEqual(clean_title('Song [LiveVersion]'),'Song [LiveVersion]')
        self.assertEqual(clean_title('Song (Music)'),'Song (Music)')
        self.assertEqual(clean_title('Song - Official Video - YouTube'),'Song')
        self.assertEqual(clean_title('Rock &amp; Roll (Official Audio)'),'Rock & Roll')

    def test_stale_lookup_results_do_not_open_or_apply_a_dialog(self):
        import queue
        from unittest.mock import Mock
        from visualizer_app import Application
        app=Application.__new__(Application)
        app.root=Mock();app.q=queue.Queue();app.song_lookup_generation=2
        app.song_lookup_control=Mock();original=app.song_lookup_control
        app.find_song_button=Mock();app.audio=Mock();app.audio.get.return_value='new.mp3'
        app.review_song_suggestions=Mock()
        app.q.put(('song_lookup',(1,'old.mp3',[],'',None)))
        app.poll()
        self.assertIs(app.song_lookup_control,original)
        app.review_song_suggestions.assert_not_called()
        app.q.put(('song_lookup',(2,'old.mp3',[],'',None)))
        app.poll()
        app.review_song_suggestions.assert_not_called()
        self.assertIsNone(app.song_lookup_control)

    def test_bad_artist_tag_can_fall_back_to_title_only_search(self):
        from song_identity import find_names,SongSuggestion
        correct=SongSuggestion('September','Earth, Wind & Fire','MusicBrainz')
        with patch('song_identity.read_metadata',return_value={'title':'September','artist':'Wrong uploader'}),patch('song_identity.search_musicbrainz',side_effect=[[],[correct]]) as search:
            result,notice=find_names('unrelated filename.mp3')
        self.assertEqual(search.call_args_list[0].args,('Wrong uploader','September'))
        self.assertEqual(search.call_args_list[1].args,('','September'))
        self.assertEqual(result[0],correct)
