# Monomoon Translator 1.0.0 validation

Built on 2026-11-18.

- 22 source regression tests passed with Python 3.12, NumPy 1.26.4, OpenCV 4.11.0.86, PySide6 Essentials / Shiboken 6.8.3.
- The simplified interface starts with Advanced hidden. Buttons and image controls have hover hints. Read is disabled until an image is loaded.
- Source tests cover image clipboard data and text paste, transparency, profile round trips and Windows-safe names, resource paths independent of working directory, matching ambiguity, touching glyphs, text-block detection, and the real screenshots.
- Windows x64 uses the official CPython 3.12.10 embedded runtime plus pinned Windows wheels. It includes the trained alphabet, assets, sources, and dependency licenses.
- The native PE32+ Windows GUI launcher was tested under Wine 9 using its embedded pythonw.exe, not a Linux or system Python. GUI creation, Advanced toggle, clipboard image paste, Unicode profile saving/loading, and three real OCR cases passed.
- The Windows bundle was exercised in a folder containing spaces and accented characters. The published ZIP subsequently passed on a native Windows Server 2025 GitHub runner: its downloaded checksum, native launcher, bundled runtime, GUI, Advanced toggle, clipboard image paste, Unicode profile round trip, and three real OCR examples all passed. The check ran outside the application's working directory. Report: `verification/Windows-Native.json`.
- All 22 source regression tests also passed on the native Windows and Ubuntu 24.04 GitHub runners. [Cross-platform source checks](https://github.com/evanjrizzo/monomoon-translator/actions/runs/44247877996) and [published Windows ZIP check](https://github.com/evanjrizzo/monomoon-translator/actions/runs/44248062629).
- The frozen Linux x64 bundle passed equivalent checks under the offscreen and real XCB platforms after moving into a different path containing spaces and accented characters.
- Linux targets Ubuntu/Pop!_OS 24.04 and compatible systems with glibc 2.39 or newer. The missing XCB cursor dependency was bundled with its notice.
- Portable data is stored beside the app. Image and profile paths explicitly chosen by the user can still point outside the app folder.
- OCR remains heuristic. In the moon-board photo, CRIMS?? retains two unresolved letters; other small diagram markings remain unverified.

The Windows hosted check used Windows Server 2025; a physical Windows 10/11 consumer desktop was not available. The portable package includes a runtime-check command for the recipient's first-run verification.
