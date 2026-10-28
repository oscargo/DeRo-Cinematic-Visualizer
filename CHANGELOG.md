# Changelog

## v0.1.6 — Quick Export Selection
- Added draggable start/end range handles and editable times in seconds.
- Added Full Song, playhead boundary shortcuts, selection playback, pause, loop, and play from start.
- MP4 export trims video and audio to the selection while retaining original visual timestamps.
- Added automated range validation and real FFmpeg export tests.

## v0.1.5 — Export folder memory

- Export MP4 save dialog starts in the most recently selected export directory.
- Last export directory saved separately from music and background in Windows AppData.
- Open Export Folder can open the remembered directory after restarting, even before a new export.
- Preserves automatic MP4 opening after successful export.
- No change to renderer or visual effects.

