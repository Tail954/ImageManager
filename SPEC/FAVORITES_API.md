# お気に入りフォルダ：共通API契約 v1

> 更新：全体リファクタリングが承認済み。`REFACTOR_API.md`の単一所有者・Store・Thumbnail/Selection・FileOperations契約が本書より優先。Windowsパス、FavoriteFolders、GUIシグナル、B方式、ナビゲーションの機能規則は本書を使用。

2026-10-31 / Astra確定。実装前の契約。Sol・Terra・Lunaは担当指示書と本書を読む。ここにない表示方式追加や設定移行は不要。

## 1. 管理データ・保存（Sol所有）

`src/favorite_folders.py`はQt、Widget、Explorer、画像モデルをimportしない。

```python
@dataclass(frozen=True)
class FavoriteEntry:
    key: str          # 正規化比較キー。GUI内部ID。表示ラベルをIDにしない
    path: str         # 正規化した絶対パス。元の大文字/小文字は保存
    name: str         # basename、ドライブ/共有ルートならルート表記
    display_name: str # 同名なし:name、同名あり:name + " — " + 親フルパス

@dataclass(frozen=True)
class FavoriteResult:
    status: str       # added / removed / reordered / duplicate / unchanged /
                      # invalid / not_found / save_failed
    message: str      # 表示可能な日本語。成功は空でもよい

class FavoriteFolders:
    def __init__(self, raw_paths, persist): ...
    def entries(self) -> tuple[FavoriteEntry, ...]: ...
    def get(self, key: str) -> FavoriteEntry | None: ...
    def add(self, path: str) -> FavoriteResult: ...
    def remove(self, key: str) -> FavoriteResult: ...
    def reorder(self, keys: list[str]) -> FavoriteResult: ...

def normalize_folder_path(path: str) -> tuple[str, str]: ... # (path, key), ValueError
```

`persist`は`Callable[[list[str]], bool]`。候補配列を保存し、成功時True。Falseまたは例外ならsave_failed、管理状態は旧スナップショットのまま。登録／解除／並替は保存成功後にだけ状態をcommit。duplicate/unchanged/invalid/not_foundでは保存しない。reorderは現在のキーを重複なく全件一度ずつ含む順列のみ受理。登録順は末尾追加。

Windowsパスの規則：

- 入力は空でないstr。前後の空白をstripしない（パスの一部）。NUL、URL、相対パス、`C:foo`や`\foo`等ドライブ依存の不完全パスはinvalid。UIは既存currentの絶対パスのみ渡す。
- `ntpath.normpath`で区切りと`.`/`..`を正規化。末尾区切りはルート以外除去。ドライブルート`G:\`とUNC共有ルート`\\server\share\`は末尾`\`ありに統一。`/`も`\`へ。
- keyは上記pathの`ntpath.normcase`。例`G:/Pictures/A/`と`g:\pictures\a`は同一。表示pathは最初に登録した表記を保持する。
- `\\?\C:\...`と`\\?\UNC\server\share\...`の通常ドライブ/UNC表記はprefixを除去して同一キーにする。`\\.\`、GLOBALROOT等のデバイス名前空間は対象外でinvalid。
- `realpath`、ファイルID、`samefile`で実体解決しない。symlink/junction、8.3名、別ドライブ割当、別サーバーaliasは異なるパスとして扱う。ネットワーク照会不要、移動／不存在でもキー不変。case-sensitiveな特別設定のWindowsディレクトリも今回の比較はcase-insensitive。
- 管理サービスは存在確認をしない。currentの可読性確認はナビゲーション担当。起動復元時は有効な絶対パスを残し、不存在でも保持。非listの保存値は空扱い、list中の無効型/パスは読み飛ばし、正規化重複は先頭優先。起動時の自動保存はしない。
- `name`のcasefoldが一致する複数項目は全員を「name — 親フルパス」にする。rootのnameはpathそのもの。GUI側の省略とtooltipを除き、この表示規則は管理サービスが返す。

既存`app_settings.json`にキー`favorite_folders`、値は順序付き絶対パス文字列配列（初期値`[]`）だけを追加。定数`FAVORITE_FOLDERS = "favorite_folders"`を`src/constants.py`へ。タブ状態や名前の複製保存はしない。

`src/settings_store.py`は`SettingsStore(path)`、`load() -> dict`、`save(settings: dict) -> bool`。UTF-8・既存indent=4を維持し、同じディレクトリの一時ファイルへ書き終えてから`os.replace`。失敗はログ＋False、元ファイル保持、一時ファイルを後始末。loadは既存と同じ不正JSON時の空辞書フォールバック＋ログ、起動直後の自動上書きはしない。CWD相対保存場所は移動しない。

MainWindowのapp_settingsを実行中の全設定辞書とし、全保存入口は「そのコピー＋既存UI状態の更新」で作る共通collectorを使用。`_write_app_settings_file(settings_dict=None) -> bool`は引数あり/なしとも既存キーを落とさず保存する。`_save_settings`、設定ダイアログ、タグパレットからの既存呼出しを互換維持。お気に入りpersistはcollectorの候補辞書のfavorite_foldersだけ差替え、成功時にapp_settings更新。現在の管理リストから上書きして候補を消さない。

## 2. GUI境界（Terra所有、Solが接続）

```python
class FavoritesPanel(QWidget):
    addRequested = pyqtSignal()
    activateRequested = pyqtSignal(str)       # entry.key
    removeRequested = pyqtSignal(str)
    copyPathRequested = pyqtSignal(str)
    openInExplorerRequested = pyqtSignal(str)
    orderChanged = pyqtSignal(list)           # 全entry.key、新しい順序
    def set_entries(self, entries: tuple[FavoriteEntry, ...]) -> None: ...
    def set_current_key(self, key: str | None) -> None: ...
    def set_can_add(self, enabled: bool) -> None: ...
```

`FavoriteEntry`は型としてimport可能。GUIからFavoriteFolders操作、設定I/O、存在確認、クリップボード／Explorer操作を行わない。set_*は何回呼んでも上記要求シグナルをemitしない。モデルのUserRoleにkey、tooltipにpath、表示にdisplay_name。選択されたお気に入りと「現在開いている」状態を混同しない（アクセス失敗時はset_current_keyで表示を復元）。

UIManagerは`folder_navigation_tabs: QTabWidget`、`favorites_panel: FavoritesPanel`を公開。`folder_tree_view`と`file_system_model`の既存名を維持する。タブ0=お気に入り、1=フォルダ。currentChangedからナビゲーション・再読込・選択変更を呼ばない。フォルダ選択ボタンはタブ外の既存位置。

内部moveのみ、一回のdrop完了でorderChangedを一回emit。右クリック・drag開始/終了・行のプログラム選択でactivateRequestedを発火しない。左クリックrelease時はdragが成立していない場合のみactivate。double click専用の第二要求を接続しない。外部dropや複数選択移動を受け付けない。

SolはUI構築後に6シグナルを接続。操作結果ごとにentries/current_key/can_addを再反映し、save_failed時のD&D仮表示も戻す。登録・解除・並替・パスコピーは画像再読込を呼ばない。コピーは`QApplication.clipboard().setText(entry.path)`。Explorerはディレクトリの存在・アクセス確認後`os.startfile(entry.path)`、例外を通知。Explorerでcurrentを変えない。データ消失や実ファイル操作を解除へ混ぜない。

`UIManager.set_thumbnail_loading_ui_state(loading)`の既存メソッド名を維持し、全左overlayは使用しない。loading中は再帰、ソート、フィルタ、全選択/解除、移動/コピー/モードを無効化。フォルダ選択・ツリー・タブ・FavoritesPanelは有効。右画像一覧の既存表示を保ち、selection/modelの業務ロジックは変更しない。unlock時はcopy modeに応じた既存ファイル操作ボタン条件を復元。

## 3. 共通ナビゲーション（Sol所有）

```python
@dataclass(frozen=True)
class NavigationResult:
    status: str  # accepted / unchanged / invalid / unavailable / busy
    message: str

MainWindow.request_folder_navigation(
    path: str, *, source: str, force_reload: bool = False
) -> NavigationResult
# source: dialog / tree / favorite / refresh
```

この入口はMainWindowに残す既存フォルダ切替処理の集約であり、お気に入り専用の画像ローダーを作らない。

1. file_operationsの実行中、またはアプリ終了待機中ならbusy。存在しないkeyや無効pathはinvalid。例外をWidgetまで伝播させず通知する。
2. normalize→ディレクトリ検証→`os.scandir`でルート列挙権限確認（コンテキストを確実に閉じる）→既存QDirIteratorの規則でファイル配列を完成させる。not-found/PermissionError/OSErrorならunavailable。検証・列挙成功までcurrent、モデル、選択、copy順、sort、旧load世代を変更しない。配列完成直後にもルート存在を確認する。子ディレクトリの非可読領域を既存QDirIteratorが読み飛ばす挙動は今回一律エラー化しない。
3. 同一currentでforce_reload=Falseなら、アクセス検証後unchanged（再読込も初期ソート変更もなし）。同一パスでも消失/権限剥奪時はunavailableを通知。root検証後であり不要な全画像列挙は省略してよい。
4. source=dialogだけ既存の初期ソート方針と空フォルダ削除確認を適用。空フォルダ処理内の再読込は抑止し、その後の本要求で一度だけ列挙・commitする。削除確認cancelは削除だけ中止しフォルダ表示へ進む。favorite/tree/refreshは削除確認を追加しない。
5. 成功時のみ世代更新、current切替、選択とcopy順の解除、旧metadata/hidden pathsのクリア、placeholderを既存列挙順で生成。Qt選択変更シグナルによる削除済みitem参照を防ぎ、copy順をモデルclearより前に解除。favorite/dialogではツリールートを親へ同期、treeは既存ルート・展開状態を維持。表示同期は再読込を起こさない。
6. 読込controllerへ委譲。準備中にprocessEventsしない。favoriteとtreeのsortは現在値維持、dialogは既存設定値。フィルタ文字列、AND/OR、再帰設定、画像サイズは維持。選択を別フォルダへ引き継がない。

`select_folder`、`on_folder_tree_clicked`、お気に入りactivateはこの入口へ。`load_thumbnails_from_folder`と`update_folder_tree`は外部の旧呼出し・テストを考慮した薄いrefresh委譲にするか、呼出し元をすべてこの入口へ移す。UI同期専用`_sync_folder_tree`を分離し読込を含めない。サムネイルサイズ変更と空フォルダ削除後の更新も世代管理を通す。タブ切替には接続しない。

## 4. ローダー契約・競合（Sol所有）

```python
class ThumbnailLoaderThread(QThread):
    thumbnailLoaded = pyqtSignal(int, str, object, dict) # gen,path,QImage|None,metadata
    progressUpdated = pyqtSignal(int, int, int)         # gen,processed,total
    # 独自finishedは定義/emitしない。QThread標準finishedを使用
    def __init__(self, generation, file_paths, target_size, parent=None): ...
    def stop(self) -> None: ...                        # 冪等・非blocking

class ThumbnailController(QObject):
    thumbnailReady = pyqtSignal(int, str, object, dict)
    progressChanged = pyqtSignal(int, int, int)
    completed = pyqtSignal(int)                        # 最新世代のみ、実終了後
    idle = pyqtSignal()                                # 実workerも予約もない
    def replace(self, file_paths: list[str], target_size: int) -> int: ...
    def shutdown(self) -> None: ...                    # 新規不可、予約取消、stop
    def is_idle(self) -> bool: ...
```

controllerは単調増加generationを所有し、replaceは新世代を返す。replace呼出し中に上記GUI向けシグナルは同期emitしない（空配列も次のイベントで完了）。GUI側は戻り値をactive_generationとして保存した後に結果を受ける。QStandardItemはワーカーへ渡さずGUIでpath→item索引を持つ。QImageは結果後にワーカーから変更しない。QPixmapはGUIのみ。

- 実行中AでB要求：Aを旧世代にしstop要求。Bを予約、currentとplaceholderは検証済みBを表示。「前の読み込みの停止を待っています」を表示しloadingを維持。Aの実終了前に破棄・B開始しない。
- A停止待ちでC要求：Bの未開始予約をCへ置換。実workerはAだけ。Aの結果/進捗/完了が届いてもCへ反映しない。Aの標準finishedでAだけdeleteLaterし、最新Cを開始。タイムアウトを正常終了扱いにしない。
- 空フォルダも世代を持つ。旧Aが残る場合はA終了後に最新空世代を完了。一世代のcompletedは一度。現在世代の完了だけ既存フィルタ/ソート適用・loading解除・完了statusを行う。
- controllerで旧世代を除外し、MainWindowでも世代一致を最初に検査してからitem/metadata/statusへ触れる。旧finishedから`self.thumbnail_loader_thread`のような最新可変参照を消さない。threadごとの接続にオブジェクトと世代を固定する。
- stopは未着手futureのcancelを試行し、実行中画像I/Oの終了を待つ。強制terminateしない。終了待ちでGUIのwait(7000)等を呼ばない。画像個別失敗は既存のplaceholder/metadata扱いを維持して全体の完了を妨げない。
- closeEventはshutdownを一度呼び、実workerが残る場合event.ignoreで破棄を延期。idle後に再closeする。閉じる間は新規ナビゲーションを拒否。既存ファイル操作の終了処理は維持し、アプリ全体のファイル操作寿命改善へ範囲を拡大しない。

ファイル操作実行中のAPIナビゲーションはbusyとして現表示を維持する。GUIのmodalだけを保護条件にしない。現在世代の完了でファイル操作実行中にもかかわらずボタンを再有効化しないこと。

## 5. 非変更保証と検証境界

登録/解除/並替/タブ切替/右クリックメニュー表示でthumbnail load回数は0。1回の成功した異なるフォルダクリックは共通入口1回、ローダー開始は最大1回（開始前に新要求で置換された世代は0回）。失敗したパスは既存世代も取消しない。

保存直後再起動で情報と順序が復元。登録解除は実フォルダ・画像・ごみ箱操作0回。PNG/JPEG/WebP対象、読み込み順、再帰、フィルタ、ソート、通常/コピー選択、サイズ変更、画像ビューア、既存ファイル操作の仕様を維持する。
