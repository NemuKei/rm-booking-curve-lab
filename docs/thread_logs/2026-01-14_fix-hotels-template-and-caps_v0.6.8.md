# Thread Log: v0.6.8 fix/hotels-template-and-caps

## Meta
- Branch: fix/hotels-template-and-caps
- Release: v0.6.8
- Anchor (zip/commit): （不明→後で追記）
- Scope: hotels.jsonテンプレ運用 / cap運用の整理

## Done (実装・変更)
- hotels.jsonテンプレ運用を「まっさら配布で安全な最小雛形」に寄せた
- テンプレ側のデフォルト仮値は 0 ではなく固定整数 100 を採用
- cap（forecast_cap等）は「hotels.json」と「GUIローカル上書き」の二層運用で確定

## Decisions (決定)
- 配布テンプレは匿名性・安全性優先で “最小” にする
- capは二層（設定ファイル + ローカル上書き）でよい

## Docs impact (docs反映が必要)
- spec_overview / README:
  - hotels.jsonテンプレの設計意図（配布用＝最小・安全）
  - capの二層運用（hotels.json / GUI local overrides）
- Future（要望メモ）:
  - “いま適用されているcapの出所（hotels.json / gui_settings等）”をUI表示したい

## Known issues / Open
- なし（または不明→後で追記）

## Next
- v0.6.9でGUI設定の保存先統一へ