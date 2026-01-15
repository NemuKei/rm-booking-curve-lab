# Thread Log: v0.6.9 fix/move-gui-settings-to-local-overrides

## Meta
- Branch: fix/move-gui-settings-to-local-overrides
- Release: v0.6.9
- Anchor (zip/commit): （不明→後で追記）
- Scope: GUI設定の保存先（output/→local_overrides/）統一

## Done (実装・変更)
- GUI設定（gui_settings.json相当）の出力先が output/ だった点を修正
- GUIでの上書き設定を local_overrides/ 配下に集約（端末ローカル上書きの置き場所を統一）

## Decisions (決定)
- 以後「GUIでの上書き設定」は local_overrides/ に集約する（APP_BASE_DIR運用の一貫性）

## Docs impact
- spec_overview / README:
  - local_overrides の位置付け（端末ローカル上書き）
  - output/ と local_overrides/ の役割分担

## Known issues / Open
- なし（または不明→後で追記）

## Next
- feature/pace14-market-forecast でモデル拡張・表示仕様の整理へ
