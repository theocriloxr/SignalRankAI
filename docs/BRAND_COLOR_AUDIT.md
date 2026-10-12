# SignalRankAI brand and color audit — source-grounded

Authority: `frontend/public/brand/icon.svg` (approved identity) → current `frontend/src/app/globals.css` theme tokens → established production interface → original derived supporting shades. The requested master prompt's blue-market-terminal palette is *not* higher authority than approved production green/silver. The existing stylesheet has a historical first `:root` and a later active shared-emerald `:root`; the latter wins for matching token declarations.

| Role | Current HEX | RGB | Source |
| --- | --- | --- | --- |
| Dark background | #08120F | 8,18,15 | `globals.css` active dark root |
| Dark surface | #101E19 | 16,30,25 | `globals.css` |
| Elevated dark | #14251D | 20,37,29 | `globals.css` |
| Dark text | #E6EEEA | 230,238,234 | `globals.css` |
| Supporting text | #A5B8AD | 165,184,173 | `globals.css` |
| Borders | #294036 | 41,64,54 | `globals.css` |
| Primary accent | #4CE0A4 | 76,224,164 | `globals.css` |
| Secondary accent | #BCF4D7 | 188,244,215 | `globals.css` |
| On primary action | #071C12 | 7,28,18 | `globals.css` |
| Light background | #F1F5F3 | 241,245,243 | light theme |
| Light surface | #FFFFFF | 255,255,255 | light theme |
| Light text | #152A21 | 21,42,33 | light theme |
| Light accent | #08754E | 8,117,78 | light theme |

For OKLCH, compute exact conversions and inspect actual browser contrast before documenting values. No guessed OKLCH data. Financial gain/loss, success, warning and danger remain **semantic**, never decorative. Existing accent green is not a positive-trade state by itself. Do not change favicon/logo, Telegram mark or trade direction colors without product evidence.
