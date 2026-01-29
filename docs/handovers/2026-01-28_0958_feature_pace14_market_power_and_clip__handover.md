Proposed file path: docs/handovers/2026-01-28_0958_feature_pace14_market_power_and_clip__handover.md

---

## 1. スレッド移行宣言（新スレッドに貼る前提の文面）
- このスレッドは、pace14_market の市場補正（power+decay）に対して「clip張り付き」を減らすための調整（decay_k探索）と、説明可能な診断ツール整備を行った作業ログです。
- 次スレッドでは、(1) docs/spec_models への反映（Docs Gate判定→更新案作成）(2) 固有名排除方針の実装（HOTEL_TAG撤去・hotel_tag必須化）を進めます。

---

## 2. 現在地サマリ（何ができて、何が未完か：箇条書き）

### できたこと
- pace14_market の市場補正で、`MARKET_PACE_DECAY_K=0.25` を暫定採用（clip張り付きが減り、ASOF差/ホテル差でも挙動が自然なことを確認）
- market帯の診断用 detail（pf_info）に説明用の列を追加（`current_oh/base_now/base_final/base_delta/final_forecast`）
- 恒久の診断ツール `tools/diag_market_effect.py` を追加（ASOF/ホテル/target/capacity 指定で、market_factor と delta_market のTop10を再現可能）
  - 主要変更ファイル：`src/booking_curve/forecast_simple.py`, `tools/diag_market_effect.py`

### 未完（残課題）
- docs 未反映：pace14_market のデフォルト（decay_k/clip）と診断ツールの位置づけを `docs/spec_models.md` 等へ反映
- 固有名排除：コード上の `HOTEL_TAG="daikokucho"` 等の実名デフォルト撤去、hotel_tag未指定時の挙動統一（例外 or 中立スキップ）

---

## 3. 決定事項（仕様として合意したこと）
- pace14_market の `MARKET_PACE_DECAY_K` は暫定的に 0.25 を採用し、`MARKET_PACE_CLIP=(0.85–1.25)` と組み合わせて運用する（追加ASOF・kansaiでも確認済）
- market影響の説明可能性を優先し、detailに `base_delta/current_oh` 等の列を露出し、診断ツールでTop10を見られるようにする
- ローカル設定ファイルを除き、ホテル固有名（daikokucho/kansai 等）の実名はコード上から排除する方向で進める

※注意：仕様の唯一の正は `docs/spec_*.md` と `AGENTS.md`。ここは「合意のログ」。

---

## 4. 未解決の課題・バグ（再現条件／影響範囲／暫定回避策）

### 課題1：LT=15付近で raw が高いと上限clipに当たりやすい（構造）
- 再現条件：market_pace_7d が大きく、`market_pace_eff` が raw_clip上限付近に張り付くケース（LT=15〜16）
- 影響範囲：market帯の一部日付が上限で潰れる（ただし decay_k=0.25 で頻度は軽減）
- 暫定回避策：現状は clip を安全弁として許容。必要になった時点で「βのLTオフセット」または raw_clip上限見直しを検討
- 備考：本質的には設計調整（仕様影響）になり得る

### 課題2：hotel_tag 未指定時の実名デフォルトが事故要因
- 再現条件：forecast関数を単体利用し hotel_tag を渡し忘れる
- 影響範囲：別ホテルに daikokucho の補正（calendar_features 等）が誤適用され得る
- 暫定回避策：運用で必ず hotel_tag を渡す／次スレでコード側を必須化

---

## 5. 次にやる作業（優先度P0/P1/P2、各タスクに“完了条件”）

### P0（最優先）
1. docs反映（Docs Gate判定→Yesなら更新案作成）
   - 完了条件：`docs/spec_models.md` に pace14_market のデフォルト（decay_k=0.25、clip=0.85–1.25）と診断ツール参照が追記され、差分パッチ化できている

2. 固有名排除の第一弾：`HOTEL_TAG="daikokucho"` 撤去＋hotel_tag未指定の挙動統一
   - 完了条件：実名デフォルトがコードから消え、未指定時は「例外」または「補正スキップ」に統一され、既存実行が壊れない

### P1（次）
3. 追加検証：別target_monthや別ASOF複数点で `diag_market_effect` を回して傾向を確認
   - 完了条件：代表ケースのログ（market_pace_7d/clip_rate/delta_market）が保存され、0.25採用の妥当性が説明できる

### P2（余裕があれば）
4. 診断ツールの取り回し改善（`docs/command_reference.md` 追記、出力整形）
   - 完了条件：実行例が docs に載り、手元の再現が迷わない

---

## 6. 参照すべきファイル一覧（パス、関連理由つき）
- `docs/spec_models.md`：pace14_market / 市場補正の仕様反映先
- `docs/spec_evaluation.md`：診断列・検証観点の導線候補
- `AGENTS.md`：運用ルール（唯一の正、Docs Gate等）
- `src/booking_curve/forecast_simple.py`：decay_k/clip と pf_info 診断列の実装
- `tools/diag_market_effect.py`：今回追加した恒久診断ツール
- `docs/decision_log.md`：今回の決定を追記する導線

---

## 7. 実行コマンド／手順（分かっている範囲で）
- 起動：`python src/gui_main.py`
- バッチ：`python src/run_forecast_batch.py ...`
- 診断（market effect）：`python tools/diag_market_effect.py --hotel <tag> --asof <YYYY-MM-DD> --target <YYYYMM> --capacity <float>`
- source_zip（引継書作成の材料ZIP）：`rm-booking-curve-lab_20260128_0238_samp_feature-pace14_market_power_and_clip_feb4668_full.zip`
- anchor_zip（次スレで添付するアンカーZIP）：TBD（クローズ時に make_release_zip.py で作成し、次スレ冒頭で添付する）

---

## 8. 注意点（データ、同名ファイル、前提、トークン等の運用ルール）
- 仕様の唯一の正：`docs/spec_*.md` と `AGENTS.md`
- 共有物の唯一の正：make_release_zip.py で作成した最新ZIP
- 推測禁止：不足は不足として明記し、質問は最大5つまで
- 個人情報・企業機密を含むデータ/ログは同梱しない（ダミーのみ）
- Docs Gate が Yes の場合、docs更新は docs/templates/prompt_docs_update.md を唯一の手順として行う（独自手順禁止）

---

## 9. 次スレッドで最初に確認すべきチェックリスト（5項目まで）
1. 最新ZIPが添付されている（ZIP名・branch・commit一致）
2. この handover を読んだ（引き継ぎ正本）
3. `tools/diag_market_effect.py` が動作し、detail列（base_delta等）が出る
4. `docs/decision_log.md` 末尾10〜20件と矛盾しない
5. Docs Gate 判定を実施し、Yes の場合は docs/templates/prompt_docs_update.md に従って更新案を作成

---

## 10. 質問（最大5つ・必要なもののみ）
1. hotel_tag 未指定時の挙動は「例外で落とす」/「補正スキップ（中立）」のどちらで統一しますか？
2. 固有名排除の表示名（例：`hotel_001`）はログ/GUIにも適用しますか？（ローカル設定のみでマッピング想定）
3. pace14_market の raw_clip 上限（現状 2.2）の見直しは今回スコープ外でOKですか？
