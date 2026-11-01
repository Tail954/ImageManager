# 全体リファクタリング：統合API契約 v1

2026-10-31 / Astra。**FAVORITES_API.mdのSettingsStore最小仕様、ThumbnailControllerの寿命だけの責務、MainWindow辞書所有、file operation寿命改善対象外という記述を本書で置換する。** お気に入りのパス・データ・UIシグナル・B採用・切替ルールはそのまま有効。

## 1. SettingsStore（Sol）

唯一の設定辞書所有者。`SettingsStore(path=APP_SETTINGS_FILE)`、`load() -> dict`（検証済snapshotを返す）、`get(key, default=None)`、`snapshot() -> dict`（deepcopy）、`update(changes: Mapping) -> None`（検証して実行中状態だけ変更）、`save(changes: Mapping | None = None) -> bool`（現状態＋変更の候補を検証・原子的保存、成功時だけcommit）。

既存キーのdefault・検証を一箇所にする。現行の有効値・保存場所・UTF-8/indent=4を維持、未知キーも保持。boolとintを混同せずサイズ/列挙値/geometry型/パス型を検証。ディレクトリの存在によるfavorite削除はしない。JSONがdict以外なら不正として既定値＋ログ。ファイル欠損と破損を区別して記録し、自動保存しない。

saveは同一dirの一時ファイルを書き終えて置換。失敗はFalseとログ、原本と候補前のStoreを保持（過去の明示updateは戻さない）。MainWindow.app_settingsの独立辞書を廃止。移行互換が必要ならStoreの同じ実体に委譲し、snapshotを書換えて保存できたつもりにしない。既存 `_write_app_settings_file` / `_save_settings` はStoreへ薄く委譲。新規コードは公開Storeを使用する。

お気に入りpersistは`store.save({FAVORITE_FOLDERS: candidate_paths})`。FavoriteFolders自身も保存成功時だけcommit。タグ・geometry等をこの保存で失わない。DialogManagerは設定適用に成功した値だけupdate/saveする。サイズ変更拒否時に未適用サイズを保存しない。読込後double_click_actionの既定値再代入を除去。

Terra接続：SettingsDialog既存constructor引数を維持し、`current_preview_mode`等の渡された値だけ表示する。独自JSON読込は廃止。必要ならkeyword-only `settings_snapshot=None`を追加するが全呼出し元へ通知。TagPaletteWindowはconstructorへ`settings_store`のkeyword注入を追加し、get/saveを使用。MainWindowのprivate saveや可変辞書へ直接アクセスしない。SolがDialogManager生成時にstoreを渡す。

## 2. ThumbnailController（Sol）とUIManager（Terra）

```python
ThumbnailController(source_model, proxy_model, parent=None)
replace(file_paths: list[str], target_size: int) -> int  # 新世代
item_for_path(path: str) -> QStandardItem | None
paths() -> tuple[str, ...]                             # ソース列挙順
metadata_for(path: str) -> dict | None
cache_metadata(path: str, metadata: dict) -> None       # dialogsの追加解析結果
remove_paths(paths: Iterable[str]) -> None              # 冪等
shutdown() -> None
is_idle() -> bool
```

source_model、path索引、metadata_cache、hidden paths、世代、workerと予約はControllerが所有。UIManagerが既存モデルを生成してconstructorへ注入し、以後は表示用参照としてのみ保持してよい。MainWindowに別モデル/cache/indexを作らない。metadata_cache互換プロパティはcontrollerへ転送。placeholders作成・QPixmap化・アイテム更新・削除はControllerのGUIスレッド処理。モデルclear前の選択解除はMainWindowがSelectionControllerへ指示してからreplaceする。

FAVORITES_API.mdのthumbnailReady/progressChanged/completed/idleと世代契約を維持。Controller内部で最新世代のみモデルへ反映後、必要な公開通知を出す。MainWindowの重複item更新は撤去する。空配列でも同期completedをemitしない。実worker最大1、予約最新1、実finished前に解放しない。ThumbnailLoaderThreadはbounded submission（実行worker数の小さい倍数まで未完了futureを制限）と取消しを実装する。worker結果は値だけ、画像errorはmetadataと別フィールドの小さなDTOまたは補助signalで持ち、既存metadataキーを勝手に変えない。古い世代はすべての表示通知で無視。

UIManagerは`bind_controllers(thumbnails, selection)`を公開しMainWindowがUI構築とcontroller生成後に呼ぶ。既存source_thumbnail_model/filter_proxy_model参照を維持し、業務操作はcontrollerへ。favorite panel公開名と6シグナルはFAVORITES_API.mdどおり。全左overlayではなく対象操作をlock。読込／ファイル操作／終了のロック理由はSol側で集約し、片方の完了で他方のロックを解除しない。

## 3. SelectionControllerとフィルタ（Sol）、GUI委譲（Terra）

```python
SelectionController(thumbnails, proxy_model, view, parent=None)
selected_paths() -> tuple[str, ...]
copy_paths() -> tuple[str, ...]              # ユーザー選択順、長寿命item参照禁止
is_selected(path) -> bool
set_copy_mode(enabled: bool) -> None
sync_from_view() -> None
clear() -> None
select_all() -> None
toggle(path: str) -> None
apply_filters(positive, negative, generation, search_mode,
              preserve_selection=True) -> None
apply_sort(key_type, order) -> None
remove_paths(paths) -> None                 # 選択だけから除去、モデルはThumbnail側
selectionChanged = pyqtSignal()             # UI/件数更新用
```

選択とコピー順の唯一の所有者。モデル/ビュー/表示用SELECTION_ORDER_ROLEを同期。filter/sortの前にパスsnapshotを取り、シグナルを抑止し、一回の変更後に可視項目を復元。finallyで抑止・描画を必ず戻す。コピー順は存続する選択の相対順を維持し連番を振り直す。フィルタで非表示になる項目を復元対象から外す既存仕様をLuna基準で確認し、差異を発見したら勝手に変えず統括へ報告。

`MetadataFilterProxyModel.set_filters(positive, negative, generation, search_mode)`を追加。既存setterの文字列正規化とマッチ仕様を共通化し、一回のinvalidateFilter。旧setterは互換として維持可能。読み込み順sort復元はソース配列順を変えずproxyのソート解除を使う。MainWindowに選択・コピー順の可変リストを複製しない。

Terraの`UIManager.apply_filters_preserving_selection`はbindされたselection.apply_filtersへ薄く委譲し、現在の長い選択復元実装を撤去。MainWindowの既存ボタンhandlerはSelectionControllerに委譲。FileOperationManagerのモード切替も同じAPIへ。全選択、フィルタ、ビューアtoggle、行削除で一貫した状態にする。

## 4. FileOperation DTOとサービス（Terra）、Manager（Sol）

`src/file_operation_types.py`で以下のfrozen dataclassをTerraが定義し双方がimport。

```python
FileOperationRequest(operation_id: int, operation_type: str,
                     source_paths: tuple[str, ...], destination_folder: str)
FileSuccess(source_path: str, destination_path: str)
FileOperationResult(operation_id: int, operation_type: str, status: str,
                    destination_folder: str, successes: tuple[FileSuccess, ...],
                    errors: tuple[str, ...])
# operation_type: move/copy。status: completed/cancelled/error
# renamed_files/件数はsuccessesから導出。全経路で同じフィールド。
```

コピー番号は開始時source_pathsの順を採用、既存宛先数字prefix最大+1から`001_元名`、成功時だけ次番号へ。移動の衝突時`元名_1.ext`を維持。WorkerはQStandardItem/Qt role/MainWindow/Managerにアクセスしない。要求データをスナップショット化し、パス入力の外部リスト変更が実行へ影響しない。

```python
FileOperations(parent=None)
start(request: FileOperationRequest) -> bool    # idle時だけ受理
stop_operation() -> None                        # 非blocking・冪等
is_busy() -> bool                               # thread実終了までTrue
progress = pyqtSignal(int, int, int)             # operation_id, processed, total
result = pyqtSignal(object)                     # FileOperationResult、操作ごと一回
idle = pyqtSignal()                             # 実finished後
```

サービスはoperation_id付き結果を外へ転送、worker.resultでquit要求、thread.finishedで参照解放/idle。resultとidleの順序を保証し、例外経路でもresultを必ず一度出す。Manager/parentをhasattrで探索する接続は削除。既存`start_operation`互換を残すならGUIオブジェクトを受けずパス配列のみ、主配線は上記startを使う。外部コードは`_thread`でbusy判定しない。workerはGUI threadからstopを受けられるthreading.Event等で停止要求を確認する。

SolのFileOperationManagerがmonotonic operation_id、要求作成、progress dialog、明示signal接続、結果反映を持つ。コピーはselection.copy_paths、移動はselected_pathsのsnapshot。処理済みoperation_idを保持し二重配送で再適用しない。move成功分だけThumbnailController.remove_pathsとSelectionController.remove_pathsへ反映し、cancelled/errorでも成功を無視しない。失敗／未実行項目は残し、成功に応じた最終宛先・改名表示を更新。全成功後の選択解除は既存方針、部分成功は未成功項目を再操作可能にする。受付再開はresult時でなくidle時。

MainWindowの_process_file_op_completionはManagerへの委譲へ移行し、内部に長い別実装を残さない。closeはthumbnailとfile operationsの双方へstop要求、双方実idleになるまでignoreし再close。closing中の新規操作は拒否。cancelボタンはDialogManager等を探索せず明示stop接続。

## 5. folder_cleanup（Terra）とダイアログ接続（Sol）

`find_empty_subfolders(parent_dir: str) -> list[str]`、`is_dir_empty_recursive(path: str) -> bool`を既存実装から抽出。探索に副作用なし、OSErrorは非空として扱う現行方針を維持。削除候補の範囲と順序を勝手に拡張しない。MainWindowの確認とsend2trash処理はSolが維持し、選択ダイアログ以外へ自動削除を追加しない。

DialogManagerはparent Widget、Store、Thumbnail/Selectionへの明示参照またはcallbackをconstructorで受ける。MainWindow丸ごとのprivate属性探索を新たに増やさない。既存公開handler名はUI接続のため維持してよい。Metadata dialog/viewerのキャッシュ取得更新はmetadata_for/cache_metadata、選択はis_selected/toggleを注入する。ImageWithMetadataDialogも同じcallbackを受ける。TagPaletteWindowにはStoreを注入。WC、DropWindowの動作・形式は変更しない。

## 6. 非同期切替と所有者の合流

FAVORITES_API.mdの共通request_folder_navigationはSolがMainWindowで集約。検証・列挙成功→SelectionController.clear→ThumbnailController.replace→current/UI同期。引数なし保存はStoreへ、画像更新はControllerへ、結果反映はManagerへ移す。失敗時はcurrent/選択/旧世代を維持、同一currentは検証後no-op、タブはナビゲーションなし。

TerraはMainWindowを変更せず、Solに公開名と準備完了を通知。Solは新APIに従ってMainWindowを配線し、Lunaへ安定した境界を通知。Lunaだけがtestsを編集する。API名を実装中に変えた場合はこの文書と他担当を同時更新し、互換層で不一致を隠さない。
