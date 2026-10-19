# Comet Hop: Playabl Green Light Demo

A one-tap mobile game. Your comet circles a planet. Tap to let go, fly along the arrow, and land in the next orbit. Hop all the way up to the ringed goal world.

Everything is in `index.html`: plain HTML, CSS and canvas, with no build step and no dependencies apart from two Google Fonts. Open the file in a browser to play.

## How it meets the brief

| Requirement | In the demo |
| --- | --- |
| Fun in the first 30 seconds | Two taps from the title screen to the first hop. World 1 opens with a "Tap anywhere to let go" hint and a slow orbit, so the first hop succeeds almost every time. |
| 3 playable levels, each adding something new | **1 · First Flight** teaches the hop. **2 · Drift** adds moving planets and asteroid lanes. **3 · Event Horizon** adds black holes that bend your path, with a final asteroid lane on top. |
| Mobile-ready | Full-screen canvas, touch-first input, safe-area aware, frame rate independent (fixed 240 Hz physics). Pauses when the tab is hidden. Also works with mouse and keyboard (Space to launch, Esc to pause). |
| A natural rewarded moment | **Second Wind**: after a crash, watch an ad to respawn on your last planet and keep your stars. **Aim guide**: watch an ad to see your predicted flight path for the rest of the world. The button pulses after two deaths. Both are optional, and "Retry world" is always free. |

Each world has 3 collectible stars. Best scores and unlocked worlds are saved on the device.

## Wiring up real rewarded ads

All ad logic goes through one function in `index.html`:

```js
function showRewarded(placement) { /* returns Promise<boolean> */ }
```

Right now it shows a 3-second placeholder. Replace its body with Playabl's rewarded-ad call, and resolve `true` only when the player watched to the end. There are two placements, `'second-wind'` and `'aim-guide'`, and the game pauses while the ad is up.

## Playtest numbers

An automated playtest launched from every angle on every planet. Every world is beatable, every star can be reached, and asteroids never cross an orbit.

| World | Timing window per hop | Orbit speed |
| --- | --- | --- |
| 1 · First Flight | 0.3–0.5 s | 2.1 rad/s |
| 2 · Drift | 0.3–0.4 s | 2.5 rad/s |
| 3 · Event Horizon | 0.18–0.3 s | 2.3 rad/s |

Free flight is capped at 0.9 s, during which the comet visibly dims. A very precise shot can skip one planet, but never a whole world.

To make a world easier or harder, change `spin` (orbit speed), `grab` (how far outside the dashed ring a planet catches you), or the planet, rock and black-hole positions in `LEVELS`.

## Rebuilding it inside Playabl

Playabl builds games through chat. To recreate the demo there, use the design above as the spec and build it one step at a time. Use Lite or Power for these steps, and save Max or Ultra for polish passes.

1. "One-tap vertical space game. A glowing comet orbits a planet. Tapping releases it along the tangent. It is caught when it enters another planet's dashed orbit ring. The camera follows upward. Reach the ringed goal planet to win."
2. "Add 3 collectible stars per level, a star counter, and a win screen with stars and time."
3. "Level 2: planets slide side to side; asteroids move along dotted horizontal lanes and destroy the comet on contact."
4. "Level 3: black holes pull the comet while it flies and destroy it at the core. Show a swirling disc and inflowing rings."
5. "Rewarded ad moments: Second Wind (respawn on last planet, keep stars) on the crash screen, and an Aim guide button that shows the predicted path."
6. Polish: particles on launch, capture and crash, screen shake, sounds, and the level intro banner.
