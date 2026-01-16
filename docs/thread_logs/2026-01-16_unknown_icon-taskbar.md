# ファイル名案: docs/thread_logs/2026-01-16_unknown_icon-taskbar.md

# Thread Log: EXEアイコン設定とタスクバー反映トラブルシュート

## Meta

* Date: 2026-01-16（推定：会話ログ中のZIPタイムスタンプが2026-01-15で、直後の継続スレッドのため）
* Branch: 不明（未提示）
* Commit: d7886dd（ZIP名より推定）
* Zip: rm-booking-curve-lab_20260115_1743_samp_main_d7886dd_full.zip（他：d46cc63 / d7886dd 等）
* Scope: PyInstallerのアイコン設定（EXE/ICO）、Tkinterのウィンドウアイコン（タイトルバー）設定、タスクバーアイコン未反映の原因切り分け、運用ドキュメント（command_reference）方針整理

## Done（実装・変更）

* アイコン案を作成し、ネオン版を採用（PNG/ICO生成）
* ネオン版ICOの再作成（ユーザー指定デザインを基にICO化）
* Tkinter側で GUI上部（タイトルバー左上）にアイコンを表示するための実装方針を整理
* `gui_main.py` に以下の追加方針を提示

  * `sys._MEIPASS` 対応のリソースパス解決（frozen/通常実行両対応）
  * `iconbitmap()` によるウィンドウアイコン設定
  * AppUserModelID（SetCurrentProcessExplicitAppUserModelID）によるタスクバー安定化の試行
* PyInstaller `.spec` 実行時の `__file__` 未定義エラーを特定し、`SPECPATH`/`os.getcwd()` を使う修正方針を提示
* venvで `python -m PyInstaller` を使う運用に切り替え、PyInstallerがvenv側で動いていることを確認
* `.spec` をGit管理に含めるべき（再現性の観点）という方針を整理（`.gitignore` の例外案も提示）
* `docs/command_reference.md` を作る方針と叩き台を提示（腐りにくい範囲に限定）
* タスクバーアイコン未反映の継続を確認し、Windows側キャッシュ/ピン留め/ショートカット・AppID挙動を中心に切り分けを進行
* `assets/icon/BookingCurveLab.ico` の内容を確認し、ICO内のサイズが正方形でない（256×171等）点を問題として特定
* 正方形マルチサイズICO（16/24/32/48/64/128/256内包）の作り直しを実施・差し替え方針を提示（ただしタスクバーは依然「羽」のまま）

## Decisions（決定）

* Decision:

  * アイコン素材の唯一の正は `assets/icon/BookingCurveLab.ico`（リポジトリ直下に1つ、重複配置しない）
  * `.spec` は再現性のためGit管理に入れる（ignore解除/例外指定）
  * Tkinterのタイトルバーアイコンは `iconbitmap()` で設定し、PyInstaller時は `_MEIPASS` を使って参照する
  * タスクバー未反映が続く場合の最終手段として、WinAPI（WM_SETICONでICON_BIG/ICON_SMALL）強制を検討
* Why:

  * アイコン素材を複数箇所に置くと差し替え漏れが起き、再現性が壊れるため
  * `.spec` を無視するとビルド設定（icon/datas/hiddenimports等）が共有できず、配布物が環境依存でブレるため
  * TkinterはEXE埋め込みアイコンとは別にウィンドウアイコン設定が必要で、frozen環境では参照パスの解決が必須なため
  * WindowsのタスクバーはキャッシュやAppID/ショートカットの影響を受けやすく、Tk設定だけで反映しないケースがあるため

## Docs impact（反映先の候補）

* spec_overview:

  * なし（仕様変更ではなくビルド/見た目の運用）
* spec_data_layer:

  * なし
* spec_models:

  * なし
* spec_evaluation:

  * なし
* BookingCurveLab_README:

  * なし（ただし運用手順としては command_reference で管理するのが適切）

### Docs impact 判定（必須/不要 + Status）

* 必須:

  * 項目: なし

    * 理由: 仕様（spec_*）には影響しないため
    * Status: 該当なし
    * 反映先: 該当なし
* docs不要:

  * 項目: アイコン設定（PyInstaller icon / Tk iconbitmap / taskbar対応）

    * 理由: アプリ仕様ではなくビルド・配布とUI外観の実装/運用メモ領域のため（Thread Log/command_referenceで十分）
  * 項目: `.spec` のGit管理方針

    * 理由: 仕様ではなく開発運用ルール（必要ならAGENTS/開発ガイドに寄せるが、必須ではない）

## Known issues / Open

* タスクバーアイコンが「羽（汎用）」のまま変わらない（タイトルバー左上は反映済み）
* AppUserModelID有無、ショートカット/ピン留め、Windowsキャッシュの影響が残る可能性
* ICOを正方形マルチサイズにしても改善しなかったため、WM_SETICON（ICON_BIG/ICON_SMALL）強制が次候補

## Next

* P0:

  * `src/gui_main.py` に Windows限定の WM_SETICON（SendMessageW）で ICON_BIG/ICON_SMALL を強制セットする実装を入れて再検証
  * 反映確認手順を固定（Explorer再起動・ピン留め無し/有りの差分確認・python実行/EXE実行の比較）
* P1:

  * `docs/command_reference.md` を正式に追加し、ビルド/リリース手順（specビルド、make_release_zip、必要なdatas同梱）を最小限で確定
  * `.gitignore` で `BookingCurveLab.spec` の管理方針を確定（例外 `!BookingCurveLab.spec`）
