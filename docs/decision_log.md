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
