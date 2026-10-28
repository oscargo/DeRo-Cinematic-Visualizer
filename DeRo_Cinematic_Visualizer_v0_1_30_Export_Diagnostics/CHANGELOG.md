# Changelog

## v0.1.30 — Export Diagnostics

- Add View/Copy/Save local performance reports for successful, failed, and canceled exports.
- Measure decoding, analysis, renderer setup, GPU probing, frame rendering, FFmpeg frame-feed blocking, and final wait separately.
- Record cache-miss reasons, encoder attempts/fallback categories, frame timings, effective export FPS, sampled RAM, and software/available NVIDIA device versions.
- Exclude media contents, titles, filenames, full paths, raw subprocess logs, and credentials from report data.
- Add recent-throughput remaining-time estimates, with explicit estimation/finalization states and retry resets.
- Add safe cancellation during decoding, analysis, particle setup, encoder probing, pipe writes, and finalization; preserve existing output files.
- Wait for cancellation cleanup before closing the application during an export.
- Add psutil for sampled RAM measurements; exports still work if monitoring is unavailable.

## v0.1.29 — Export Timing

- Show a live HH:MM:SS elapsed timer in the top export progress area.
- Keep the total duration visible after success or failure, using the worker completion time.
- Include analysis, GPU probing, rendering, encoding, muxing, and any CPU retry in the duration.
- Display the actual GPU/CPU encoder in the same area, marking CPU fallback and CPU visual rendering explicitly.
- Update elapsed time even when no frame-progress event arrives; reset it for each new export.

## v0.1.28 — NVIDIA GPU Encoding

- Add Auto, NVIDIA NVENC, and CPU H.264 encoding choices in Output; save the choice in projects.
- Test NVENC with a real one-frame encode at the selected dimensions/FPS before selecting it.
- Show the actual encoder or fallback reason in Output; keep GPU probing off the UI thread.
- Fall back to CPU if NVENC is unavailable or fails during export, without repeating audio analysis.
- Encode to a temporary MP4 and replace the destination only after success.
- Preserve CPU rendering, deterministic timestamps, cached analysis, and original-audio muxing.
- Validate CPU fallback and simulated GPU failures; physical NVIDIA encoding remains unverified in this cloud environment.

## v0.1.27 — Export Analysis Reuse

- Reuse preview samples and features for export when source metadata and all analysis inputs match.
- Capture a stable snapshot before the export worker starts and recheck source metadata in the worker.
- Fall back to fresh decoding and analysis for missing/stale caches, mismatched settings, or custom FFmpeg commands.
- Keep original audio muxing, selection timing, rendering, and encoding behavior unchanged.
- Verify cached/fresh decoded video and audio equivalence with real FFmpeg exports.

## v0.1.26 — Preview Performance

- Skip disabled particle initialization while preserving live re-enabling.
- Cache fonts and reuse unchanged audio decoding and spectrum analysis.
- Invalidate preview caches when source file identity or analysis settings change.
- Rebuild particle previews on one background worker; cancel queued obsolete edits and discard stale results.
- Preserve deterministic rendering and existing CPU MP4 encoding.

## v0.1.25 — Continuous Particles

- Added continuous particle replenishment for speeds up to 30x.
- Fade new particles in and outgoing particles near frame edges.
- Support Out, Left, Right, Up, and Down without visible wrapping.
- Keep original non-recycling mode available through a saved toggle and Reset.
- Verify two-minute high-speed population, hidden births, and deterministic seeking.

## v0.1.24 — Peak Shape Options

- Added Stepped (previous), Smooth (current), and Balanced peak shapes.
- Apply the selected shape in frequency analysis and visible-bar mapping.
- Reanalyze automatically and save the choice with each project.
- Include an individual Reset button and retain Smooth as the default.

## v0.1.23 — Resets & Export Alerts

- Added individual setting resets, panel resets, and confirmed all-settings reset.
- Preserve selected files, song names, project path, and range during broad resets.
- Restore original loaded song/artist names with individual text resets.
- Added a generated three-note chime, test button, and visible sound-failure reporting.
- Make successful export notification a prominent green top banner.
- Added optional auto-open with a two-second delay to allow the alert to be seen/heard.

## v0.1.22 — Smooth Spectrum Mapping

- Replace integer FFT-bin rounding with fractional frequency-band power integration.
- Replace nearest-value repetition with interpolation when mapping visible bars.
- Remove artificial stepped plateaus without random variation or added audio detail.
- Add bass-bin and high-density regression tests and a same-signal comparison image.

## v0.1.21 — Spectrum Styles

- Added Classic, Gradient, Glow, Reflected, and Filled spectrum styles and mirroring toggle.
- Added 16–2048 analysis bands, independent density/thickness, and a live visible-bar count.
- Added configurable 20–20,000 Hz ranges, spacing, and automatic frequency reanalysis.
- Added Whole spectrum, Bass, Vocals/Midrange, Treble, and Original presets.
- Added selectable particle beat sources; presets align particles with the displayed range.
- Preserve original defaults, project compatibility, and unfiltered playback/export audio.

## v0.1.20 — Particle Speed 30x

- Increased the particle speed limit to 30x in the UI and project validation.
- Added explanations for particle controls in the Elements panel.
- Verified 30x motion and saved-project compatibility; retain the 1x default.

## v0.1.19 — Project Folder Memory

- Remember the project folder across restarts for Open, Save, and Save As.
- Preserve separate music/background/export folder preferences and cancellation behavior.
- Correctly document the standard 50–10,584 Hz spectrum range and mirrored bar count.
- Add folder persistence, reopen, save-as, cancellation, and missing-folder tests.

## v0.1.18 — Elements Studio

- Organized settings into Audio, Backdrop, Text, Visualizer, Elements, and Output panels.
- Added highlighted navigation and graphical on/off switches.
- Added live particle direction, visibility, beat-reaction, and color controls.
- Added spectrum color and a default-backdrop action.
- Added an image/logo layer with circular crop, opacity, size, position, and visibility.
- Save new element settings and image references with backward-compatible projects.

## v0.1.17 — Fullscreen Preview

- Added a Fullscreen preview button and F11 shortcut.
- Scale preview frames to fill the screen while preserving aspect ratio.
- Exit with Escape, F11, or the onscreen button; Space toggles playback.
- Preserve normal workspace layout and ongoing preview sound/playback.

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
