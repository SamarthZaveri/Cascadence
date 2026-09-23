# Phase 3 data sources and provenance

Catalog reviewed 2026-09-21. `backend/app/services/extra_signals/data/catalog.json` is the
versioned source list. It is a small, dated starter dataset, not a comprehensive live feed.

| Source | Included evidence | Interpretation |
|---|---|---|
| [Apple, November 2022](https://www.apple.com/newsroom/2022/11/update-on-supply-of-iphone-14-pro-and-iphone-14-pro-max/) | Zhengzhou assembly constraints | Historical company announcement; no invented end date |
| [Toyota, May 2022](https://global.toyota/en/newsroom/corporate/37370481.html) | Scheduled Japanese plant suspensions | Announcement-specific May/June dates, not total shortage duration |
| [Apple, August 2025](https://www.apple.com/newsroom/2025/08/apple-increases-us-commitment-to-600-billion-usd-announces-ambitious-program/) | TSMC, Corning and TI supplier context | Announced expansion is not proof every facility is operating |
| [Apple/Amkor, November 2023](https://www.apple.com/newsroom/2023/11/apple-announces-expanded-partnership-with-amkor-for-silicon-packaging/) | Established packaging relationship and Peoria development | Existing corporate relationship and planned site are distinguished |
| [Le Monde, September 2026](https://www.lemonde.fr/en/economy/article/2026/09/14/houthi-control-of-bab-al-mandab-strait-poses-new-threat-to-global-economy_6757506_19.html) | Reported Maersk/CMA CGM route exposure | Attributed report, not verified company-specific delay; ages out after 30 days |

Only brief original summaries are stored, not copied articles. Company membership does
not imply disruption. The four supplier links are curated public-source evidence rather
than automated extraction guesses. Their confidence label denotes curator assessment,
not measured probability; edge criticality remains 0.5 pending real impact calibration.

Twelve areas include Zhengzhou, four Toyota locations, TSMC Phoenix, Amkor Peoria, Corning
Harrodsburg, TI Sherman, Los Angeles/Long Beach ports and Bab al-Mandab. Coordinates are
explicitly approximate manually selected WGS84 centers, not surveyed facility polygons.
Linked announcements document location context, not precise coordinates. Regional imagery
can include unrelated land uses. Do not infer facility output from these windows.

## Observational sources

[Copernicus Process API](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Process.html)
and its [authentication guide](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Overview/Authentication.html)
underlie the Sentinel-2 L2A adapter. Real red/NIR/RGB/SCL/dataMask values are requested
on a common grid. Source-product IDs, actual timestamps, bounding boxes and raster hashes
are retained. Cloud/coverage checks can reject an area; that rejection produces no image.

[NASA VNP46A3](https://ladsweb.modaps.eosdis.nasa.gov/missions-and-measurements/products/VNP46A3)
provides monthly Black Marble observations. The adapter uses Collection 002, masks poor
quality/fill pixels, applies file scaling metadata, and records tile/grid/units and
source hashes. Monthly light variation can have many causes; it is not a factory output
or risk label. A bearer token is needed to download the HDF5 files.

[NOAA MarineCadastre's official repository](https://github.com/ocm-marinecadastre/ais-vessel-traffic)
provides the original data links and CC0 licensing. Its
[point-data specification](https://github.com/ocm-marinecadastre/ais-vessel-traffic/blob/main/data/ais-broadcast-points-2024-readme.md)
describes UTC timestamps and WGS84 WKB geometry. The downloader reads Jan 1–4, 2024 files
and filters to [-118.28,33.70,-118.25,33.74]. It records each file's URL/hash and the subset
hash. Original positions are retained; no interpolation, invented vessel identities or
synthetic missing days are inserted. The ZIP ships this downloader, not a predownloaded
sample. Source failure remains visible until a real download succeeds.

Source bytes are cached outside Git. Provider credentials, caches and test fixtures are
not included in the delivered data catalog. The previous incomplete checkpoint's missing
AIS sample is not claimed recovered or verified; the new explicit downloader replaces
that dependency. Full live-source validation remains an installation acceptance step.
