# Mae Sai Real Context Integration Quality Report

> Open context joined to real Sentinel-1 candidate evidence. Non-operational. Not official validation. Not an official warning.

## Integration Result

- COD-AB ADM3 reporting units: 8
- OSM drivable ways: 4,458
- Routable road edges: 30,443
- OSM bridge-tagged ways: 121
- OSM candidate facilities: 42
- Road-snapped population nodes: 13,620
- WorldPop 2020 aggregate population: 81,799

## Coverage And Join Quality

- Minimum WorldPop bbox coverage: 97.5%
- Minimum road-snap population coverage: 100.0%
- Minimum DEM population coverage: 81.9%
- Highest expected-exposure proxy: TH570906 / Wiang Phang Kham

## Material Limitations

- The manual weak-reference polygon does not overlap official Thailand ADM3 geometry; it is nearby cross-border calibration evidence only.
- WorldPop is a 2020 modeled population surface, not a current census.
- OSM roads, bridge tags, and facilities are community-mapped and unverified for emergency operations.
- DEM coverage can be partial along the eastern edge of Mae Sai because the selected N20/E099 tile ends at 100E.
- Vulnerability is a terrain/remoteness proxy, not demographic vulnerability.
- Road risk uses ADM3-level Sentinel-1 mean/P90 proxies rather than segment-level raster intersections.
- Road disruption and access loss are modeled candidates, not observed closures.

> Open context joined to real Sentinel-1 candidate evidence. Non-operational. Not official validation. Not an official warning.
