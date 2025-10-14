# Dataset Reference

This document defines the listing datasets by county and their corresponding zip codes.

## Datasets by County

### Murray County (Utah)
**File:** `s3://demo-hearth-data/murray_listings.json`
**Zip Codes:** 84117, 84121, 84124
**Total Listings:** 1,588
**Status:** ✅ Fully indexed
**Cities Included:** Salt Lake City, Holladay, Millcreek, Murray, Cottonwood Heights

### Salt Lake City County
**File:** `s3://demo-hearth-data/slc_listings.json`
**Zip Codes:** 84101, 84102, 84103, 84104, 84105, 84106, 84108, 84109, 84110, 84111, 84112, 84113, 84114, 84116, 84122, 84125, 84126, 84127, 84130, 84131, 84132, 84133, 84134, 84136, 84137, 84138, 84139, 84140, 84141, 84142, 84143, 84144, 84145, 84147, 84148, 84150, 84151, 84152, 84153, 84158, 84171, 84180, 84184, 84189, 84190, 84199
**Total Listings:** 3,904
**Status:** 🔄 Currently indexing (~155/3904 complete)
**Cities Included:** Salt Lake City, North Salt Lake, and surrounding areas

---

## Notes

- "Murray" refers to the zip code area (84117, 84121, 84124), not just Murray city
- Listings are scraped by zip code, so one dataset may contain multiple cities
- Use zip codes (not city names) to accurately count listings from a specific dataset
