Proposed file path: docs/thread_logs/2026-01-25_1543_feature_pace14_market_power_and_clip_housekeeping__thread_log.md

# Thread Log

## Meta
- Date: 2026-01-25
- Branch: feature/pace14_market_power_and_clip
- Commit: f61a896
- Version: v0.6.10
- Release Zip: rm-booking-curve-lab_20260125_1257_samp_feature-pace14_market_power_and_clip_f61a896_full.zip
- Scope: pace14_market_power_and_clip の運用整備（LF固定・ruff導入・diag出力改善）

## Context
- スレッド移行後、意図した実装になっているか（weekshape gating / market補正 / 環境差）を確認しつつ、CRLF→LF整流と ruff の導入不整合（保存時自動適用が効かない）を解消した。
- `tools/diag_weekshape_factors.py` の出力で `gated_true=-1` 等の混乱があったため、診断を実数表示に修正した。
- 次の開発（加算/ハイブリッド検討、評価ログ整備）に向け、運用の足場を固めた。

## Done
- LFを正とするための整流を実施し、`.gitattributes` を整備して line ending を固定した。
  - 変更ファイル：`.gitattributes`, `patches/p0_fix_21ac434_lineendings.patch`
- ruff を `pyproject.toml` の dev extras（`.[dev]`）として固定し、導入手順を `docs/command_reference.md` に追記した。
  - 変更ファイル：`pyproject.toml`, `docs/command_reference.md`
- `tools/diag_weekshape_factors.py` の診断出力を、`gated_true` / `factor!=1` が実数で出るよう修正した。
  - 変更ファイル：`tools/diag_weekshape_factors.py`
- VSCode保存時ruffが効かない原因（ruff未導入）を切り分け、`pip install -e ".[dev]"` 運用で解消した。

## Decisions (non-spec)
- capacity は「月の販売室数（固定室数）」を採用する。
- “ベースが小さい”の定義・閾値は、LT0–14（pace14帯）と LT15–45（weekshape帯）で別々に持つ方針で進める。
- ruff は pyproject の dev extras（`.[dev]`）で導入・固定し、個別環境の手動導入に依存しない運用とする。
  - Decision Log 追記が必要（D-20260125-XXX）。

## Pending / Next
### P0
- market補正（power＋clip）が期待どおり効いているかの評価ログを1本残す
  - 完了条件：条件（ASOF/TARGET/HOTEL/主要パラメータ）込みで再現でき、差分の要点が記録されている。
- “ベース小”救済（加算/ハイブリッド）導入の検証設計（daikokucho/kansai、LT帯別）
  - 完了条件：LT0–14 / 15–45 それぞれで `residual_rate` 分布（P90/P95/P97.5）を出し、加算上限候補を絞れる。

### P1
- 学習データがある場合は最適パラメータを学習し、ない場合は既定値を使う運用の設計（保存先・優先順位・再現性）
  - 完了条件：保存先とロード順が明文化される（ファイル増加の可否含む）。

## Risks / Notes
- “倍率型”は `base_delta` が小さい帯で効きが弱くなりやすい（構造的）。加算/ハイブリッドの導入は、cap正規化した分布から上限を決めて暴発を避ける必要がある。
- 端末差（ローカルタスクでの新規ファイル未追跡等）を避けるため、作業後の `git status`（Untracked確認）の運用を固定する。

## References
- `AGENTS.md`：仕様/運用の唯一の正
- `docs/spec_models.md`：pace14_market / pace14_weekshape_flow の仕様導線（今後の“ベース小”設計反映先）
- `src/booking_curve/forecast_simple.py`：pace14 / weekshape 実装本体
- `tools/diag_weekshape_factors.py`：weekshape factor 診断（実数出力）
- `pyproject.toml`：dev extras（ruff）
- `docs/command_reference.md`：導入/実行コマンド
- `.gitattributes`：LF固定ルール
- `docs/decision_log.md`：横断決定の追記先