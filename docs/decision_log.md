# Decision Log（横断決定ログ）

> 目的：スレッドを跨いでも「何を決めたか」を見失わないための決定集。
> 注意：仕様の唯一の正は spec_*。本ログは spec_* への導線。

---

## D-20260105-XXX rooms予測モデルの標準セットを4本に固定

* Decision:

  * rooms予測の標準モデルは `recent90` / `recent90w` / `pace14` / `pace14_market` の4本を主軸とし、以後の比較・表示・運用はこの4本を基本とする（`adj` は主ライン外）。
* Why:

  * 市況急変で過去寄りモデルが過大予測になりやすく、直近ペース反映モデルを標準化して運用判断を安定させるため。
* Spec link:

  * docs/spec_overview.md: （予測モデル体系の概要・UI表示方針の追記）
  * docs/spec_models.md: （roomsモデル一覧・推奨/非推奨の区分）
  * docs/spec_data_layer.md: なし
  * docs/spec_evaluation.md: （比較対象モデルの前提として追記）
* Status: 未反映

## D-20260105-XXX pace14のPF定義とclip初期値を固定（通常/スパイク）

* Decision:

  * PF（pace factor）は差分の強弱ではなく **倍率（比率）**として扱う。
  * PFの通常clip初期値は **0.7〜1.3** に固定する。
  * スパイク時の強clip初期値は **0.85〜1.15** に固定する。
* Why:

  * 倍率移植の方が安定し、clipで補正の暴れを抑えて事故率を下げられるため。
* Spec link:

  * docs/spec_overview.md: （pace14導入の狙い・直感説明）
  * docs/spec_models.md: （pace14/pace14_marketの計算定義、PF/clip既定値）
  * docs/spec_data_layer.md: なし
  * docs/spec_evaluation.md: なし
* Status: 未反映

## D-20260105-XXX スパイク判定はSP-A（機械判定＋診断表示）を標準運用に固定

* Decision:

  * スパイク判定は **SP-A**（機械判定）を標準とする。
  * スパイク判定された日はフラグ表示し、診断情報（その日のΔ、q_hi/q_lo、PF、適用clip=通常/強）を表示する。
* Why:

  * 例外日を握りつぶさず透明化し、現場が「なぜこの日だけ挙動が違うか」を説明・判断できるようにして運用事故を減らすため。
* Spec link:

  * docs/spec_overview.md: （例外処理を透明化する運用方針の追記）
  * docs/spec_models.md: （スパイク判定SP-Aの定義、診断表示項目、強clip適用）
  * docs/spec_data_layer.md: なし
  * docs/spec_evaluation.md: なし
* Status: 未反映

## D-20260105-XXX 予測曲線の生成方式と「日別Forecastとの最終着地一致」を必須要件に固定

* Decision:

  * BookingCurve等の予測曲線は **「最終着地 × baselineの累積比率（cum_ratio）配分」**で生成する（方法1）。
  * **日別Forecastの最終着地と曲線の最終値を一致**させることを必須要件とする。
* Why:

  * 画面間で最終値がズレると誤解・運用事故の最大要因になるため、仕様として固定する必要がある。
* Spec link:

  * docs/spec_overview.md: （UI間整合の原則の追記）
  * docs/spec_models.md: （曲線生成の方式・前提・一致要件）
  * docs/spec_data_layer.md: なし
  * docs/spec_evaluation.md: なし
* Status: 未反映

## D-20260105-XXX BookingCurveのbaselineはrecent90、avg線は廃止に固定

* Decision:

  * BookingCurveタブのbaseline（薄青の基準カーブ）は **`recent90`** を採用する。
  * `avg（3ヶ月平均）` の線は **表示不要として廃止**する。
* Why:

  * avgは悲観寄りになりやすく基準線として誤解を生むため、recent90に統一して判断のブレを減らす。
* Spec link:

  * docs/spec_overview.md: （画面上の線の意味の追記）
  * docs/spec_models.md: （baselineの定義）
  * docs/spec_data_layer.md: なし
  * docs/spec_evaluation.md: なし
* Status: 未反映

## D-20260105-XXX 欠損補完は「表示用のみ」先行導入し、適用範囲を固定

* Decision:

  * 欠損補完の切替は **表示用のみ**として先行導入し、モデル計算には当面影響させない。
  * 適用範囲は **BookingCurve＋MonthlyCurve** に固定し、日別Forecastは後回しとする。
* Why:

  * 計算に混ぜると再現性・評価が崩れやすいので、まず視覚補助として安全に導入するため。
* Spec link:

  * docs/spec_overview.md: （欠損補完の目的と適用範囲の追記）
  * docs/spec_models.md: なし
  * docs/spec_data_layer.md: （欠損の扱い・表示補完の位置づけ）
  * docs/spec_evaluation.md: なし
* Status: 未反映

## D-20260105-XXX LT_DATAを rooms/pax/revenue の3ファイルへ拡張し、revenue定義を固定

* Decision:

  * LT_DATAは **rooms/pax/revenue の3ファイル**で運用する（データレイヤー変更を前提に進める）。
  * revenue（ADR定義A）は **税抜宿泊売上のみ**で統一し、朝食等は混ぜない。
* Why:

  * roomsだけでは売上予測・評価の土台にならず、下流の整合（ADR/RevPAR等）にも拡張できないため。
* Spec link:

  * docs/spec_overview.md: （予測対象指標の拡張の追記）
  * docs/spec_models.md: （revenue/ADR定義、指標の前提）
  * docs/spec_data_layer.md: （LT_DATAの構造・命名・出力規約の更新）
  * docs/spec_evaluation.md: （rooms以外の評価指標の前提追記）
* Status: 未反映

## D-20260105-XXX phase_biasは「月別×フェーズ×強度3段階」、保存先はlocal_overrides、適用先はrevenueのみで固定

* Decision:

  * phase_bias入力は **月別（当月/翌月/翌々月）×フェーズ（悪化/中立/回復）×強度3段階**（スライダー無し）で固定する。
  * phase_biasの保存先は **local_overrides（端末ローカル）**に固定する。
  * phase_biasの適用先は当面 **revenueのみ**（roomsのpace14_marketとは独立）に固定する。
* Why:

  * 人が違和感に応じて補正できる余地を残しつつ、複数人運用の混乱を避け、評価比較の前提を崩さないため。
* Spec link:

  * docs/spec_overview.md: （手動補正の位置づけ・運用導線）
  * docs/spec_models.md: （phase_biasの定義・適用範囲）
  * docs/spec_data_layer.md: （local_overridesの役割・保存項目）
  * docs/spec_evaluation.md: （phase_bias有無の評価前提の追記）
* Status: 未反映

## D-20260105-XXX 出力は生値、丸めはGUI表示のみ（rooms/pax=100、revenue=10万円）に固定

* Decision:

  * 日別ForecastのCSV出力は **丸め無し（生値）**を標準とする。
  * 報告資料向けの丸めは **GUI表示のみ**で行い、初期の丸め単位は **rooms/pax=100単位、revenue=10万円単位**に固定する。
* Why:

  * 生値を失うと評価・再現性が壊れる一方、報告用途には視認性が必要なため（役割分離）。
* Spec link:

  * docs/spec_overview.md: （表示と出力の役割分離の追記）
  * docs/spec_models.md: なし
  * docs/spec_data_layer.md: （CSVは生値であることの明記）
  * docs/spec_evaluation.md: （評価は生値ベースであることの明記）
* Status: 未反映

## D-20260105-XXX ベストモデル評価基準はM-1_END固定を優先し、UIは2段表示を採用

* Decision:

  * ベストモデル評価基準は当面 **M-1_END（前月末時点）固定**を最優先とする。
  * BookingCurve/日別Forecastのベスト表示は **M-1_ENDベスト＋ALL平均ベスト**の2段表示を採用する。
* Why:

  * 評価期間が可変だと現場が優先すべき軸を誤解しやすく、最重要の運用タイミング（M-1_END）に揃えて判断を安定させるため。
* Spec link:

  * docs/spec_overview.md: （評価の使い方・優先軸の追記）
  * docs/spec_models.md: なし
  * docs/spec_data_layer.md: なし
  * docs/spec_evaluation.md: （ベストモデル定義、M-1_END固定、UI表示方針）
* Status: 未反映

## D-20260109-XXX Revenue予測V1の定義（税抜宿泊売上＋OH基準ADR×phase）

* Decision:

  * revenue（ADR定義A）は **税抜宿泊売上のみ**（朝食等は含めない）で統一する。
  * revenue予測（V1）は **`OH売上 + remaining_rooms × adr_pickup_est`** で算出する。
  * `adr_pickup_est` は **`OH ADR × phase_factor`**（phase_bias）を基本とし、当面はこの形をV1として固定する（DOR収束/曜日差はV2）。
* Why:

  * まず破綻しにくい最小V1を固定し、運用・評価を回せる土台を先に作るため。
* Spec link:

  * docs/spec_overview.md: 売上予測のスコープ（rooms/pax/revenue）追記予定
  * docs/spec_models.md: 売上予測V1（ADR推定/式/対象外売上）追記予定
  * docs/spec_data_layer.md: revenue系Forecast列（定義・単位・raw出力）追記予定
  * docs/spec_evaluation.md: （必要なら）revenue評価の対象/指標の扱い追記予定
* Status: 未反映

## D-20260109-XXX phase_biasの適用範囲と保存先（revenueのみ・local_overrides）

* Decision:

  * phase_bias は **手動UI入力（3ヶ月×3フェーズ×強度3）** を基本とし、保存先は **local_overrides（端末ローカル）** とする。
  * 適用先は **当面 revenue のみ**（rooms予測とは独立）とし、影響範囲を固定する。
* Why:

  * roomsへ波及させると事故率が上がるため、まずは意思決定で効くrevenueに限定して導入する。
* Spec link:

  * docs/spec_overview.md: local_overrides運用（端末ローカル設定）追記予定
  * docs/spec_models.md: phase_bias UI仕様／適用範囲（revenueのみ）追記予定
  * docs/spec_data_layer.md: phase_bias保存データ（場所・キー）追記予定
  * docs/spec_evaluation.md: （必要なら）phase_bias適用有無の評価条件追記予定
* Status: 未反映

## D-20260109-XXX 「CSVはraw」「丸めはGUI」＋月次丸めは配分整合で行う

* Decision:

  * 「CSVは生値（raw）」を運用ルールとして固定し、資料用の大きい丸め（例：rooms/pax=100単位、rev=10万円単位）を **CSVに焼かない**。
  * 月次丸めは **GUIチェックボックスでON/OFF**できるものとし、ON時は「月次丸めゴール」に合わせて **日別へ配分して整合**を取る（末日だけ調整はしない）。
  * 丸め後は派生指標（例：PU Exp / OCC等）を **再計算**する前提を固定する。
* Why:

  * 再現性（評価/検証）と現場資料（丸め表示）を分離し、誤読とデータ劣化を防ぐため。
* Spec link:

  * docs/spec_overview.md: 出力と表示の責務分離（raw vs 表示丸め）追記予定
  * docs/spec_models.md: 月次丸め（整合配分）と派生指標再計算の扱い追記予定
  * docs/spec_data_layer.md: Forecast CSVはraw、GUIのみ丸め・表示単位の規約追記予定
  * docs/spec_evaluation.md: （必要なら）丸めON/OFF時の評価の扱い注意追記予定
* Status: 未反映

## D-20260109-XXX pax_capの既定（未入力時は直近6ヶ月ACT paxのp99）

* Decision:

  * paxには理論上のcapを持たせる。
  * pax_cap未入力時は max ではなく **p99（上位1%）** を採用する。
  * p99の母集団は **直近Nヶ月の各日ACT pax**（運用は **直近6ヶ月** をデフォルト）とする。
* Why:

  * 外れ値（max）依存を避けつつ、満室近辺での“限界突破”を抑制するため。
* Spec link:

  * docs/spec_overview.md: cap概念（rooms/pax）追記予定
  * docs/spec_models.md: pax_cap算出（p99、lookback=6ヶ月）追記予定
  * docs/spec_data_layer.md: cap入力・既定値の取り扱い追記予定
  * docs/spec_evaluation.md: （必要なら）cap適用時の評価条件追記予定
* Status: 未反映

## D-20260109-XXX TopDown（RevPAR）を別窓で提供し、予測範囲はASOF基準で固定

* Decision:

  * TopDown（RevPAR）は **別窓（ポップアップ）**で提供する（別タブではない）。
  * 初期指標は **RevPARのみ**（ADR/OCCは後追い可）。
  * 表示する過去年数はデフォルト **直近6年**。
  * 予測範囲は **最新ASOF基準**で固定し、

    * 下限（月）は **「最新ASOFが属する月」起点**
    * 上限は **「最新ASOF + 90日後にかかる月まで」**
  * Forecast CSVが存在しない月は **載せない（欠損扱い）** をTopDown/日別で共通ルール化する。
* Why:

  * 座標系（基準）を固定して形状比較の違和感検知を強め、月選択で範囲がズレる混入バグを避けるため。
* Spec link:

  * docs/spec_overview.md: TopDown機能（別窓・対象指標・既定表示年数）追記予定
  * docs/spec_models.md: TopDownの予測範囲定義（ASOF月起点〜ASOF+90日）追記予定
  * docs/spec_data_layer.md: 「Forecast未作成月は欠損」規約追記予定
  * docs/spec_evaluation.md: （必要なら）TopDownの利用目的（意思決定補助）注意追記予定
* Status: 未反映

## D-20260109-XXX 設定はホテル別を原則（丸め単位・TopDown期首月）

* Decision:

  * 月次丸め単位（rooms/pax/rev）は **ホテル別設定**で保持する方針とする（将来拡張を前提に固定）。
  * TopDownの年度開始月（期首月、現状は6月固定）は **V2でホテル別設定化**する方針とする。
* Why:

  * マルチホテル/外部展開で差が出る前提を、コード分岐ではなく設定で吸収するため。
* Spec link:

  * docs/spec_overview.md: 設定の階層（ホテル別）追記予定
  * docs/spec_models.md: 丸め単位・期首月のパラメータ化方針追記予定
  * docs/spec_data_layer.md: hotels.json等の設定項目追加方針追記予定
  * docs/spec_evaluation.md: 影響なし（原則不要）
* Status: 未反映

## D-20260110-XXX TopDown予測範囲は「最新ASOF+90日後にかかる月まで」＋描画対象は“全日程揃い”のみ

* Decision:

  * TopDown RevPAR の予測範囲上限は「最新ASOF + 90日後にかかる月まで」とする。
  * TopDownで描画・比較に使う月は「日別Forecastが全日程分そろう月のみ」とし、CSVが出ていても一部日程のみの月（INCOMPLETE）は除外する。
* Why:

  * CSV出力の有無だけでは不完全予測（月内欠損）が混入し、スパイク等の誤読・誤判断を招くため。
* Spec link:

  * docs/spec_overview.md: TopDown RevPAR（予測範囲の定義・表示対象月の条件）追記
  * docs/spec_models.md: 影響なし
  * docs/spec_data_layer.md: INCOMPLETE判定（全日程未充足）の定義と、可視化/比較からの除外ルール追記
  * docs/spec_evaluation.md: 影響なし
* Status: 未反映

## D-20260110-XXX 回転モードは「再計算なしの再描画」で切替する

* Decision:

  * TopDown RevPAR の表示モード「回転」は、再計算を伴わない再描画（表示だけ切替）とする。
* Why:

  * 再計算は待ち時間・不具合・運用ロスを増やす一方、回転は表現上の切替であり結果差異を生まないため。
* Spec link:

  * docs/spec_overview.md: TopDown RevPAR（表示モード切替の挙動：再計算有無）追記
  * docs/spec_models.md: 影響なし
  * docs/spec_data_layer.md: 影響なし
  * docs/spec_evaluation.md: 影響なし
* Status: 未反映

## D-20260110-XXX p10–p90帯はA/Cの二本立て（ハイブリッド表示）を正式採用

* Decision:

  * p10–p90帯は二系統で扱う：

    * A：直近着地月アンカー帯
    * C：前月アンカー帯
  * UIは「同時表示」または「片方のみ表示」を選べる（ハイブリッド運用）とする。
* Why:

  * 3ヶ月予測運用では、当月基準（A）だけでなく前月起点のレンジ（C）も意思決定に必要で、単一帯だと解釈が固定されるため。
* Spec link:

  * docs/spec_overview.md: TopDown RevPAR（p10–p90帯A/Cの意味・表示ルール）追記
  * docs/spec_models.md: 影響なし
  * docs/spec_data_layer.md: p10–p90算出に使う分布（過去年の月次比率分布）とアンカー入力（着地/Fc）を明記する追記
  * docs/spec_evaluation.md: 影響なし
* Status: 未反映

## D-20260110-XXX 前月アンカー（C）は「前月が予測でもOK」＋予測欠損は“最後の予測”を起点に延長

* Decision:

  * 前月アンカー帯（C）のアンカーは「前月が予測値でも可」とする（確定月に限定しない）。
  * 予測が存在しない期間は「直近で存在する最後の予測」を起点として帯を延長してよい。
* Why:

  * 予測レンジの解釈を“予測の連鎖”として扱う運用ニーズがあり、確定月限定だと帯が途切れて運用価値が落ちるため。
* Spec link:

  * docs/spec_overview.md: p10–p90帯C（前月アンカー）のアンカー定義と欠損時挙動追記
  * docs/spec_models.md: 影響なし
  * docs/spec_data_layer.md: 「予測欠損」と「最後の予測」の扱い（可視化側の補完ルール）追記
  * docs/spec_evaluation.md: 影響なし
* Status: 未反映
