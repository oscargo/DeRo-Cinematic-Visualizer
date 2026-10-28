# Preview optimization measurements

Measured in the onboarding Linux cloud environment with Python 3.12.14,
NumPy 2.3.5 and Pillow 12.3.0. These single-run wall-clock observations are
illustrative, not performance thresholds or predictions for another machine.

Renderer construction used 14,400 zero-feature frames, 32 bands, 800 particles,
and a 320×180 output. Particle arrays are float32 positions and fades.

| Check | Before | After |
| --- | ---: | ---: |
| Particles disabled, construction | 2.125 s | 0.008 s |
| Particles disabled, trajectory arrays | 138,240,000 bytes | 0 bytes |
| Particles enabled, construction | 2.269 s | 1.754 s |
| Particles enabled, trajectory arrays | 138,240,000 bytes | 138,240,000 bytes |
| 120 frames with title/artist, particles off | 0.388 s | 0.145 s |

The enabled-construction variation is not evidence of a simulation improvement;
the enabled algorithm is unchanged. Array sizes exclude process RSS, feature data,
backgrounds and temporary allocations. Background rebuilding improves interaction,
not total computation; old and new renderers can coexist during a build.

The frame comparison used 24 particles, 120 zero-feature frames, 32 bands,
320×180 output, and timestamps 0, 1.5, 0.3, 1.5 seconds. Every compared RGB byte
matched the original renderer. Regression tests cover disabled/live-enabled
particles, font cache changes, source replacement at the same path and size,
analysis-key changes, and queued rebuild cancellation. Existing export tests
exercise real FFmpeg output and trimmed-audio alignment.
