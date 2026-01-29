# ファイル名案: docs/thread_logs/2025-12-26_feature-daily-snapshots-partial-build_nface-layout-asof.md

# Thread Log: N@FACE RAW判定強化とASOF警告整理（Phase 1.6前提づくり）

## Meta

* Date: 2025-12-26（ZIP名から推定）
* Branch: feature/daily-snapshots-partial-build
* Commit: 不明（会話内に明示なし）
* Zip: rm-booking-curve-lab_20251226_1203_samp_feature-daily-snapshots-partial-build_04eb537_full.zip
* Scope:

  * 欠損検知（ops/audit）と asof_missing の扱い整理
  * Phase 1.6（Range rebuild）方針確定と既存UI導線（LT_DATA(4ヶ月)）との統合検討
  * N@FACE「売上予算実績表」RAWの現場加工パターン対応（誤取得防止・STOP方針）
  * GUIの最新ASOF表示/警告の概念整理（混同防止）

## Done（実装・変更）

* 欠損検知を2モード（運用/監査）で扱う前提の整理（ops/audit CSVの分離運用）
* asof_missing（ASOF丸抜け）を欠損として検知する方針整理（監査モードでノイズ抑制）
* Phase 1.6（Range rebuild）を「LT_DATA(4ヶ月)」導線の裏側に置き換える方針を合意
* Range rebuild の既定：buffer_days=30（安全側）＋ stay_months 自動算出（asof_max+120日先まで両端含む）＋ 前月常時含める
* N@FACE RAWのレイアウト自動判定を安全側へ寄せ、予算行をOHとして誤取得しない方向に修正
* 予算行削除（1行持ち/inline）と2行持ち（予算/実績）の分岐を整理し、曜日列依存を必須にしない設計へ
* A列日付探索は必ず9行目以降で行う方針を確定（A1に手入力日付があるケースを回避）
* 月次ブッキングカーブの「0大量発生による乱れ」について、原因候補をRAW誤取得（予算行取得）として特定→改善を確認
* layout_unknown となっていた「日付を丸ごと1行ズラし」系のパターンを拾えるよう調整し、ログが改善
* samples/raw/README.md の一覧破綻を修正し、カテゴリ（正常/異常/要件確認）を崩さず更新（ZIP内が最新）

## Decisions（決定）

* Decision:

  * 欠損検知は ops（運用）/ audit（監査）で分け、監査は「最古〜最新のSTAY MONTH範囲」に限定してノイズを抑える
  * asof_missing（ASOF丸抜け）は欠損として検知する（ただし「欠損のみ取り込み」は raw_missing のみ対象でよい）
  * Phase 1.6（Range rebuild）は「LT_DATA(4ヶ月)」の裏側へ統合し、運用導線を一本化する
  * Range rebuild の既定は buffer_days=30（安全側）
  * stay_months は「asof_maxから+120日先まで（両端含む）」＋「前月を常に含む」で固定（これにより月初例外の特判を不要化）
  * N@FACE RAWの不変条件を固定：A列=日付、OH=EFG、曜日=C列（曜日は存在する場合の補助情報で必須にしない）
  * A列の日付判定は必ず9行目以降で行う（ヘッダ等の手入力日付に引っ張られない）
  * 判定不能は推測せずSTOP（layout_unknown）を維持（誤取り込み防止を優先）
  * GUIマスタ設定で「最新ASOF」を重複表示する必要は薄い（鮮度ラベルで担保済）。出すなら「欠損検査の未実施/要確認」等の運用警告に寄せ、観測最新ASOFと混同させない
  * FULL_ALLで止まる「A列日付不足（start_row=9, found=0）」は欠損扱いでOK
  * 次リリースは v0.6.5 相当へ進め、docs整合も同時に取る
* Why:

  * 欠損検知は「運用の穴埋め」と「監査の棚卸し」で目的が違い、同一ロジックだと過去月ノイズで使い物にならないため
  * Range rebuild を既存UI導線へ統合すると、運用が「鮮度→更新→必要なら欠損チェック」に収束し、操作負荷が減るため
  * N@FACE RAWは現場加工が多様でA列加工リスクが高く、誤取得（予算行をOHとして取る）の事故コストが最大のため
  * 「前月常時含める」設計で月初例外を吸収でき、分岐条件の複雑化を避けられるため
  * マスタ設定の stale_latest_asof は概念が異なり、最新ASOF（観測値）と混同すると運用判断を誤るため

## Docs impact（反映先の候補）

* spec_overview:

  * 欠損検知（ops/audit）とGUI導線（更新・警告）の概念整理
* spec_data_layer:

  * missing_report（ops/audit）出力の位置づけ、asof_missing/raw_missing、Range rebuildの対象月算出（asof_max+120日先、前月含む）
* spec_models:

  * （直接の変更は薄いが）LT_DATA更新導線がRange rebuildへ統合された場合の運用上の前提
* spec_evaluation:

  * （直接の変更は薄いが）daily_snapshots再生成/部分更新と評価再計算の関係が明示されるとよい
* BookingCurveLab_README:

  * RAW前提（売上予算実績表）と“現場加工対策”である旨、STOP方針、欠損チェックの使い分け

### Docs impact 判定（必須/不要 + Status）

* 必須:

  * 項目: 欠損検知の2モード（ops/audit）と asof_missing の位置づけ

    * 理由: 運用と監査で目的が違い、出力/範囲制御が仕様として必要
    * Status: 未反映
    * 反映先: docs/spec_data_layer.md（missing_report/欠損検知の節）
  * 項目: Range rebuild（Phase 1.6）の対象月算出（asof_max+120日先＋前月常時含む、buffer_days=30）

    * 理由: 部分更新の“唯一の正”となる運用ロジックで再現性が必要
    * Status: 未反映
    * 反映先: docs/spec_data_layer.md（partial build/range rebuildの節）
  * 項目: GUI警告の概念分離（最新ASOF=観測値 vs stale_latest_asof=鮮度/要確認、マスタ設定は運用警告寄せ）

    * 理由: 同一文言で概念が混在すると誤運用を誘発する
    * Status: 未反映
    * 反映先: docs/spec_overview.md（GUI/運用導線の節）＋ BookingCurveLab_README
  * 項目: RAW前提（売上予算実績表）と現場加工対策、STOP方針、日付探索start_row=9固定

    * 理由: 解析ロジックの前提が曖昧だと再発する
    * Status: 一部反映（samples/raw/README.md は更新済）
    * 反映先: BookingCurveLab_README ＋（必要なら）docs/spec_data_layer.md（RAW入力の節）
  * 項目: 次リリースを v0.6.5 相当へ進め、docs整合も同時に行う方針

    * 理由: roadmap側表記との整合が崩れているため
    * Status: 未反映
    * 反映先: docs/roadmap.md（現在地の節）＋（必要なら）docs/tasks_backlog.md
* docs不要:

  * 項目: 個別サンプルファイルの追加/リネーム詳細（README内の列挙レベル）

    * 理由: Thread Logとsamples/raw/README.mdで追跡可能。spec_* に入れると肥大化する

## Known issues / Open

* マスタ設定タブの「最新ASOF:要確認（stale_latest_asof）」が FULL_ALL→LT_ALL 等で自動更新されず、ブッキングカーブ/日別FCの最新ASOF（観測値）と混乱を招く（概念分離/表示整理が必要）
* 古いRAWで A列日付行不足（start_row=9, found=0）があり FULL_ALL が停止する（欠損扱いでOKだが、欠損監査ノイズとのバランスは要確認）
* layout_unknown は原則STOP方針だが、対象月に関係する加工パターンが残っていれば samples に追加して対応余地あり
* 警告の「繰り返し抑止（ACK）」は未実装（再起動で復活する前提）。必要ならUI状態の永続化設計が要る

## Next

* P0:

  * マスタ設定タブの表示を「最新ASOF」から切り離し、欠損検査の未実施/要確認など運用警告へ寄せる（観測最新ASOFと混同しない）
  * A列日付不足（start_row=9, found=0）を欠損扱いで固定し、ログ/欠損CSVで追える形にする
  * v0.6.5 リリース方針に合わせ、docs（roadmap等）整合タスクを切り出す
* P1:

  * Phase 1.6（Range rebuild）を運用として完成（LT_DATA(4ヶ月)導線の完全置換、範囲限定更新の安定化）
  * 欠損・変換ログを「整理対象の棚卸しリスト」としてCSV化（運用作業に落とす）
* P2:

  * docs/spec_*・README・backlog の現実追従（今回の決定事項を“唯一の正”へ反映し、スレッド依存を減らす）
