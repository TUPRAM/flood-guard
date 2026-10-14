# The Nan case: plan v1

Written on 14 October 2026, before any reference of the case was opened, on
the owner's word of the same day ("go, do it with the recommended
decisions"). The rules that bind are in
`docs/proposal_execution/nan_case_protocol_v1.json`; this page says the same
in words. Decision log R51.

Every figure the case produces is agreement with a reference layer, not
accuracy. It is planning guidance, not an official warning, and not
real-time.

## 1. Why this case

The project's own radar flood map has never fed a planning score: at Mae
Sai no pass falls at the peak and no dated reference exists, so case SE1
reads the agency's season layer. This case tests our map on another Thai
flood where references from other satellites exist, then feeds it through
the unchanged chain to a class per tambon.

The Nan River floods of late July 2025 (Tropical Storm Wipha) are the only
flood that the THEOS-2 images we hold cover which also has, all public:

- a district-wide radar map from a different satellite and wavelength: the
  JAXA ALOS-2 Flood Proxy Map of 28 July 2025 (L-band), and one of 19 July;
- twelve Sentinel-1 passes from 16 July to 13 August, from Sentinel-1A and
  Sentinel-1C, with a Sentinel-1C pass on 28 July;
- the THEOS-2 chip of a flooded part of Wiang Sa town (31 July 2025, 0.5 m)
  and a chip of dry hills from the same scene;
- road cuts reported by the Ministry of Transport inside the frame, and news
  of the provincial hospital flooding.

The Ubon Ratchathani event of October 2022 stays unopened, as a reserve test.

## 2. The frame

The 35 tambons of Mueang Nan, Phu Phiang and Wiang Sa. Hospitals and routing
follow the SE2 frame rule of protocol v1b: the units buffered by 3 km, and
every OpenStreetMap hospital inside. Everything else of the planning chain
is that of protocols v1a and v1b, unchanged: closure rule v1 at three
levels, a hospital within 30 minutes by vehicle, a main road within 15
minutes, the national anchors, the weights and the class rules.

Grid: EPSG:32647, 20 m, 4,303 rows by 4,280 columns.

## 3. The method under test, M1-z

Each cell's VH backscatter on the flood day is set against its own
dry-season mean and spread: the passes of January to April 2025 of the same
orbit, at most ten, at least six valid. A cell is flagged when it is both
anomalous (a z-score at or below a limit) and dark (VH at or below a limit).

- Permanent water is never flagged.
- Ground high above the nearest drainage, or with a slope of 5 degrees or
  more, is answered "not flooded" by terrain.
- Built-up and tree-covered cells on low ground get no answer, as do cells
  with unstable dry-season backscatter or too few dry passes: the radar is
  not asked where it cannot see.
- Flagged groups smaller than 800 m² are dropped.

Four limits are chosen on three other events only: the THEOS-2 chip at
Sukhothai (30 July 2025), Mae Sai's dated agency layer of 22 October 2024,
and Chaiyaphum (Sentinel-1B of 27 September 2021 with a Sentinel-2 image 4.9
hours later). The choice is the best mean IoU with at most 20% of cells
without an answer in every set; ties go to the stricter limits. The choice
is frozen by SHA-256 and pushed before any Nan reference is read.

## 4. The five tests

| # | What | Reference | Rule fixed now |
|---|---|---|---|
| 1 | Water across the frame | JAXA ALOS-2, 28 July (fresh, another sensor) | IoU ≥ 0.40 with no-answer cells counted as not flagged, and at most 20% without an answer. Usable only if JAXA's product says where ALOS-2 looked over at least half the frame; otherwise the GFM map of the Sentinel-1A pass of 31 July, worded as same-pass agreement |
| 2 | Water in a town, and a dry control | THEOS-2 Wiang Sa chip (seen image, new method) and the dry hill chip | Reported. The dry chip: at most 5% of its answered cells flagged |
| 3a | Roads under water | THEOS-2 roads in the Wiang Sa chip | Share of closed edges with 20 m on water, as at Sukhothai |
| 3b | Reported road cuts | The Ministry's four points in the frame | Found if an edge within 300 m is closed on a pass of 20 to 31 July. Points placed before any flag is computed |
| 4 | The provincial hospital | News of its flooding in late July | A check only |
| 5 | Decisions | Classes from JAXA's map (case N2); the 180-cell ensemble | At least 70% of tambons in the same class; a class holds in at least 60% of cells |

## 5. What binds

If test 1 and the dry control pass, a tambon gets medium confidence where at
most 20% of it has no answer and at least 80% has an answer, and the other
conditions of confidence rule v1 hold. Its class is then binding (A to D
possible). Otherwise it is class E, low confidence, with the would-be class
beside it. The planning score is never accepted: `accepted_fpps` stays null.

## 6. What is not done in this run

Calibration of z-scores into probabilities, a Studio page for the case, the
DOPA registered ages for Nan, a rerun on a second machine, and 10 m maps of
the whole frame.

## 7. Rights

Sentinel-1 is Copernicus open data. The THEOS-2 samples are hackathon data
for free use (the owner's report of 3 July 2026); the originals stay outside
Git. The JAXA files are used under the Sentinel Asia site policy (scientific
use, no modification, credit "Provided by JAXA"): they stay sealed as
downloaded until the test, unmodified outside Git, and only figures computed
from them are published. Per-tambon results of case N2 stay in the work
folder. The Ministry's points are facts with a citation; their positions
come from OpenStreetMap (ODbL).
