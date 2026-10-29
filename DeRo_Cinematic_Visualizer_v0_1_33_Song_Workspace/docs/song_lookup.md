# Artist and song lookup

In Audio, choose a music file. Edit Song title
and Artist name directly, or click **Find artist and song**. Text appearance remains
in the Text tab. Audio has no panel-reset button or extra reset controls beside
the names; the existing global reset continues preserving the names and media.

## Lookup order

1. Read title and artist tags locally through FFprobe.
2. Clean obvious promotional suffixes and a duplicated artist prefix. Use the
   filename only to fill gaps or provide a fallback suggestion.
3. Search MusicBrainz's public recording database using the cleaned artist/title.
   If no suitable result is found, try one additional filename/title query.
4. Show matching online names first, followed by distinct local suggestions.
   Select a match, edit the two names if necessary, then click Apply names.

Only artist/title search text is sent to MusicBrainz over verified HTTPS. No audio,
file path, artwork, project document, or credential is sent. There is no audio
fingerprinting, speech recognition, or API key requirement. Search confidence
scores are used as a filter, not treated as proof of recording identity. Covers,
remixes, and unrelated recordings can have the same title, so user review remains
necessary. The app never applies search results automatically.

Source labels and notices stay in the review window. Only the song title and
artist name are written to the existing project variables. The music file and
its tags are never modified. Project saving and export filenames use the same
variables as before. Name corrections update preview text through the existing
layout controls.

## Name cleanup

Promotional markers such as `(Official HD Video)`, `(Official Audio)`, `- YouTube`,
and common bracketed download IDs are removed when identifiable. An artist prefix
is removed from a song title only when it matches the known artist. Punctuation,
apostrophes, ampersands, diacritics, deliberate capitalization, and meaningful
Live/Remix/Remaster qualifiers are preserved. Numeric artists such as 311 are not
mistaken for a track number when no separate artist/title pair follows.

Published names are used as returned by the database. The app does not invent
English translations, strip all symbols, or blindly title-case names such as
AC/DC, P!nk, or will.i.am. Local filename guesses remain explicitly unverified.

## Availability and limits

Online lookup needs access to `https://musicbrainz.org`. Requests use an identifying
User-Agent, verified TLS, at least 1.1 seconds between request starts, a ten-second
timeout, bounded responses, and at most two recording searches per click. Lookup
runs off the UI thread. Changing music or projects invalidates old results and
cancels the metadata subprocess. An in-flight HTTP request can take up to its
timeout to finish, after which its result is discarded.

If the service is offline, blocked, busy, or returns an unreadable response, the
review window states that condition and keeps local suggestions available. Missing
artist names must be entered before applying; they are not fabricated. If no
reliable match is found, edit the names manually in Audio.

Tests cover canonical names in representative MusicBrainz responses, metadata-first
queries, punctuation/credit joins, promotional cleanup, local fallback, and offline
handling. The cloud network policy denies MusicBrainz access (proxy CONNECT 403),
so live service results could not be validated here. GUI behavior is checked with
representative service responses. Verify live lookup on the Windows machine with
internet access. MusicBrainz is a third-party community database, so matches may be
incomplete or incorrect.
