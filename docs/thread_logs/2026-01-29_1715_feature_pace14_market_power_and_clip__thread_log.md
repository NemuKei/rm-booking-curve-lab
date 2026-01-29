Proposed file path: docs/thread_logs/2026-01-29_1715_feature_pace14_market_power_and_clip__thread_log.md

# Thread Log

## Meta
- Meta Date: 2026-01-29
- Type: feature
- Scope: pace14_market_power_and_clip
- Branch: feature/pace14_market_power_and_clip
- Commit: f0751a0
- Version: UNKNOWN
- Source ZIP: rm-booking-curve-lab_20260129_1651_samp_feature-pace14_market_power_and_clip_f0751a0_full.zip

## Goal
- LT_DATA(4ヶ月) の対象レンジのズレを止血（latest_asof起点固定、必要なら前月も含める）
- raw_inventory の重複キーで欠損チェック等が全停止する問題を解消
- 固有名ハードコード撤去と hotel_tag 未指定挙動の統一（誤適用防止）
- 初回セットアップ（hotels.json 空テンプレ）でウィザード導線を整備

## Work summary (What happened)
1) LT_DATA(4ヶ月) のレンジ問題
- target_months を動かした際の “起点ズレ” を回避する方針として、latest_asof起点で固定レンジを採用
- 止血として「常に前月も含める」案で合意し、挙動のズレを抑制

2) RAW 0/欠損の整理（保留含む）
- 0頻発＝欠損扱いにしない方向で壁打ち
- 「欠損＝特定ASOFのRAWが丸ごと欠損」を前提に、まず欠損チェックとエラーハンドリングを改善（詳細定義の分離は保留）

3) 欠損チェックのエラーハンドリング改善
- 欠損チェック失敗時に“失敗理由（例外CAUSE）”をダイアログへ表示する方針で合意・反映

4) GUI（マスタ設定）改善
- cap_ratio_override の入力バリデーション：0 < x <= 1
- 空欄時は学習済み/既定パラメータ利用であることをUI上で説明
- カレンダー表示/操作周りのUIを整理（ホテル選択をカレンダー枠から独立）
- 「カレンダー再生成」ボタンは表示と並置し、注釈（通常不要）を付与する方向で合意・調整

5) 初回セットアップ導線（hotels.json 空テンプレ + ウィザード）
- 同梱側 config/hotels.json を {} に
- HOTEL_CONFIG が空なら初回ウィザード必須（キャンセル時は明確に停止）
- 「対象ホテル」枠に「＋追加…」で任意追加導線
- ウィザード入力：hotel_id / display_name（空欄はIDコピー）/ capacity / adapter_type / raw_root_dir / include_subfolders / forecast_cap=capacity（注釈）

6) 固有名排除 + hotel_tag未指定の統一
- src/ と tools/ から実名ハードコードを撤去（src/_archive除外）
- CLI/Tools は --hotel 必須化
- ホテル依存補正は hotel_tag 未指定なら ValueError（無音スキップを避ける）

7) CRLF 混入の止血
- w/crlf が残存し続ける問題を切り分け
- 最終的にVSCodeでLFへ手動統一し、ZIP化
- 再発防止として .vscode/settings.json（files.eol=\n）作成手順を整理

## Files changed (high level)
- GUI: マスタ設定UI（cap_ratio_override validation、欠損チェックCAUSE表示、カレンダー/ホテル選択配置、ホテル追加導線）
- Config: hotels.json 空テンプレ、空許容、hotel追加API、reload
- CLI/Tools: --hotel 必須化、実名削除、help例匿名化
- Models: hotel_tag 必須（ホテル依存補正でValueError）
- Line endings: 対象ファイルLF統一

## Decisions (agreement log; not spec)
- hotels.json は同梱側を空テンプレ {} にし、初回はウィザードで作成
- hotel_tag 未指定時に黙って補正スキップはしない（エラーで気づけるようにする）
- CLI/Tools は --hotel 必須で統一

## Validation
- 初回起動でウィザード起動、追加後にホテル選択へ反映
- --hotel 未指定で明確にエラー
- git ls-files --eol で w/crlf が残らない（LF統一）
