# MC.GOLD promo shorts

Three vertical shorts (1080×1920, 30 fps, H.264 + AAC, -14 LUFS) for TikTok, YouTube Shorts and Instagram Reels.
Every short ends on a **JOIN NOW / SERVER IP: MC.GOLD** card. The IP also stays on screen the whole time after the opening hook.

| File | Length | Hook | Story |
|---|---|---|---|
| `out/mcgold-short-1-get-paid.mp4` | 17s | "GET PAID TO PLAY MINECRAFT?" | Logo → 5+ events every Saturday → $5 per win → win 5 = $25 in one Saturday → join |
| `out/mcgold-short-2-beat-number-one.mp4` | 20s | "CAN YOU BEAT #1?" | Pans the real leaderboard (Netwax 23, Qocy 20) → "YOURS: 0?" → "LET'S CHANGE THAT." → $5 per win → join |
| `out/mcgold-short-3-new-pvp-server.mp4` | 20s | "LOOKING FOR A NEW PVP SERVER?" | Server-list entry gets clicked → Vanilla PvP → 2v2 ELO → Weekend Events → $5 per win → join |

Each short has a matching `-cover.png` to use as the thumbnail.

## Captions to paste

**Short 1: Get paid**
> Win an event on MC.GOLD = $5 💰 5+ events EVERY Saturday. IP: mc.gold
> #minecraft #minecraftserver #minecraftpvp #mcgold #minecraftevents

**Short 2: Leaderboard**
> Netwax has won 23 events. What's your number? 🏆 Every event win pays $5. IP: mc.gold
> #minecraft #minecraftserver #minecraftpvp #leaderboard #mcgold

**Short 3: PvP server**
> Vanilla PvP, ranked 2v2 ELO and 5+ events every Saturday. Bring your duo ⚔️ IP: mc.gold
> #minecraft #minecraftserver #minecraftpvp #2v2 #mcgold

## Editing and re-rendering

All the copy, timing, music and sound effects are in `render.py`. The functions `short_paid`, `short_leaderboard` and `short_pvp` each hold a readable timeline: change a line of text or a time, then run:

```sh
python3 render.py              # all three (about 2 minutes on 4 cores)
python3 render.py leaderboard  # just one: paid | leaderboard | pvp
```

You need Python 3 with `numpy` and `pillow`, plus `ffmpeg` and `curl`. On the first run, the two pixel fonts (Silkscreen and Press Start 2P, both SIL Open Font License) download into `.fonts/`.

Notes:
- The brand art in `assets/` is your own: the logos, the Weekend Events banner, the server-list entry and the leaderboard screenshot. The coins, sword, heads, blocks and night sky are pixel art generated in code, not game textures. The chiptune music and sound effects are synthesized in code too, so there are no copyright or music claims.
- The `0/3500` player count in the server-list screenshot is blanked out so the promo never shows an empty-looking server.
- When the leaderboard changes, replace `assets/leaderboard.png` with a new screenshot (same framing) and re-render. If row positions move, adjust the `A_NETWAX`, `A_QOCY` and `A_YOURS` boxes near the top of the shorts section.
