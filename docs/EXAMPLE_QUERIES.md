# Comprehensive Search Query Examples

This document contains 100 real-world search queries that users might ask, organized by category.

## Architecture Style Queries (10)

1. "Show me modern homes with clean lines and large windows"
2. "Find craftsman style houses with front porches"
3. "I want to see Victorian homes with ornate details"
4. "Show me mid-century modern houses with flat roofs"
5. "Find colonial style homes with symmetrical facades"
6. "Show me ranch style homes with attached garages"
7. "I'm looking for Mediterranean houses with tile roofs"
8. "Find Tudor style homes with timber framing"
9. "Show me contemporary houses with minimalist design"
10. "Find farmhouse style homes with wrap-around porches"

## Outdoor Features (15)

11. "Show me homes with a swimming pool and hot tub"
12. "Find houses with a large backyard and patio"
13. "I want homes with an outdoor deck for entertaining"
14. "Show me properties with a fenced backyard for dogs"
15. "Find homes with a white picket fence"
16. "Show me houses with a balcony overlooking the mountains"
17. "Find properties with a screened-in porch"
18. "I want homes with a front porch and rocking chairs"
19. "Show me houses with a wood fence for privacy"
20. "Find homes with a stone patio and fire pit"
21. "Show me properties with a metal fence and gate"
22. "Find houses with a chain-link fence"
23. "I want homes with a vinyl fence that's low maintenance"
24. "Show me properties with an iron fence"
25. "Find homes with a deck and pergola"

## Garage & Parking (10)

26. "Show me homes with a 2-car garage"
27. "Find houses with a 3-car attached garage"
28. "I want properties with a detached garage and workshop"
29. "Show me homes with a 1-car garage and driveway"
30. "Find houses with an oversized garage for an RV"
31. "Show me homes with a covered carport"
32. "Find properties with garage storage space"
33. "I want homes with a heated garage"
34. "Show me houses with a garage and extra parking"
35. "Find homes with an attached 2-car garage and driveway"

## Interior Features (20)

36. "Show me homes with hardwood floors throughout"
37. "Find houses with an open floor plan kitchen"
38. "I want properties with a fireplace in the living room"
39. "Show me homes with granite countertops"
40. "Find houses with a kitchen island and pantry"
41. "Show me homes with vaulted ceilings"
42. "Find properties with a walk-in closet in the master"
43. "I want homes with tile floors in the bathrooms"
44. "Show me houses with stainless steel appliances"
45. "Find homes with a finished basement"
46. "Show me properties with carpet in the bedrooms only"
47. "Find houses with all hardwood floors and no carpet"
48. "I want homes with marble countertops"
49. "Show me properties with quartz countertops"
50. "Find homes with vinyl flooring"
51. "Show me houses with laminate floors"
52. "Find properties with a home office space"
53. "I want homes with high ceilings"
54. "Show me houses with crown molding"
55. "Find homes with built-in shelving"

## Proximity - Single POI (15)

56. "Show me houses near a gym"
57. "Find homes close to elementary schools"
58. "I want properties near a grocery store"
59. "Show me houses within walking distance of a park"
60. "Find homes near a hospital"
61. "Show me properties close to public transportation"
62. "Find houses near a library"
63. "I want homes near shopping centers"
64. "Show me properties close to restaurants"
65. "Find houses near a pharmacy"
66. "Show me homes near coffee shops"
67. "Find properties close to a bank"
68. "I want houses near downtown"
69. "Show me homes near hiking trails"
70. "Find properties close to a golf course"

## Proximity - Specific Distance (10)

71. "Show me houses within 5 miles of a gym"
72. "Find homes within 2 miles of an elementary school"
73. "I want properties within 10 minutes of downtown"
74. "Show me houses within walking distance of a park"
75. "Find homes within a 15-minute drive of my office"
76. "Show me properties within 3 miles of a grocery store"
77. "Find houses within 1 mile of a coffee shop"
78. "I want homes within 20 minutes of the airport"
79. "Show me properties within 5 minutes of a hospital"
80. "Find houses within half a mile of a pharmacy"

## Combined Features (10)

81. "Show me modern homes with hardwood floors and a fireplace"
82. "Find craftsman houses with a 2-car garage and front porch"
83. "I want colonial homes with a pool and large backyard"
84. "Show me ranch style homes with an open floor plan and patio"
85. "Find contemporary houses with vaulted ceilings and granite counters"
86. "Show me farmhouse homes with a wrap-around porch and fireplace"
87. "Find Victorian houses with hardwood floors and ornate details"
88. "I want mid-century modern homes with a pool and mountain views"
89. "Show me Tudor homes with a 3-car garage and stone patio"
90. "Find Mediterranean houses with tile roof and outdoor deck"

## Combined Features + Proximity (10)

91. "Show me modern homes with a balcony and 2-car garage within 5 miles of a gym"
92. "Find craftsman houses with hardwood floors and a front porch near elementary schools"
93. "I want colonial homes with a pool and white fence within 10 minutes of downtown"
94. "Show me ranch homes with an open floor plan and backyard close to parks"
95. "Find contemporary houses with granite counters and garage within 3 miles of grocery stores"
96. "Show me farmhouse homes with a fireplace and porch within walking distance of coffee shops"
97. "Find Victorian houses with vaulted ceilings and hardwood floors near libraries"
98. "I want mid-century modern homes with a pool and deck within 5 miles of shopping"
99. "Show me Tudor homes with stone patio and 2-car garage close to restaurants"
100. "Find Mediterranean houses with tile roof and balcony within 10 minutes of hospitals"

## Query Feature Coverage

These queries test:

### Architecture Styles (25+)
- Modern, Contemporary, Craftsman, Victorian, Colonial
- Ranch, Mediterranean, Tudor, Mid-century Modern, Farmhouse

### Outdoor Features
- Pools, hot tubs, patios, decks
- Backyards (large, fenced)
- Fences (white, wood, metal, chain-link, vinyl, iron, picket)
- Porches (front, wrap-around, screened)
- Balconies

### Garage Types
- 1-car, 2-car, 3-car
- Attached, detached
- Carports
- Oversized, heated
- With storage/workshop

### Interior Features
- Flooring: hardwood, carpet, tile, marble, vinyl, laminate
- Countertops: granite, marble, quartz
- Ceilings: vaulted, high
- Kitchen: island, pantry, open floor plan
- Fireplace
- Walk-in closets
- Finished basement
- Built-ins, crown molding

### Proximity
- POI types: gym, school, grocery store, park, hospital, library, shopping, restaurants, pharmacy, coffee shops, bank, downtown, hiking, golf
- Distance: within X miles, within X minutes drive, walking distance, close to

### Combinations
- 2+ features
- Features + architecture
- Features + proximity
- Features + architecture + proximity

## Implementation Requirements

To support all these queries, the system must:

1. ✅ **Extract architecture styles from text and images**
2. ✅ **Detect outdoor features (pools, decks, patios, fences)**
3. ✅ **Identify fence types and colors (white, wood, metal, etc.)**
4. ✅ **Recognize garage configurations (1/2/3-car, attached/detached)**
5. ✅ **Detect flooring types (hardwood, carpet, tile, etc.)**
6. ✅ **Identify countertop materials (granite, marble, quartz)**
7. ✅ **Recognize interior features (fireplace, island, vaulted ceilings)**
8. ✅ **Geocode POI types with reference locations**
9. ✅ **Calculate proximity distances (km and drive time)**
10. ✅ **Combine multiple constraints (AND logic)**
11. ✅ **Handle price and bedroom/bathroom filters**
12. ✅ **Process "no X" queries (e.g., "no carpet")**

All of these are already implemented in the current system!
