# Refactor QA report

Date: 2026-11-01 (JST)  
Tested source base: `ab9459046cb3c31416517653eb8c73f22d551f23` plus the current Sol/Terra worktree changes.  
QA owner: Luna.

## Test result

Full suite command:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$env:PYTHONDONTWRITEBYTECODE='1'
& '.\venv\Scripts\python.exe' -m pytest -q -p no:cacheprovider `
  --basetemp='G:\ImageManager\.qa_final_verification' `
  -o faulthandler_timeout=20 --tb=short
```

Final result after the decoder conversion-order fix: **168 passed, 2 xfailed, 0 skipped** in 4.58 seconds, independently rerun by the parent with workspace basetemp `.qa_final_verification`. Luna's immediately preceding run also passed 168 tests and 2 xfails. The two expected failures remain the existing JPEG UserComment and PNG eXIf metadata cases in `tests/test_metadata_utils.py`. `git -c core.whitespace=cr-at-eol diff --check` reports no whitespace errors.

The Phase 0 baseline against the original source was **172 passed, 12 skipped, 2 xfailed, 1 failed**. Its failure was the FullImageDialog initial selection state. The test suite now exercises the formerly skipped image-dialog cases using small PNGs generated under each test's `tmp_path`; it does not write into `tests/test_data/images`. The current raw test count is smaller because the old MainWindow suite repeated inherited test methods across many subclasses and asserted moved private implementation details. The scenario mapping below records where those behaviors now live.

## Safety and fixture isolation

- `tests/conftest.py` uses a single session `QApplication`, offscreen Qt, a per-test CWD, a `tmp_path` SettingsStore for every MainWindow, and a no-op trash adapter. Test images and file-operation inputs are generated in isolated test directories.
- Tests were run with a workspace basetemp because Windows `os.replace` denied writes from the default AppData temp area. The `app_settings.json` SHA256 was `9FFF01C5A05824A64180AEDF42249C450994AC38C21F3E5986AD41E6671D17E7` at the start and end of Luna's run; its timestamp remained `2026-10-31 21:10:31`. It already differed from the earlier Phase 0 hash (`BEBEDA97A844EF2E93C7D8783885F94140C1AFA2ABF8E5C50B4E46ED9F6CFD36`) before this resumed QA work, and it was not restored or edited here.
- The 23 user-provided image files now present under `tests/test_data/` were not modified or removed. Parent's hash-protected image smoke copied them into an isolated temp area and decoded two previews per image (**46/46 preview decodes succeeded**); extracted metadata hashes match the original implementation and source image hashes remained unchanged. The smoke identified and Sol corrected a memory regression by shrinking images before RGBA conversion, matching the old decode order. The parent repeated the full suite after that fix with the final result above.
- Cleanup note: one workspace test directory remains locked at `.qa_pytest_tmp_luna\test_partial_cancelled_move_re0`. Luna had no live pytest `exec` session handle to interrupt; the read-only process list showed no Python/pytest process, and the remaining lock owner could not be identified. No process was terminated. Other test temp directories were cleaned by the parent.

## Old behavior to new-contract test mapping

| Previous test focus | Current coverage |
| --- | --- |
| `TestMainWindowBase.test_apply_filters_*`, `TestUIManager.test_apply_filters_preserving_selection_*` | UIManager delegation in `tests/test_ui_manager.py`; path-based preservation, hidden selections, AND/OR, sort, select-all, clear and copy order in `tests/test_selection_controller.py` |
| `TestMainWindowSelection.test_thumbnail_selection_changed_*`, `test_select_all_deselect_all_thumbnails` | `tests/test_selection_controller.py`: user copy order, numbering, filter pruning, select-all, removal and clear |
| `TestMainWindowFolderSelectionAndLoading.test_select_folder_*`, `test_load_thumbnails_from_folder_*` | `tests/test_main_window.py`: common dialog route, generated-image navigation, source-specific sorting, recursion, same-folder and inaccessible-folder behavior |
| `TestMainWindowThumbnailUpdatesAndFilters.test_update_thumbnail_item`, `test_on_thumbnail_loading_finished` and old loader item mocks | Worker value contract in `tests/test_thumbnail_loader.py`; latest-generation, stale result, empty-folder, removal and shutdown behavior in `tests/test_thumbnail_controller.py` |
| `TestMainWindowSortFunctionality`, load-order setting tests and thumbnail-size tests | Sorting/filter restoration in `tests/test_selection_controller.py`; dialog/favorite source policy and size refresh/rollback in `tests/test_main_window.py`; rejected size persistence in `tests/test_dialog_manager.py` |
| `TestMainWindowFileOperations.test_handle_*`, completion tests and old worker mocks | Immutable request, copy numbering, move collision, failures, cancellation and real service result/idle in `tests/test_file_operations.py`; partial-success/deduplication and navigation lock in `tests/test_file_operation_manager.py` |
| `TestMainWindowEmptyFolderFunctions.*` | Read-only discovery, recursive scope, Yes/No confirmation and trash failure in `tests/test_folder_cleanup.py`; dialog-only cleanup routing in `tests/test_main_window.py` |
| Old favorite model/panel expectations | Windows path normalization, duplicate naming, tooltip, add/remove/reorder persistence failure and internal/external drop dispatch in `tests/test_favorites_integration.py`; MainWindow removal, tab, navigation and Explorer failure in `tests/test_main_window.py` |
| Full image tests skipped because fixtures were absent | Generated valid/invalid images in `tests/test_full_image_dialog.py`; initial selected state is also checked in `tests/test_selection_toggle.py` |
| DialogManager metadata/settings tests using MainWindow internals | Explicit SettingsStore, ThumbnailController and SelectionController test doubles in `tests/test_dialog_manager.py`; other-setting retention is checked with partial Store saves |

The internal D&D test runs `_FavoriteList.dropEvent` with an internal source and simulates Qt's accepted item move at the base list-widget drop boundary. It verifies one reorder signal, no activation, and rejects an external source. It does not claim native OS drag gesture coverage.

## Contract coverage

- SettingsStore validation, defaults, unknown-key retention, favorites partial save, atomic replacement failure, and failed-write state retention.
- Favorite path normalization (drive/UNC/extended/root/device/relative), case-insensitive deduplication, duplicate-name labels, tooltip paths, persisted order, failed reorder rollback, tabs without navigation, missing paths and add/remove behavior without filesystem deletion.
- MainWindow common navigation, one load for a new folder, same-folder no-op, current-path permission error, unavailable folder state retention, selected/copy order retention, recursive enumeration, and dialog/favorite/tree source differences.
- Thumbnail worker path snapshots, generated image decoding, broken-image errors, stop and bounded submission count; controller generation replacement A→B→C, stale results/progress rejection, one asynchronous empty completion, idempotent removal, and shutdown wait.
- File-operation snapshots, copy source order and numbering, move collision suffix, individual failure continuation, cancelled partial success, one result, busy-until-real-idle, duplicate-result protection, and successful-path-only model/selection updates.
- Dialog settings save through Store, favorite/other-key retention through partial saves, and not persisting a size that was rejected.

## Manual checks and limits

Parent completed an offscreen 1200×800 visual review; the B tabs do not overlap. The reference is [refactor-ui.png](refactor-ui.png). Final post-fix reference measurements for both generated and user-provided images are recorded in [REFACTOR_MEASUREMENT.md](REFACTOR_MEASUREMENT.md). The generated set measured 0.2014 s load / 0.636 ms filter / 67.32 MiB peak memory; the 23 provided images measured 0.3403 s / 0.749 ms / 113.31 MiB. These are single-run smoke measurements, and no general performance improvement is claimed.

Native interactive D&D, 350 px/high-DPI visual checks, actual Explorer launch, real ACL/UNC permission behavior, and a full desktop restart smoke were not performed by Luna. Parent ran the separate read-only/hash-protected smoke against the user-supplied images as summarized above. These limitations do not change the automated result above.
