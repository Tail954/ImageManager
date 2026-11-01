# QA baseline — Phase 0

## Starting point

- Source baseline: `ab9459046cb3c31416517653eb8c73f22d551f23` (`2026-10-31`).
- Python: 3.10.6; pytest 9.0.2; PyQt6 6.8.0; Pillow 11.1.0; Send2Trash 1.8.3; pytest-mock 3.15.1.
- The project `app_settings.json` SHA256 was recorded by the parent before testing as `BEBEDA97A844EF2E93C7D8783885F94140C1AFA2ABF8E5C50B4E46ED9F6CFD36`.

## Isolation and collection fixes

`tests/conftest.py` keeps one `QApplication` alive for the session, sets the Qt offscreen platform, switches each test to its own `tmp_path`, redirects MainWindow and SettingsDialog settings paths into that directory, and stubs `send2trash`. Tests that create image or operation files use temporary directories. Existing image fixtures are read-only inputs.

The initial `--collect-only` run failed on `PREVIEW_MODE_ORIGINAL_ZOOM` imported from `src.full_image_dialog`; the constant is defined in `src.constants`. The import was corrected. `TestApp` was being mistaken for a pytest test class and is now marked `__test__ = False`.

The first full run paused at the empty-folder confirmation path because the success `QMessageBox.information` call was not mocked. The behavior test now mocks that message as well as the confirmation and trash API; the isolated test passes.

## Full baseline run

To keep this run independent of the active refactor, HEAD source was extracted to `C:\Users\koyam\.codex\visualizations\2026\10\31\01a191c7-f9ed-7c01-9e09-b910d96cec9d\ImageManager-qa-baseline-ab94590`; the isolated tests were overlaid there. The source tree in `G:\ImageManager` was not restored or changed for this run.

```powershell
$env:QT_QPA_PLATFORM='offscreen'
& 'G:\ImageManager\venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider -o faulthandler_timeout=20 --tb=short
```

Result against HEAD source: **172 passed, 12 skipped, 2 xfailed, 1 failed** in 7.14 seconds. The remaining failure is `TestSelectionToggle.test_full_image_dialog_integration`: a selected-state callback is supplied to `FullImageDialog`, but the initial `ImagePreviewWidget.update_image` call omits that state, leaving the selection button unchecked. This is an existing behavior defect, not a collection or environment failure. The 12 skips require image fixtures absent from `tests/test_data/images/`.

## Changes made to tests before the baseline run

- Corrected the preview constant import and SettingsDialog constructor expectations for the existing double-click setting.
- Updated stale preview button text and `None` image title assertions to match the current widget behavior.
- Updated the moved-file status assertion to match the existing success message.
- Changed tests that wrote under the repository or used a fixed working-directory folder to use `tmp_path` / `TemporaryDirectory`.
- Kept the selection integration assertion intact because it exposes the behavior defect above.

No test was deleted or skipped to obtain this result. No application source file was modified by this QA task.
