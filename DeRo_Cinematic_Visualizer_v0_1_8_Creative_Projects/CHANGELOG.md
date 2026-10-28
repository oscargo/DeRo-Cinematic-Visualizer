# Changelog

## v0.1.8 — Creative Projects

- Added New, Open, Save, and Save As project commands with keyboard shortcuts.
- Added versioned .dero files for composition, media references, and export selection.
- New restores all defaults; unsaved changes can be saved before replacing or closing a project.
- Added title font family, bold/italic, capitalization, size, color, and independent position.
- Added title and spectrum position arrows with live preview updates.
- Widened the default spectrum to 82%, with adjustable width, height, and position.
- Added layout reset and spectrum width buttons.

## v0.1.7 — Midnight Studio

- Redesigned the interface with a dark navy theme and blue accents.
- Organized sources, atmosphere, and output settings in a scrollable sidebar.
- Added a responsive preview that preserves the frame aspect ratio.
- Refined range controls, playback layout, export progress, and primary export action.
- Added a one-click 480p / 30 FPS test-export preset.
- Preserved selection export, folder memory, and renderer behavior.

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
