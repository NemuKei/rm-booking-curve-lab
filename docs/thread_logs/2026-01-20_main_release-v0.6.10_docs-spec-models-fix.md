# ファイル名案: docs/thread_logs/2026-01-20_main_release-v0.6.10_docs-spec-models-fix.md

# Thread Log: v0.6.10 リリース後のdocs整合（pace14_market最終仕様固定）

## Meta

* Date: 2026-01-20（会話上の現在日。Thread Logの日付誤りを過去日に修正した旨の言及あり＝実際の作業日は別の可能性あり）
* Branch: main（feature/revenue-forecast-phase-bias は main取り込み済→mainマージ→v0.6.10 リリース済み）
* Commit: 7ab8356（ZIP名より推定）
* Zip: rm-booking-curve-lab_20260120_1725_samp_main_7ab8356_full.zip
* Scope: v0.6.10（feature/revenue-forecast-phase-bias 含む）リリース後の docs 更新方針整理／spec_models の追記内容精査（pace14・pace14_market・market補正clip・revenue定義の配置）

## Done（実装・変更）

* feature/revenue-forecast-phase-bias は最新 main（v0.6.9 以降）を取り込んだ状態であることを確認。
* 次リリースは v0.6.10 とし、v0.7.0 に上げるほどの破壊的変更は無い前提を確認。
* docs更新は「mainにマージしてからまとめて」実施する運用で合意。
* docs更新用のスレッド横断まとめ（pace14/pace14_market、revenue定義、pax/phase_bias/月次丸め等）を前提情報として整理。
* pace14_market の market_factor 形状を最終確定（B：指数/power）として固定。
* pace14_market の clip適用順序を最終確定（PF→market→任意最終ガード）として固定。
* market_pace_raw に clip を入れる方針を最終確定し、初期値を 0.95–1.05 に固定する方針を整理。
* revenue 定義（税抜宿泊売上のみ）は spec_models だけでなく spec_data_layer にも明記すべき（データ契約）という方針を整理。
* Thread Log の日付が「今日」になっていたため過去日に修正した旨を共有（作業ログ整備）。

## Decisions（決定）

* Decision:

  * feature/revenue-forecast-phase-bias は最新 main を取り込んだ状態で進める（取り込み済）。
  * 次リリースは v0.6.10（v0.7.0相当の破壊的変更ではない）。
  * docs更新は main マージ後にまとめて行う。
  * pace14_market の market補正は power で適用：final_pace14_market = final_pace14 × (market_pace^β)。
  * clip順序は PF→market→（任意の最終ガード）で固定。
  * market_pace_raw に clip を適用し、初期値は 0.95–1.05 を採用する。
  * revenue 定義（税抜宿泊売上のみ）は spec_data_layer に固定し、spec_models は参照（重複最小）で持つ。
* Why:

  * market_pace は倍率概念であり、power のほうが 1.00 近傍の微調整が自然で、上下対称かつ暴れにくく運用事故が少ない。
  * market は「月全体補正」で爆発半径が大きいため、market側にも clip が必要。
  * revenue 定義はモデル都合ではなく「列の意味（データ契約）」なので data_layer に書かないと混入事故（朝食等）が止められない。

## Docs impact（反映先の候補）

* spec_overview: docs更新の運用（mainマージ後）や、設定保存階層の説明に関係（必要なら最小追記）。
* spec_data_layer: revenue の定義（税抜宿泊売上のみ）を固定する追記が必要。
* spec_models: pace14 / pace14_market の定義（power式、βの意味、clip順序、market_pace clip初期値）を反映する追記が必要。
* spec_evaluation: 今回の決定の直接反映は薄い（必要なら “モデル追加” の記載程度）。
* BookingCurveLab_README: v0.6.10 での変更点（モデル説明・docs導線）を簡潔に追記する余地あり。

### Docs impact 判定（必須/不要 + Status）

* 必須:

  * 項目: pace14_market の market_factor を power（market_pace^β）で定義し、βの意味を明記

    * 理由: 実装・合意と docs の不整合が残ると、将来の検証・改修で事故るため
    * Status: 未反映
    * 反映先: docs/spec_models.md（モデル一覧：pace14 / pace14_market の節）
  * 項目: clip 適用順序（PF→market→任意最終ガード）を明記

    * 理由: 順序を誤るとスパイク抑制の意図が崩れ、事故率が上がるため
    * Status: 未反映
    * 反映先: docs/spec_models.md（pace14系の計算手順）
  * 項目: market_pace_raw に clip を適用し、初期値 0.95–1.05 を固定（1行で可）

    * 理由: market補正の爆発半径が大きく、欠損/偏りがそのまま最終着地に乗る事故を防ぐため
    * Status: 未反映
    * 反映先: docs/spec_models.md（pace14_market の注意点／安全弁）
  * 項目: revenue 定義（税抜宿泊売上のみ、朝食等除外）を spec_data_layer に固定

    * 理由: 列の意味＝データ契約であり、data_layer に無いと混入事故が止まらないため
    * Status: 未反映
    * 反映先: docs/spec_data_layer.md（LT_DATA value_type / revenue列定義、または forecast CSV の列定義）
* docs不要:

  * 項目: v0.6.10 の採番自体

    * 理由: リリースノートやタグ管理の領域であり、spec_* の仕様本文に固定する必要は薄い
    * Status: 不要
  * 項目: Thread Log の日付修正の経緯

    * 理由: 作業記録のメタであり仕様ではない
    * Status: 不要

## Known issues / Open

* Thread Log の Date が「今日」になっていたため修正した旨があり、実作業日と会話日がズレている可能性（最終的な Date は正ファイルに合わせて確定が必要）。
* docs/spec_models.md の現状記述が、pace14 / pace14_market の他モデルと比べて簡略すぎる懸念（詳細度の調整が必要）。
* revenue 定義の記載場所（spec_data_layer のどの節に置くか：LT_DATA value_type 定義 vs forecast列定義）は最終決定が必要。

## Next

* P0:

  * docs/spec_models.md：pace14 / pace14_market の定義を最終確定仕様（power式、β、clip順序、market_pace clip初期値）へ更新し、他モデルと同程度の説明量に整える。
  * docs/spec_data_layer.md：revenue 定義（税抜宿泊売上のみ）をデータ契約として明記し、spec_models 側は参照導線にする（重複最小）。
* P1:

  * v0.6.10 リリース本文（リリースノート）で、モデル追加・仕様固定点（power式・clip）を短く明示し、docsへの導線を付ける。
