# ファイル名案: docs/thread_logs/2025-12-24_feature-daily-snapshots-partial-build_missing-ops-audit-rawfx-zip.md

# Thread Log: 欠損検知ops/audit分離・RawFX安全化・リリースZIP整備

## Meta

* Date: 2025-12-24（推定：zip名/作業ログより）
* Branch: feature/daily-snapshots-partial-build
* Commit: 0ecb0ff（ログ出力より）
* Zip: rm-booking-curve-lab_20251224_full_full.zip
* Scope:

  * 欠損検知を2モード（ops/audit）に分離し、ASOF丸抜け（asof_missing）を検知
  * auditはSTAY MONTH min..maxに限定し未来ASOFをキャップ
  * GUI（マスタ設定）に欠損チェック/監査/欠損のみ取り込み/最新ASOF鮮度warningを整備
  * RawInventory/設定の“唯一の正”をhotels.json中心に寄せる方針整理
  * nface RAWのレイアウト/日付判定を安全側へ固定（誤取り込み回避）
  * make_release_zip.pyの同梱物・ログ・サンプルRAW fixture運用を整備

## Done（実装・変更）

* 欠損検知を ops/audit の2モードに分離し、CSV出力名の上書き衝突を解消（2ファイル並走を確認）
* ops: asof_missing（ASOF丸抜け）/ raw_missing を区別して出力、Excel起動時の日本語message文字化けを解消
* audit: 対象STAY MONTHをmin..max連続月に限定し、asof_date>today を欠損扱いしないようキャップ
* 「欠損のみ取り込み」は raw_missing のキーを基準に再生成/再取り込み（asof_missingは対象外の整理）
* GUIで latest_asof 鮮度warning を視覚化（塗りつぶし等）し運用誤解を減らす導線を追加
* RAW→daily_snapshots変換で「raw exists but daily snapshot is missing」の原因パターンを棚卸し（例：日付行不足、ネーム解釈不可、ASOF不一致 等）
* nface変換を安全側へ寄せる方針を確定：宿泊日=A列のみ、2行持ち判定（空白＋同日付連続）、判定不能STOP、ASOFはセル優先/欠落時のみネームfallback、OH列EFG固定
* 代表RAW fixture を samples/raw に整備（A列なしSTOP、unknown STOP、inline/shifted、dup/blank/mix等）
* make_release_zip.py を改修し、profile/with-output-samplesで必要物のみ同梱できる運用を整備
* ログ同梱は output/logs へ集約し、latest log抽出に優先順位（full_all_*.log優先）を追加
* zip命名の衝突回避として、日付だけでなく時刻（YYYYMMDD_HHMM）＋（任意でcommit）を推奨
* forecast_cap の hotels.json 側保持を確認し、安全装置閾値（WARN<80%, STOP<30%）の方針を合意

## Decisions（決定）

* Decision:

  * 欠損検知は ops/audit の2モード（目的分離）で運用する
  * auditはSTAY MONTH min..maxに限定し、未来ASOFはキャップする
  * opsで asof_missing（ASOF丸抜け）を検知対象に含める
  * 「欠損のみ取り込み」は当面 raw_missing のみ（asof_missingは“再生成で消える”ため対象外のまま）
  * nface RAWは安全側固定：宿泊日=A列唯一の正、2行持ち判定は空白＋同日付連続を考慮、判定不能STOP、ASOFはセル優先/欠落時のみネームfallback
  * make_release_zip は必要物のみ同梱する方針（with-output-samplesでサンプル出力/fixture/最新ログを追加）
  * 同梱ログは full_all_*.log を最優先で抽出する
* Why:

  * 取り込み漏れ検知（ops）と歴史棚卸し（audit）で期待キーの作り方が異なり、単一モードだと誤検知/ノイズが大きい
  * ASOF丸抜けは「観測ASOF起点」だと検知不能なため、asof_missing を別カテゴリで持つ必要がある
  * すべてのRAWパターン対応は誤取り込みリスクを増やすため、安全側に寄せてSTOPで早期発見する方が運用に強い
  * ログ同梱は無制限だとサイズ/漏洩リスクが増えるため、最新・代表に絞るのが妥当
  * ZIPは「開く前に識別できる」ことが重要で、時刻/commitの命名規約が参照齟齬を減らす

## Docs impact（反映先の候補）

* spec_overview: 欠損検知（ops/audit）と運用導線、release zip運用の概要追記候補
* spec_data_layer: NaN保持/NOCBはGUI直前のみ、missing_report（ops/audit）仕様、future ASOF cap、asof_missing/raw_missing定義
* spec_models: monthly_curve raw保持、補完は表示直前のみ、評価は欠損補完せずサンプル除外が基本
* spec_evaluation: 欠損補完しない前提での評価/除外ルールの明文化（必要なら）
* BookingCurveLab_README: make_release_zip の実行例、handover/fullの使い分け、同梱サンプル（samples/raw, output/logs）の説明

### Docs impact 判定（必須/不要 + Status）

* 必須:

  * 項目: missing_report（ops/audit）仕様（asof_missing/raw_missing、auditのmin..max、future ASOF cap、鮮度warning）

    * 理由: 運用判断（欠損の意味/優先度）に直結し、実装だけだと解釈がブレる
    * Status: 未反映
    * 反映先: docs/spec_data_layer.md（欠損/品質チェック節）
  * 項目: “データレイヤはNaN保持、補完はGUI表示直前のみ”

    * 理由: 予測/評価/可視化の整合に直結し、迷いの根になるため
    * Status: 未反映
    * 反映先: docs/spec_data_layer.md または docs/spec_models.md（データ取扱い節）
  * 項目: リリースZIP（make_release_zip）運用（with-output-samples、ログ抽出方針、命名規約）

    * 理由: 引き継ぎ/共有手順の再現性担保
    * Status: 未反映
    * 反映先: BookingCurveLab_README / docs/spec_overview.md（運用手順）
* docs不要:

  * 項目: 個別RAWファイルの実データ不備（手打ち年ズレ等）の具体例

    * 理由: 作業記録としてはThread Logで十分、仕様書に入れるとノイズ
    * Status: 不要

## Known issues / Open

* 「raw exists but daily snapshot is missing」系ログは、運用上は“整理対象リスト”として残る（根治はP1でCSV棚卸し化）
* A列日付が無いRAWはSTOP（データ救済はしない方針）だが、古い月に少数混在するため整理判断が必要
* hotels.json / config.py / gui_backend.py / build_daily_snapshots_from_folder.py の参照統一（唯一の正）をP0で完了させる必要あり
* samples/raw の README.md（fixture説明）は運用の唯一の正として整備継続が必要

## Next

* P0:

  * hotels.json を唯一の正として RawInventory/GUI/CLI/Backend の設定参照を統一（直書き/独自ローダー排除）
  * nface: A列日付ルール＋2行持ち判定を安全側へ完全固定（判定不能STOPの基準を明確化）
  * make_release_zip: ログ抽出は full_all 優先を正式仕様化、命名規約（YYYYMMDD_HHMM＋任意でcommit）を固定
* P1:

  * Partial build（Phase 1.6）を運用として完成（範囲限定 rebuild）
  * 欠損/変換ログを“整理対象棚卸しCSV”として出力（作業リスト化）
* P2:

  * docs/spec_* と tasks_backlog を現実実装に追従（特に欠損検知/NaN保持/ZIP運用）
