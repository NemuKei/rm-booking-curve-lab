Proposed file path: docs/handovers/2026-01-29_1715_feature_pace14_market_power_and_clip__handover.md

## Thread Closeout Handover

### Source of truth
- source_zip: rm-booking-curve-lab_20260129_1651_samp_feature-pace14_market_power_and_clip_f0751a0_full.zip
- branch: feature/pace14_market_power_and_clip
- commit: f0751a0
- scope: pace14_market_power_and_clip
- version: UNKNOWN

### What changed in this thread
1) LT_DATA(4ヶ月) レンジの止血
- 「target_months起点でズレる」問題に対し、LT_DATAの対象レンジを latest_asof 起点で固定（止血）
- 止血として「常に前月も含める」方針で運用上のズレを抑制

2) raw_inventory の重複キーで全停止する問題の解消
- 欠損チェック等で raw_inventory の重複キーが出た際に全停止しないように整理（運用/実装どちらかで “警告+優先ルール” の方向）
- 例外原因（CAUSE）をダイアログで表示する改善も実施

3) GUI改善（マスタ設定）
- cap_ratio_override の入力バリデーションを 0 < x <= 1 に
- 空欄時は学習済み/既定パラメータが使われることを補助説明（UI側で親切に）
- 欠損チェックの“失敗理由”をダイアログに表示（例外CAUSEを添付）
- マスタ設定のカレンダーUIを整理（ホテル選択を独立、カレンダー表示と操作の配置見直し）

4) 初回セットアップ導線（hotels.json 空テンプレ + ウィザード）
- 同梱側 config/hotels.json を {}（空テンプレ）に
- HOTEL_CONFIG が空のとき、GUI起動時に「新規ホテル作成ウィザード」を必ず表示
- 「対象ホテル」枠に「＋追加…」を設置し、任意でホテル追加可能
- ウィザード最小セット：
  - hotel_id（匿名ID推奨）
  - display_name（空欄なら hotel_id を使用）
  - capacity
  - adapter_type（現状 nface）
  - raw_root_dir（フォルダ選択）
  - include_subfolders
  - forecast_cap は capacity と同値で自動設定（後で変更）

5) 固有名排除 + hotel_tag 未指定の挙動統一
- src/ と tools/（src/_archive除く）からホテル実名ハードコードを撤去
- CLI/Tools 側は --hotel 必須化（未指定で黙って進まない）
- ホテル依存補正（例：segment_adjustment 等）は hotel_tag 未指定なら ValueError（黙殺スキップをしない）

6) 改行（CRLF混入）の止血
- 一部ファイルが w/crlf になったため、VSCodeでLFへ手動統一してZIP化
- 再発防止として repo に .vscode/settings.json を追加する運用が有効（files.eol=\n）

### How to verify (quick)
- 初回起動（hotels.json が空）→ ウィザードが必ず出る／キャンセル時は明確に停止
- ホテル追加（＋追加…）→ hotels.json に追記→選択肢更新→新規ホテルへ切替
- CLI/Tools：--hotel 未指定で明確にエラー、指定すれば正常起動
- hotel_tag 未指定：ホテル依存補正は ValueError で止まり、誤適用を防ぐ
- 改行：git ls-files --eol | findstr /i "w/crlf" が空

### Known issues / risks
- “version” の確定値がこのクローズアウト入力からは取得できていない（要確認）
- CLI only 運用で「初回セットアップをGUIなしで完結」させたい場合は、別導線（例：--init-config）検討が必要

### Next tasks (suggested)
- P0-1: pace14_market の power/clip 等の仕様を docs/spec_*.md に反映（Docs Gateに従う）
- 改行再発防止：.vscode/settings.json（files.eol=\n）を追加し、コミット前チェックを運用化

### Questions
1) Version（例：v0.x.y）はこのスレッドのクローズ時点で何に確定していますか？
回答：v0.6.11がリリース済の最新
2) raw_inventory 重複時の “優先ルール” は「先勝ち／後勝ち／最大asof優先」など、どれで固定しますか？
回答：後勝ち
