python run\_build\_lt\_csv.py（LTデータ作成）

python build\_calendar\_features.py（カレンダー作成）

python run\_plot\_monthly\_curve.py



FC系

python run\_forecast\_from\_avg.py

python run\_forecast\_from\_recent90.py

python run\_forecast\_from\_recent90\_weighted.py

python run\_forecast\_batch.py（3ポイントFC一括作成）



評価系

python build\_daily\_errors.py（日別誤差一括作成）

python run\_evaluate\_forecasts.py（誤差評価作成）

python run\_segment\_error\_summary.py（タイプ別誤差作成）

python run\_full\_evaluation.py



python gui\_main.py





cd C:\\Users\\中村圭一\\projects\\rm-booking-curve-lab\\src

コマンドプロンプト：pyinstaller --name BookingCurveLab --windowed --noconfirm gui\_main.py

VSCode：pyinstaller --noconfirm BookingCurveLab.spec





\# いじる予定のファイルだけ、修正＋フォーマット

ruff check booking\_curve/gui\_backend.py --fix

ruff format booking\_curve/gui\_backend.py





\# venv 有効化後にまとめて

python -m pip install \\

  pandas \\

  numpy \\

  matplotlib \\

  openpyxl \\

  jpholiday \\

  ruff



python -m pip install tkcalendar





スレッド引き継ぎ用（最小）：

python make\_release\_zip.py --profile handover



出力サンプルも入れる：

python make\_release\_zip.py --with-output-samples



広め（従来に近い）：

python make\_release\_zip.py --profile full

python make\_release\_zip.py --profile full --with-output-samples









