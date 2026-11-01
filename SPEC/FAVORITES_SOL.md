# Sol担当：管理・保存・ナビゲーション

> 更新：全体実装が承認済み。最新の担当は`REFACTOR_EXECUTION.md`、契約は`REFACTOR_API.md`。本書の実装禁止は失効し、testsはすべてLuna所有。以下はお気に入り固有の参考指示。

前提：現在は設計フェーズで実装禁止。実装指示後、本書と`FAVORITES_API.md`を読むだけで着手してよい。GUI方式はB（お気に入り／フォルダのタブ）で確定。初期表示はお気に入り、タブ切替は画像読込なし。

## 所有ファイル

- 新規：`src/favorite_folders.py`、`src/settings_store.py`、`src/thumbnail_controller.py`。
- 変更：`src/main_window.py`、`src/thumbnail_loader.py`、`src/constants.py`。
- テスト：新規`tests/test_favorite_folders.py`、`tests/test_settings_store.py`、`tests/test_thumbnail_controller.py`、変更`tests/test_thumbnail_loader.py`。
- GUIファイル（UIManager含む）とLuna担当の統合／MainWindowテストを編集しない。不足は所有者へ伝える。既存`SPEC/REFACTOR_PLAN.md`、ユーザー設定・実画像を変更しない。

## 実装順序

1. HEAD差分と既存モジュール有無を確認。APIのデータ型・Windowsパス規則を実装する。保存復元で不存在を消さず、重複は正規化key、順序は配列、同名は親フルパスで識別。FavoriteFoldersにQt依存を入れない。
2. 既存JSON場所のまま保存helperを作る。MainWindowの引数なし保存は既存辞書を保持する共通collectorへ。設定・タグパレットの既存呼び出しを維持し、お気に入り変更の保存失敗はメモリもロールバックする。
3. ローダーを世代＋パス＋QImage＋metadataへ変更。QStandardItemを渡さない。独自finished宣言/emitを除去し、ThreadPool内QPixmapをQImageに置換する。controllerは実worker最大1、予約最新1、実終了後のみdeleteLater。cancel済み世代の進捗と完了で最新状態を変更させない。
4. MainWindowへAPIの共通ナビゲーションをまとめる。検証・列挙成功前にcurrent／選択を変更しない。既存ツリー表示更新を読込から分離する。ソートと空フォルダ削除はsourceごとの契約を守る。削除後と選択後の二重読込を防ぐ。モデルclear前にコピー選択参照を安全に解除する。
5. UIManager.favorites_panelの6シグナルをAPIどおり接続する。set_*呼出し、保存失敗通知、clipboard、Explorerもここで担当。画像更新、進捗、完了はGUI側でも世代を最初に検査。閉じる際は実終了前にQThreadを破棄しない。
6. TerraへAPI実装完了と使用可能なUI境界を通知。自身の単体試験を通したうえでLunaに統合を渡す。テスト都合だけで公開APIや所有範囲を変更しない。

## 読むべき実ソース

`main_window.py:276`保存、`:428`フォルダ入口、`:483`読込、`:654`完了、`:778`フィルタ、`:1012`空フォルダ後更新、`:1046`close。`thumbnail_loader.py:19`シグナルと`:144`run。呼び出し元`dialog_manager.py:119`、`tag_palette_window.py:75,297`、`file_operation_manager.py:28,62`。対象関数と呼び出し元を読む。全面書換えや全既存計画の先行実施は不要。

## 完了条件

Windows同一性（大小・区切り・ドライブ/UNCルート・namespace方針）、復元時の不正項目、同名表示、全順列検証、保存失敗復元、未知キー保持を単体試験。cancel→遅延画像/進捗/finished、B予約→C置換、空フォルダ、close延期を制御可能なfake workerで確認し、実Qt workerでも寿命を一回以上確認する。sleepに依存する競合試験にしない。

GUI更新は既存フィルタ・ソートを流用し、読み込み順を変えない。別フォルダへの成功切替は選択解除、同一current・失敗・タブ操作は維持。画像I/Oの強制停止や同期列挙の全面非同期化は行わない。未解決の既存失敗と変更による失敗を分けて報告する。
