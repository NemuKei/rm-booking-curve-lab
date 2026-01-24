Proposed file path: docs/handovers/2026-01-24_1940_feature_pace14_weekshape_min_events_gate__handover.md

---

## 1. スレッド移行宣言（新スレッドに貼る前提の文面）
- このスレッドは、`pace14_weekshape_flow` の **週境界トグル（iso/sun）検証**と、**weekshape が常時無効化される原因（gating）特定**を行った作業ログです。
- 次スレッドでは、**WEEKSHAPE_MIN_EVENTS のデフォルト修正（P0）** と **spec_models 反映（P0）** を進めます。

---

## 2. 現在地サマリ（何ができて、何が未完か：箇条書き）

### できたこと
- `tools/diag_weekshape_factors.py` により、週境界トグル（iso/sun）が **week_id へは反映されている**一方で、weekshape係数が **gatingにより全て 1.0 になっていた**ことを確認した。
- gating の根本原因として、`compute_weekshape_flow_factors` が `(week_id, group)` 単位集計であるため **n_events が最大7（group分割でさらに小）**になり得るのに、`WEEKSHAPE_MIN_EVENTS=10` が設定されており **到達不能条件**になっていたことを確認した。
- 一時的に `WEEKSHAPE_MIN_EVENTS=2` とした診断で、係数が `0.85–1.15` の範囲で発生し、iso/sun で **forecast差分が出る**ことを確認した（`different_days=4/28`, `delta_sum≈5.2`）。

  - 主要関連ファイル：`src/booking_curve/forecast_simple.py`, `docs/spec_models.md`, `tools/diag_weekshape_factors.py`

### 未完（残課題）
- **P0**：`src/booking_curve/forecast_simple.py` の `WEEKSHAPE_MIN_EVENTS` デフォルトを **到達可能な値（<=7）**へ修正（候補：2 or 3）。
- **P0**：`docs/spec_models.md` の既定値表記（デフォルト10）を修正し、到達不能になり得る旨を補足。
- **P1**：`tools/diag_weekshape_factors.py` の Ruff 警告（E402/E501）を解消、または lint 対象外扱いの方針整理。
- **P?（既存引継の残課題）**：`segment_adjustment` 実行時クラッシュ修正、`compute_market_pace_7d` 定義移植（別スレッドP0として残っている）。

---

## 3. 決定事項（仕様として合意したこと）
- weekshape_flow の gating は「安全ガード」だが、現行の `WEEKSHAPE_MIN_EVENTS=10` は `(week_id, group)` 集計の性質上 **到達不能**になり得るため、デフォルトは **到達可能な値（<=7）**へ変更する。
- 週境界トグル（iso/sun）の挙動自体は、week_id の切り替えとしては有効である（差が出なかった主因は gating 側）。

※注意：仕様の唯一の正は `docs/spec_*.md` と `AGENTS.md`。ここは「合意のログ」。

---

## 4. 未解決の課題・バグ（再現条件／影響範囲／暫定回避策）

### 課題1：weekshape_flow が実質OFF（factor=1.0固定）になり得る
- 再現条件：`WEEKSHAPE_MIN_EVENTS=10` のまま `pace14_weekshape_flow` を実行（(week_id,group) 集計で n_events が閾値に到達しない）。
- 影響範囲：週境界（iso/sun）を変えても予測が一致し、「効いていない」ように見える。weekshape_flow の価値が出ない。
- 暫定回避策：一時的に `WEEKSHAPE_MIN_EVENTS` を 2〜3 に下げて検証する（確定は次スレで実装反映）。
- 備考：`tools/diag_weekshape_factors.py` の gated_true / factor!=1 / stats により検出可能。

### 課題2：tools スクリプトで Ruff 警告（E402/E501）
- 再現条件：`tools/diag_weekshape_factors.py` を lint すると E402（import順）と E501（行長）警告。
- 影響範囲：品質ゲートが lint を含む運用の場合、CI/ローカルでノイズになる。
- 暫定回避策：`# noqa: E402` 付与や行分割で抑制、または tools 配下を lint 対象外にする（方針決めが必要）。
- 備考：実行自体には影響なし。

---

## 5. 次にやる作業（優先度P0/P1/P2、各タスクに“完了条件”）

### P0（最優先）
1. `WEEKSHAPE_MIN_EVENTS` のデフォルトを修正（候補：2 or 3）
   - 完了条件：デフォルト設定のまま `tools/diag_weekshape_factors.py` で `factor!=1 > 0` が観測され、iso/sun で差分が出るケースが存在する（少なくとも gating 全件ではない）。

2. `docs/spec_models.md` の既定値・説明を実装に合わせて更新
   - 完了条件：spec上のデフォルト値が実装と一致し、到達不能条件の注意が明記される。

### P1（次）
3. `tools/diag_weekshape_factors.py` の Ruff 警告を解消（E402/E501）
   - 完了条件：Ruff 警告が消える、または lint 対象外にする運用が合意される。

### P2（余裕があれば）
4. 週境界（iso/sun）の採用方針を仕様として確定
   - 完了条件：specに採用境界が明文化され、モデルが一貫した境界で動く。

---

## 6. 参照すべきファイル一覧（パス、関連理由つき）
- `docs/spec_models.md`：weekshape_flow の仕様（既定値・gating条件の表記更新箇所）
- `AGENTS.md`：運用・仕様の正
- `src/booking_curve/forecast_simple.py`：`WEEKSHAPE_MIN_EVENTS` 定義および gating 実装
- `tools/diag_weekshape_factors.py`：iso/sun 差分と gating 状態の診断（今回の再現・検証スクリプト）
- `docs/handovers/2026-01-24_0942_feature_pace14_market_power_and_clip__handover.md`：既存の残課題（segment_adjustment, market_pace移植）を含む引継
- `docs/thread_logs/2026-01-24_0942_feature_pace14_market_power_and_clip__thread_log.md`：当日AM時点の実装ログ
- `docs/decision_log.md`：横断決定の追記先

---

## 7. 実行コマンド／手順（分かっている範囲で）
- 起動：`python src/gui_main.py`
- 診断：`python tools/diag_weekshape_factors.py`
- source_zip（引継書作成の材料ZIP）：`rm-booking-curve-lab_20260124_1935_samp_feature-pace14_market_power_and_clip_fcfb300_full.zip`
- anchor_zip（次スレで添付するアンカーZIP）：TBD（クローズ時に make_release_zip.py で作成し、次スレ冒頭で添付する）

---

## 8. 注意点（データ、同名ファイル、前提、トークン等の運用ルール）
- 仕様の唯一の正：`docs/spec_*.md` と `AGENTS.md`
- 共有物の唯一の正：make_release_zip.py で作成した最新ZIP
- 推測禁止：不足は不足として明記し、質問は最大5つまで
- 個人情報・企業機密を含むデータ/ログは同梱しない（ダミーのみ）

---

## 9. 次スレッドで最初に確認すべきチェックリスト（5項目まで）
1. 最新ZIPが添付されている（ZIP名・branch・commit一致）
2. 直近 handover（本ファイル＋2026-01-24_0942）を読んだ
3. `forecast_simple.py` の `WEEKSHAPE_MIN_EVENTS` と `spec_models.md` の既定値が一致している
4. `tools/diag_weekshape_factors.py` で gating が全件にならないことを確認した
5. Decision Log 末尾と矛盾しない（必要なら追記差分を作成）

---

## 10. 質問（最大5つ・必要なもののみ）
1. `WEEKSHAPE_MIN_EVENTS` のデフォルトは **2** で確定しますか？（3にする方針ならそれに合わせます）
回答：一旦2で進める
2. `tools/diag_weekshape_factors.py` の Ruff 警告は「解消する」方針で良いですか？（それとも tools 配下を lint 対象外にしますか？）
回答：解消します
