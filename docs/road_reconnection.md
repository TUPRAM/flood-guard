# Which road reconnects whom: the district, case SE1

**What this is.** The Ko Chang road sheet asked which closed roads, kept
passable, would give the residents of one tambon a route back. This page asks
it for the eight tambons together: in the scenario, at the central closure
level, 21,798 residents lose every road route. Which roads would give the most
of them a route back?

**How to read it.** A what-if on the model graph, report-only. A road is an
OpenStreetMap way; "kept passable" means every closed piece of it is taken as
open, and says nothing about how, or whether it can be done. Closures are
modelled from the season layer of 1 August to 12 October 2024, not observed;
no road was looked at on the ground. It is not an official warning, and
nothing here is a route to take in a flood.

- Result: `outputs/road_reconnection/se1_mae_sai_v1.json`
- Code: `scripts/build_road_reconnection.py`
- Source time: season layer of 1 August to 12 October 2024. Confidence: low.

## Who is cut off

| Tambon | Residents who lose every road route |
|---|---:|
| Mae Sai | 11,614 |
| Ko Chang | 5,972 |
| Si Mueang Chum | 2,897 |
| Pong Pha | 730 |
| Ban Dai | 359 |
| Pong Ngam | 149 |
| Wiang Phang Kham | 76 |
| Huai Khrai | 0 |
| **District** | **21,798** |

These are the counts of the committed access table.

## One road after another

At each step the road is added that gives the most residents a route back,
given the roads before it.

| Step | Road (OpenStreetMap way) | Closed length | Residents who get a route back | Mostly in | Share of all cut-off residents so far |
|---:|---|---:|---:|---|---:|
| 1 | Unnamed, unclassified ([206803562](https://www.openstreetmap.org/way/206803562)), in Si Mueang Chum | 1.3 km | **3,574** | Ko Chang (3,369) | 16% |
| 2 | Mueangdang Road, ชร.3059, tertiary ([1114870832](https://www.openstreetmap.org/way/1114870832)) | 0.8 km | **2,121** | Mae Sai | 26% |
| 3 | Unnamed, residential ([93294657](https://www.openstreetmap.org/way/93294657)) | 0.7 km | 431 | Si Mueang Chum | 28% |
| 4 | Mueangdang Road, ชร.3059, tertiary ([1112593664](https://www.openstreetmap.org/way/1112593664)) | 1.6 km | 323 | Ko Chang | 30% |
| 5 | Mueangdang Road, ชร.1041, tertiary ([935666325](https://www.openstreetmap.org/way/935666325)) | 1.1 km | 319 | Mae Sai | 31% |
| 6 to 10 | Five more roads | 11.9 km together | 1,097 together | Mae Sai, Ko Chang | 36% |

After ten roads 13,933 residents are still cut off, 8,402 of them in Mae Sai.

## What this says

1. **Two short roads do most of what single roads can do.** The first, 1.3 km
   in Si Mueang Chum, is the road the Ko Chang sheet names first; across the
   district it gives 3,574 residents a route back. The second, 0.8 km of
   Mueangdang Road, gives 2,121 residents of Mae Sai one. Together: a quarter
   of everyone cut off, for 2.1 km of road.
2. **After that the gains are small.** Steps 3 to 10 add 10 points for more
   than 15 km of road.
3. **Most of those cut off cannot be reached by keeping a road open.** Nearly
   two thirds stay cut off after ten roads. The need mix says why: of the
   21,798 residents who lose every route, 14,288 are in the water themselves.
   For them the road to their door is under the layer; what they need is not
   a route kept open.
4. **For Ko Chang the picture of the road sheet holds.** Its first road is
   the district's first road, and the same piece of Mueangdang Road (step 4)
   comes next for it.

## What may be said, and what may not

- "In this scenario two short roads, kept passable, would reconnect about a
  quarter of the cut-off residents" may be said, with "modelled" and "not
  checked on the ground".
- No road may be called passable, raised or safe. Whether the first road
  stayed above the water is exactly what the THEOS-2 image of the event is
  meant to show, and that image has not arrived.
- The order is greedy: the best single road at each step, not the best set.

## What was checked before anything was written

- The cut-off residents of every tambon are those of the committed access
  table.
- The first road of the Ko Chang sheet gets, for Ko Chang, the 3,369
  residents the sheet gives it.
- The fast count (joining parts of the graph) equals a full relabelling of
  the graph, for the best road on its own and at every step.

## Limits

- One closure level and the flood layer as provided. The Ko Chang sheet shows
  how its first road fares at the strict and the permissive level.
- Roads are OpenStreetMap ways as mapped; a way may be a track, a dyke road
  or a bridge approach. 1,129 ways have a closed piece; 100 help on their own.
- A road outside a tambon can be the one that reconnects it.

## Credits

Roads © OpenStreetMap contributors (ODbL 1.0). UNOSAT and GISTDA,
FL20240912THA, UNOSAT product 4009 (CC BY-SA 4.0); changed by FloodGuard, and
the figures derived from it are shared under CC BY-SA 4.0. Residents: WorldPop
2020 (CC BY 4.0).

## To run it again

```bash
python scripts/build_road_reconnection.py --external-root <external-data-root>
```
