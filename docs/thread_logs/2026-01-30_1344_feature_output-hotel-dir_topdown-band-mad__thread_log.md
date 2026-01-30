Proposed file path: docs/thread_logs/2026-01-30_1344_feature_output-hotel-dir_topdown-band-mad__thread_log.md

# Thread Log

## Meta
- Date: 2026-01-30
- Branch: feature/output_hotel_dir_reset
- Commit: 4243ccd
- Version: v0.6.12（ユーザー報告：リリース済）
- Release Zip: rm-booking-curve-lab_20260130_1628_samp_feature-output_hotel_dir_reset_4243ccd_full.zip
- Scope: output配下のホテル別ディレクトリ整理＋TopDownRevPAR帯をdelta+MAD+min/maxへ変更

## Context
- output直下に新旧ファイルが混在し、複数ホテル出力が混ざる課題を解消するため、ホテル別ディレクトリに整理する対応を進めた。
- TopDownRevPARのA/C帯が12→1付近で不自然に暴れる問題があり、帯の定義を「傾き（フロー）」へ寄せる方針で修正した。

## Done
- output生成物をホテル別ディレクトリへ整理（混在を抑制）
  - 変更ファイル：`src/gui_main.py`、`src/booking_curve/gui_backend.py`（ほか出力スクリプト群）
- TopDownRevPARの帯（A/C）をdeltaレンジで算出し、MAD外れ値除外（n>=5）＋min/max包絡で表示
  - abs guard（絶対値クランプ）を撤去
  - notesにMAD適用状況を追記
  - 変更ファイル：`src/booking_curve/gui_backend.py`
- TopDown画面内の「p10–p90」表記を実態（min/maxレンジ）に合わせて整理（文言・凡例・表ヘッダ）
  - 変更ファイル：`src/gui_main.py`
- Ruff警告（未使用ローカル変数等）の解消を確認
- マスタ設定の「出力先フォルダ」表示のホテル切替追従が動作OKであることを確認

## Decisions (non-spec)
- TopDown帯（A/C）は「比率/分位点」よりも「傾き（フロー）の実現レンジ」を優先して表現する（deltaレンジ採用）
- 年度サンプルが少ない前提のため、外れ値対策はMADで「明らかな外れ」だけ除外（n>=5で適用、n<5はスキップ）
- abs guardは副作用が大きいため撤去

## Pending / Next
- P1: 内部キー/列名の互換方針を決める（band_p10等を維持するか、band_low/highへ移行するか）
  - 完了条件：命名と互換方針が一貫し、最小差分で反映できる
- P2: ratio系の残存命名をdelta系へリネーム（機能変更なし）
  - 完了条件：挙動不変で可読性が改善

## Risks / Notes
- ロジックはp10–p90ではなくmin/maxレンジのため、UI/Docsで誤解表記が再発しないよう注意。
- サンプル不足（月ペアで参照年のデータが薄い）時のフォールバック動作は継続監視。

## References
- `AGENTS.md`：プロジェクト運用ルール
- `docs/spec_*.md`：仕様の唯一の正（TopDown帯仕様が未記載なら追記候補）
- `src/booking_curve/gui_backend.py`：TopDown帯の算出（delta+MAD+min/max）
- `src/gui_main.py`：TopDown画面の文言/凡例/診断テーブル表示
- `VERSION.txt`：ZIPメタ（branch/commit/生成時刻）
