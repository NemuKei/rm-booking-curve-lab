# Handover（本文テンプレ）

Proposed file path: docs/handovers/2026-01-29_2140_feature_pace14_market_power_and_clip__handover.md

---

## 1. スレッド移行宣言（新スレッドに貼る前提の文面）
- このスレッドは、GUIの運用改善（LT_DATA対象月レンジの安全化／欠損チェックのフリーズ回避／日別CSV出力の導線改善）と、月次カーブ補完のバグ修正＋docs差分反映を行った作業ログです。
- 次スレッドでは、マージ準備（Closeout Pack最終確認→mainへマージ→Release ZIP作成→GitHub Release）のP0を進めます。

---

## 2. 現在地サマリ（何ができて、何が未完か：箇条書き）

### できたこと
- GUI「LT_DATA(4ヶ月)」の対象月レンジを、latest_asof起点で「+120日先がかかる月まで（前月含む）＋最低翌4ヶ月保証」へ変更
  - 主要変更ファイル：`src/gui_main.py`
- 「欠損チェック（運用）」実行時のUIフリーズ回避（非同期化・多重実行防止・完了後の復帰）
  - 主要変更ファイル：`src/gui_main.py`
- 日別フォーキャストCSV出力後にCSVを自動で開く導線を追加
  - 主要変更ファイル：`src/gui_main.py`
- 月次カーブ：ACTあり／LT0欠損のとき線形補完が効かず補完グラフが出ない問題を修正（ビュー上でLT0にACTをコピーしてから補完）
  - 主要変更ファイル：`src/booking_curve/gui_backend.py`
- docs差分更新（spec_overview / spec_data_layer / README / decision_log）
  - 主要変更ファイル：`docs/spec_overview.md`, `docs/spec_data_layer.md`, `docs/BookingCurveLab_README.txt`, `docs/decision_log.md`

### 未完（残課題）
- P0: main へマージ、Release ZIP作成、GitHub Release（Release Notes整理）
- P1: Decision Log の `D-20260129-XXX` を採番スクリプトで確定（運用手順どおり）

---

## 3. 決定事項（仕様として合意したこと）
- raw_inventory の重複キーは **後勝ちでOK**（運用停止しない）。tie-break は実装どおり `mtime -> path`。
- LT_DATA(4ヶ月) は運用安全のため、+120日先だけでなく **最低翌4ヶ月先まで**を保証する。
- 月次カーブの線形補完では、`LT0欠損 & ACTあり` の場合のみ **ビュー上でLT0へACTコピー**して端点を確保してから補完する。

※注意：仕様の唯一の正は `docs/spec_*.md` と `AGENTS.md`。ここは「合意のログ」。

---

## 4. 未解決の課題・バグ（再現条件／影響範囲／暫定回避策）

### 課題1：なし（回帰確認OK）
- 再現条件：
- 影響範囲：
- 暫定回避策：
- 備考：

### 課題2：なし（docs更新済）
- 再現条件：
- 影響範囲：
- 暫定回避策：
- 備考：

---

## 5. 次スレッドのP0（最初にやることチェックリスト）
- Closeout Pack最終確認（この引継＋Thread Log）
- main へマージ（差分・コンフリクトなしを確認）
- make_release_zip.py で Release ZIP 作成（これを唯一の共有物に）
- GitHub Release 本文（変更点・影響・Known Issues）を作成して公開
