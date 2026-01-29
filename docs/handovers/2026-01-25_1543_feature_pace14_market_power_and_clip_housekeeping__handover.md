Proposed file path: docs/handovers/2026-01-25_1543_feature_pace14_market_power_and_clip_housekeeping__handover.md

---

## 1. スレッド移行宣言（新スレッドに貼る前提の文面）
- このスレッドは、`feature/pace14_market_power_and_clip` で **CRLF→LF整流 / ruff導入の開発依存固定 / diag出力の改善**を行い、運用面の詰まり（VSCode保存時ruff等）を解消した作業ログです。
- 次スレッドでは、**market補正（power＋clip）の評価ログ作成（P0）** と、**“ベース小”時の加算/ハイブリッド方針の検証設計（P0）** を進めます。

---

## 2. 現在地サマリ（何ができて、何が未完か：箇条書き）

### できたこと
- CRLF→LF の一括整流（renormalize）を実施し、`.gitattributes` で **LFを正**として固定した。
  - 主要変更ファイル：`.gitattributes`, `patches/p0_fix_21ac434_lineendings.patch`
- ruff を「環境依存のインストール」ではなく、`pyproject.toml` の **dev extras（`.[dev]`）**として固定した。
  - 主要変更ファイル：`pyproject.toml`, `docs/command_reference.md`
- `tools/diag_weekshape_factors.py` の診断出力で、`gated_true` / `factor!=1` を **実数で出る**ように整備（-1固定の混乱を解消）。
  - 主要変更ファイル：`tools/diag_weekshape_factors.py`
- VSCode 側の「保存時ruff自動適用」が効かない問題について、原因が **ruff未導入**であることを特定し、`pip install -e ".[dev]"` 運用へ誘導して解消。

### 未完（残課題）
- **P0**：market補正（power＋clip）が「期待どおりに効いているか」の **評価ログを1本**残す（再現性のある出力）。
- **P0**：“ベースが小さい”ケースの扱い（加算/ハイブリッド）について、**LT帯別（0–14 / 15–45）に分布を見て上限を決める**検証設計を固める。
- **P1**：pace14（0–14）側も含めて、“ベース小”救済の設計方針（倍率＋加算の境界条件）を spec に落とす準備。
- **P1**：学習データがある場合はパラメータ学習、ない場合はハードコード既定値、の運用設計（保存先/優先順位/再現性）を決める。

---

## 3. 決定事項（仕様として合意したこと）
- capacity の定義は **「月の販売室数（固定室数）」**を採用する（休館/工事反映の“有効キャパ”ではなく）。
- “ベースが小さい”の定義・閾値は、**pace14帯（0–14）と weekshape帯（15–45）で別々に持つ**方針で進める。

※注意：仕様の唯一の正は `docs/spec_*.md` と `AGENTS.md`。ここは「合意のログ」。

---

## 4. 未解決の課題・バグ（再現条件／影響範囲／暫定回避策）

### 課題1：market補正（power＋clip）が期待どおり効いているかの“証跡”が薄い
- 再現条件：`pace14_market` を使っても、効き方（power/beta/clip）が意図どおりかをログで説明できない。
- 影響範囲：将来の評価改善・モデル比較時に、仕様と挙動の説明責任が弱くなる。
- 暫定回避策：現状は `docs/decision_log.md` と実装で整合は取れているが、評価ログが不足。
- 備考：ログ1本で十分（入力条件・差分・要点）。

### 課題2：“ベース小”時に倍率補正が効かない（構造的制約）
- 再現条件：baseline の残りpickup（`base_delta`）がほぼ0のケースで、倍率（pfやweekshape factor）を掛けても増分が小さい。
- 影響範囲：小キャパや特定帯で「動きはあるのに補正が効かない」状況が発生し得る。
- 暫定回避策：まずは rate（cap正規化）で分布を見て、加算/ハイブリッド導入の要否と上限を決める。
- 備考：LT帯別に設計（0–14 / 15–45）。

---

## 5. 次にやる作業（優先度P0/P1/P2、各タスクに“完了条件”）

### P0（最優先）
1. market補正（power＋clip）の評価ログを1本残す
   - 完了条件：同一条件で「market補正あり/なし」の差分が、ログ（またはmd）で再現可能に説明されている（入力ASOF/TARGET/HOTEL/主要パラメータ/差分指標を含む）。

2. “ベース小”救済（加算/ハイブリッド）導入に向けた検証設計（daikokucho/kansai）
   - 完了条件：LT0–14 と LT15–45 それぞれで `residual_rate` 分布（P90/P95/P97.5）を出し、加算上限（cap比）候補を3点に絞れる。

### P1（次）
3. “学習データあり→学習パラメータ / なし→既定値”の読み込み優先順位と保存先を決める
   - 完了条件：保存先（既存ファイルに入れる/新規ファイルにする/出力物として扱う）と、ロード順（学習→既定）が明文化される。

4. 上記を spec_models に落とす準備（Docs Gate 判定のうえ）
   - 完了条件：spec反映の追記案（該当セクションと文面）が用意できる。

### P2（余裕があれば）
5. 加算/ハイブリッド導入後の評価観点（MAE/Biasだけでなく、帯別/曜日別など）を拡張
   - 完了条件：評価ログのテンプレ（項目）を決められる。

---

## 6. 参照すべきファイル一覧（パス、関連理由つき）
- `docs/spec_models.md`：pace14_market / pace14_weekshape_flow の仕様定義と、今後の “ベース小”設計反映先
- `docs/spec_overview.md`：モデル/運用方針の上位整理（必要なら導線）
- `docs/spec_evaluation.md`：評価ログ拡張時の反映先候補
- `AGENTS.md`：仕様の唯一の正と運用ルール
- `src/booking_curve/forecast_simple.py`：pace14 / weekshape の補正実装本体
- `tools/diag_weekshape_factors.py`：weekshape factor の診断（実数出力）
- `pyproject.toml`：dev extras（ruff）固定
- `docs/command_reference.md`：導入/実行コマンドの正
- `patches/p0_fix_21ac434_lineendings.patch`：LF整流のパッチ記録
- `docs/decision_log.md`：横断決定の追記先

---

## 7. 実行コマンド／手順（分かっている範囲で）
- venv作成/有効化：`python -m venv .venv` → `.\.venv\Scripts\activate`
- 依存導入（推奨）：`pip install -e ".[dev]"`
- GUI：`python src/gui_main.py`
- 診断：`python tools/diag_weekshape_factors.py`
- Lint/Format：`ruff check .` / `ruff format .`
- source_zip（引継書作成の材料ZIP）：`rm-booking-curve-lab_20260125_1257_samp_feature-pace14_market_power_and_clip_f61a896_full.zip`
- anchor_zip（次スレで添付するアンカーZIP）：TBD（クローズ時に make_release_zip.py で作成し、次スレ冒頭で添付する）

---

## 8. 注意点（データ、同名ファイル、前提、トークン等の運用ルール）
- 仕様の唯一の正：`docs/spec_*.md` と `AGENTS.md`
- 共有物の唯一の正：make_release_zip.py で作成した最新ZIP
- 推測禁止：不足は不足として明記し、質問は最大5つまで
- 個人情報・企業機密を含むデータ/ログは同梱しない（ダミーのみ）
- LFを正とする（`.gitattributes` に準拠）。OS/端末差を出さない。

---

## 9. 次スレッドで最初に確認すべきチェックリスト（5項目まで）
1. 最新ZIPが添付されている（ZIP名・branch・commit一致）
2. 本引き継ぎ（正本）を読んだ
3. `pip install -e ".[dev]"` で ruff が有効化できる
4. `tools/diag_weekshape_factors.py` で gated_true / factor!=1 が実数で出る
5. Decision Log 末尾と矛盾しない（必要なら追記差分を適用）

---

## 10. 質問（最大5つ・必要なもののみ）
1. “学習パラメータ”の保存先は、既存 `config/hotels.json` へ追記（ファイル増やさない）で進めてOKですか？（Yes/No）
回答：Yes
2. “ベース小”救済は、まずは **weekshape（15–45）から**導入→次に pace14（0–14）へ展開、の順でOKですか？（Yes/No）
回答：Yes