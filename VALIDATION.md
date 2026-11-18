# Monomoon Translator 1.1.0 validation

Built on 2026-11-18 with Python 3.12, NumPy 1.26.4, OpenCV 4.11.0.86, and PySide6 Essentials / Shiboken 6.8.3.

- 32 local source regression tests passed, including all previous screenshot cases.
- Added checks for all selectable character labels, rejecting invalid labels, mixed letters/numbers/punctuation, disconnected standalone punctuation, accepted question-mark confidence and annotation, number-only profiles, legacy profile loading, and version 2 profile round trips.
- GUI checks exercise the Alphabet teaching tab, number/punctuation selection, teaching from a selected crop, saving/loading, invalid input, and sample removal. Advanced remains hidden at startup; buttons retain hover hints.
- Number and punctuation recognition is tested using synthetic glyph samples. The included game key still contains only verified A–Z mappings.
- The portable self-check additionally exercises teaching 7, ?, :, and =, version 2 profile saving/loading, and recognition, alongside GUI, clipboard, Unicode paths, and three real screenshot checks. Its JSON report records the application version and platform.
- Source tests run on Windows and Ubuntu 24.04 in GitHub Actions. The manually dispatched workflow verifies the selected release ZIP checksum and runs its actual Windows launcher and embedded runtime outside the app's working directory, in a path with spaces and an accented character.
- Linux x64 targets Ubuntu/Pop!_OS 24.04 and compatible systems with glibc 2.39 or newer. Normal desktop graphics libraries are required; libxcb-cursor is included in the distributed build.
- No physical Windows 10/11 desktop test is claimed. Windows hosted checks use Windows Server 2025.
- OCR remains heuristic. The shaded moon-board label remains CRIMS??; other small diagram markings are unverified.

The source and portable checks do not guarantee a correct reading for every screenshot. Use the bundled runtime check to inspect the current installation. Historical 1.0.0 reports below refer only to that release; they are not evidence for a later build.

## Historical 1.0.0 validation


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
