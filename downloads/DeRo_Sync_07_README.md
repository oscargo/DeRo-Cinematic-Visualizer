# DeRo Sync 07 TEST — Windows checker correction

Download DeRo_Sync_07_App_and_Windows_Kit.zip and extract ALL files into a NEW folder.

1. Run Run_Windows_Checks.bat. The Acceptance_Results folder opens at the end.
2. Return Automatic_Results.json and the full regression.log.
3. Manual_Results.json can remain pending until automatic failures are reviewed.

This update fixes explicit UTF-8 reads for the Windows default-codepage test errors, adds discovery of existing FFmpeg/ffprobe beyond PATH, and retains complete regression logs. The app launcher uses process-local media tool discovery too. Nothing installs packages or changes permanent PATH. Do not reinstall Torch/CUDA for these errors.

If ffprobe remains missing, START_HERE.txt explains how to use existing ffmpeg.exe/ffprobe.exe in the app tools/ffmpeg/bin folder, or optionally install a complete FFmpeg distribution yourself.

112 tests pass locally and under simulated cp1252 Path text defaults. Actual Windows rerun and manual acceptance are pending. This is still a TEST candidate.

Uploaded songs, projects, Windows reports and private validation evidence are excluded.

ZIP: 368955 bytes.
SHA-256: 695a86cd3e7c8a6314c6e8ca445f29c3659325252f8f634cc71571b1f1d780e9
