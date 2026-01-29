Proposed file path: docs/thread_logs/2026-01-29_2140_feature_pace14_market_power_and_clip__thread_log.md

# Thread Log

## Meta
- Date: 2026-01-29
- Branch: feature/pace14_market_power_and_clip
- Commit: f4c5332
- Version: UNKNOWN
- Release Zip: rm-booking-curve-lab_20260129_2130_samp_feature-pace14_market_power_and_clip_f4c5332_full.zip
- Scope: GUI運用改善（LT_DATAレンジ/欠損チェック非同期/CSV導線）＋月次カーブ補完バグ修正＋docs差分反映

## Context
- 既存の「LT_DATA(4ヶ月)」は固定月レンジ運用だったが、当日起点+120日先までの取り込み要件に対して安全側が欲しかった。
- 欠損チェック（運用）ボタン押下時の処理が重く、UIが固まる体験が課題だった。
- 日別フォーキャストCSVは出力後にファイルを開く導線が弱く、運用手間があった。
- 月次カーブで ACT 行があるのに LT0 が欠損のケースで、線形補完が効かず補完グラフが出ない問題があった。

## Done
- GUI「LT_DATA(4ヶ月)」の対象月を、latest_asof起点で「+120日先がかかる月まで（前月含む）＋最低翌4ヶ月保証」へ変更
  - `src/gui_main.py`
- 欠損チェック（運用）の非同期化（フリーズ回避、多重実行防止、完了後の復帰処理）
  - `src/gui_main.py`
- 日別フォーキャストCSV出力後にCSVを自動で開く導線を追加
  - `src/gui_main.py`
- 月次カーブ：ACTあり／LT0欠損で線形補完が効かない問題を修正（ビュー上でLT0へACTコピー→補完）
  - `src/booking_curve/gui_backend.py`
- docs差分更新（仕様・運用記述・Decision Logの方針更新）
  - `docs/spec_overview.md`, `docs/spec_data_layer.md`, `docs/BookingCurveLab_README.txt`, `docs/decision_log.md`

## Decisions (non-spec)
- raw_inventory の重複キーは STOP せず後勝ちで継続（tie-break: mtime -> path）
  - Decision Log: `D-20260129-XXX`
- GUIの「LT_DATA(4ヶ月)」は +120日先に加えて翌4ヶ月先まで最低保証
  - Decision Log: `D-20260129-XXX`
- 月次カーブの線形補完：`LT0欠損 & ACTあり` の場合のみビュー上で `LT0 <- ACT` を行い端点確保して補完する
  - spec: `docs/spec_overview.md`

## Pending / Next
- P0: main へマージして GitHub Release を作る
  - 完了条件：main に変更が入り、Release本文が作成され、make_release_zip.py で作ったZIPが共有物として確定する
- P1: Decision Log の `D-20260129-XXX` を採番して確定
  - 完了条件：採番済みIDで docs/decision_log.md が更新され、ZIPに含まれる

## Risks / Notes
- Decision Log は仕様の唯一の正ではないが、重複方針（STOP vs 後勝ち）は運用事故に直結するため、spec_data_layer と Decision Log の両方で矛盾がない状態を維持する。

## References
- `AGENTS.md`（AI運用ルール）
- `docs/START_HERE.md`（唯一の正とClose Gate）
- `docs/spec_overview.md`（欠損補完の扱い）
- `docs/spec_data_layer.md`（LT_DATA / raw_inventory の仕様）
- `src/gui_main.py`（LT_DATA/欠損チェック/CSV出力導線）
- `src/booking_curve/gui_backend.py`（月次カーブ補完）
- `docs/decision_log.md`（方針ログ）
- `make_release_zip.py`（リリースZIP作成）
