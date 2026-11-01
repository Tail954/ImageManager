# ImageManager リファクタリング計画（Sol実装用）

作成日: 2026-10-31 / 調査対象: `ab94590`（タグパレットツール追加）

## 1. 目的と範囲

既存のPyQt6アプリの操作・保存データを維持しつつ、MainWindowへの責務集中と、UIオブジェクトに依存するバックグラウンド処理を解消する。今回の成果物は計画のみ。アプリコード、既存テスト、依存関係は変更していない。

実装は下記のPhase順で進める。各Phaseで動作確認を完了してから次へ進み、構造変更と既存不具合修正は別コミットにする。一括書き換え、UIデザイン変更、フレームワーク変更、依存ライブラリ更新、DB導入は対象外。

## 2. 調査結果

| 対象 | 現状と根拠 | 計画上の対応 |
| --- | --- | --- |
| `src/main_window.py`（1,164行） | 設定I/O、フォルダ走査、ローダー管理、選択、ソート、操作結果反映、空フォルダ処理まで保持 | 責務単位で抽出し、最後に配線とウィンドウイベント中心にする |
| `UIManager` / `DialogManager` / `FileOperationManager` | MainWindowの状態と他Managerの内部へ直接アクセス | 状態の所有者を決め、必要な依存・操作だけ渡す |
| `MainWindow._save_settings` / `_write_app_settings_file` | 設定辞書生成が重複。引数なしの保存は固定キーから再構築し、タグパレット設定やダブルクリック設定を含まない | 設定の読み書きを一本化し、未知キーも保持 |
| `MainWindow.__init__` | `_load_app_settings()`後に`double_click_action`を既定値で再代入 | 再現テストを追加し、設定抽出とは別の修正として扱う |
| `SettingsDialog._load_settings_for_dialog_display` | MainWindowとは別に同じJSONを読む | 渡された設定値から表示する |
| 選択処理 | パス一覧、QStandardItemのコピー順、Qtの選択状態を複数箇所で更新 | パスを識別子にして選択・コピー順の更新を集約 |
| `ThumbnailLoaderThread` | QStandardItemを受け渡し、プール内でアニメーションWebP用のQPixmapを作成。全タスク投入後、停止フラグだけで中断 | データだけを返す境界に変更し、世代管理と終了管理を導入 |
| ローダー停止・アプリ終了 | 待機がタイムアウトしても削除・終了へ進む経路がある | 実際のスレッド終了まで参照を保持する設計へ変更 |
| `FileOperationsWorker` | コピー処理がQStandardItemを読む。成功・失敗・キャンセルで結果辞書のキーが異なる | 開始時スナップショットと共通の結果契約を導入 |
| `MainWindow._process_file_op_completion` | キャンセル時は即returnし、既に移動したファイルの表示反映を行わない | 部分成功を表現し、成功分の反映後に終了理由を表示 |
| `FileOperations._on_worker_finished` | quit要求の直後にthreadのdeleteLaterと参照解除を行う | ワーカー結果通知とスレッド終了通知を区別 |
| `MetadataFilterProxyModel` | 各setterがinvalidateし、呼び出し側でも追加invalidate | 条件を一括適用し、選択復元までを一回の処理にする |
| テスト | 大規模なMainWindowモック、各ファイル独自のQApplication準備、古い内部構造に依存するテストがある | 境界のテストと実Qtモデルを使う統合テストへ段階的に移行 |

スレッド関連はコード上のリスクを確認したもので、今回クラッシュを再現したという意味ではない。

### 実行した確認

既存の `venv\Scripts\python.exe` はPython 3.10.6。

```powershell
.\venv\Scripts\python.exe -m pytest --collect-only -q -p no:cacheprovider
```

結果: 171件を収集した時点で1件の収集エラー。`tests/test_full_image_dialog.py:11`が`PREVIEW_MODE_ORIGINAL_ZOOM`を`src.full_image_dialog`からimportするが、そのモジュールには存在しない。定数の定義先は`src.constants`。また、`tests/test_simple_sort_model.py`の`TestApp`には収集警告がある。

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.\venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_metadata_utils.py tests/test_metadata_filter_proxy_model.py tests/test_file_operations.py --tb=short
```

結果: **35 passed, 2 xfailed**。全体テストの成功は未確認。GUI手動確認、性能測定、スレッド競合の再現は今回未実施。

## 3. 維持する仕様

- 既存の日本語UI、右クリック動作、2種類のプレビュー、ビューアからの選択切り替え。
- サムネイルサイズ96 / 128 / 200、アニメーションWebPの目印、メタデータ表示。
- フォルダ走査の再帰ON/OFF、走査時の列挙順を基準にした「読み込み順」、ファイル名・更新日時の昇降順。
- フィルタはフィールド間AND、各フィールド内のカンマ区切りキーワードはUI指定のAND/OR。空欄は制約なし。
- Enterによるフィルタ適用時の選択維持と、選択を解除する適用経路の区別。非表示になった項目とコピー順の詳細はPhase 0で固定する。
- コピーの選択順と、既存の数値接頭辞の最大値に続く`001_元名`形式。移動時の同名回避`元名_1.ext`形式。
- 空フォルダのごみ箱送りは現行の確認と実行タイミングを維持する。ツリークリック時や移動完了時へ勝手に追加しない。
- `app_settings.json`の既存キー、値、保存場所、ウィンドウ配置、タグパレットのYAMLとWC出力形式。

フォルダ走査は現在png/jpg/jpeg/webpに限定され、ドロップ受付の`IMAGE_EXTENSIONS`とは異なる。この差を整理名目で統一せず、機能変更として別途扱う。メタデータ解析仕様と現在のxfailも本計画で無断変更しない。

## 4. 目標の責務分担

新しい階層を多数導入せず、原則として既存の`src/`直下で抽出する。

| 所有者 | 責務・境界 |
| --- | --- |
| `MainWindow` | 依存の生成と接続、トップレベルウィンドウイベント、終了要求の調整 |
| `UIManager` | Widget生成、表示値反映、操作シグナル。設定ファイルI/Oや選択の業務ルールを持たない |
| `SettingsStore`（新規） | JSON読み書き、既定値、検証、未知キー保持。パスを注入可能にする |
| `SelectionController`（新規） | パス単位の選択、コピー順、モデル・ビューとの同期、フィルタ前後の復元 |
| `ThumbnailController`（新規） | 読み込み世代、ローダー寿命、サムネイルモデルとパス索引、現フォルダのメタデータキャッシュ |
| `ThumbnailLoaderThread` | ファイルとサイズからQImage・メタデータを生成。Widget / QPixmap / QStandardItemを保持しない |
| `FileOperationManager` | 操作要求の作成、進捗表示、結果に応じたモデル・選択・設定更新の調整 |
| `FileOperations` / Worker | 非同期実行と寿命管理 / ファイルI/O。MainWindowやManagerを探索しない |
| `DialogManager` | ダイアログの生成、再利用、終了。設定・選択・メタデータには明示した操作経由でアクセス |

Qtオブジェクトが必要なControllerはGUIスレッド上のQObjectとする。ワーカーからのUI更新はGUI側QObjectのslotで受ける。巨大な共通AppStateやサービスロケータでMainWindowへの依存を置き換える方法は採用しない。

移行中は旧MainWindowメソッドを薄い委譲として残してよい。状態は二重保存せず、互換プロパティで新しい所有者に転送する。参照元とテストを移したPhaseで不要な互換層を除去する。

## 5. 実装順序と完了条件

### Phase 0 — テスト基準を確立

1. 現在のHEAD・作業差分・依存バージョンを記録する。着手時のユーザー変更を保持する。
2. FullImageDialogの定数importを定義元へ修正する。プレビュー内部Widgetへ移された処理に古いテストが依存していないか点検する。テスト都合だけの不要な再exportは追加しない。
3. `tests/conftest.py`等でQApplicationの寿命とテスト用設定パスを統一。設定保存、テスト画像、コピー・移動、ごみ箱処理は一時領域またはfakeへ隔離する。現在のユーザー設定・画像へ触れる全体実行は避ける。
4. 全体テストを実行し、既存失敗を「古いテスト」「実装不具合」「環境不足」に分類する。テストを削除・skipして通過扱いにしない。
5. 構造変更前に、検索と選択、コピー順、設定保存、操作の部分失敗について不足する振る舞いのテストを追加する。

完了条件: 収集エラーなし。基準結果と既存失敗理由を記録し、以後新しい失敗を識別できる。主要な選択・モデル操作は実Qtモデルを使って確認する。

### Phase 1 — 設定管理を抽出

対象: `main_window.py`、`settings_dialog.py`、`dialog_manager.py`、`tag_palette_window.py`。

1. `src/settings_store.py`を追加し、load / update / saveの入口を一本化する。既存JSONの未知キーも保持し、部分更新で他機能の設定を失わないようにする。
2. 既定値と検証をまとめる。既存の有効な値を保持し、不正値のfallbackをテストする。保存は同一ディレクトリの一時ファイルから置換し、保存失敗時に元ファイルを壊さない。
3. SettingsDialogは渡された値を表示し、変更結果を返す。DialogManagerとTagPaletteWindowも同じstoreを使う。保存場所の移行は行わない。
4. 別コミットで、読込後のdouble_click_action上書きと、引数なし保存で設定キーが落ちる問題を修正する。

完了条件: 読込→一部変更→保存→再読込で、ダブルクリック・タグパレット・geometry・未知キーが残る。設定キャンセル時とサムネイルサイズ変更拒否時の現行動作を維持する。

### Phase 2 — 選択とモデル操作を整理

対象: `main_window.py`の選択・ソート・フィルタ、`ui_manager.py`の選択復元、`file_operation_manager.py`のモード切替、`metadata_filter_proxy_model.py`。

1. `src/selection_controller.py`へ選択状態とコピー順を集約する。コピー順は長寿命のQStandardItem参照ではなくパスの順序として保持し、`SELECTION_ORDER_ROLE`を表示用に反映する。
2. モデル更新時にパス索引を更新する窓口を定める。索引はThumbnailControllerへ引き継ぐまで単一の所有者に置き、モデルクリア・行削除後に無効な項目が残らないようにする。
3. フィルタ条件をまとめて適用するAPIを追加する。選択の退避→一回の再評価→可視項目の選択復元→コピー順と件数反映を一つの操作として扱う。
4. シグナル抑止と描画抑止は例外時にも復旧する。ソートやフィルタの途中状態で選択情報を書き換えない。

完了条件: 通常選択・選択解除・全選択・モード切替・フィルタ・ソート・ビューア操作・フォルダ変更を組み合わせても、選択件数とコピー順が一致する。順序維持の意味はPhase 0の振る舞いテストに従う。

### Phase 3 — サムネイルのデータ境界と寿命管理

対象: `thumbnail_loader.py`、`main_window.py`の読み込み・更新・終了処理。

1. `src/thumbnail_controller.py`を追加する。入力はパス列・サイズ・load_id、結果はload_id・path・QImage・metadata・errorとする。小さなdataclassまたは型付きの結果で契約を明示する。
2. モデル作成、QPixmap/QIcon生成、アイテム更新はGUI側へ集約する。WebPの目印はQImageへの描画かGUI側描画へ移す。Pillow画像のクローズと、返すQImageのデータ寿命を保証する。
3. フォルダ切替ごとにload_idを更新し、古い結果・進捗・完了通知を無視する。読み込み順は完了順ではなく、開始時の列挙順を維持する。
4. キャンセル後は追加投入を止め、未着手futureをキャンセルする。全ファイルの無制限な先行投入を避け、同時実行数と投入数を制限する。実行済みI/Oの強制停止は行わない。
5. 結果処理完了とQThread終了を区別する。QThreadのfinishedを独自の処理完了signalとして再定義せず、実際に終了した時点で解放する。
6. 終了要求後も動いているジョブがあれば、その参照を保って終了を非同期に待つ。タイムアウトを根拠に実行中threadを破棄しない。閉じる要求の重複を防ぐ。

完了条件: 空フォルダ、壊れた画像、途中で消えた画像、アニメーションWebP、A→B→Aの切替、サイズ変更、読み込み中の終了で、古い結果の混入・二重完了処理・破棄済みitem参照がない。制御可能なfake workerと実スレッドの小さな統合テストを併用する。

フォルダ走査自体の別スレッド化や独自QAbstractListModel化は初回では行わない。必要性はPhase 5の計測で判断する。

### Phase 4 — ファイル操作の契約と結果反映を整理

対象: `file_operations.py`、`file_operation_manager.py`、`main_window.py`の操作完了・空フォルダ処理。

1. `src/file_operation_types.py`等に要求と結果を定義する。要求はoperation_id・種別・順序確定済みパス列・宛先を持ち、開始時にコピーする。WorkerはUI項目を読まない。
2. 結果は全経路でoperation_id・種別・終了理由・宛先・成功した元/先パス・改名情報・エラーを返す。件数は成功結果と一致させる。
3. FileOperationsはprogress / result / idle等の公開signalを持つ。MainWindowやManagerのメソッドをhasattrで探索するfallbackを除去し、接続は生成側で行う。
4. 操作結果反映をFileOperationManagerへ移し、ThumbnailController / SelectionController経由で成功項目だけ更新する。再度同じ結果を受けても二重削除しない。
5. 別コミットで、キャンセル前の部分成功も画面に反映する修正を行う。失敗・未実行項目はモデルに残し、ユーザーが再操作できるようにする。
6. worker結果受信時にはthreadを即破棄せず、thread.finished後に参照解除する。操作の受付再開とUIのボタン有効化も実際のidleに合わせる。読み込み中等の別理由での無効化も維持する。
7. 空フォルダ探索だけを`src/folder_cleanup.py`等へ抽出する。確認ダイアログはUI側に残し、削除対象とタイミングを変更しない。

完了条件: 一時フォルダで同名移動、既存連番へのコピー、欠損ファイル、宛先不存在、I/O失敗、途中キャンセル、連続実行、処理中終了を検証する。成功分とディスク・表示が一致し、ユーザー画像で試験しない。

### Phase 5 — 統合、残存依存の解消、文書化

1. MainWindowの互換委譲を必要最小限にし、他クラスからprivate属性を辿る経路を除去する。DialogManagerへは親Widgetと必要な設定・選択・画像情報の取得手段を渡す。
2. デッドコード・重複import・古い変更履歴コメントを整理する。実装理由を説明するコメントは残す。`WCController`は本体参照の有無を確認してから削除または維持を決め、名前だけで新規抽象化を追加しない。
3. READMEへ起動方法、テスト方法、責務一覧、設定保存場所を記載する。Phaseごとの変更と検証結果を記録する。
4. 全体テストと手動スモークを実施する。手動確認はフォルダ選択→表示→検索→選択→両ビューア→コピー/移動→WC→タグパレット→設定保存→再起動。
5. 同一マシン・同一画像セットで、着手前後の読み込み完了時間、最大メモリ、フィルタ反応、キャンセル・終了の挙動を比較する。速度向上を未計測のまま主張しない。

完了条件: 新しいテスト失敗がない。既知失敗の残存は理由を明記。設定互換性と上記主要操作を確認済み。MainWindowの行数だけを達成指標にしない。

## 6. Solへの実行指示

- まずPhase 0のみを実施し、基準を確立してからPhase 1以降へ進む。Phaseごとにレビュー可能な差分・検証結果を残す。
- 本計画の構造整理と、明記した設定・部分キャンセル・スレッド寿命の修正を対象とする。それ以外の仕様変更を発見時に混ぜない。
- テストの内部参照先は新構造に合わせて変更してよいが、検証対象の振る舞いを弱めない。巨大なMainWindowモックの複製を新Controllerへ持ち込まない。
- ユーザーの`app_settings.json`と画像を保持する。依存更新や新しいライブラリの導入は前提にしない。
- 終了報告は、完了Phase、変更理由、テスト結果、既存失敗、未実施のGUI/性能確認を記載する。
