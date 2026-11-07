# Pattern design — "Dawn Patrol"

Designed for: 7–11AM daylight riding, sessions up to 3 hours, Cobber Mini Rear.

## What the evidence says

**Daytime running lights work, and the effect is large.** A Danish controlled
experiment found cyclists running permanent daytime lights had 33% fewer
crashes and 41% fewer injury-producing crashes over a year, with the effect
strongest in daylight. Running a rear light at 8AM is not optional kit.

**Flashing is detected far sooner than steady.** A Clemson study found a
flashing rear light was detected at roughly 3.1× the distance of a steady
one — about 82 m sooner. The mechanism is exogenous attention capture: abrupt
onsets involuntarily grab attention and defeat the "selective attention" that
makes drivers look without seeing.

**But flashing alone has a known cost.** The long-standing objection is that a
light which keeps vanishing gives drivers nothing stable to judge distance and
closing speed against. More recent work (2024) found steady *flashing* actually
improved distance estimates versus static, so the effect is weaker than folk
wisdom holds — but the safe design is not to bet on it.

**So the recommended configuration is both at once:** something bright and
abrupt for attention, plus something continuously present for ranging. Normally
this means running two lights. The Cobber Mini does not need two, because a
step can be dim rather than off — the pattern below never goes fully dark.

**Frequency has a hard constraint.** Avoid flash rates in the 3–30 Hz band,
which is the photosensitive-epilepsy risk range. Stay below 3 Hz.

**Daylight demands peak brightness.** Against bright ambient, dim modes are
invisible; the guidance floated for daytime is 100 lm and up. This light peaks
at 75 lm, so every flash should use the full 7/7 brightness — there is nothing
to hold back for.

## The 7–11AM problem specifically

That window is the worst case for a *rear* light. The sun is low in the east
for much of it, so on any easterly leg the driver behind you is looking
straight into low sun with your light silhouetted against glare. Peak output
during flashes is what survives that; an average-brightness "steady bright"
mode does not.

## The design

```
Mode 1 "Dawn Patrol"
  0xEF  brightness 7/7  ch 1-4   short (20)   flash A
  0x2E  brightness 1/7  ch 1-3   short (20)   dip - never fully dark
  0xEF  brightness 7/7  ch 1-4   short (20)   flash B
  0x3E  brightness 1/7  ch 1-3   long (250)   steady floor
```

The first version used a brightness 2 floor and a long delay of 150. It died
after about 2 hours on a 27 °C ride, so both were cut back for runtime (see
[Runtime](#runtime)).

Three deliberate choices:

- **A doublet, not a single flash.** Grouped, irregular flashes read as more
  urgent than a metronomic blink and hold attention better once captured.
- **The floor never reaches zero.** Brightness 1 between doublets is the
  "steady light" half of the recommended pairing, so there is always something
  to range against. It also means the light reads as a steady lamp with pulses
  rather than a pure flasher, which matters where pure flashing rear lights are
  restricted (Germany's StVZO being the obvious case — Knog sells a separate
  StVZO variant for exactly this reason). **Check your local rule.**
- **Flashes use all four channels, the floor uses three.** The factory PULSE
  mode does the same thing — `0xEF` at peak — so channel 4 appears to be the
  full-output configuration even though the catalog lists this model as
  3-channel.

`Mode 2 "Glare"` is a triplet with a brightness 3 floor for the worst
conditions. It costs about 2 hours of runtime, so use it for stretches, not
whole rides. `Mode 3 "Peloton"` is a steady brightness 1 for group riding.

## Runtime

Factory figures for the Cobber Mini Rear:

| Mode | Lumens | Runtime |
|------|--------|---------|
| HIGH | 40 | 2 hr |
| LOW | 10 | 8 hr |
| PULSE | 75 | 6 hr |
| STROBE | 75 | 8 hr |
| ECO | 15 | 75 hr |

Note that PULSE peaks brighter than HIGH (75 lm vs 40) yet lasts three times
longer. That is duty cycle doing the work, and it is the whole basis of this
design: **a 3-hour session cannot be served by a steady bright mode** (HIGH
gives 2 hr), but is trivially served by a low-duty pattern with full-brightness
peaks.

### Estimating a pattern

HIGH (40 lm for 2 hr) and LOW (10 lm for 8 hr) both work out to about **80
lumen-hours**, so treat the battery as an 80 lm·hr budget and divide by the
pattern's average output. Assume 7/7 on ch 1-4 is 75 lm and that brightness
scales linearly. That second assumption is unverified, so the numbers are
estimates.

A steady floor is a constant load. Do not compare it to ECO: ECO is a flash
mode, and its 75 hr comes from being dark most of the time. The original
version of this doc made that mistake and predicted 5-7 hours for a pattern
that lasted about 2.

| Pattern | Cycle | Avg output | Runtime (new battery) |
|---|---|---|---|
| Dawn Patrol v1 (floor 2, long 150) | 210 | ~27-30 lm | ~2.7-3 hr (measured ~2) |
| **Dawn Patrol v2 (floor 1, long 250)** | 310 | ~17-19 lm | **~4-5 hr** |
| Glare | 170 | ~38 lm | ~2 hr |
| Peloton (steady 1/7) | - | ~8 lm | ~10 hr |

In v2 the flashes are 13% of the cycle (down from 19%), and the floor draws
half what it did. That leaves room for battery wear and partial charges against
a 3-hour ride. If v2 still falls short of 3 hours from a full charge, the
battery has worn and the light needs replacing.

## The one unconfirmed number

The delay **unit** is unknown. The factory values (10, 150, 175) are unitless
in the firmware. If one unit is ~2.6 ms then this pattern runs at ~2.2 Hz,
comfortably under the 3 Hz floor of the risk band — but that is inferred from
assuming the factory PULSE mode runs at about 1 Hz.

**Calibrate it before trusting the rate.** Put the light in its current mode 2
(the factory pulse), time ten full cycles with a stopwatch, and divide. The
factory mode 2 cycle is 390 units, so:

```
unit_ms = (seconds_for_10_cycles * 1000) / (10 * 390)
```

If the unit turns out much larger than ~2.6 ms, the doublet spacing should
stretch to keep the rate under 3 Hz; much smaller and the whole cycle should
lengthen so the pattern does not blur into apparent steadiness.

## Preview it

`patterns/dawn-patrol.json` is written in backup format, so it loads straight
into `web/index.html` via *Load backup JSON* and animates — no hardware, no
writes.

## Sources

- [Safety effects of permanent running lights for bicycles: a controlled experiment](https://www.researchgate.net/publication/230653054_Safety_effects_of_permanent_running_lights_for_bicycles_A_controlled_experiment)
- [The conspicuity benefits of rear-facing bike lights in daylight](https://journals.sagepub.com/doi/10.1177/1071181319631427)
- [The effect of rear bicycle light configurations on drivers' perception of cyclists' presence and proximity](https://www.sciencedirect.com/science/article/pii/S0001457523004657)
- [Highlighting bicyclist biological motion enhances their conspicuity in daylight](https://www.sciencedirect.com/science/article/abs/pii/S0001457519311753)
- [Flashing vs steady bike lights: which is safest and what does the law say?](https://www.bikeradar.com/advice/buyers-guides/flashing-bike-lights)
- [Cobber Mini Rear specifications](https://us.knog.com/products/cobber-mini-rear-bike-light)
