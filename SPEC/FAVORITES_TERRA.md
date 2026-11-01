# Terra担当：お気に入りGUI

> 更新：全体実装が承認済み。最新の担当は`REFACTOR_EXECUTION.md`、契約は`REFACTOR_API.md`。本書の実装禁止は失効し、testsはすべてLuna所有。以下はお気に入りGUI固有の参考指示。

前提：現在は設計フェーズで実装禁止。実装指示後、本書と`FAVORITES_API.md`のみで開始可能。**Bを採用済み。A/Cの切替設定を実装しない。**

## 所有ファイル

- 新規`src/favorites_panel.py`、変更`src/ui_manager.py`。
- 新規`tests/test_favorites_panel.py`、変更`tests/test_ui_manager.py`。
- MainWindow、constants、管理サービス、ローダー、統合テストは編集しない。MainWindowへの配線と通知はSol担当。型FavoriteEntryはSolモジュールからimportし、別定義を作らない。

## 実装内容

1. 現在の`UIManager._create_left_panel`末尾（`src/ui_manager.py:126`）をQTabWidgetへ。タブ0「お気に入り」、1「フォルダ」。既存QTreeViewとQFileSystemModelは同じ属性名のまま第2ページに配置。既存上部のフォルダ選択ボタンとソート／フィルタ／ファイル操作位置を維持。
2. FavoritesPanelに「現在のフォルダを登録」と単一選択の一覧を作成。APIの6要求シグナルと3表示メソッドを提供。set_*、タブ切替、プログラム選択からナビゲーションをemitしない。
3. 名前はentry.display_name、tooltipはフルpath、内部IDはentry.key。長いラベルは省略し、tooltipとコピー操作で全文取得できるようにする。登録なし時は短い案内「現在のフォルダを登録できます」を表示。存在検査・バックグラウンド監視をしない。
4. 左クリックはdragが成立しなかったreleaseだけで一回activate。右クリックは対象keyの解除／パスコピー／Explorerメニューのみ、開かない。表示選択変更シグナルをactivateへ接続しない。Enter操作を追加する場合も同じ一要求に統一し、doubleClickedには別接続しない。
5. 内部一項目moveのみ。drop完了で新しい全キー順を一度通知。ドラッグ中や外部dropは保存しない。set_entriesによる再描画はorderChangedをemitしない。失敗時はSolがset_entriesで旧順を再反映する。drag後releaseによるフォルダ切替を必ず防ぐ。
6. `set_thumbnail_loading_ui_state`を画像操作のみの無効化へ変え、全左overlayをこの経路では使わない。お気に入り・ツリー・フォルダ選択・タブは読込中も触れる。フィルタ等の既存有効化、copy mode条件を正しく復元し、画像選択ロジックを再実装しない。

## 調査根拠と完了条件

`ui_manager.py:68`横splitter、`:74`初期最大350px、`:93`左パネル、`:247`独立した右画像モデル、`:289`overlay、`:312`読込ロック、`:325`選択維持。新GUIは右画像モデルと完全に独立させる。

単体試験で左クリック一回、右クリックゼロ、dragゼロ（orderのみ）、タブ切替ゼロ（画像読込／選択変更）、set_*ゼロ（要求emit）を数える。fake entryで同名／長パス／ルートの描画を確認。保存・パス同一性・存在確認はSolに任せる。

Lunaへ350px幅、縮小、splitter拡張、高DPI、空一覧、多数行、現在項目解除、D&D先頭末尾の手動確認項目を渡す。統合前はAPIに従うstubで確認可能だが、stubを本番コードへ埋め込まない。ソース差分とGUI単体試験結果を報告する。
