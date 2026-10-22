# Rendering, movement and accessibility

The town retains its 40×23 grid and familiar buildings. Static pixel art is painted
once into a texture; sprites, labels, lighting and pooled smoke occupy separate
layers. Coordinate-based smooth noise produces coherent grass patches. Flowers
cluster by an independent noise seed, while building pots and shadows are drawn
without consuming terrain randomness. Cosmetic variation never changes Python RNG.

## Movement

Python owns destinations and resident schedules. The renderer adds per-actor,
seeded Gamma(shape=2, mean=0.6 seconds) departure delays and interpolates walking
between adjacent grid cells. It does not invent outings or send all residents to
bed when Aethel sleeps.

Parking slots are unique walkable tiles; one continuous street lane is excluded
from parking. BFS uses an indexed queue, returns adjacent tile waypoints and
reports failure as an empty route. It never takes a direct obstacle-crossing hop.
Actors reserve both ends of active edges, preventing overlaps and head-on swaps.
Waiters gain priority, replan around occupied cells, and yield to a free neighboring
tile after two seconds of blockage. Unchanged snapshot destinations preserve
ongoing movement. Deterministic stress tests exercise crowded opposing traffic.

Sprites have one idle and two alternating walking frames per direction. Labels
are textured once per actor and removed when that actor leaves. Smoke reuses a
bounded sprite pool. The default Canvas renderer avoids software-WebGL overhead
for this cached 2D scene; lighting and filters do not require WebGL.

## Day, night and performance

“Her rhythm” follows Aethel's sleep; Daylight and Nightfall override presentation
only. CSS custom properties coordinate panel colors, controls and readable text.
The canvas uses a blue-violet gradient/vignette with warm additive window and lamp
light. A slow, translucent CSS atmosphere adds subtle movement without a heavy
full-scene shader. There are no runtime image-generation or external font calls.

“Quiet & light” lowers smoke density and disables fireflies and atmospheric drift.
Reduced motion suppresses decorative animation, bobbing and twinkling while
retaining informative character movement. A hidden document suspends the Phaser
loop. Preferences persist locally; credentials do not.

The application shell loads before the separately split Phaser bundle. Static
assets are fingerprinted; only hashes receive immutable caching. The snapshot
hook avoids overlapping polls, bounds request duration and keeps prior real data
on failures. Stable journal IDs avoid remounting every entry on each update.

The canvas has a text description of resident locations. All care actions, filters
and presentation selectors are ordinary keyboard-operable controls with focus
indicators. A skip link, live connection status, reduced-motion treatment, mobile
layout and explicit empty/error states are part of the release checks.
