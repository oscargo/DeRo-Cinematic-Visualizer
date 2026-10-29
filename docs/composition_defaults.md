# Approved composition defaults

The application's initial state, New project, a confirmed new-song import, and
Reset controls now use the non-identifying settings from the supplied project.
The renderer's normalized defaults use the same profile.

| Setting | Default |
| --- | --- |
| Frequency spacing | Linear |
| Peak shape | Stepped |
| Frequency range | 50–10,584 Hz |
| Spectrum | Classic bars, mirrored, 384 analysis bands |
| Reactive particles | 24% |
| Particle response | 3.0 |
| Particle speed | 20x |
| Particle count | 130 |
| Song size / position | 12% height; X 50%, Y 42% |
| Artist size / position | 8% height; X 50%, Y 58.5% |
| Spectrum width / position / height | 80%; X 50%, Y 90%; height 19.8% |
| Spectrum gain | 1.5 |
| Output | 1920×1080, 60 FPS, Auto GPU encoder |

All other non-media settings in that saved project already matched the existing
defaults and are retained. Continuous particles, the saved colors, fonts, mirroring,
preview sound, completion tone and automatic opening after export remain enabled
as saved. The image-overlay enable state remains off.

The saved song/artist names, input/background paths, and song-length selection are
not application defaults. An actual background image was not included with the
project upload, so a private/dangling image path is not embedded in the app. The
normal built-in background remains the fallback until an image is selected.

Opening a project that explicitly contains other settings still respects that
project. Changing defaults does not rewrite existing .dero files. The selected
Song language and stem references remain per-project metadata.
