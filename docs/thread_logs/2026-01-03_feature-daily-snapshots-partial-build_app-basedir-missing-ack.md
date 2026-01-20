# ファイル名案: docs/thread_logs/2026-01-03_feature-daily-snapshots-partial-build_app-basedir-missing-ack.md

# Thread Log: APP_BASE_DIR集約＋欠損ACK（ops）＋配布前提の運用整備

## Meta

* Date: 2026-01-03（推定：ログ/コミット時刻より）
* Branch: feature/daily-snapshots-partial-build
* Commit: 9f6339c6d9e8594e5c3be54c606a9544b036a94c（main HEAD / 2026-01-03 16:00頃）
* Zip: packages/rm-booking-curve-lab_20260103_1551_samp_main_b3165be_full.zip
* Scope:

  * EXE配布前提で、設定/出力/ACK/override を APP_BASE_DIR（%LOCALAPPDATA%/BookingCurveLab/）へ寄せ切り
  * 欠損検査（ops）のACK（確認済み除外）をGUIで運用可能に
  * 初回テンプレ展開の失敗を握りつぶさず通知（showerror＋ログ）
  * マスタ設定に「設定フォルダを開く」「設定を再読み込み」を追加

## Done（実装・変更）

* 欠損検査（ops）の欠損一覧GUIを実装し、ACK列クリックで確認済みトグル可能にした
* ACK保存（missing_ack_<hotel>_ops.csv）を端末ローカル（APP_BASE_DIR/acks/）へ固定
* ACK済み（severity=ERROR/WARNのみ）を ops 集計（ERROR/WARN件数）から除外する仕様で実装
* 欠損一覧に「ACK済み非表示」フィルターを追加（デフォルトONで運用ノイズを抑制）
* 欠損一覧の保存ボタンが小窓で見えない問題を解消（UI配置/表示改善）
* 欠損一覧の message が nan 表示になり得る点を修正（NaN→空文字等）
* 実行時の config/output/logs/acks/local_overrides を APP_BASE_DIR 配下へ統一（EXE配下へ出力しない）
* 初回起動のテンプレコピー（例：config/hotels.json）の失敗時に showerror＋ログ出力で通知（無言握りつぶし回避）
* 「設定フォルダを開く」ボタンをマスタ設定タブに追加（Explorer起動）
* 「設定を再読み込み」ボタンをマスタ設定タブに追加（hotels.json等の再ロード導線）
* “frozen”（pyinstaller配布形態）を前提に BASE_DIR 解決の設計を整理し、配布後のEXE移動耐性を強化
* docs/spec_* と README に、APP_BASE_DIR配下のフォルダ構成・ACK保存先などを追記/整合
* リリースZIP作成・packages/の扱いについて運用整理（gitignore見直しを含む）

## Decisions（決定）

* Decision:

  * APP_BASE_DIR（%LOCALAPPDATA%/BookingCurveLab/）基準に寄せ切る（設定/出力/ACK/overrideをEXE配下に出さない）
  * 欠損ACKは「opsのみ」「severity=ERROR/WARNのみ」を対象とし、ops集計（ERROR/WARN件数）からACK済みを除外する
  * 欠損監査（audit）は統制用の全体像確認で固定し、ACKで除外しない
  * ACK同一性キーは最小要件として kind + target_month + asof_date + path を採用
  * 初回テンプレ展開が失敗した場合は A案（showerror＋ログ）で明示的に通知する
  * 配布形態は「各端末ローカルにEXE配置」「端末ごと独立運用」（共有フォルダ起動は前提にしない）
  * 欠損一覧のACK済み行はデフォルト非表示（フィルターON）で運用ノイズを抑える
* Why:

  * EXE位置依存や共有フォルダ起動は壊れやすく、運用事故（EXE移動/権限/出力散乱）を招くため
  * opsは日々の運用を回すための警告であり、確定欠損のノイズを除去したい（ただし監査は全体像維持が目的）
  * GUIで「確認済み」を付けられると現場運用が回る（毎回同じ欠損警告に時間を取られない）

## Docs impact（反映先の候補）

* spec_overview: v0.6.7の内容（欠損ops/audit、ACK、APP_BASE_DIR配下構成、EXE配布前提の保存先）を追記・整合【】
* spec_data_layer: パスは論理パスであり実体はAPP_BASE_DIR配下、欠損レポート/ACK仕様（ops/audit差分、ACK同一性キー、保存先）を追記・整合【】
* spec_models: 今回は主にデータ/運用層（欠損/配布）で、モデル仕様の変更は無し（要確認）
* spec_evaluation: 今回は主に欠損/配布で、評価仕様の変更は無し（要確認）
* BookingCurveLab_README: 配布先ユーザー（部下運用想定）向けにマスタ設定タブとローカルフォルダ構成/導線を追記

### Docs impact 判定（必須/不要 + Status）

* 必須:

  * 項目: APP_BASE_DIR配下への寄せ切り（config/output/logs/acks/local_overrides）

    * 理由: 配布運用の前提が変わり、EXE配下出力禁止が外部仕様に近い扱いになるため
    * Status: 反映済（要最終目視）
    * 反映先: docs/spec_overview.md（前提/保存先）、docs/spec_data_layer.md（パス注記/欠損レポート節）、BookingCurveLab_README.txt（運用手順）
  * 項目: 欠損検査（ops）ACK仕様（対象/同一性キー/集計除外/保存先/GUI運用）

    * 理由: 運用フローが追加され、警告件数の解釈が変わるため
    * Status: 反映済（要最終目視）
    * 反映先: docs/spec_overview.md（v0.6.7差分）、docs/spec_data_layer.md（欠損レポート節）、BookingCurveLab_README.txt（操作説明）
  * 項目: 初回テンプレ展開失敗時の通知方針（showerror＋ログ）

    * 理由: 初期導入時のトラブルシュートに直結するため
    * Status: 反映済（要最終目視）
    * 反映先: docs/spec_overview.md（技術前提/起動時挙動）、BookingCurveLab_README.txt（初回起動時）
* docs不要:

  * 項目: 「欠損だけ取り込み」で最新ASOFを増やすかの議論

    * 理由: 現状維持で確定し、仕様変更は入れていないため
  * 項目: RMSE列や評価CSV出力列の再設計予定

    * 理由: 今回は見送りで、別フェーズで再検討のため（計画に留める）

## Known issues / Open

* output/logs/startup_init.log が期待どおり生成されないケースがあった（APP_BASE_DIR配下に logs フォルダはあるが当該ログが無い）

  * 再現条件: 初回起動時の初期化ログ出力の経路次第で未生成
  * 影響範囲: 初期化失敗時の原因追跡が難しくなる
  * 暫定回避策: GUIのエラーダイアログ（showerror）と、他ログ（存在するログ）で確認
* packages/ や make_release_zip.py の取り扱いが混乱しやすい（gitignore/復旧手順）

  * 影響範囲: リリース作成・共有フローの再現性
  * 暫定回避策: make_release_zip.py はgit管理、packages/は（原則）git管理外に戻す運用で整理（ただし「ChatGPT共有効率」の事情あり）

## Next

* P0:

  * docs/tasks_backlog.md への差し込み（このブランチで完了した項目のステータス整理）
* P1:

  * “まっさら配布用 hotels.json テンプレ”の安全な最小雛形を確定し、テンプレとして同梱（spec/READMEにも整合させる）
* P2:

  * 初回起動時の「匿名デフォルトホテル」導線（ホテル追加UIは今は入れず、テンプレ編集で回す方針の明文化）
  * startup_init.log の生成有無を整理し、必要なら出力経路を一本化

---
