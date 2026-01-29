# ファイル名案: docs/thread_logs/2026-01-09_feature-revenue-forecast-phase-bias_revpar-topdown-rounding.md

# Thread Log: Revenue予測（pax/revenue）＋phase_bias＋月次丸め＋TopDown RevPAR（ポップアップ）

## Meta

* Date: 2026-01-09（推定：ZIP名のタイムスタンプより）
* Branch: feature/revenue-forecast-phase-bias
* Commit: e473d72
* Zip: rm-booking-curve-lab_20260109_1510_samp_feature-revenue-forecast-phase-bias_e473d72_full.zip
* Scope: LT_DATA（rooms/pax/revenue）前提での日別Forecast拡張、phase_bias（revenueのみ）導入、月次丸め（GUIのみ・日別配分整合）、TopDown RevPARグラフ（別窓）追加、GUIの視認性改善

## Done（実装・変更）

* LT_DATA を rooms/pax/revenue の value_type として扱い、月別LT CSVを value_type 指定で解決できる導線を実装（rooms互換名も探索対象に保持）
* 日別Forecastに pax/revenue を追加（rooms/pax/revenue の3系統を同一導線で生成）
* revenue予測（V1）を実装：`revenue_oh_now + remaining_rooms * (adr_oh_now * phase_factor)`（ADRは `revenue_oh_now / rooms_oh_now`）
* phase_bias UI（3ヶ月×3フェーズ×強度3）を導入し、local_overrides に保存/読込（適用は当面 revenue のみ）
* pax_cap を追加し、未入力時は「無制限」ではなく「p99（直近Nヶ月のACT pax）」で自動キャップする方針に確定（運用は直近6ヶ月を想定）
* 「予測ゼロでもCSVは必ず出す」「未作成CSV読み込みをエラー扱いにしない」を確定し、GUI運用上の欠損耐性を強化
* 月次丸めを GUI チェックボックスで切替（丸めは月次合計のみ・CSVは生値のまま）を導入
* 月次丸めON時、日別合計が月次丸めゴールに一致するよう日別へ配分して整合を取る方針を確定（末日調整ではなく全体配分）
* 日別Forecastの数値表示を改善（カンマ区切り、ADR/RevPARの整数表示など）
* 日別Forecastサマリを「Forecast合計」ではなく「projected（過去ACT＋未来Forecast）」中心に寄せる方針に確定し反映
* TopDown（RevPAR）を「別窓（ポップアップ）」で追加（年度固定表示＋回転表示モードを導入）
* TopDownの予測範囲を「最新ASOF基準（上限=ASOF+90日がかかる月）」へ寄せ、下限は「最新ASOFが属する月」起点に確定
* TopDownで Forecast CSV が存在しない月はグラフに載せない（欠損扱い）を確定
* GUI上部メニュー/余白/配置を再設計して圧縮（最新版でレイアウト改善を反映）

## Decisions（決定）

* Decision:

  * 日別Forecastは rooms/pax/revenue の3系統を扱う（LT_DATAも value_type 別）
  * revenue定義は「税抜宿泊売上のみ」（ADR定義A）で統一（朝食等は対象外）
  * phase_bias は UI入力＋local_overrides 保存、適用先は当面 revenue のみ（roomsとは独立）
  * pax予測は roomsと同型ロジック（OH起点＋残りpickup構造）に寄せる
  * pax_cap 未入力時は max ではなく p99 を使用（母集団は「モデル履歴収集範囲＝直近Nヶ月の各日ACT pax」、運用は直近6ヶ月想定）
  * 「CSVは生値」＝資料用の大きい丸め（100単位/10万円単位）をCSVに焼かない（丸めはGUI側の責務）
  * 月次丸めはチェックボックスで切替可能にし、日別は月次丸めゴールに一致するよう配分調整（末日調整ではなく全体配分）
  * ASOFが対象月より後（着地後ASOF）でも無言で通す（警告は出さない）
  * TopDownは別タブではなく別窓（ポップアップ）で提供する
  * TopDownの予測範囲は「最新ASOFが属する月」起点＋「ASOF+90日がかかる月」上限
  * Forecast CSVが存在しない月は TopDown/日別ともに「載せない（欠損扱い）」
  * 月次丸め単位（rooms/pax=100、rev=10万円）とTopDown年度開始月（6月）は将来ホテル別設定化する
* Why:

  * 指標追加（pax/revenue）を rooms と同じ運用導線に揃え、比較・保守の複雑化を避けるため
  * revenueは OHと残室×ADR推定で破綻しにくい最小V1を優先し、DOR/LT収束等はV2へ分離するため
  * phase_bias を rooms と独立させ、影響範囲（事故率）を限定しつつ意思決定補助を先に提供するため
  * pax_cap は「現場の現実的上限」を担保しつつ、maxの外れ値依存を避けるため p99 を採用するため
  * 月次丸めは資料作成の必要性がある一方、評価・再現性のためCSVは生値を保持する必要があるため
  * TopDownの“違和感検知”は座標系固定が重要であり、別窓で独立させた方がUX/保守が安定するため
  * ASOF起点を統一して混入バグ（対象月変更で予測範囲がズレる等）を避けるため

## Docs impact（反映先の候補）

* spec_overview: 機能概要（pax/revenue対応、TopDown別窓、local_overrides保存の存在）
* spec_data_layer: forecast CSV（rooms/pax/revenue列、欠損扱い、CSV生値・丸めはGUI）の明文化
* spec_models: pax/revenue予測V1、phase_bias仕様、TopDownの表示ロジック、（必要なら）pace14/pace14_marketの追記
* spec_evaluation: 現状は rooms中心のままか、pax/revenue評価をいつ追加するかの位置づけ
* BookingCurveLab_README: 操作手順（phase_bias、月次丸めチェックボックス、TopDown別窓、欠損時の挙動）

### Docs impact 判定（必須/不要 + Status）

* 必須:

  * 項目: revenue予測V1（OH + remaining_rooms×ADR推定）と phase_bias（revenueのみ適用）の仕様明文化

    * 理由: 実装が先行しており、運用・再現のため仕様として固定が必要
    * Status: 未反映
    * 反映先: docs/spec_models.md（4. 売上予測モデル（ADRモデル）の構想レベル仕様 / 6. 日別フォーキャストタブの表示定義）
  * 項目: 日別Forecastのpax/revenue追加、および pax_cap（未入力時p99）の仕様

    * 理由: 出力/運用が変わり、現場誤解（過小/過大、限界突破）を防ぐ必要がある
    * Status: 未反映
    * 反映先: docs/spec_models.md（6. 日別フォーキャストタブの表示定義）
  * 項目: 「CSVは生値」「月次丸めはGUIのみ＋日別配分で整合」の運用仕様

    * 理由: 予測値の再現性・評価と、資料用表示を混同すると事故る
    * Status: 未反映
    * 反映先: docs/spec_data_layer.md（LT_DATAに続く出力レイヤ説明 or 追補セクション）、BookingCurveLab_README.txt（運用手順）
  * 項目: TopDown（RevPAR）別窓、予測範囲（ASOF起点/ASOF+90日上限）、欠損月非表示、表示モード（年度固定/回転）

    * 理由: UIとして新規で、意思決定の読み違いを防ぐため前提の明文化が必要
    * Status: 未反映
    * 反映先: BookingCurveLab_README.txt（TopDown画面の使い方）、docs/spec_overview.md（機能概要の追記）
  * 項目: 月次丸め単位（rooms/pax/rev）と TopDown年度開始月の「ホテル別設定化」方針

    * 理由: マルチホテル運用で値が変わり得る前提を仕様側に置く必要がある
    * Status: 未反映
    * 反映先: docs/spec_overview.md（設定方針）、docs/spec_data_layer.md（設定の保存場所の方針）
* docs不要:

  * 項目: GUI余白・配置の微調整（レイアウト改善の過程）

    * 理由: 仕様ではなくUIの見た目調整であり、証跡としてThread Logに残せば十分
  * 項目: VSCode上の一時的な表示/不具合相談（環境依存）

    * 理由: プロダクト仕様ではなく端末環境の事象のため

## Known issues / Open

* TopDownのp10–p90帯は現状「過去値帯」寄りで、要件の「最新着地月からの傾き帯（傾き分布）」へ作り替えが未完（V2）
* TopDown回転モードの違和感（年度で色分けする場合の線の切れ方/凡例/予測部分の連結ルールの最終確定が必要）
* 月次丸めON時に派生指標（例：PU Exp、OCC等）の再計算が漏れないことの回帰確認が必要
* 月次丸め配分（最大剰余法系）で cap（rooms/pax）超過を確実に回避する制約の最終確認が必要
* 「月次丸め単位」「TopDown年度開始月」のホテル別設定保存の実装（保存先の具体：hotels.json等）を未実装の場合は対応が必要

## Next

* P0:

  * TopDownの回転モードを「年度固定色分け」前提で整合させる（年度境界での線/色/凡例/予測連結のルールを確定し実装修正）
  * TopDownのp10–p90帯を「最新着地月からの傾き帯（傾き分布）」に作り替える（V2の最小実装）
  * 月次丸めON時の派生指標再計算と、cap超過回避の回帰確認を固める
* P1:

  * 月次丸め単位（rooms/pax/rev）と TopDown年度開始月をホテル別設定として保存/読込できるようにする（hotels.json等へ）
  * 異常年（COVID/万博等）をTopDown帯計算から除外する運用（除外年トグル等）の検討・導入（必要なら）
