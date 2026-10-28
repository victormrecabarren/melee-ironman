# Melee Iron Man

A local, two-player Super Smash Bros. Melee Iron Man tracker. No account or backend required.

## Run locally

Requires Node.js 22+.

```sh
npm install
npm start
```

Open the local address printed by Vite. `npm run build` creates a static site in `dist/`; `npm run preview` serves the production build. The relative asset paths also support hosting under a subdirectory.

## Play

The animated match tracker is the main page at `/`. Existing `/?animation-preview` links still open the same app and use the same browser save.

- Player 1 starts with Dr. Mario; player 2 starts with Roy and follows the reverse order.
- New matches open on a card using the original US Melee title textures. **Start match** unlocks browser audio and begins the arrival and original GO! sequence; saved matches resume directly.
- Tap the winning character to remove one opponent stock. Each character starts with two stocks; losing both brings in the next character.
- Hold a character to charge their forward smash, then release to strike. A winner taunts after taking a character's final stock while the next arrival continues independently.
- Tap anywhere in the arena during an arrival or respawn platform wait to drop immediately. The full fall and landing still play; this tap never awards a stock.
- Both sides have live per-character stock totals with original stock icons identifying their defeated opponents.
- The final roster stock triggers the original Game! overlay and announcer.
- Matches, stats, and undo history save in this browser and resume after reload.
- **Start Over** resets characters, stocks, stats, undo history, animation state, and preferences, and replaces the saved match with a fresh one.
- Sound and reduced-motion preferences are available below the match.

## Development controls

The header's **More** menu appears only in development (`import.meta.env.DEV`). It contains replay entrance, phase/character corrections, undo, and animation frame inspection. These controls are absent from production builds.

All 26 roster characters are installed in both real facing directions, with separate Nana exports for the Ice Climbers. The roster exporter stages both directions independently. Missing exports are disabled and labeled **preparing**. A rendered atlas is not a full fidelity certification: the audit records clipping, missing effects, and move-specific mechanisms that still require review. Current limitations include character-specific held items, independent Ice Climbers partner AI/percent, some custom effects, and pitch-shifted sound scripts. Camera/knockback choreography is an adaptation, not a running Melee engine.

**Inspect animation frames** includes previous/next single-frame controls and play/pause beside the slider. Scrubbing or changing sequence pauses playback; play at the end restarts the selected sequence. Inspection does not change stocks.

Ice Climbers load Popo and Nana as separate original model/motion atlases in both facing directions. Both are drawn during entrance, idle, attack, damage, offscreen tracking, and respawn, with shared stocks. The paired smash has separate animation clocks, two contact bursts six frames apart (matching the supplied 60 Hz reference), and independent attacker hitstop. The opponent launches after Nana's hitstop ends. Their five-unit idle separation, approach into the paired hit, and shared elimination are preview choreography; independent partner AI, recovery, percent and collision simulation are not implemented.

The normal contact burst (used by Falco) is a particle-only effect: `EfCoData.dat` model 10 emits generators 2, 306, and 307. Export it with `render_particles.py --only normal-impact`, then compact it. Importing that model as a mesh produces invisible black frames. The particle export retains the source yellow/red/blue/green cycle and damage-based scale, and is checked for visible RGB, clipped particles, and decoded memory usage.

Reproduction details and source references are in `tools/melee/pipeline.json`. Use `render_roster.py` with a staging directory, then `import_roster.py` to check and install exports; `roster-audit.json` retains the findings. `export_stocks.py` rebuilds the stock HUD from locally extracted game files. No ISO is bundled.

`export_title_card.py` decodes the unchanged logo, Melee lettering, and Smash symbol from `GmTtAll.usd / TtlMoji_Top_joint`; `title-card-source.json` records their source IDs and archive hash. `export_game_end.py --kind go` exports the original GO model and announcer. Fresh arrivals use the original trophy platform, entry effect 0x43E and color animation 117; revival invincibility applies only to returning characters.

After importing fighter exports, run `compact_fighters.py --output public/melee-preview`. Run it again with `--environment` after effect exports. It trims transparent borders and packs unchanged pixels into pages no larger than 2048×2048, retaining logical anchors and every animation frame. This avoids enormous idle textures (Ness idle: 210 → 7.63 MiB; all preloaded effects: about 380 → 74 MiB). Regenerated raw atlases remain readable, but should be repacked before phone review. Development phase profiles cover the result, respawn, and ready transitions; these desktop timings are not an iPhone benchmark.

After exporting KO models or particles, run `compact_effects.py --output public/melee-preview`. Playback uses packed visible rectangles instead of decoding the padded 8192px particle sheet; the three KO atlases together use about 14 MiB of decoded pixels. KO size is adapted to the viewport independently of fighter-camera zoom. Development builds log a short KO frame-timing profile after each blast; those measurements describe the current browser, not an iPhone benchmark.

Fighter exports use `source-specular-v1`: original specular RGB controls highlight color, the original enable flag controls whether highlights appear, and shininess controls highlight width. This corrects the legacy Blender tint conversion that made dark fur look gray and glossy. `refresh_installed_materials.py` regenerates installed animations with their existing framing and timing; complete fighters publish atomically using versioned atlas names. The roster importer rejects stale material exports. Online gameplay comparisons and their limits are recorded in `asset-research/verification/material-reference-review.json`; stage lighting and the Cycles shader remain approximations of GX.

The preview chooses matchup spacing from posed forward-smash hitboxes and neutral idle hurt capsules extracted from the disc. It accounts for animated forward reach, delays contact until the move reaches the opponent, and uses the same positions for camera framing and tap targets. `export_combat_geometry.py` backfills this metadata into installed atlases without rerendering them; full fighter exports include it automatically. This is staged choreography using source collision shapes, not a full collision simulation.

## Verify

```sh
npm test
npm run build
```

Tests cover roster order, carryover, final outcomes, a maximum-length run, results statistics, save validation, and undo replay.

The app saves its match to `melee-ironman:animation-session:v1` in localStorage. The existing key is retained so earlier animation-page saves continue to load. Each accepted stock is journaled before the next fighter is loaded; snapshots retain the pending transition, relative animation clock, stock history, played characters, undo stack, and sound/motion preferences. Reloading restores the pending KO or completed match without applying the stock twice. Visibility/page-hide saves preserve the latest playback position, and background tabs skip drawing. Storage failures surface an alert. Saves are local to the browser and origin, so changing the hostname/port or clearing site data does not carry them over.
