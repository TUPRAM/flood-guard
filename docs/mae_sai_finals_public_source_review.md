# Mae Sai finals: bounded public-source review

Reviewed on 21 September 2026. This review adds evidence to the non-operational
prototype; it does not change the flood-reference, scoring, or routing gates.
The durable review directory is `public_review` within the
`2026-09-21-mae-sai-finals` evidence release. Original responses stay outside Git.

## Useful additions

- `public_origins.json` and `public_origins.geojson` contain two prepared site
  markers: Mae Sai Municipal Office and Mae Sai Hospital. Each record binds its
  source URL, retrieval time, original-response hash, and coordinate basis.
  Both use `geometry_role=official_site_marker_not_entrance`; neither is a
  surveyed entrance or an assertion of event-time access.
- `public_identity_reviews_addendum.json` preserves the existing hospital and
  two municipal DDPM source-record IDs. It adds current official addresses,
  without approving a room-level identity merge, replacing historical source
  coordinates, or inferring capacity. Deduplicate the hospital against an
  existing OSM destination before using an alternate official site marker.
- `event_timeline.json` separates the original SAFE amplitude pair
  (3 to 15 September UTC) from the separate RTC experiment
  (22 August to 15 September UTC). Its official reports retain their own
  publication dates and observation precision.
- `finals_rules_review.json`, `source_gap_register.json`,
  `acquisition_manifest.json`, and `review_receipt.json` record the public
  findings, limitations, download attempts, and byte checks.

## Competition facts verified from the organizer

The [official GeoHackathon 2026 site](https://geohackathon.gistda.or.th/) exposes
the current instructions through **LET'S GO! → รายละเอียดการแข่งขัน**. The
judging tab specifies final-round weights of 40% Geo Intelligence, 35% GeoAI
methodology, and 25% communication and impact. The schedule and competition
format tabs give final pitching on **31 October 2026**, at Thailand Space Expo
2026. The application deadline is 2 August; it must not become an assumed
final-deliverable deadline.

The reviewed public sections do not specify the final file-upload cutoff,
pitch/Q&A duration, or required artifact formats. They direct finalists to
email for exact mentoring times. Participant-specific instructions remain a
separate input; no private account was accessed.

## Event and identity evidence

The [hospital's own site](https://www.maesaihospital.com/maesai/?stat=history)
gives its address and explicitly positions a map marker at
20.429362973196653 N, 99.87954134446397 E. The
[municipality's own page](https://www.maesai.go.th/?page=home) gives 68 Moo 8
and links to a named place marker at 20.4265478 N, 99.8843238 E. These are site
markers, not entrance observations. The
[Mittraphap contact page](https://www.maesaimittraphap.go.th/contact.php) gives
242 Moo 9, Ban San Sai. Its embedded map viewport centre was not accepted as
an exact site point.

The [11 September PRD report](https://chiangrai.prd.go.th/th/content/category/detail/id/9/iid/322964)
reports temporary-shelter occupancy at the municipality. The
[14 September DWF report](https://www.dwf.go.th/contents/70750) describes relief
delivery at the Mittraphap temporary shelter and kitchen. These support named
venue activity, not usable capacity or the exact historical inventory point.
The direct DWF HTTP response was a browser-check page; its HTTP200 status was
not counted as acquisition of the article.

An additional [municipal notice](https://www.maesai.go.th/filesAttach/news/1751614670.pdf)
is signed **21 October 2024** and retrospectively describes flooding from
10 September. Its riverbank/Big Bag restriction is October evidence, not a
September road-closure layer. The signed document date takes precedence over
search-index or filename timestamps for this statement.

## Gaps preserved

The [UNOSAT 3991 product](https://unosat.org/products/3991) still exposes a PDF
only. The public API has no vector or observation-footprint links, and the
reviewed HDX UNOSAT Thailand catalog has no corresponding September dataset.
The downloaded PDF is georeferenced but has no attached GIS dataset. Its four
map viewports are not observation footprints. It is cumulative for
13–19 September and preliminary; it cannot supply an independently accepted
15 September mask. PDF and API area summaries also differ slightly
(approximately 300 versus 305 square kilometres).

The product links to [UNITAR's terms](https://unitar.org/legal), which describe
attributed research and noncommercial uses. This review does not promote them
to an unrestricted, source-specific derivative GIS license. The October
product's unresolved 12/22 October discrepancy and its lack of per-patch dates
remain unchanged. No PDF tracing, synthetic footprint, or permission from an
unrelated dataset was substituted.

The [official DOPA catalog](https://gdcatalog.go.th/dataset/gdpublish-statbyagemonth-66)
lists 2024 monthly age statistics at multiple administrative levels, but its
resource leads to the same interactive DOPA site. Three public DOPA routes
timed out during this bounded review. Metadata was saved; no 2024 age-count
table or district age-definition clarification was acquired.

Official tourism material supports Mae Sai's market identity, but the map
link inspected resolved to a district centre. It was rejected as a market
origin pin. Absence from the checked routes is not a claim that no source
exists.
