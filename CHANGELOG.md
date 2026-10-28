# Changelog

## v0.1.16 — Slim Window Resize

- Removed the oversized panel divider and square grip.
- Use a slim 5-pixel draggable panel edge with a horizontal resize cursor.
- Preserve native outer-window resizing and all existing settings.

## v0.1.15 — Sound, Peaks & Alerts

- Removed the hard spectrum ceiling that flattened strong peaks.
- Added independent Spectrum sensitivity with Lower/Normal/Higher buttons.
- Added top-area export completion notification and an independently switchable pleasant tone.
- Added stereo preview playback with a Sound on toggle beside the timeline.
- Synchronize preview visuals to the audio playback clock.
- Support seeking, selection loops, pause, and muting without stopping playback.
- Save the preview sound toggle with the project; exported audio is unaffected.
- Update the Windows launcher to install sounddevice for preview playback.

## v0.1.14 — Particle Motion

- Added a 0.1–5× particle speed control, live preview updates, and project persistence.
- Preserved the 1× default and non-recycling outward motion.
- Added descriptive version folders at the repository root for v0.1.6 through v0.1.14.
- Added a matching named ZIP under releases/ for the current version.
- Audio behavior unchanged pending clarification of the reported clipping.

## v0.1.13 — Export Access

- Moved Open export folder beside Export MP4 in the export range panel.
- Removed the old sidebar button; preserved remembered folder behavior.

## v0.1.12 — Project Identity

- Display the current project name below the app name in the upper-left header.
- Update the name on project actions and unsaved song/artist edits.
- Wrap long project names without widening the header.

## v0.1.11 — Preview Workspace

- Moved export progress and status to the header.
- Moved Export MP4 alongside the selected range.
- Removed the separate bottom export panel to enlarge the responsive preview.
- Preserved project settings and rendering behavior.

## v0.1.10 — Song & Artist

- Added separate song-name and artist-name rows with independent formatting and position.
- Auto-fill title and artist metadata when choosing music; retain manual edits in projects.
- Suggest Artist - Song filenames for project saves, Save As, MP4, and PNG exports.
- Preserve older project values and add a blank artist row for compatibility.
- Added real tagged-audio, naming, artist-rendering, and project round-trip tests.

## v0.1.9 — Studio Workflow

- Highlighted Choose music and Choose background with distinct accent colors.
- Added top-right New, Open, Save, and Save As buttons.
- Added a resizable sidebar divider and explicit window resize support.
- Widened the sidebar scrollbar with a brighter thumb and grip.
- Timeline clicks and drags seek directly and start visual playback.
- Added timeline navigation tests and updated release descriptions.

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
