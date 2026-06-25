# WeChat Cover Spec

Last checked: 2026-06-25.

No publicly indexed official WeChat backend documentation page was found during this check. Current public design references in the WeChat ecosystem consistently describe:

- Main/top article cover: `2.35:1`, commonly `900x383`.
- Main cover safe square: center crop around `383x383`; keep important subjects inside this area.
- Attached/sub article thumbnail: `1:1`, commonly square.

References checked:

- Canva China WeChat official account sizes: https://www.canva.cn/sizes/wechat-official-account/
- Yiban 2026 cover guide: https://yiban.io/geo/36058
- Yiban cover-size article: https://yiban.io/blog/24836
- 135 Editor guide: https://www.135editor.com/essences/10593.html

Execution rule:

Treat `900x383` / `2.35:1` and square attached thumbnails as the working production spec, but the future WeChat publishing skill must re-check the live WeChat backend UI before upload and record the observed backend guidance in `publish_draft_report.json`.
