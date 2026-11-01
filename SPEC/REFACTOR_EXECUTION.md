# 全体リファクタリング＋お気に入り：実行統括計画

2026-10-31 / Astra設計・統括 / 基準HEAD `ab9459046cb3c31416517653eb8c73f22d551f23`

## 最新指示と優先順位

ユーザーは初回のお気に入り設計依頼の後、**ImageManager全体のリファクタリングを実行し、Astra=設計統括、Sol=コア、Terra=独立機能、Luna=QA**と指定した。実装・検証までが現在の承認済み範囲であり、「設計のみ」「実装禁止」という以前の資料記述は失効した。

仕様優先順位は **本書とREFACTOR_API.md → FAVORITES_API.mdの矛盾しない機能仕様 → 既存REFACTOR_PLAN.md → その他の担当資料**。既存REFACTOR_PLAN.md自体はユーザーの未追跡資料として変更しない。5つのお気に入り資料は調査証跡と機能仕様を保持し、担当範囲・単一所有者・APIは本統合版が上書きする。テストはすべてLuna所有。

目的は全体の責務分離と既知の設定消失／部分成功喪失／非同期寿命問題の修正、およびお気に入り機能の追加。既存PyQt6、日本語UI、画像対象、保存場所、タグYAML、WC出力、コピー番号規則、移動時改名、空フォルダ削除の確認・タイミングを維持。フレームワーク・依存ライブラリ・DB刷新はしない。

## 調査から確定した構造

お気に入りとGUIの調査根拠・8観点比較はFAVORITES_DESIGN.mdを参照。B（同領域タブ）採用は変更しない。全体の追加依存調査では次を確認した。

| 根拠 | 結論 |
| --- | --- |
| `main_window.py:110`、`:112`、`:276`、`:312` | 設定読込後double_click_action再代入と、引数なし保存によるキー消失を切り分けて修正。SettingsStoreが唯一の辞書所有者 |
| `ui_manager.py:325`、`main_window.py:704` | 選択復元とコピー順がGUIとMainWindowに分散。パス順序へ集約しQtアイテム参照を長期保存しない |
| `metadata_filter_proxy_model.py:66`、`:79`、`:86`、`:93` | 複数setterで反復invalidate。条件一括更新APIを追加し選択復元と一回の再評価にまとめる |
| `thumbnail_loader.py:19`、`:93`、`:173`、`:212` | workerのitem依存、プール内QPixmap、全件先行投入、独自finishedを除去。世代と実終了を分ける |
| `file_operations.py:17`、`:106`、`:136` | コピーworkerがQStandardItemを読む。要求時点のパスtupleに置換。終了経路ごとに異なるdictを共通結果へ |
| `file_operations.py:207`、`:241` | Manager/parentを探索する自動接続を除去。result後quit要求だけで参照を捨てず、実finishedまで保持 |
| `main_window.py:810`、`:816`、`:936` | result反映をFileOperationManagerへ移す。cancelledで成功分を捨てず、成功分反映後に終了理由を表示 |
| `main_window.py:951`、`:1022` | 純粋な空フォルダ探索をfolder_cleanupへ。確認ダイアログとごみ箱操作はUI側に残す |
| `settings_dialog.py:228`、`tag_palette_window.py:74`、`:295` | SettingsDialog独自JSON読込を廃止。タグ設定は同一Storeの公開APIを使う |
| `dialog_manager.py:123`、`:202`、`:279`、`image_with_metadata_dialog.py:96` | ダイアログの画像/metadata/選択参照はcontrollerまたは明示callbackへ。private属性の探索を解消 |
| `wc_controller.py:5` | 本体からのimport/useは今回のrg調査では見つからず、専用テストはある。公開moduleの無断削除はせず維持。新しい抽象化も作らない |

全ソースを一括読込せず、既存計画・対象関数・全呼出し元を追跡した。既存コードのリスクであり実クラッシュを再現したという意味ではない。Astraは収集だけを実行し171件＋既知ImportError 1件を確認。Lunaが隔離した試験本体の基準を取得中。

## ファイル所有表（排他的）

| 担当 | 所有ファイル | 受渡し |
| --- | --- | --- |
| Sol | `src/main_window.py`、`src/settings_store.py`、`src/selection_controller.py`、`src/thumbnail_controller.py`、`src/thumbnail_loader.py`、`src/favorite_folders.py`、`src/constants.py`、`src/metadata_filter_proxy_model.py`、`src/dialog_manager.py`、`src/file_operation_manager.py`、`src/image_with_metadata_dialog.py`、`README.md` | コアcontrollerと全体配線。Terraの部品を公開契約で使用 |
| Terra | `src/ui_manager.py`、`src/favorites_panel.py`、`src/file_operation_types.py`、`src/file_operations.py`、`src/folder_cleanup.py`、`src/settings_dialog.py`、`src/tag_palette_window.py` | GUIと独立I/O部品。MainWindowは編集しない |
| Luna | `tests/`全体、`SPEC/QA_BASELINE.md`、`SPEC/REFACTOR_QA_REPORT.md`、必要なら`SPEC/FAVORITES_QA_REPORT.md` | 基準・単体・統合・回帰・実GUI検証。実装者は試験ケースを提案し自身でtestsを編集しない |
| Astra/親 | `SPEC/REFACTOR_EXECUTION.md`、`SPEC/REFACTOR_API.md`、設計資料 | API変更調整と統合判定。コード所有者へ問題を返す |

未列挙のソースを変更する前に統括へ理由を伝え所有者を一人に決める。同一ファイルを並行編集しない。APIを変更する場合は統括と相手担当へ先に通知。ユーザーの未追跡SPECとapp_settings.jsonを保持し、コミットに無関係ファイルを含めない。コミット実行の要否は親が判断し、段階差分とテスト記録でレビュー可能にする。

## 段階とゲート

1. **Phase 0 / Luna：基準。** 一時CWD/設定/画像、QApplication寿命を隔離し、既知収集エラーを修正。古いテスト・実装不具合・環境不足を分類。選択、コピー順、フィルタ、設定、部分失敗を固定する。調査と独立moduleの準備は並行可。本体を全面置換する前に基準を記録する。
2. **Phase 1 / Sol設定、Terra独立部品。** Storeを単一所有者として確立。TerraはFileOperation DTO/worker、folder_cleanup、FavoritesPanelをAPIに対して実装できる。SettingsDialog/TagPaletteの保存連携はStore公開後に接続。設定キー保持・失敗原本保持がゲート。
3. **Phase 2–3 / Solコア、Terra GUI。** SelectionController、ThumbnailControllerへ状態を移す。UIManagerはmodel参照を表示用に持ち、選択復元をcontrollerへ委譲。世代、順序、有界future、実終了、close待機を試験。独自ListModelや非同期フォルダ走査へ拡大しない。
4. **Phase 4 / Sol統合、Terra I/O。** FileOperationManagerが不変要求作成と結果反映を所有。部分成功と二重配送を扱う。workerのresultとidleを区別し、モデル反映後も実idleまでは操作再開しない。フォルダ探索は既存タイミングを維持。
5. **お気に入り統合。** Bタブ、管理/保存、単一ナビゲーション、Windowsパス、失敗時状態保持、内部D&Dを接続。旧結果対策を使い回し専用loaderを作らない。
6. **Phase 5 / 全員＋Luna。** private探索・重複状態・不要互換・デッドコードを整理しREADME更新。全体試験＋手動スモーク＋同一画像セット計測。構造整理とバグ修正を報告で区別し、速度向上を未計測のまま主張しない。

各段階でAPIの実動作と関連試験を確認。新規失敗、保存破損、旧結果混入、実行中thread破棄、部分成功の不整合を残したまま完了扱いにしない。全体の実装承認済みなので、Phaseごとにユーザーの再承認を求める必要はない。

## 担当別の最小指示

**Solは本書＋REFACTOR_API.mdを読み、必要なお気に入りパス/UI規則だけFAVORITES_API.mdから読む。** 設定→選択→サムネイル→FileOperationManagerの順で単一所有者化し、MainWindowは配線・ウィンドウイベント・薄い互換委譲中心にする。既存APIの互換プロパティは同じ実体へ転送し二重状態を持たない。UIManager/独立I/Oを編集せずTerraへ要求。テスト変更はLunaへ渡す。Lunaの基準で仕様が曖昧なら既存動作を固定してから抽出する。

**Terraは本書＋REFACTOR_API.mdの境界とFAVORITES_API.mdのGUI節を読む。** FileOperationsはQtアイテム・MainWindow・Manager探索なし、入力スナップショットと全経路共通結果、寿命は実finishedまで。UIはB確定、読込中もnavigationを操作可能にし、選択規則はSol controllerへ委譲。SettingsDialogは渡された設定のみ、TagPaletteは公開Storeのみ。folder_cleanupは探索のみで削除しない。MainWindow/定数はSolへ依頼。testsはLunaへ渡す。

**Lunaは本書＋REFACTOR_API.mdとFAVORITES_LUNA.mdのマトリクスを読む。** tests全体を一人で管理。Phase0の実ファイル隔離を最優先。現行の誤った内部構造期待は改訂するが、仕様試験を削除/skipして成功扱いにしない。各部品の契約、実Qtモデル/実threadとfake制御の両方を検証。全機能手動スモークと未測定事項を明記。基準と後続を別記録にする。

## 残る制約

統合時の追加割当：`src/full_image_dialog.py`はSol所有。LunaのHEAD基準で確認した初回選択状態の未反映を、構造変更とは区別して修正する。変更前全体基準は`SPEC/QA_BASELINE.md`参照。

同期列挙・停止不能I/Oは残る。性能計測結果がない段階で非同期走査や高速化を追加しない。case-sensitive Windowsフォルダ・symlink実体同一視はお気に入りの対象外方針のまま。既存WCControllerは維持。手動GUI、性能、実権限環境が確認できない場合は未確認として報告し、完了結果の範囲を明示する。
