# Hearth Search Test UI

A simple Flask web interface to test the Hearth natural language property search backend.

## Quick Start

```bash
./run_ui.sh
```

Then open your browser to: **http://localhost:5000**

## Features

✅ **Natural Language Search**
- Enter queries like "3 bedroom house with pool under 500k"
- The LLM automatically extracts must-have features (pool, garage, etc.)
- Hybrid search combines BM25, kNN text, and kNN image vectors

✅ **Filters**
- Min/Max Price
- Min Bedrooms
- Min Bathrooms

✅ **Results Display**
- Shows all matching properties with scores
- Highlights boosted results (matching must-have tags)
- Direct links to Zillow listings
- Property details: price, beds, baths, lot size
- Feature tags extracted by LLM
- Property descriptions

## Example Queries

```
3 bedroom house with pool under 500k
modern home with mountain views
house with garage and large backyard
luxury home with 5 bedrooms in Holladay
property with hardwood floors and granite counters
```

## Technical Details

- **Backend**: AWS Lambda (hearth-search function)
- **Search Engine**: Amazon OpenSearch with kNN vectors
- **Embeddings**: Bedrock Titan (text & image)
- **LLM**: Claude 3 Haiku for feature extraction
- **Database**: Currently ~270+ properties indexed (upload in progress)

## Files

- `app.py` - Flask backend
- `templates/index.html` - UI frontend
- `run_ui.sh` - Startup script

## Stopping the Server

Press `Ctrl+C` in the terminal where the server is running.
