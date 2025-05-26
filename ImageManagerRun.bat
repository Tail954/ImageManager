@echo off
REM 仮想環境のパスを設定
SET VENV_PATH=venv

REM 仮想環境が存在するか確認
IF NOT EXIST %VENV_PATH% (
    echo 仮想環境が見つかりません。仮想環境を作成します...
    python -m venv %VENV_PATH%
)

REM 仮想環境をアクティブ化
CALL %VENV_PATH%\Scripts\activate

REM requirements.txtパッケージをインストール
IF EXIST requirements.txt (
    echo パッケージをインストールしています...
    pip install -r requirements.txt
)

REM ImageMover.pyを実行
echo ImageMover.pyを実行しています...
python main.py

REM 仮想環境を非アクティブ化
deactivate

echo 処理が完了しました。
pause
