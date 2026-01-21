Proposed file path: docs/handovers/2026-01-21_main_docs-governance-start-here.md

---

## 4-1. スレッド移行宣言（新スレッドに貼る前提の文面）

このスレッドは、**Thread Log / Decision Log / 引継書の運用を整備し、docs/templates と docs/dev_style.md・docs/START_HERE.md を追加・更新して「スレッド開始〜終了（Docs Gate/Close Gate）」の型を固めた**作業ログです。
次スレッドではまず、**このスレッド後半で作られた docs/ルール（START_HERE・templates・dev_style 等）が矛盾なく運用に耐えるかを精査（Docs Gate）**したうえで、必要なら修正します。

---

## 4-2. 現在地サマリ（できたこと / 未完）

### できたこと

* **運用ドキュメントを追加・整備**

  * `docs/START_HERE.md` を新設（唯一の正・Gate・参照先・命名ルールを集約）
  * `docs/dev_style.md` に運用ルールを追記（Docs Gate 手順、テンプレ参照、A-番号運用、締めモード等）
* **テンプレ体系を docs/templates/ に集約**

  * `handover_request.md` / `handover_body.md`
  * `prompt_thread_log_generate.md` / `prompt_decision_log_update.md` / `prompt_docs_update.md`
  * `thread_start.md`（スレッド冒頭の貼り付け用テンプレ）
* 既存の Thread Log 群が ZIP 内に存在することを確認（`docs/thread_logs/`：複数本）
* `docs/decision_log.md` に **revenue 定義（税抜・宿泊売上のみ）を spec_data_layer 固定**の決定（`D-20260120-005`）があり、Status が **spec反映済**であることを確認

### 未完（残課題）

* **このスレッド自体の Thread Log が未作成**（ZIP内の最新は `docs/thread_logs/2026-01-20_main_release-v0.6.10_docs-spec-models-fix.md` まで）
* 後半で追加・更新した docs が「相互参照・文言・粒度・運用実態」と整合しているか、**再精査が必要**（ユーザー懸念点）
* `docs/decision_log.md` の末尾が必ずしも「最新決定」になっていない可能性がある（IDが存在するが末尾に来ていないケースがあるため、運用上の“見落とし”リスク）

---

## 4-3. 決定事項（仕様として合意したこと）

* 共有物の唯一の正は **make_release_zip.py で作成した最新ZIP**（単体ファイル添付運用は原則しない）
* 仕様の唯一の正は **`docs/spec_*.md` と `AGENTS.md`**
* 次スレ冒頭で **Docs Gate を必ず実施**し、Yesの場合は `docs/templates/prompt_docs_update.md` を唯一の手順として docs 更新を先に行う
* `revenue` 定義は **「税抜・宿泊売上のみ（朝食等除外）」で固定**（Yesで確定済）

  * `D-20260120-005` にて「spec_data_layer を正、spec_models は参照導線（重複最小）」の方針が **spec反映済**

---

## 4-4. 未解決の課題・バグ（再現条件／影響範囲／暫定回避策）

### 課題1：後半で追加・更新した運用docsの整合性に不安（ユーザー申告）

* 再現条件：`docs/START_HERE.md` / `docs/dev_style.md` / `docs/templates/*` を横断で読むと、参照先やGate手順が二重化・矛盾・不足している可能性
* 影響範囲：次スレ冒頭の手順がブレて、参照齟齬や「推測で進める」事故が起きる
* 暫定回避策：次スレ冒頭で **Docs Gate（精査）を最優先**にし、矛盾があれば docs を先に直す（実装より前）

### 課題2：decision_log の“末尾10〜20件確認”が最新決定を保証しない可能性

* 再現条件：`docs/decision_log.md` 内に新しいIDが存在するが、末尾の並びが時系列になっていない
* 影響範囲：Docs Gate の判定で「未反映決定」を見落とす
* 暫定回避策：次スレ冒頭の確認では「末尾確認」だけでなく、必要に応じて **該当日のID（例：D-20260120-00X）を検索**して確認する運用に寄せる（※運用コストと相談）

---

## 4-5. 次にやる作業（P0/P1/P2）

### P0（次スレ冒頭：最優先）

1. **後半で追加・更新した docs/ルールの精査（Docs Gate）**

* 完了条件：

  * `docs/START_HERE.md` / `docs/dev_style.md` / `docs/templates/*` の内容が矛盾なく繋がる
  * 「唯一の正」「Docs Gate」「Close Gate」「テンプレ参照先」が重複や食い違いなく表現できている
  * 必要なら docs を最小修正して ZIP に同梱（実装より先）

2. **このスレッドの Thread Log を追加**

* 完了条件：

  * `docs/thread_logs/YYYY-MM-DD_main_<scope>.md` を作成し、今回の docs 整備（START_HERE・templates・dev_style）を追跡可能にする
  * Date/Branch/Commit/Zip/Scope が揃う

### P1

3. **decision_log の“見落とし耐性”を上げる（運用整理）**

* 完了条件：

  * 「末尾10〜20件」確認だけで足りない場合の補助手順（検索ルール等）が docs に軽く整理される
  * ※並び替えや大改修は必須ではない（事故が起きるなら最小で対処）

### P2

4. **会話カウンタ（A-番号）運用の定着**

* 完了条件：

  * `docs/dev_style.md` の規約（A-番号、A-25締めモード、逸脱即停止）が実運用で機能することを確認

---

## 4-6. 参照すべきファイル一覧（パス＋理由）

* `docs/START_HERE.md`：入口。唯一の正／Gate／参照先を集約。次スレの最初に読む
* `docs/dev_style.md`：運用ルールの正本（Docs Gate、テンプレ参照、A-番号、締めモード）
* `docs/templates/thread_start.md`：スレッド冒頭貼り付け用（迷わないため）
* `docs/templates/prompt_docs_update.md`：Docs Gate が Yes の場合の唯一手順
* `docs/templates/handover_request.md` / `docs/templates/handover_body.md`：引継書の依頼と本文型
* `docs/thread_logs/2026-01-20_main_release-v0.6.10_docs-spec-models-fix.md`：直近Thread Log（ただし今回スレッド分は未反映）
* `docs/decision_log.md`：決定の正本（末尾10〜20件＋必要に応じ検索で確認）
* `AGENTS.md`：AI運用ルールの唯一の正

---

## 4-7. 実行コマンド／手順（分かっている範囲）

* ZIP確認（参照の唯一の正）

  * `rm-booking-curve-lab_20260121_1146_samp_main_11f166b_full.zip`
  * `MANIFEST.txt` に branch/commit/generated_at が記載されている
* アプリ起動（参考）

  * `python src/gui_main.py`
* ログ（参考）

  * `gui_app.log`（例外時のスタックトレース）

---

## 4-8. 注意点（参照齟齬・データ・トークン等）

* 仕様の唯一の正は `docs/spec_*.md` と `AGENTS.md`。Thread Log / Decision Log / 会話は仕様ではない
* 共有物の唯一の正は最新ZIP。単体ファイル添付で運用しない
* 推測禁止：不足があれば要求。残るなら壁打ちに切替（Codex用プロンプトは出さない）
* スレッド終盤はトークン溢れで事故るため、**議論より先に Thread Log / Handover を作って閉じる**判断を優先する（dev_style に準拠）

---

## 4-9. 次スレッドで最初に確認すべきチェックリスト（最大5項目）

1. 最新ZIP（`..._11f166b_full.zip`）の branch/commit が想定どおりか（Yes/No）
2. `docs/START_HERE.md` と `docs/dev_style.md` と `docs/templates/*` に矛盾がないか（Yes/No）
3. Docs Gate 判定：decision_log / thread_log / spec_* の間に「未反映で事故りうる矛盾」があるか（Yes/No）

   * **Yes の場合の更新対象**：該当する `docs/spec_*.md`（必要なら）＋運用docs（START_HERE/dev_style/templates）
4. このスレッド分の Thread Log が `docs/thread_logs/` に追加されているか（Yes/No）
5. `docs/decision_log.md` の末尾10〜20件確認だけで見落としが出ない状態か（Yes/No）

---

## 6. 不明点がある場合の質問（最大5つまで）

1. このスレッドの Thread Log の scope 名は、どれを採用しますか？（例：`docs-governance` / `templates-start-here` など短文で）
回答：Thread Log scope：docs-governance
2. decision_log の“並び順”は、今後「時系列に揃える」方針まで踏み込みますか？（Yes/No）
回答：Decision Log の並び：時系列に揃える方針で進める（Yes）
3. 次スレのP0精査で、対象を「運用docs（START_HERE/dev_style/templates）のみ」に限定してOKですか？（Yes/No）
回答：次スレP0精査の対象：運用docs（START_HERE / dev_style / templates）のみに限定（Yes）