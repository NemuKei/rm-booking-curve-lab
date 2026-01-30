# Decision Log（横断決定ログ）

> 目的：スレッドを跨いでも「何を決めたか」を見失わないための決定集。
> 注意：仕様の唯一の正は spec_*。本ログは spec_* への導線。

---

## D-20251218-001 daily snapshots 更新モードを3段に固定（FAST/FULL_MONTHS/FULL_ALL）

* Decision:

  * daily snapshots 更新は 3モードで運用を固定する：FAST / FULL_MONTHS / FULL_ALL。
  * FAST：宿泊月フィルタ（GUIの直近4ヶ月等）＋ASOF固定窓（latest ASOF から buffer_days=14 日戻し）で高速更新。
  * FULL_MONTHS：宿泊月（期間指定）で更新、ASOF窓は設けずフルスキャン（過去取り込み用途）。
  * FULL_ALL：全量再生成は例外運用として扱う。
* Why:

  * 週次運用の速度要件はASOF側の窓で担保しつつ、更新漏れ・運用ミスを宿泊月単位で抑えるため。
  * 期間指定時は過去取り込みが主目的で、速度より網羅性を優先するため。
* Spec link:

  * docs/spec_overview.md: daily snapshots運用（更新モードの位置づけ）追記予定
  * docs/spec_models.md: 影響なし
  * docs/spec_data_layer.md: daily snapshots build modes（FAST/FULL_MONTHS/FULL_ALL、ASOF窓=latest-14d、FULL_MONTHSはASOF窓なし）追記予定
  * docs/spec_evaluation.md: 影響なし
* Status: 未反映

## D-20251218-002 FULL_ALL は誤爆防止の奥配置＋事前見積り＋強制ログ＋最終確認を必須化

* Decision:

  * FULL_ALL は通常導線に置かず、マスタ設定など普段触らない場所に配置する。
  * 実行前に対象ファイル件数と概算時間（files/sec を用いた見積り）を表示する。
  * 実行ログは `output/logs/full_all_YYYYMMDD_HHMM.log` へ強制保存する。
  * 実行には最終確認（例：確認文字列入力 / CLIでは `--yes` または `--confirm-full-all FULL_ALL`）を必須とする。
* Why:

  * 全量再生成は負荷・所要時間・誤操作リスクが高く、誤爆時の機会損失が大きい。
  * 事後検証/再現性のためログを必須化する必要がある。
* Spec link:

  * docs/spec_overview.md: 危険操作のガード方針（GUI/CLI）追記予定
  * docs/spec_models.md: 影響なし
  * docs/spec_data_layer.md: full rebuild運用（実行ガード・ログ保存）追記予定
  * docs/spec_evaluation.md: 影響なし
* Status: 未反映

## D-20251218-003 monthly_curve は LT_DATA フォールバック禁止、daily_snapshots から生成→保存→描画を正とする

* Decision:

  * monthly_curve が無い場合は、`daily_snapshots_{hotel}.csv` からその場で monthly_curve を生成し、CSV保存したうえで描画する。
  * daily_snapshots が無い/薄くて生成できない場合は、更新（FAST/FULL_MONTHS/FULL_ALL）を促すエラーにする。
  * LT_DATA から monthly_curve へフォールバックする挙動は採用しない。
* Why:

  * LT_DATA 由来のカーブは定義が異なり、正しい月次ブッキングカーブにならず意思決定を誤らせるため。
  * 生成元を一本化しないと、表示結果の整合性が崩れて検証不能になるため。
* Spec link:

  * docs/spec_overview.md: monthly_curve生成・描画の優先順位（missing時の挙動）追記予定
  * docs/spec_models.md: 影響なし
  * docs/spec_data_layer.md: monthly_curve生成ルート（daily_snapshots→monthly_curve）とフォールバック禁止を追記予定
  * docs/spec_evaluation.md: 影響なし
* Status: 未反映

## D-20251220-001 月次カーブ生成の正を daily_snapshots 基準に統一（LT_DATAフォールバック禁止）

* Decision:

  * 月次カーブ（monthly_curve）は `daily_snapshots` から生成する方式を正とする。
  * 月次カーブ生成で `LT_DATA` をフォールバック経路として使用しない（禁止）。
  * 月次LT定義は **ASOFベース（month_end - asof_date）** を採用する。
* Why:

  * 月次カーブのLT定義分裂が曲線崩れを引き起こし、LT_DATA由来の不整合が再発するため。
* Spec link:

  * docs/spec_overview.md: （データ生成フロー概要：monthly_curve生成経路の正を追記）
  * docs/spec_models.md: （参照のみ：必要なら注記）
  * docs/spec_data_layer.md: （monthly_curveの生成元とLT定義、LT_DATA非フォールバックを追記）
  * docs/spec_evaluation.md: （影響小／参照のみ）
* Status: 未反映

## D-20251220-002 monthly_curveはNaN保持で保存し、欠損補完（NOCB）はGUI表示直前のみ

* Decision:

  * `monthly_curve` 生成物は **rawのまま保存（NaN保持）** する。
  * 欠損補完（NOCB）は **GUI表示直前のみ** 適用し、データレイヤには反映しない。
  * NOCBの向きは「欠損LTは**次のASOF（より新しい観測）**で埋める」前提を維持する。
* Why:

  * データレイヤで補完すると監査・再現性・後続分析に影響が出るため。表示用途に限定するのが思想に合うため。
* Spec link:

  * docs/spec_overview.md: （必要なら思想として注記）
  * docs/spec_models.md: （モデル入力時の前提として追記）
  * docs/spec_data_layer.md: （欠損の取り扱い方針：NaN保持と補完適用点を明文化）
  * docs/spec_evaluation.md: （評価時の前提として注記）
* Status: 未反映

## D-20251220-003 予測・評価は欠損補完せずサンプル除外を基本（0補完はしない）

* Decision:

  * 予測・評価の計算は当面 **欠損補完を行わず、欠損サンプルは除外**を基本とする。
  * 欠損の **0補完は採用しない**。
  * 補完モード等の導入は、まず「補完なし」で精度・影響を確認してから判断する。
* Why:

  * 0補完は歪みが大きく、未来リークやACT整合の副作用も出やすい。まず安全側（除外）でベースラインを確立するため。
* Spec link:

  * docs/spec_overview.md: （必要なら注記）
  * docs/spec_models.md: （モデル入力の欠損値取扱い：除外を基本と明記）
  * docs/spec_data_layer.md: （NaN保持思想との接続として補足）
  * docs/spec_evaluation.md: （評価対象の除外ルール、ACT欠け時の扱いの導線）
* Status: 未反映

## D-20251220-004 欠損検知は「運用（入れ忘れ）/監査（歴史ギャップ）」の2モードに分離し、運用ASOF窓は180日

* Decision:

  * 欠損検知（missing_report）は **運用/監査の2モード**に分離する。
  * 運用モードのASOF窓は **180日** とする（期待ASOFは日次、severityで緩急）。
  * 運用モードは **ASOF丸抜け（asof_missing）** と **raw_missing** を別種として扱い、asof_missingは取り込み対象外とする。
  * 監査モードは **STAY MONTHの最古〜最新範囲** に限定し、期待ASOFは日次で生成する。
* Why:

  * 観測ASOF起点だとASOF丸抜けを検知できず、古い期間の粒度差で欠損が爆発して運用不能になるため。目的別に分離が必要。
* Spec link:

  * docs/spec_overview.md: （運用フロー：欠損チェック/監査の役割分担を追記）
  * docs/spec_models.md: （欠損検知→モデル計算の前提導線）
  * docs/spec_data_layer.md: （missing_reportのモード、ASOF窓180日、出力種別を追記）
  * docs/spec_evaluation.md: （ACT欠け/データ欠け時の評価除外・遮断の導線）
* Status: 未反映

## D-20251220-005 RAW取り込みはサブフォルダ許可＋(target_month, asof)重複は即エラー停止

* Decision:

  * RAWデータはホテル配下で **サブフォルダ配置を許可**（再帰探索で取り込み対象とする）。
  * 同一キー **(target_month, asof)** の重複（拡張子違い含む）は **即エラー停止**し、両パスを表示する。
  * 拡張子は「読めるものは許可、読めないものは明示エラー」を基本とする。
* Why:

  * サブフォルダ運用の利便性が高い一方、重複は事故に直結するため安全側で止める必要がある。拡張子混在にも現実的に対応するため。
* Spec link:

  * docs/spec_overview.md: （入力データの前提・運用手順の注記）
  * docs/spec_models.md: （入力整合がモデル前提である旨の導線）
  * docs/spec_data_layer.md: （raw配置ルール、探索範囲、重複扱い、拡張子方針を追記）
  * docs/spec_evaluation.md: （影響小／注記レベル）
* Status: 方針変更（D-20260129-XXXで上書き）
* Note: 重複キーは STOP せず、後勝ち（tie-break: mtime→path）で 1件に解決して運用継続。

## D-20251224-001 欠損検知は ops/audit の2モードで固定する

* Decision:

  * 欠損検知は **ops（運用）** と **audit（監査）** の2モードに分離して運用する。
  * ops は入れ忘れ検知を主目的とし、**asof_missing（ASOF丸抜け）** と **raw_missing（(ASOF, STAY MONTH)欠落）** を区別して扱う。
  * audit は棚卸しを主目的とし、期待キーの作り方を ops と分ける（下記の別Decision参照）。
* Why:

  * 単一モードだと、ASOF丸抜けが検知不能になったり、古い月が大量欠損に見えるノイズが増えるため。
* Spec link:

  * docs/spec_overview.md: 欠損検知（ops/audit）導線・運用目的の整理（追記予定）
  * docs/spec_models.md: （追記予定：欠損補完しない前提での可視化/評価の位置づけ）
  * docs/spec_data_layer.md: 欠損カテゴリ定義（asof_missing/raw_missing）とモード分離（追記予定）
  * docs/spec_evaluation.md: （必要なら）欠損除外/扱いの前提（追記予定）
* Status: 未反映

## D-20251224-002 audit 欠損の対象範囲は STAY MONTH の min..max に限定し、未来ASOFは欠損扱いしない

* Decision:

  * audit 欠損抽出は、raw から観測された **STAY MONTH の最古〜最新（min..max）の連続月**の範囲に限定する（範囲外は欠損と見なさない）。
  * **asof_date > today（未来ASOF）** は欠損として出さない（キャップする）。
* Why:

  * 古い月が大量欠損に見える誤検知（ノイズ）を潰し、棚卸しとして意味のある範囲に限定するため。
  * 未来ASOFは入力され得ないため、欠損扱いすると監査結果が壊れるため。
* Spec link:

  * docs/spec_overview.md: 監査モードの目的/対象範囲（追記予定）
  * docs/spec_models.md: （該当薄め）
  * docs/spec_data_layer.md: audit の期待キー生成・future ASOF cap・対象月レンジ（追記予定）
  * docs/spec_evaluation.md: （該当薄め）
* Status: 未反映

## D-20251224-003 欠損のみ取り込みは当面 raw_missing のみを対象にする

* Decision:

  * 「欠損のみ取り込み」は **ops レポートを入力**にし、**raw_missing のキーだけ**を対象として再取り込み/再生成する。
  * **asof_missing は対象外**（ASOF自体が無いケースのため、取り込み対象としては扱わない）。
* Why:

  * asof_missing は「入力ファイルが存在しない」問題であり、欠損キー駆動での再取り込みに向かないため。
  * 運用上は raw を追加して ops レポートを再生成すればリストから消えるため、対象外でも実害が少ないため。
* Spec link:

  * docs/spec_overview.md: 欠損のみ取り込みの導線/前提（追記予定）
  * docs/spec_models.md: （該当薄め）
  * docs/spec_data_layer.md: raw_missing/asof_missing の扱い、再取り込み対象の制約（追記予定）
  * docs/spec_evaluation.md: （該当薄め）
* Status: 未反映

## D-20251224-004 データレイヤは NaN 保持、欠損補完は GUI 表示直前のみとする

* Decision:

  * monthly_curve / daily_snapshots などデータレイヤは **NaN を保持**して保存し、欠損補完（NOCB等）は **GUI表示直前**に限定する。
  * 予測/評価は原則「欠損補完せず、サンプル除外」を基本方針とする（補完モードは後で検討）。
* Why:

  * どこで補完したかが不明確だと、曲線・予測・評価の整合が壊れ、再現性が落ちるため。
* Spec link:

  * docs/spec_overview.md: 全体方針（NaN保持/補完位置）整理（追記予定）
  * docs/spec_models.md: NOCBは表示直前のみ、評価は欠損除外が基本（追記予定）
  * docs/spec_data_layer.md: データ層のNaN保持ルール（追記予定）
  * docs/spec_evaluation.md: 欠損除外の前提（追記予定）
* Status: 未反映

## D-20251224-005 nface RAW 変換は安全側固定（宿泊日=A列のみ、判定不能はSTOP）

* Decision:

  * nface RAW の宿泊日は **A列が唯一の正**とし、A列日付が無いRAWは対象外（STOP）。
  * 「2行持ち判定」は **空白の有無＋同日付連続**も考慮し、**判定不能はSTOP**（部分取り込みはしない）。
  * ASOF は **セル優先**、セル欠落時のみ **ファイル名からfallback**する。
* Why:

  * すべての派生レイアウトに対応しようとすると誤取り込みリスクが増えるため。安全側に倒し、早期に異常を顕在化させる方が運用に強い。
* Spec link:

  * docs/spec_overview.md: adapter の安全側方針（追記予定）
  * docs/spec_models.md: （該当薄め）
  * docs/spec_data_layer.md: RAW→daily_snapshots の前提（A列唯一の正、STOP条件、ASOF優先順）（追記予定）
  * docs/spec_evaluation.md: （該当薄め）
* Status: 未反映

## D-20251224-006 リリースZIPは “必要物のみ” 同梱し、ログは最新N本かつ full_all を優先する

* Decision:

  * `make_release_zip.py` により、共有ZIPは **必要物のみ**を同梱する運用を基本とする（profile/with-output-samplesで制御）。
  * 同梱ログは `output/logs` を基本の保存先とし、同梱は **最新N本**に限定する。
  * 最新ログ選定は **full_all_*.log を最優先**し、次点で他ログを補完する。
* Why:

  * 共有データの肥大化と漏洩リスクを抑えつつ、再現に必要な証跡（最新ログ）だけ残すため。
  * ログ種別が複数ある状況で、再現の基準を full_all に寄せることで参照ブレを減らすため。
* Spec link:

  * docs/spec_overview.md: 共有/引き継ぎ（zip作成）運用（追記予定）
  * docs/spec_models.md: （該当薄め）
  * docs/spec_data_layer.md: output/logs 配下のログ運用（追記予定）
  * docs/spec_evaluation.md: （該当薄め）
* Status: 未反映

## D-20251224-007 共有ZIPの命名規約は YYYYMMDD_HHMM を基本とし、必要なら commit で一意化する

* Decision:

  * 共有ZIPのファイル名には **日付だけでなく時刻（YYYYMMDD_HHMM）**を含める。
  * 同日複数回やり取り等で衝突リスクがある場合は、**short commit hash** を付与して一意化する運用を許可する。
* Why:

  * VERSION.txt を開く前に一覧で誤送付/誤展開を防ぐ必要があるため（参照齟齬の予防）。
* Spec link:

  * docs/spec_overview.md: 共有物の命名規約（追記予定）
  * docs/spec_models.md: （該当薄め）
  * docs/spec_data_layer.md: （該当薄め）
  * docs/spec_evaluation.md: （該当薄め）
* Status: 未反映

## D-20251226-001 Range rebuild の既定パラメータと対象月算出を固定

* Decision:

  * Phase 1.6（Range rebuild）の既定値を **buffer_days=30** とする（安全側）。
  * stay_months は **asof_max から +120日先までの月（両端含む）** を自動算出し、さらに **前月を常に含める**（月初例外はこの固定で吸収し、特判は持たない）。
* Why:

  * 月初や月長（2月等）で「翌3〜4ヶ月」の揺れが出る問題を、日次（+120日）で一意に解消できる。
  * 前月を常時含めることで、月初取り込みタイミング差による取り漏れ・分岐の複雑化を避ける。
  * 運用で「安全側」へ寄せつつ、対象範囲の自動化で作業負荷を下げる。
* Spec link:

  * docs/spec_data_layer.md: （Partial build / Range rebuild / 対象月算出の節に追記予定）
  * docs/spec_overview.md: （運用導線：更新対象の既定値の節に追記予定）
  * docs/spec_models.md: （必要なら：LT_DATA更新の前提として参照）
  * docs/spec_evaluation.md: （不要）
* Status: 未反映

## D-20251226-002 LT_DATA(4ヶ月) 導線は Range rebuild に統合して運用を一本化

* Decision:

  * GUIの「LT_DATA(4ヶ月)」実行は、裏側の更新方式を **Range rebuild（Phase 1.6）** に置き換え、日常運用の更新導線を一本化する。
* Why:

  * 「鮮度warningで気づく→更新実行」の運用が既に成立しており、更新手段が複数あると迷い・手戻りが増える。
  * 部分更新（範囲限定 rebuild）を標準動線に置くことで、重いFULL_ALL依存を減らせる。
* Spec link:

  * docs/spec_overview.md: （GUI導線 / LT_DATA更新の節に追記予定）
  * docs/spec_data_layer.md: （Partial build / Range rebuild の運用位置づけに追記予定）
  * docs/spec_models.md: （不要〜軽微）
  * docs/spec_evaluation.md: （不要）
* Status: 未反映

## D-20251226-003 N@FACE RAW の不変条件を固定し、判定不能は STOP（誤取得防止優先）

* Decision:

  * N@FACE「売上予算実績表」RAWの入力前提を固定する：

    * **日付はA列**（判定は **9行目以降のみ** を対象）
    * **OHは E/F/G 列**（必須）
    * 曜日列は **C列**（存在する場合の補助情報。必須にはしない）
  * 前提逸脱（列移動等）や判定不能は **推測せず STOP（layout_unknown）** とし、欠損扱いで運用する。
* Why:

  * 最大事故は「予算行をOHとして誤取得」すること。ここを避けるには安全側STOPが最小コスト。
  * A1等への手入力日付が混入する運用があり、上部セルに引っ張られると誤判定するため（start_row=9固定）。
  * 現場加工の多様性はあるが、列の前提まで崩す加工を許すと仕様が破綻する。
* Spec link:

  * docs/spec_data_layer.md: （RAW入力の前提 / アダプタ要件の節に追記予定）
  * docs/spec_overview.md: （安全側STOP方針・運用の注意に追記予定）
  * docs/spec_models.md: （不要）
  * docs/spec_evaluation.md: （不要）
* Status: 未反映

## D-20251226-004 欠損検知は ops/audit の2モード運用とし、auditは対象月範囲を制限

* Decision:

  * 欠損検知は **運用（ops）** と **監査（audit）** の2モードに分けて運用する。
  * audit は「古い月が大量欠損に見えるノイズ」を避けるため、**最古〜最新のSTAY MONTH範囲に限定**して欠損抽出する。
  * **asof_missing（ASOF丸抜け）** は欠損として検知対象に含める。
* Why:

  * ops は日々の「入れ忘れ検知・運用支援」、audit は「棚卸し」で目的が異なる。単一出力だとノイズで運用不能になる。
  * asof_missing は「欠損として上がらない」という設計上の盲点になり得るため、検知対象に含める必要がある。
* Spec link:

  * docs/spec_data_layer.md: （missing_report / 欠損検知モードと対象範囲の節に追記予定）
  * docs/spec_overview.md: （GUIの欠損チェック導線に追記予定）
  * docs/spec_models.md: （不要）
  * docs/spec_evaluation.md: （不要）
* Status: 未反映

## D-20251226-005 マスタ設定タブは「最新ASOF」を重複表示せず、欠損検査 remember/未実施など運用警告へ寄せる

* Decision:

  * 最新ASOF（観測値）の通知は鮮度ラベル等で担保できるため、マスタ設定タブで「最新ASOF」を重複表示する設計は避ける。
  * マスタ設定タブで表示するなら、**欠損検査の未実施/要確認**など、運用判断に直結する警告へ寄せ、**観測最新ASOFと混同しない**表現・配置にする。
  * なお現状の「最新ASOF:要確認」は **stale_latest_asof（鮮度ズレ）** を指し、欠損そのものではない前提で扱う。
* Why:

  * 同じ「最新ASOF」ラベルで参照元や意味が違うと、運用判断を誤る（安心/誤警戒）リスクが高い。
  * マスタ設定の役割は“運用の注意喚起”であり、観測値の提示は他タブで十分。
* Spec link:

  * docs/spec_overview.md: （GUI表示ルール / 警告の意味の節に追記予定）
  * docs/spec_data_layer.md: （stale_latest_asof と missing の区別が必要なら追記予定）
  * docs/spec_models.md: （不要）
  * docs/spec_evaluation.md: （不要）
* Status: 未反映

## D-20251226-006 FULL_ALLでA列日付不足（start_row=9, found=0）は欠損扱いで運用許容

* Decision:

  * FULL_ALLで検出される **A列日付行不足（start_row=9, found=0）** は、推測での復旧は行わず **欠損扱いでOK** とする（取り込み不能として扱う）。
* Why:

  * 古いRAWや加工崩れの救済を仕様に入れると誤取り込みリスクが上がり、運用コストが増える。
  * 欠損として監査/棚卸しに回す方が安全で合理的。
* Spec link:

  * docs/spec_data_layer.md: （RAW取り込みエラーの扱い/STOP方針の節に追記予定）
  * docs/spec_overview.md: （運用上の許容/欠損扱いの注意に追記予定）
  * docs/spec_models.md: （不要）
  * docs/spec_evaluation.md: （不要）
* Status: 未反映

## D-20260103-001 APP_BASE_DIR（LOCALAPPDATA）基準へ“寄せ切り”を標準運用とする

* Decision:

  * 配布形態は「各端末ローカルにEXE配置」「端末ごと独立運用」を前提とする（共有フォルダ起動は前提にしない）。
  * 設定・出力・ログ・ACK・local_overrides などの実体保存先は、EXE配下ではなく **APP_BASE_DIR = `%LOCALAPPDATA%/BookingCurveLab/`** に統一する。
  * EXE配下には一切出力しない（移動リスク/汚染回避）。
* Why:

  * EXEの配置場所に依存すると、移動・権限・共有フォルダ運用で事故が起きやすく、再現性と保守性が落ちるため。
  * 端末ごとの独立運用に寄せることで、配布・運用の責務境界が明確になり、トラブルシュートも容易になるため。
* Spec link:

  * docs/spec_overview.md: 配布運用前提／ローカル保存先（APP_BASE_DIR）方針の追記
  * docs/spec_data_layer.md: 生成物（output/logs等）の保存先注記（論理パスと実体パスの関係）
  * docs/spec_models.md: 影響なし（想定）
  * docs/spec_evaluation.md: 影響なし（想定）
* Status: spec反映済

## D-20260103-002 欠損検査（ops）のACK運用を正式採用し、集計から除外する

* Decision:

  * ACKの対象は **opsのみ**（auditは対象外）。
  * ACK対象のseverityは **ERROR/WARNのみ**（それ以外は対象外）。
  * ACK済みは **運用集計（ERROR/WARN件数）から除外**する（ノイズ削減のため）。
  * 欠損一覧のデフォルト表示は **ACK済み非表示＝デフォルトON** とする。
  * 行の同一性キーは **kind + target_month + asof_date + path** を採用する。
* Why:

  * 「確定欠損」を毎回同じ警告として扱うと運用の意思決定が鈍り、確認コストが増えるため。
  * auditは統制目的（全期間の状態確認）であり、ACKで“見えなくする”と統制目的を損なうため。
  * 同一性キーは厳密すぎるとACKが効かず、緩すぎると別物まで消えるため、実務的な最小単位を固定する。
* Spec link:

  * docs/spec_overview.md: ops/auditの役割分担、ACK運用の位置づけ（運用ルールとして）
  * docs/spec_data_layer.md: missing_report_ops と missing_ack_ops の関係／集計除外ルール／同一性キー
  * docs/spec_models.md: 影響なし（想定）
  * docs/spec_evaluation.md: 影響なし（想定）
* Status: spec反映済

## D-20260103-003 初回テンプレ展開（初期化）失敗は握りつぶさず通知する

* Decision:

  * 初回起動時のテンプレコピー（例：hotels.json等）が失敗した場合は、**showerrorで通知＋ログに記録**する（無言で続行しない）。
* Why:

  * 初期導入時にテンプレが展開されないと、その後の挙動が“設定未反映”として誤解されやすく、原因追跡が困難になるため。
  * 失敗時は即時に明示して止血する方が、現場運用にとって安全で再現性が高い。
* Spec link:

  * docs/spec_overview.md: 起動時初期化の期待挙動／失敗時の通知方針
  * docs/spec_data_layer.md: 初期ファイル生成（テンプレ展開）の扱い・保存先注記
  * docs/spec_models.md: 影響なし（想定）
  * docs/spec_evaluation.md: 影響なし（想定）
* Status: spec反映済

## D-20260103-004 欠損監査（audit）は“全期間の状態確認＝統制用”として固定する

* Decision:

  * 欠損監査（audit）の定義を **「全期間の状態確認（統制用）」**で固定する。
  * ops（運用）とは目的が異なるため、ACKや集計除外など運用最適化の対象にはしない。
* Why:

  * 運用の効率化（ノイズ除去）と統制（全体の欠損状態把握）を混ぜると、どちらも中途半端になり誤判断が増えるため。
* Spec link:

  * docs/spec_overview.md: ops/auditの定義と使い分け
  * docs/spec_data_layer.md: auditレポートの出力・解釈（ACK対象外である旨）
  * docs/spec_models.md: 影響なし（想定）
  * docs/spec_evaluation.md: 影響なし（想定）
* Status: spec反映済

## D-20260105-001 rooms予測モデルの標準セットを4本に固定

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

## D-20260105-002 pace14のPF定義とclip初期値を固定（通常/スパイク）

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

## D-20260105-003 スパイク判定はSP-A（機械判定＋診断表示）を標準運用に固定

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

## D-20260105-004 予測曲線の生成方式と「日別Forecastとの最終着地一致」を必須要件に固定

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

## D-20260105-005 BookingCurveのbaselineはrecent90、avg線は廃止に固定

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

## D-20260105-006 欠損補完は「表示用のみ」先行導入し、適用範囲を固定

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

## D-20260105-007 LT_DATAを rooms/pax/revenue の3ファイルへ拡張し、revenue定義を固定

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

## D-20260105-008 phase_biasは「月別×フェーズ×強度3段階」、保存先はlocal_overrides、適用先はrevenueのみで固定

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

## D-20260105-009 出力は生値、丸めはGUI表示のみ（rooms/pax=100、revenue=10万円）に固定

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
※初期丸めは**rooms/pax=50単位**に変更（2026/1/23）

## D-20260105-010 ベストモデル評価基準はM-1_END固定を優先し、UIは2段表示を採用

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

## D-20260109-001 Revenue予測V1の定義（税抜宿泊売上＋OH基準ADR×phase）

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

## D-20260109-002 phase_biasの適用範囲と保存先（revenueのみ・local_overrides）

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

## D-20260109-003 「CSVはraw」「丸めはGUI」＋月次丸めは配分整合で行う

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

## D-20260109-004 pax_capの既定（未入力時は直近6ヶ月ACT paxのp99）

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

## D-20260109-005 TopDown（RevPAR）を別窓で提供し、予測範囲はASOF基準で固定

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

## D-20260109-006 設定はホテル別を原則（丸め単位・TopDown期首月）

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

## D-20260110-001 TopDown予測範囲は「最新ASOF+90日後にかかる月まで」＋描画対象は“全日程揃い”のみ

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

## D-20260110-002 回転モードは「再計算なしの再描画」で切替する

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

## D-20260110-003 p10–p90帯はA/Cの二本立て（ハイブリッド表示）を正式採用

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

## D-20260110-004 前月アンカー（C）は「前月が予測でもOK」＋予測欠損は“最後の予測”を起点に延長

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

## D-20260114-001 月次丸めは表示値のみ・着地済非改変・未来日配分で固定

* Decision:

  * 月次丸めは **display列（表/サマリ/CSV表示の整合）にのみ適用**し、内部forecast値は保持する。
  * **着地済（stay_date < ASOF）は一切触らない**（丸め・配分の対象外）。
  * 丸め差分の配分先は **対象月内 かつ stay_date >= ASOF の未来日だけ**に限定する。
* Why:

  * 予測本体を毀損せず、運用上必要な「表示整合」だけを担保するため。
  * 実績の改変リスクを排除し、説明可能性を確保するため。
  * 配分範囲を限定して副作用（翌月以降や過去日の汚染）を防ぐため。
* Spec link:

  * docs/spec_overview.md: 月次丸めの位置づけ（表示整合目的・実績非改変）
  * docs/spec_models.md: 月次丸めの仕様（displayのみ、着地済スキップ、配分先）
  * docs/spec_data_layer.md: （必要なら）出力CSVにおける表示値整合の取り扱い
  * docs/spec_evaluation.md: （必要なら）評価対象のデータがdisplay/forecastどちらかの注記
* Status: 未反映

## D-20260114-002 月次丸めの適用条件を「対象月内の未来日数N>=20」に固定

* Decision:

  * 月次丸めの適用は **対象月内の未来日数 N（stay_date >= ASOF かつ 対象月内）>= 20 のときのみ**とする。
  * N条件を満たさない場合は **丸め処理を行わない**。
* Why:

  * 小サンプル（月中盤以降など）での過剰調整を防ぎ、境界条件の納得感を確保するため。
  * 仕様として明確なON/OFF条件を持たせ、運用・検証を安定させるため。
* Spec link:

  * docs/spec_overview.md: 丸めの適用条件（閾値の定義）
  * docs/spec_models.md: 月次丸めの適用条件（N>=20）とNの定義（対象月内・stay_date>=ASOF）
  * docs/spec_data_layer.md: N算出に使う日付条件の定義（対象月/ASOF）
  * docs/spec_evaluation.md: （必要なら）N条件により出力が変わる点の注記
* Status: 未反映

## D-20260114-003 丸め単位はホテル別設定（Rooms/Pax/Rev）とし、丸めOFF時は単位を無視

* Decision:

  * 月次丸め単位は **ホテル別設定**として Rooms / Pax / Rev をそれぞれ持てるようにする。
  * **月次丸めOFF時は単位設定を無視**し、UIも連動して無効化する（運用上の誤操作防止）。
* Why:

  * ホテルごとの規模・粒度に合わせた運用が必要で、単一ルールだと現場適合しないため。
  * OFF時に単位が生きていると混乱と誤解釈を生むため。
* Spec link:

  * docs/spec_overview.md: 設定の位置づけ（ホテル別パラメータ）
  * docs/spec_models.md: 月次丸めの単位（Rooms/Pax/Rev）とON/OFF時の扱い
  * docs/spec_data_layer.md: hotels.json等の設定項目（丸め単位）と出力への反映方針
  * docs/spec_evaluation.md: （基本不要）評価がdisplayに依存する場合のみ注記
* Status: 未反映

## D-20260114-004 Pax予測はDOR経由ではなく直接forecast（A案）を標準とする

* Decision:

  * Pax予測は **DOR/PU DOR経由ではなく、Paxを直接forecastする方式（A案）**を標準とする。
* Why:

  * DOR/PU DORの過大化に引っ張られてPaxが非現実的に膨らむ問題を抑制し、予測の現実性を上げるため。
* Spec link:

  * docs/spec_overview.md: 予測値の定義（Rooms/Pax/Revの関係の前提）
  * docs/spec_models.md: Pax予測モデル（直接forecast方式）と従来方式との差分
  * docs/spec_data_layer.md: Pax予測に必要な入力列・派生列の扱い（必要なら）
  * docs/spec_evaluation.md: （必要なら）Pax指標の評価対象定義
* Status: 未反映

## D-20260114-005 着地済ターゲット月は予測生成せず実績表示として扱い、サマリのFC/PUは表示しない

* Decision:

  * target_month が **ASOF時点で完全に過去（着地済）**の場合、forecast生成を**SKIP**し、日別表は実績（OH/ACT）表示として扱う。
  * 着地済ケースではサマリの **Forecast / Pickup（FC/PU）は表示しない**（空欄/“-”）。
* Why:

  * 着地済月の予測生成は意味がなく、例外や型変換エラーの温床になるため。
  * FC/PUが出ると誤解（「予測がある」ように見える）を誘発し、運用判断を誤らせるため。
* Spec link:

  * docs/spec_overview.md: 着地済月の扱い（予測生成しない/実績表示）
  * docs/spec_models.md: forecast生成条件（着地済スキップ）と表示方針
  * docs/spec_data_layer.md: （必要なら）着地済月で生成される出力（CSV等）の扱い
  * docs/spec_evaluation.md: （必要なら）評価対象月の前提（着地済月のスキップ方針）
* Status: 未反映

## D-20260114-006 フェーズ補正「中立」は強弱選択不可（固定）とする

* Decision:

  * フェーズ補正（売上）の **中立**では強弱に意味が無いため、UI上で **強弱を選択不可**にし、値は固定（例：中）に寄せる。
* Why:

  * 操作可能だと「効くはず」という誤解を誘発し、バグ疑義や運用混乱の原因になるため。
* Spec link:

  * docs/spec_overview.md: フェーズ補正の概念整理（中立の定義）
  * docs/spec_models.md: phase_biasの仕様（中立は係数固定・強弱なし）
  * docs/spec_data_layer.md: （必要なら）設定保存項目（phase/strength）の取り扱い
  * docs/spec_evaluation.md: （基本不要）評価に影響する場合のみ注記
* Status: 未反映

## D-20260116-001 PyInstallerのspecファイルはGit管理する

* Decision:

  * `BookingCurveLab.spec` は `.gitignore` 対象から外し、リポジトリで管理する（ビルド設定の唯一の正として扱う）。
* Why:

  * icon / datas / hiddenimports / onedir・onefile など配布物の再現性に直結し、ローカル依存にすると環境差で事故るため。
* Spec link:

  * docs/spec_overview.md: （開発・配布運用の補足として追記候補）
  * docs/spec_models.md: なし
  * docs/spec_data_layer.md: なし
  * docs/spec_evaluation.md: なし
* Status: 未反映

## D-20260116-002 アイコン素材はリポジトリ直下assets配下に単一配置で固定する

* Decision:

  * アイコン素材（`assets/icon/BookingCurveLab.ico`）はリポジトリ直下に1つだけ置き、`src/` 配下へコピー・重複配置しない。
* Why:

  * 2箇所配置は差し替え漏れ・参照ズレを誘発し、配布物の見た目（EXE/GUI）に不整合が出るため。
* Spec link:

  * docs/spec_overview.md: （開発・配布運用の補足として追記候補）
  * docs/spec_models.md: なし
  * docs/spec_data_layer.md: なし
  * docs/spec_evaluation.md: なし
* Status: 未反映

## D-20260116-003 TkinterのウィンドウアイコンはEXE埋め込みとは別にアプリ側で設定する

* Decision:

  * EXE埋め込みアイコン（PyInstaller）とは別に、Tkinter側で `iconbitmap()` によりウィンドウアイコン（タイトルバー/タスクバー反映の基礎）を設定する。
  * frozen環境では `sys._MEIPASS` を用いたリソース解決を標準とする。
* Why:

  * Windowsでは「EXEファイルのアイコン」と「実行中ウィンドウのアイコン」は別系統で、後者はアプリが明示設定しないと反映されないため。
* Spec link:

  * docs/spec_overview.md: （GUI/配布の補足として追記候補）
  * docs/spec_models.md: なし
  * docs/spec_data_layer.md: なし
  * docs/spec_evaluation.md: なし
* Status: 未反映

## D-20260116-004 docs/command_reference.mdを設け、コマンド運用の参照点を作る

* Decision:

  * 日常運用で使うコマンド（venv有効化、PyInstallerビルド、リリースZIP作成など）は `docs/command_reference.md` に集約する方針とする。
* Why:

  * Thread Logは証跡であり手順書としては散逸するため、再現性の高い“参照点”を別に持つ必要があるため。
* Spec link:

  * docs/spec_overview.md: （運用ドキュメントの位置付けとして追記候補）
  * docs/spec_models.md: なし
  * docs/spec_data_layer.md: なし
  * docs/spec_evaluation.md: なし
* Status: 未反映


## D-20260116-005 Windowsアイコン問題は「ショートカット/ピン留め運用」で止血し、コード恒久対応は後回し

* Decision:

  * Windows環境で「EXE直叩き起動だとタスクバーが羽アイコンになる」個体差が出る場合は、当面の標準運用として「デスクトップショートカット作成（必要ならタスクバーにピン留め）」を採用し、アイコン表示を安定させる。
  * 「直叩き起動でも常に正しく出す」ためのAUMID固定・StartMenuショートカット生成などの恒久対策は、コスト高のため優先度を下げ、必要になった時点で検討する。
* Why:

  * Windowsのタスクバー/エクスプローラー/タスクマネージャーは、アイコン参照元・縮小・アルファ合成・キャッシュが異なり、コードのみで完全統一するのは難易度とコストが高い。
  * ショートカット/ピン留めにより参照元が固定され、環境差（キャッシュ/既存関連付け）による表示ブレを現実的に抑えられる。
* Spec link:

  * docs/spec_overview.md: 反映不要（仕様ではなく配布/運用の話）
  * docs/spec_models.md: 反映不要
  * docs/spec_data_layer.md: 反映不要
  * docs/spec_evaluation.md: 反映不要
* Status: 未反映（BookingCurveLab_READMEへの運用追記のみが候補）

## D-20260116-006 LT_DATA生成はdaily_snapshotsを標準、timeseries設定はsource依存で必須化

* Decision:

  * `source="daily_snapshots"` の場合、`hotels.json` の `data_subdir` / `timeseries_file` は未設定（空）でもエラーにしない（timeseries は参照しない）。
  * `source="timeseries"` の場合のみ、`data_subdir` / `timeseries_file` を必須として厳格チェックし、欠損・空は安全側に STOP。
  * GUI 側のデフォルト `source` は `daily_snapshots` に寄せ、未設定 timeseries による停止事故を減らす。
* Why:

  * 現行運用（daily snapshots）で legacy（timeseries）設定を必須にすると、テンプレ空欄や旧config残存で無駄な停止が頻発し、運用コストが増える。
  * 一方で timeseries は比較・互換用途として残すため、必要時のみ厳格チェックにするのが最小リスク。
* Spec link:

  * docs/spec_overview.md: hotels.json のキー定義（`data_subdir` / `timeseries_file` の位置づけと source 別必須条件）
  * docs/spec_data_layer.md: LT_DATA の生成ルート（daily_snapshots標準、timeseriesは互換/比較）と I/O 前提
  * docs/spec_models.md: （影響軽微。モデル前提がrooms中心のままか注記する場合のみ）
  * docs/spec_evaluation.md: （変更不要）
* Status: 未反映

## D-20260120-001 v0.6.10のdocs更新は「mainマージ後にまとめて」実施する

* Decision:

  * docs更新は feature 上で先行せず、**mainにマージしてリリース後にまとめて実施**する運用で固定する。
* Why:

  * ブランチ間の齟齬・二重編集・取り込み漏れを避け、唯一の正（main＋spec_*）に寄せるため。
* Spec link:

  * docs/spec_overview.md: （運用ルール／開発フローの節に追記予定）
  * docs/spec_models.md: —
  * docs/spec_data_layer.md: —
  * docs/spec_evaluation.md: —
* Status: 未反映

## D-20260120-002 pace14_marketのmarket補正はpower（指数）で固定する

* Decision:

  * `final_pace14_market = final_pace14 × (market_pace ^ β)`（線形ではなくpower）で固定する。
  * βの意味は以下で固定する：

    * β=0：market補正なし（常に1）
    * β=1：market_paceをフル反映
    * 0<β<1：弱めて反映（安全寄り）
    * β>1：増幅（原則使わない想定）
* Why:

  * market_paceは倍率指標であり、powerの方が1.00付近の微調整が自然で上下対称、暴れにくく運用事故が少ないため。
* Spec link:

  * docs/spec_overview.md: —
  * docs/spec_models.md: （rooms予測モデル：pace14_market の定義節に追記予定）
  * docs/spec_data_layer.md: —
  * docs/spec_evaluation.md: —
* Status: 未反映（将来検討）

## D-20260120-003 clip適用順序はPF→market→（任意）最終ガードで固定する

* Decision:

  * clip適用順序を **PF（pace14）→ market_pace →（任意の最終安全ガード）** の順で固定する。
  * PFのclipは **PF_rawに対して適用してから** `final_pace14` を作る（ベースラインfinalへ直接clipしない）。
* Why:

  * 順序を逆にするとスパイク抑制の意図が崩れ、月全体補正が暴れて事故率が上がるため。
* Spec link:

  * docs/spec_overview.md: —
  * docs/spec_models.md: （pace14/pace14_market の計算手順・注意点に追記予定）
  * docs/spec_data_layer.md: —
  * docs/spec_evaluation.md: —
* Status: 未反映（将来検討）

## D-20260120-004 market_pace_rawはclipを入れ、初期値は0.95–1.05で固定する

* Decision:

  * `market_pace_raw` に **clipを適用する**。
  * 初期clipレンジを **0.95–1.05（±5%）**で固定する。
* Why:

  * market補正は「月全体」に効くため爆発半径が大きく、誤差・欠損・一時的偏りがそのまま最終着地に乗る事故を防ぐ必要があるため。
* Spec link:

  * docs/spec_overview.md: —
  * docs/spec_models.md: （pace14_market の安全弁として1行追記予定）
  * docs/spec_data_layer.md: —
  * docs/spec_evaluation.md: —
* Status: 未反映（将来検討）

## D-20260120-005 revenue定義（税抜宿泊売上のみ）はspec_data_layerに固定し、spec_modelsは参照導線にする

* Decision:

  * revenue（ADR定義A）は **税抜の宿泊売上のみ**（朝食・物販・手数料・税を含めない）をデータ契約として固定する。
  * 記載場所は **spec_data_layerを正**とし、spec_modelsは「この定義を前提にする」参照導線（重複最小）で持つ。
* Why:

  * revenue定義はモデル都合ではなく列の意味（データ契約）であり、spec_modelsだけだと読み飛ばされやすく、混入事故を止められないため。
* Spec link:

  * docs/spec_overview.md: —
  * docs/spec_models.md: （売上予測V1が依存する前提として参照リンク追記予定）
  * docs/spec_data_layer.md: （LT_DATA value_type / revenue列定義 または forecast列定義に必須追記予定）
  * docs/spec_evaluation.md: —
* Status: spec反映済

## D-20260121-001 Docs Gate を次スレ冒頭の必須手順として固定（Yes時はprompt_docs_update準拠）

* Date: 2026-01-21
* Status: 反映済
* Summary: 次スレ冒頭で Docs Gate を必ず実施し、Yes の場合は `docs/templates/prompt_docs_update.md` を唯一手順として docs 更新を実装より先に行う。
* Rationale: スレッド終盤はトークン溢れで事故りやすく、仕様・運用docsの整合を先に固めないと参照齟齬が発生しやすいため。
* Scope: docs運用全体（START_HERE / dev_style / templates / handover運用）
* Spec linkage:

  * N/A（運用決定のため spec_* ではなく運用docsに反映）
  * `AGENTS.md`（運用規約の前提）
* Implementation linkage (if any):

  * `docs/templates/prompt_docs_update.md`
  * `docs/templates/handover_request.md`（Docs Gate 記載）
  * `docs/templates/handover_body.md`（Docs Gate 連携）
  * `docs/START_HERE.md`
  * `docs/dev_style.md`
* Notes:

  * 次スレP0で「後半に作られた運用docsの精査」を必須タスクとして実行する方針もセットで合意。

---

## D-20260129-003 raw_inventory の重複キーはSTOPせず後勝ちで解決する（tie-break: mtime→path）

* Decision:

  * raw_inventory（RAW入力ファイル台帳）のキー `(target_month, asof_date)` が重複した場合は、**エラー停止しない**。
  * **後勝ちで1ファイルを採用**し、採用/破棄したパスをWARNINGログに出して運用継続する。
  * 後勝ちのtie-break は **mtime が新しい方**、同一なら **path の辞書順** とする（実装：`_resolve_duplicate_path`）。
* Why:

  * 現場運用での二重保存・拡張子違い等で STOP すると復旧コストが大きいため。リスクは WARNING で可視化し、運用継続を優先する。
* Spec link:

  * docs/spec_data_layer.md: raw_inventory（入力ファイル台帳）
  * docs/spec_overview.md: データ取り込みの運用ポリシー（必要なら追記）
* Status: 実装反映済（docs反映中）

---

## D-20260129-004 GUIの「LT_DATA(4ヶ月)」は +120日先に加えて翌4ヶ月先までを最低保証する

* Decision:

  * RANGE_REBUILDの stay_months は `asof_max +120日先` がかかる月まで（両端含む）＋前月を含める（既存決定の踏襲）。
  * そのうえで GUI の「LT_DATA(4ヶ月)」実行では、運用安全のため **当月から数えて翌4ヶ月先まで** を最低保証する。
    * 例：`end_month = max(month_by_120days, asof_month + 4)`
* Why:

  * 「120日先」に月跨ぎが乗らないケースでも、運用で必要な先月（翌月群）が取り込まれない事故を避けるため。
* Spec link:

  * docs/spec_data_layer.md: 部分生成（Partial rebuild / Upsert）
  * docs/decision_log.md: D-20251226-001（asof_max起点+120日先＋前月含む）
* Status: 実装反映済（docs反映中）

## D-20260121-002 引継書は docs/handovers の単体ファイルで成立させ、連結作業を廃止

* Date: 2026-01-21
* Status: 反映済
* Summary: 引継書は `docs/handovers/YYYY-MM-DD_<branch>_<scope>.md` として保存し、次スレは「最新ZIP＋当該ファイル参照」で開始する（チャット本文への連結貼付は不要）。
* Rationale: 連結作業は手作業ミス・参照齟齬・更新漏れを生みやすく、ZIP運用（唯一の正）と相性が悪いため。
* Scope: スレッド移行運用（handover作成〜次スレ開始）
* Spec linkage:

  * N/A（運用決定のため spec_* ではなく運用docsに反映）
  * `AGENTS.md`（推測禁止／参照齟齬防止の前提）
* Implementation linkage (if any):

  * `docs/templates/handover_request.md`（handover_body準拠・ファイル化指示）
  * `docs/templates/handover_body.md`
  * `docs/START_HERE.md`（handoversの正本位置を明記）
* Notes:

  * 命名・保存・参照のルールは START_HERE に集約し、以後そこを入口とする。

---

## D-20260121-003 Thread Log / Decision Log / Handover のテンプレ体系を docs/templates に集約

* Date: 2026-01-21
* Status: 反映済
* Summary: Thread Log生成、Decision Log更新、docs更新、handover作成の各テンプレを `docs/templates/` に集約し、運用手順をテンプレ準拠に固定する。
* Rationale: 作業者・スレッドが変わっても再現性を担保し、手順ブレを減らすため。テンプレがないと「毎回の口伝」になり事故る。
* Scope: docs運用全般（ログ生成・引継ぎ・docs更新）
* Spec linkage:

  * N/A（運用決定のため spec_* ではなく運用docsに反映）
  * `AGENTS.md`（運用規約の前提）
* Implementation linkage (if any):

  * `docs/templates/prompt_thread_log_generate.md`
  * `docs/templates/prompt_decision_log_update.md`
  * `docs/templates/prompt_docs_update.md`
  * `docs/templates/handover_request.md`
  * `docs/templates/handover_body.md`
  * `docs/templates/thread_start.md`
  * `docs/START_HERE.md`（テンプレ一覧の入口）
* Notes:

  * 次スレ冒頭で templates と運用docs（START_HERE/dev_style）を再精査する（後半作成物の品質確認）。

---

## D-20260121-004 Decision Log の見落とし対策として「時系列に揃える」方針を採用

* Date: 2026-01-21
* Status: 未反映
* Summary: `docs/decision_log.md` の並び順を時系列に揃え、末尾10〜20件確認で最新決定の見落としが起きない状態を目指す。
* Rationale: 末尾確認が前提の品質ゲートになっているため、並びが崩れていると未反映決定を見落とすリスクがある。
* Scope: Decision Log 運用（確認手順の信頼性）
* Spec linkage:

  * N/A（運用決定のため spec_* ではなく運用docsに影響）
  * `AGENTS.md`（参照齟齬防止の前提）
* Implementation linkage (if any):

  * `docs/decision_log.md`
  * `docs/templates/prompt_decision_log_update.md`（末尾確認前提の運用と整合が必要）
  * `docs/START_HERE.md`（確認手順に影響）
* Notes:

  * “並び替え”が難しい場合は、代替として「検索ルール併用」を運用docsに明記する案もあり（次スレで確定）。

---

## D-20260121-005 アンカーZIP（スレッド内参照点固定）運用に統一

* Decision:

  * 参照の唯一の正は「アンカーZIP（この依頼/スレッドで共有されたZIP＝作業開始点）」とし、スレッド内では参照点を固定する。
  * スレッドを跨ぐ場合は、新しく作成したZIPを次スレ冒頭で添付し、それを次スレのアンカーZIPとして固定する（スナップショット連鎖）。
  * 引継依頼で渡すZIPと、次スレ冒頭で添付するZIPは一致させる（不一致は参照事故）。
* Why:

  * 「最新ZIP」を参照点にするとスレッド中に参照が揺れ、再現性が壊れるため。
  * 参照点固定と更新タイミング（スレッド跨ぎ）を分離して運用事故を防ぐため。
* Spec link:

  * なし（運用ルール。spec_* ではなく `AGENTS.md` / `docs/dev_style.md` / docsテンプレ群で担保）
* Status: 反映済
* Notes: D-20260121-009 により「ZIP一致」要件は撤廃（superseded）

---

## D-20260121-006 Docs Gate を「次スレ冒頭の最優先チェック」として明文化

* Decision:

  * スレッド終盤の事故を避けるため、次スレ冒頭で Thread Start Gate（アンカーZIP検算）→ Docs Gate（Yes/No判定）を最初に必ず実施する。
  * Docs更新が必要（Yes）の場合、実装作業より先に docs/spec 更新を行い、手順は `docs/templates/prompt_docs_update.md` を唯一の手順とする。
* Why:

  * トークン劣化や参照齟齬が起きやすい終盤に docs を後回しにすると、前提崩壊で事故るため。
* Spec link:

  * なし（運用ルール。docsテンプレと `docs/dev_style.md` で担保。spec_* は「唯一の正」として参照対象）
* Status: 反映済

---

## D-20260121-007 Decision Log の時系列整流をツールで担保（古→新、末尾が最新）

* Decision:

  * `docs/decision_log.md` は古→新（新しいものが末尾）の時系列を正とし、整流（ソート）は `tools/assign_decision_ids.py --sort` で担保する。
  * 採番は `D-YYYYMMDD-XXX` を維持し、XXXは採番スクリプトで付与する（手で番号確定しない）。
* Why:

  * 手作業の並び替えは漏れ・崩れが起きやすく、Decision Log が時系列にならない問題が再発するため。
* Spec link:

  * なし（運用ツール・運用ログの整合。spec_* ではない）
* Status: 実装反映済

---

## D-20260121-008 事前指示（システム側ガードレール）は圧縮し、詳細はAGENTS/docsへ寄せる

* Decision:

  * システム側の事前指示は「憲法（短いガードレール）」に圧縮し、詳細な運用規約は `AGENTS.md` と docs（例：`docs/ai_preamble_reference.md` / `docs/dev_style.md` / テンプレ群）に置く。
  * 盲点化を避けるため、システム側の要点は docs 側にも参照用として残す。
* Why:

  * 冗長な事前指示は読み落とし・矛盾・更新漏れを誘発するため。正本をAGENTSに寄せた方が事故りにくい。
* Spec link:

  * なし（運用ガバナンス。spec_* ではない）
* Status: 反映済

---

## D-20260121-009 source_zip / anchor_zip / candidate_zip の定義（引継依頼ZIP一致要件を撤廃）

* Decision:

  * source_zip＝引継書作成の材料になったZIP（引継依頼時点のZIP）と定義する。
  * anchor_zip＝次スレッドで「共有物の唯一の正」として添付するアンカーZIPと定義する。原則、引継書（docs/handovers）を同梱して作り直したZIPを用いる。
  * source_zip と anchor_zip が異なる場合は、引継書本文に source_zip（ZIP名/branch/commit）を明記する（監査用）。次スレの参照の唯一の正は anchor_zip。
  * スレッド途中に修正版ZIPを渡して検証する場合は candidate_zip（検証対象）として扱い、アンカーZIPは固定する。candidate を唯一の正として扱うなら新スレッドへ移行する。
* Why:

  * 引継書は生成物のため、引継依頼時点のZIPに物理的に同梱できず、「ZIP一致」を要求すると運用が破綻するため。
  * 参照の唯一の正（アンカー）と、途中検証（candidate）を分離して参照齟齬を防ぐため。
* Spec link:

  * なし（運用決定。spec_* ではない）
* Status: 反映済

---

## D-20260121-010 handovers/thread_logs の命名に HHMM を追加（同日衝突回避）

* Decision:

  * handovers は `docs/handovers/YYYY-MM-DD_HHMM_<branch>_<scope>.md` を正とする。
  * thread_logs は `docs/thread_logs/YYYY-MM-DD_HHMM_<branch>_<scope>.md` を正とする。
  * HHMM は作成時刻（JST, 24h）とし、同日・同scopeの衝突を機械的に回避する。
* Why:

  * 同日内で同タスクを進めた場合にファイル名が衝突し、参照齟齬や `_v2` の場当たり運用が発生するため。
* Spec link:

  * なし（運用決定。spec_* ではない）
* Status: 反映済

※2026/1/24　下記に修正済
docs/handovers/YYYY-MM-DD_HHMM_<type>_<scope>__handover.md
docs/thread_logs/YYYY-MM-DD_HHMM_<type>_<scope>__thread_log.md

---

A-019

## D-20260122-001 Phase3着手前に安定化ブランチでバグ修正を先行する（スコープ固定）

* Decision:

  * Phase3に入る前に、安定化ブランチ `fix/stabilize-before-phase3` で既知バグ修正を先行する。
  * 安定化ブランチのスコープは当面「recent90 calendar_features欠損クラッシュ / LT_ALLエラー / TopDownRevPAR不一致」の3点に固定し、追加拡張しない。
  * LT_ALL と TopDownRevPAR は、スクショ/ログ等の再現情報が揃うまで推測で修正方針を固定せず、再現→切り分け→修正の順で進める。
* Why:

  * Phase3着手前に「落ちる/誤表示」の足場を固め、後工程の手戻りを最小化するため。
  * 再現情報なしで修正を始めると原因取り違えのリスクが高く、修正パックが肥大化しやすいため。
* Spec link:

  * なし（開発運用/作業方針）
* Status: 実装反映済

---

## D-20260124-001 pace14_market の market補正を線形からpowerへ変更（clip/減衰パラメータ含む）

* Decision:

  * `pace14_market` の market_factor は「線形」ではなく **`market_pace_eff ** beta`（power）** で算出する方針とする。
  * factor の clip 初期値は **0.85–1.15** とし、LT帯は従来方針（market補正の適用帯）を維持する。
* Why:

  * market補正をより自然に効かせつつ、LTが遠いほど影響が弱まる（beta減衰）形に揃えるため。
  * 線形補正は外れ値・負値等の取り扱いが難しく、直感的な効き方になりにくいため。
* Spec link:

  * `docs/spec_models.md`: pace14_market セクション（market_factorの定義・clip方針）
* Status: spec反映済

---

## D-20260124-002 pace14_weekshape_flow を追加（LT15–45の週×グループのフロー補正、W=7、clip 0.85–1.15）

* Decision:

  * pace14の守備範囲外（LT 15–45）で「週単位の強弱」を拾う補正として **weekshape_flow（フロー/B2）** を新モデルとして追加する。
  * 窓幅は **W=7**、factor clip は **0.85–1.15** を初期値とする。
* Why:

  * 個別日のpickup補正（pace14）だけでは拾いにくい「週単位の強弱」や月末月初の弱さ等を補正できるようにするため。
* Spec link:

  * `docs/spec_models.md`: モデル一覧／weekshape_flow（新規）定義
  * `docs/spec_evaluation.md`: 評価対象モデル一覧（必要なら）
* Status: spec反映済

---

## D-20260124-003 calendar_features が無い/不足のときは自動生成する（手動生成不要）

* Decision:

  * `calendar_features_{hotel}.csv` が存在しない、または必要な日付範囲を満たさない場合、実行時に **自動生成**して補完する。
  * 生成は最低1年分（min_span_days）を確保し、手動の事前生成を必須にしない。
* Why:

  * 実行前の手動オペ（生成忘れ）でモデルが落ちる/neutral化する事故を減らし、運用を安定させるため。
* Spec link:

  * `docs/spec_data_layer.md`: calendar_features の扱い（生成/必須性の位置づけ）
  * `docs/spec_models.md`: calendar依存モデルの前提（必要なら）
* Status: spec反映済

---

## D-20260124-004 pace14_weekshape_flow の gating 閾値（MIN_EVENTS）を到達可能値へ修正

* Decision:

  * `compute_weekshape_flow_factors` は `(week_id, group)` 単位集計のため、`WEEKSHAPE_MIN_EVENTS` は到達可能な値（<=7）を前提に設定する。
  * デフォルトの `WEEKSHAPE_MIN_EVENTS=10` は到達不能になり得るため、デフォルトは 2 とする。
* Why:

  * 到達不能な閾値だと weekshape係数が常に 1.0 となり、モデルが実質OFFになって検証・運用の双方で誤解を生むため。
* Spec link:

  * `docs/spec_models.md`: pace14_weekshape_flow（gating条件とデフォルト値の記載）
* Status: spec反映済

---

## D-20260125-001 開発依存（ruff）を pyproject の dev extras で固定し、LFを正として運用する

* Decision:

  * `ruff` は `pyproject.toml` の `optional-dependencies.dev`（`.[dev]`）で導入・固定し、開発環境差を減らす。
  * 改行コードは LF を正とし、`.gitattributes` により正規化する（端末差の温床を減らす）。
* Why:

  * VSCode保存時の自動適用等が「ruff未導入」で崩れるのを防ぎ、環境依存のトラブルを減らすため。
  * CRLF/LF差分によるノイズ（パッチ/レビュー/マージ）を減らすため。
* Spec link:

  * なし（開発運用/環境整備）
* Status: 反映済

---

## D-20260125-002 capacity 定義は固定室数とし、“ベース小”判定はLT帯別に持つ

* Decision:

  * capacity は「月の販売室数（固定室数）」を採用する（休館/工事反映の有効キャパではなく）。
  * “ベースが小さい”の判定・閾値は、LT0–14（pace14帯）と LT15–45（weekshape帯）で別々に持つ方針とする。
* Why:

  * cap正規化により施設規模差を抑えつつ、帯ごとの挙動差（直近と先行）を分けて安定運用するため。
* Spec link:

  * `docs/spec_models.md`: pace14 / weekshape（“ベース小”救済設計を反映する導線）
* Status: 未反映

---

## D-20260126-001 base_small_rescue weekshape 学習を hotels.json に永続化し、学習ゲートを導入する

* Decision:

  * weekshape帯（LT15–45）の “ベース小救済” 用に、`residual_rate` 分布の分位（P90/P95/P97.5）から `cap_ratio_candidates` を学習し、`learned_params.base_small_rescue.weekshape` として hotels.json に保存する。
  * 学習結果には `trained_until_asof / n_samples / n_unique_stay_dates / window_months_used` を含め、`trained_until_asof == latest_asof` の場合は学習をスキップして再実行を抑制する。
* Why:

  * “ベース小” で倍率補正が効かないケースに対して、施設規模差を吸収しつつ安全に救済上限（cap比）を決めるため。
  * 再現性（いつのデータで学習したか）と運用負荷（無駄な再学習）の両立が必要なため。
* Spec link:

  * `docs/spec_models.md`: `3.4.3 pace14_weekshape_flow`（ベース小救済weekshapeの定義追記先）
* Status: 実装反映済

---

## D-20260126-002 forecast CSV に weekshape_gated / base_small_rescue_* の診断列を出力する

* Decision:

  * run_forecast_batch が出力する forecast CSV に、`weekshape_gated` と `base_small_rescue_*`（applied/mode/cap_ratio/pickup/reason）を含める。
  * 後方互換のため、detail_df に列が存在する場合のみCSVへ出力する（存在しないモデルでは無影響）。
* Why:

  * 救済が「どの日に」「どの理由で」「どれだけ」効いたかを、CSVだけで検証・監査できるようにするため。
* Spec link:

  * `docs/spec_models.md`: `3.4.3 pace14_weekshape_flow`（出力/診断項目の追記先）
  * `docs/spec_evaluation.md`: （必要なら）検証観点として診断列の参照を明記
* Status: 実装反映済

---

## D-20260128-001 pace14_market の市場補正は decay_k=0.25 を暫定デフォルトとし、clipは 0.85–1.25 を維持する

* Decision:

  * pace14_market の市場補正（power+decay）のデフォルトとして `MARKET_PACE_DECAY_K=0.25` を暫定採用する。
  * 安全弁として `MARKET_PACE_CLIP=(0.85, 1.25)` を維持し、上限張り付きの頻度と“効き”のバランスを取る。
* Why:

  * clip上限の調整だけでは張り付き問題が解けず、decay_k を上げることで market帯（LT15–30）の上位張り付きを減らしつつ、強い週は自然に上げる挙動が得られたため。
  * ASOF差（例：市場弱/強）およびホテル差でも、過度なブーストや不自然な抑制が出にくいことを確認できたため。
* Spec link:

  * `docs/spec_models.md`: pace14_market（market補正の定義・デフォルト値の追記先）
* Status: 実装反映済（docs未反映）

---

## D-20260128-002 market補正の説明可能性を優先し、detail列の拡充と恒久診断ツールを追加する

* Decision:

  * pace14_market の detail（診断）に `current_oh/base_now/base_final/base_delta/final_forecast` を出力できるようにする。
  * market帯の効果を再現確認できる恒久ツール `tools/diag_market_effect.py` を追加する（ASOF/ホテル/target/capacity 指定）。
* Why:

  * deltaが大きい理由が「倍率」なのか「元の増分（base_delta）」なのかを、ログだけで説明・検証できる状態が必要なため。
  * 一時スクリプト依存を減らし、再現手順を固定化して運用コストと認知負荷を下げるため。
* Spec link:

  * `docs/spec_models.md`: pace14_market（診断項目の導線）
  * `docs/spec_evaluation.md`: （必要なら）評価時の診断参照の明記
* Status: 実装反映済（docs未反映）

---

## D-20260128-003 ローカル設定ファイルを除き、ホテル固有名（実名）をコード上から排除する方針とする

* Decision:

  * ローカル設定ファイルを除き、ホテル固有名（例：daikokucho/kansai 等の実名）はコード・ツール・ログ出力から排除する方針とする。
  * まずは実名デフォルト（例：`HOTEL_TAG="..."`）を撤去し、hotel_tag未指定時の挙動を統一（例外 or 中立スキップ）する。
* Why:

  * 外部利用（副業等）との兼ね合いで、コードベースの再利用性と情報分離を確保する必要があるため。
  * hotel_tag渡し忘れによる誤適用事故（別ホテルに別ホテルの補正が乗る）を予防するため。
* Spec link:

  * `AGENTS.md`: 運用・ガバナンス方針（必要なら追記箇所）
  * `docs/spec_overview.md`: （必要なら）データ/設定の責務分離の導線
* Status: 方針合意（未実装）

---

## D-20260129-001 config/hotels.json を空テンプレ化し、初回起動ウィザードでホテル設定を作成する

* Decision:

  * 同梱の `config/hotels.json` は `{}`（空テンプレ）で固定する。
  * GUI起動時に `HOTEL_CONFIG` が空の場合、初回セットアップウィザードを必ず表示し、最初のホテル設定をGUIから作成させる。
  * 「対象ホテル」枠に「＋追加…」を設置し、任意でホテル設定を追加できる導線を提供する。

* Why:

  * コード上のホテル実名デフォルト撤去と整合させつつ、初回導入時の誤選択/黙ったフォールバックを防ぐため。
  * 設定が無い/空のときは安全側に停止・明示設定へ誘導する方針をGUIに落とすため。

* Spec link:

  * docs/spec_overview.md: 「### 2-1. 対象ホテル」（`config/hotels.json` の位置づけ・必須キー）

* Status: 実装反映済

---

## D-20260129-002 hotel_tag 未指定の黙殺を禁止し、CLI/tools は --hotel 必須で統一する

* Decision:

  * `src/` と `tools/`（`src/_archive` 除外）からホテル実名ハードコードを撤去する。
  * CLI/tools のエントリポイントは `--hotel` を必須化し、未指定で黙って進まないようにする。
  * ホテル依存の補正ロジックは `hotel_tag` が未指定（None/空）なら ValueError とし、黙って補正をスキップしない。

* Why:

  * 別ホテルの設定/補正が誤って適用される事故を防ぎ、補正が効いていないことに気付けない状態を排除するため（フェイルファスト）。
  * 「ホテル設定が欠けている/必須キー不足は安全側にSTOP」の方針と整合させるため。

* Spec link:

  * docs/spec_overview.md: 「### 2-1. 対象ホテル」（設定が欠けている場合は安全側にSTOP）
  * docs/spec_models.md: 「### 3.2 recent90 / recent90_adj モデル」内の `apply_segment_adjustment(...)`（ホテル依存補正の入力契約を明文化対象）

* Status: 実装反映済

---

## D-20260130-XXX TopDownRevPAR帯をdeltaレンジ（MAD外れ値除外＋min/max）に変更

* Decision:

  * TopDownRevPARのA/C帯は「比率や分位点」ではなく「過去年度の傾き（delta）の実現レンジ」を表現する。
  * 年度サンプルが少ない前提で、n>=5 のときのみ MAD により明らかな外れ値を除外し、残りの min/max を帯として採用する（n<5はスキップ）。
  * abs guard（絶対値クランプ）は撤去する。
* Why:

  * 年度サンプルが少ない状況でp10–p90は安定しにくく、abs guardの副作用で12→1付近の帯が不自然に暴れるため。
* Spec link:

  * なし（spec未記載：追記候補は docs/spec_models.md / docs/spec_evaluation.md）
* Status: 実装反映済

---

## D-20260130-XXX output生成物をホテル別ディレクトリに整理

* Decision:

  * output配下の生成物はホテル別ディレクトリに分離し、複数ホテルの出力混在を避ける。
* Why:

  * output直下に新旧ファイルが混在し、運用上の誤認・比較ミスが起きやすいため。
* Spec link:

  * なし（spec未記載：追記候補は docs/spec_data_layer.md）
* Status: 実装反映済

---
