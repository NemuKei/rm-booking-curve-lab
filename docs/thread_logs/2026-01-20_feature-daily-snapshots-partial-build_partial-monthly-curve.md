# ファイル名案: docs/thread_logs/2026-01-20_feature-daily-snapshots-partial-build_partial-monthly-curve.md

# Thread Log: daily snapshots 部分更新と月次カーブ整合

## Meta

* Date: 2026-01-20（推定：このスレッドの日時情報が明示されていないため）
* Branch: feature/daily-snapshots-partial-build
* Commit: （不明）
* Zip: （不明）
* Scope: daily_snapshots の部分生成（FAST/FULL_MONTHS/FULL_ALL）運用確定、FULL_ALLの安全ガード、最新ASOF更新、monthly_curve生成・描画の整合問題の洗い出しと方針決定

## Done（実装・変更）

* GUIの「LT_DATA(4ヶ月)+更新ON」を FAST（宿泊月=直近4ヶ月、ASOF窓=latest-14d）として運用する方針を確定
* GUIの「LT_DATA(期間指定)+更新ON」を FULL_MONTHS（宿泊月=指定、ASOF窓なしのフルスキャン）として運用する方針を確定
* FULL_ALL を誤爆しにくい導線（マスタ設定の奥）に置く方針を確定（強制確認/見積り/強制ログ）
* daily snapshots 更新後に「最新ASOF」ラベルと `output/asof_dates_{hotel}.csv` が最新化されることを確認
* daily_snapshots は欠損（NaN）を保持し、補完はビュー側で行うことをテスト観点として明確化
* FULL_ALL の WinError5（PermissionError）はファイルロック（開いたまま）で再現し、閉じれば解消することを確認
* FULL_ALL の実測：509ファイルで約20秒（試算が過剰になり得るため見積りロジック調整余地あり）
* monthly_curve が無い場合の月次カーブ描画が、LT_DATA由来の誤った曲線になり得る問題を確認（ロジック不整合）
* 「前年データが無いとエラー」挙動は、警告→描画（取れる月だけ）方向に寄せる方針を合意（1本も無い場合のみエラー）

## Decisions（決定）

* Decision:

  * 更新モードは 3段（FAST / FULL_MONTHS / FULL_ALL）で整理し、2段に無理やり合わせない
  * FAST は「宿泊月フィルタ（4ヶ月）＋ASOF固定窓」で速度を担保、FULL_MONTHS は「宿泊月のみ指定」で安全側（過去取り込み用）
  * FULL_ALL は「普段触らない奥」＋実行前見積り＋強制ログ保存＋最終確認で誤爆防止
  * monthly_curve フォールバックとして LT_DATA を使う案は採用しない（正しい月次カーブにならないため）
  * monthly_curve が無ければ daily_snapshots からその場生成して保存→描画、daily_snapshots も無い/薄い場合は更新を促して停止
* Why:

  * 週次運用のボトルネックは daily_snapshots 更新であり、速度を落とさずに安全に更新範囲を確定できる必要がある
  * ASOF指定をユーザー入力にすると差分意識が必要になり運用ミスが増えるため、基本は宿泊月単位で安全に運用する
  * monthly_curve を LT_DATA から代用すると定義が崩れて誤った可視化になるため、フォールバックは禁止が合理的

## Docs impact（反映先の候補）

* spec_overview: daily_snapshots 更新モード（partial/fast/full）の運用整理、monthly_curve生成と描画の優先順位
* spec_data_layer: daily snapshots 部分生成（Partial/Upsert）の運用定義、monthly_curve生成の正しいLT定義とフォールバック禁止
* spec_models: （影響小：モデル自体は未変更）
* spec_evaluation: （影響小：評価ロジック自体は未変更）
* BookingCurveLab_README: GUI操作（FAST/FULL_MONTHS/FULL_ALL）と注意点（ファイルロック、見積り/ログ）追記候補

### Docs impact 判定（必須/不要 + Status）

* 必須:

  * 項目: daily_snapshots 更新モード（FAST / FULL_MONTHS / FULL_ALL）の位置づけと範囲定義

    * 理由: 週次運用の手順と安全設計が仕様とズレると事故る（誤爆・過剰更新・更新漏れ）
    * Status: 未反映
    * 反映先: docs/spec_data_layer.md（1-4 生成モード / GUI連動の節）
  * 項目: monthly_curve の生成元優先順位（monthly_curve無→daily_snapshotsから生成→描画）と LT_DATAフォールバック禁止

    * 理由: 現状「誤った曲線」が描画され得るため、仕様で禁止・固定しないと信頼性が落ちる
    * Status: 未反映
    * 反映先: docs/spec_data_layer.md（2-4 月次ブッキングカーブ / 生成ルートの節）
  * 項目: FULL_ALL の誤爆防止（奥配置・最終確認・見積り表示・強制ログ保存）

    * 理由: 全量再生成は負荷/時間/誤操作リスクが高い
    * Status: 未反映
    * 反映先: BookingCurveLab_README.txt（運用手順/注意事項）
* docs不要:

  * 項目: FULL_ALL の WinError5 はファイルロックで起きる（閉じれば解消）

    * 理由: 仕様というより運用Tips。READMEに書くなら可だが spec_* の必須ではない
  * 項目: 509ファイル=約20秒の実測値

    * 理由: 環境依存で仕様固定に不向き（見積り実装の参考ログに留める）

 

## Known issues / Open

* 月次カーブ描画時、monthly_curve欠損時の「その場生成」ロジックが別系統（LT_DATA経由など）になっている疑いがあり、曲線が崩れる
* monthly_curve の欠損補完（ASOF欠けで1点抜け）について、本来の補完仕様（次ASOFで埋める/NOCB）と不整合の可能性あり（要精査）
* 「前年が無いとエラー」挙動は改善方向に寄っているが、完全に意図通りかは要再確認（キャッシュ/旧挙動混在の可能性）

## Next

* P0:

  * monthly_curve 生成ロジックを一本化（LT定義＝month_end - asof を厳守）し、monthly_curve無時は daily_snapshots から生成→CSV保存→描画に統一
  * monthly_curve 生成不能（daily_snapshots薄い/無し）時のエラー文言と誘導（FAST/FULL_MONTHS/FULL_ALL）を確定
* P1:

  * 月次カーブ描画：取れる月が1本でもあれば警告→描画、1本も無い場合のみエラーに統一
  * FULL_ALL 後の「全期間LT生成しますか？」確認導線＋別ボタンの追加可否を最終決定（monthly_curveは月次タブ都度生成でも可）
