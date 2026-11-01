# Luna担当：基準確認・統合QA

> 更新：全体実装が承認済み。最新の担当は`REFACTOR_EXECUTION.md`、契約は`REFACTOR_API.md`。本書の実装禁止は失効し、Lunaがtests全体を所有。以下の受入マトリクスは引き続き適用。

前提：現在は設計フェーズで実装禁止。実装指示後、本書と`FAVORITES_API.md`で開始可能。方式はB（同領域のタブ）で確定。日常の登録先移動を一クリックで行い、タブ切替は表示だけ。

## 所有・安全な環境

- 新規`tests/test_favorites_integration.py`、変更`tests/test_main_window.py`、新規`SPEC/FAVORITES_QA_REPORT.md`。
- `tests/test_full_image_dialog.py:11`の既知収集エラーは定数を`src.constants`からimportする最小修正のみ担当可能。アプリ側へテスト都合の不要exportを追加しない。
- 単体テストはSol/Terra所有。本体の不具合は該当所有者へ返す。必要な共通fixture追加はLunaだけが行い、事前に担当へファイル名を通知する。
- tmp_path＋一時CWDで全設定・画像を隔離。MainWindow生成前に設定パスを隔離する。QApplicationはプロセスに一つ。Explorer、clipboard、ごみ箱、ダイアログを適切にstub。ユーザーのapp_settings.json・実フォルダに試験を書込まない。

## 基準と実行順

Astraは変更前に`QT_QPA_PLATFORM=offscreen`、`PYTHONDONTWRITEBYTECODE=1`で`venv\Scripts\python.exe -m pytest --collect-only -q -p no:cacheprovider`を実行。171件収集＋`test_full_image_dialog.py:11`のImportError 1件、`test_simple_sort_model.py:56`のTestApp警告を確認。試験本体は未実行。この基準を「全件成功」と書かない。

最初に隔離して既存の関連試験を実行し変更前結果を保存。Sol/Terraの境界が揃ったら下表を自動試験、最後に実GUI手動試験。API変更で古い内部mockが合わない場合は期待する外部動作を保って更新し、失敗を無条件skipしない。

## 受入マトリクス

| 領域 | 必須操作 | 合格条件 |
| --- | --- | --- |
| 登録 | 未選択、current登録、同じパス再登録、大小文字/末尾区切り違い | 未選択無効、末尾へ一件追加、正規化重複なし |
| パス | ドライブ直下、UNC共有直下、日本語/空白、`.`/`..`、extended表記 | APIどおり正規化。symlink/junction別名は別項目。ルート名が空にならない |
| 復元 | 起動、登録/解除/並替直後のJSONを再読込、不正型・重複値 | 情報と順序復元。不存在を保持。起動だけでJSONを書換えない |
| 保存失敗 | readonly/書込例外/os.replace失敗 | 元ファイル保持、メモリとD&D順を復元、日本語通知。実ACL不要なら例外注入 |
| 他設定保持 | favorite変更→設定ダイアログ保存→タグパレット保存→終了保存 | favorite順序、タグ・geometry・double click・未知キーが残る |
| 解除 | 現在表示中、最後の一件、右クリック解除 | データだけ消える。current/画像/選択不変。削除・ごみ箱関数の呼出し0 |
| 同名 | 異なる親の同名、case違い、片方解除 | 全衝突項目に親フルパス。tooltip全文。解除後表示名再計算 |
| D&D | 中央→先頭/末尾、元位置、cancel、外部drop | 確定移動一回保存。cancel無変更。内部moveのみ。画像load0 |
| 右クリック | メニュー表示、パスコピー、Explorer、失敗 | 表示だけでは移動なし。コピーはフルパス。Explorer失敗を通知しcurrent不変 |
| 通常切替 | favorite、ツリー、ダイアログ、同一current | 共通入口。異なるフォルダで一読込。同一はno-opで画像選択維持 |
| source差 | favorite/treeとdialogを同じ初期ソート設定で比較 | favorite/treeは現在sort維持・空フォルダ削除なし。dialogのみ従来方針・一読込 |
| 不存在/権限 | 削除済み、切断UNC、ファイル化、root PermissionError | 登録維持と通知。current/モデル/選択/copy順/sort/世代が変わらない |
| 読込競合 | A処理中→B→C、A旧画像/旧進捗/旧finishedを遅延配送 | Cのみ反映。B未開始なら開始0。worker最大1。旧finishedはCのロックを解除しない |
| 読込境界 | 空フォルダ、画像個別破損、同じパスへのforce refresh、サイズ変更 | 一世代一完了、最新世代のみ反映。旧itemアクセス例外なし |
| 中断/終了 | 停止待ち、7秒相当を超えて終了しないfake、close中に結果配送 | timeoutで破棄しない。GUI waitなし、closeは実終了まで延期、新規要求busy |
| ファイル操作中 | move/copy中にAPIからfavorite要求 | modalの有無によらずbusy。操作結果が別フォルダへ混入しない |
| B方式 | タブ往復、ツリー展開後戻る、読込中のタブとfavorite操作 | 切替でload/選択変更0。展開状態保持。別タブのビューは非表示。設定方式項目なし |
| 既存画像機能 | 再帰ON/OFF、全sort、filter AND/OR、通常/コピー選択順、非表示画像 | 既存仕様を維持。別フォルダ成功時のみ選択リセット。filter/同一操作で維持 |
| 周辺回帰 | thumbnail size、両viewer、metadata、copy/move、空フォルダ処理 | 既存操作の結果と保存互換が変わらない。実ファイル操作は一時領域のみ |

競合試験はfake workerのシグナルを任意順で配送して再現し、単なるsleepと目視に頼らない。加えて実Qtスレッドを終了させ、QThread破棄警告がないことを確認。設定単体・GUI単体は担当の結果を再利用し、統合境界を重点にする。

手動GUI：350px幅／拡張／縮小／高DPIでタブ・登録ボタン・同名ラベル・tooltip・スクロールを確認。クリック、右クリック、D&Dのジェスチャを実入力で確認。登録→別フォルダ→一クリック復帰→フィルタ→選択→タブ往復→並替→再起動を通す。Explorerの実起動は一時テストフォルダに限定。権限の実環境確認が難しい場合、例外注入と実環境未確認を明記する。

## 報告

`SPEC/FAVORITES_QA_REPORT.md`に変更前/後のコマンド・件数・失敗、試験したHEAD、マトリクス結果、手動GUI確認、未実施を記録。重大項目（保存・旧結果混入・QThread寿命・アクセス失敗時の状態保持）が未検証なら完了扱いにしない。実装者へ返す不具合は再現操作と期待/実際を短く示す。
