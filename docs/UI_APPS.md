# UI Applications

**Last Updated**: 2025-10-24
**Status**: Current
**Related Docs**: [README.md](README.md), [API.md](API.md), [DEPLOYMENT.md](DEPLOYMENT.md)

Documentation for Production UI and Internal Testing UI.

---

## Table of Contents

1. [Production UI](#production-ui)
2. [Internal Testing UI](#internal-testing-ui)
3. [Shared Components](#shared-components)
4. [User Features](#user-features)

---

## Production UI

### Overview

**URL**: http://54.226.26.203/
**File**: [ui/production.html](../ui/production.html)
**Hosting**: EC2 + nginx (NOT S3)
**Instance**: i-044e6ddd7ab8353f9

**Purpose**: Public-facing demo of Hearth Search

### Deployment

**IMPORTANT**: Production UI must be deployed via deploy script to EC2.

```bash
# Correct deployment
./deploy_production_ui.sh

# WRONG - Do NOT deploy to S3
# aws s3 cp ui/production.html s3://...  # This will NOT work
```

**Manual Deployment**:
```bash
# SSH to EC2
ssh -i your-key.pem ec2-user@54.226.26.203

# Copy file
scp -i your-key.pem ui/production.html ec2-user@54.226.26.203:/var/www/html/index.html

# Restart nginx (if needed)
sudo systemctl restart nginx
```

### Features

#### Search

**Search Bar**:
- Natural language queries
- Real-time search as you type
- Example queries with one-click

**Example Queries** (ui/production.html:1113-1118):
```html
<div class="example-chip" onclick="fillExample('White homes with granite countertops and wood floors')">
  White homes with granite & wood floors
</div>
<div class="example-chip" onclick="fillExample('Mid century modern homes with pool')">
  Mid-century modern with pool
</div>
<div class="example-chip" onclick="fillExample('Craftsman style homes with hardwood floors')">
  Craftsman with hardwood floors
</div>
<div class="example-chip" onclick="fillExample('Ranch homes with updated kitchen')">
  Ranch with updated kitchen
</div>
<div class="example-chip" onclick="fillExample('Contemporary homes with mountain views')">
  Contemporary mountain views
</div>
<div class="example-chip" onclick="fillExample('Victorian homes with original features')">
  Victorian with original features
</div>
```

#### Filters

**Price Range**:
- Min price slider
- Max price slider
- Real-time filter application

**Property Specs**:
- Bedrooms (min)
- Bathrooms (min)
- Square footage (min/max)

**Property Type**:
- Single Family
- Condo
- Townhouse
- Multi-Family

**Active Filters Display**:
- Shows currently active filters
- One-click filter removal
- Clear all filters button

#### Results Display

**Property Cards**:
- Property image (first image from listing)
- Address, city, state
- Price (formatted with commas)
- Bedrooms, bathrooms, square footage
- Architecture style (if available)
- Property features (tags)
- View on Zillow button

**Pagination**:
- 20 results per page
- Load more button
- Infinite scroll (optional)
- Uses search_after for efficient pagination

#### Property Rating

**Star Rating System**:
- 1-5 stars per property
- Optional comment
- Tied to search query (query_id)
- Logged to PropertyRatings DynamoDB table

**UI** (per property card):
```html
<div class="rating-section">
  <span>Rate this property:</span>
  <div class="stars">
    ⭐⭐⭐⭐⭐
  </div>
  <textarea placeholder="Optional comment"></textarea>
  <button onclick="submitRating(zpid, rating, comment)">Submit</button>
</div>
```

#### Search Quality Feedback

**"Rate This Search" Button**:
- Fixed position (bottom-right)
- Appears after search is executed
- White background, green border (matches Report Issue button)
- Opens modal for feedback

**Button Styling** (ui/production.html:762-787):
```css
.search-feedback-button {
    position: fixed;
    bottom: 20px;
    right: 20px;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 20px;
    background: white;
    color: #4CAF50;
    border: 2px solid #4CAF50;
    border-radius: 30px;
    box-shadow: 0 4px 12px rgba(76, 175, 80, 0.3);
    cursor: pointer;
    font-weight: 600;
    z-index: 1000;
}
```

**Feedback Modal**:
- 1-5 star rating
- Optional text feedback
- Feedback categories (checkboxes):
  - Results matched query well
  - Results didn't match query
  - Missing expected properties
  - Too many results
  - Low quality properties
- Logged to SearchQualityFeedback DynamoDB table

**JavaScript** (ui/production.html:2290-2327):
```javascript
function showSearchFeedbackButton() {
    const button = document.getElementById('searchFeedbackButton');
    if (button && !searchQualitySubmitted) {
        button.style.visibility = 'visible';
        button.style.opacity = '1';
    }
}

function openSearchFeedbackModal() {
    document.getElementById('searchFeedbackModal').style.display = 'flex';
}

function submitSearchQuality() {
    // Get rating, feedback text, categories
    // POST to /log-search-quality
    // Close modal, hide button
}
```

#### Report Issue Button

**Purpose**: Report bugs or issues with the app
**Location**: Fixed position (bottom-right, below Rate Search)
**Styling**: White background, green border

### API Integration

**Search API**:
```javascript
const response = await fetch(
  `https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search?query=${query}&minPrice=${minPrice}&...`
);
const data = await response.json();
```

**Analytics API**:
```javascript
// Log search
await fetch('https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/log-search', {
  method: 'POST',
  body: JSON.stringify({
    session_id: sessionId,
    query: query,
    total_results: totalResults
  })
});

// Log property rating
await fetch('https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/log-rating', {
  method: 'POST',
  body: JSON.stringify({
    session_id: sessionId,
    zpid: zpid,
    rating: rating,
    comment: comment
  })
});

// Log search quality
await fetch('https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod/log-search-quality', {
  method: 'POST',
  body: JSON.stringify({
    session_id: sessionId,
    search_query: query,
    rating: rating,
    feedback_text: feedbackText,
    feedback_categories: categories
  })
});
```

### Session Management

**Session ID**:
- Generated on page load
- Stored in sessionStorage
- Used to link queries, ratings, feedback

```javascript
let sessionId = sessionStorage.getItem('hearth_session_id');
if (!sessionId) {
    sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    sessionStorage.setItem('hearth_session_id', sessionId);
}
```

---

## Internal Testing UI

### Overview

**File**: [ui/testing.html](../ui/testing.html) (if exists)
**Hosting**: S3 static website (or local)
**Purpose**: Internal testing and debugging

### Features

#### Index Selection

**IMPORTANT**: Only "listings-v2" should be available.

**Before** (INCORRECT):
```html
<select id="indexSelect">
  <option value="listings">listings (OLD)</option>
  <option value="listings-v2">listings-v2 (CURRENT)</option>
</select>
```

**After** (CORRECT):
```html
<select id="indexSelect">
  <option value="listings-v2">listings-v2</option>
</select>
```

**Note**: The "listings" index option was removed as it's outdated and should not be used.

#### Advanced Search Options

- Query decomposition toggle (enable/disable multi-query)
- Strategy weights adjustment (BM25, text kNN, image kNN k-values)
- RRF k-value tuning
- Tag boost multiplier adjustment

#### Analytics View

**Search Logs**:
- Recent searches
- Query frequency
- Average results per query
- Search time distribution

**Rating Analytics**:
- Property rating distribution
- Most rated properties
- Average ratings by architecture style

**Quality Feedback**:
- Feedback category breakdown
- Average search quality rating
- Common feedback themes

#### Raw Response View

- Full JSON response from search API
- Query info (original query, subqueries, classification)
- RRF score breakdown per property
- Strategy scores (BM25, text kNN, image kNN)

### Deployment

```bash
# Deploy to S3
aws s3 cp ui/testing.html s3://your-testing-bucket/index.html \
  --cache-control "max-age=0"

# Or run locally
open ui/testing.html
```

---

## Shared Components

### API Client

**Endpoints**:
```javascript
const API_ENDPOINTS = {
  search: 'https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search',
  crud: 'https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod',
  analytics: 'https://mwf1h5nbxe.execute-api.us-east-1.amazonaws.com/prod'
};
```

### Session Tracking

**Session ID Generation**:
```javascript
const sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
```

**Query ID Generation**:
```javascript
const queryId = 'query_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
```

### Error Handling

**Network Errors**:
```javascript
try {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }
  return await response.json();
} catch (error) {
  console.error('Search error:', error);
  showErrorMessage('Search failed. Please try again.');
}
```

**Empty Results**:
```html
<div id="noResults" class="no-results" style="display: none;">
  <h3>No properties found</h3>
  <p>Try adjusting your filters or search terms</p>
</div>
```

---

## User Features

### Search Features

1. **Natural Language Search**: "mid century modern homes with pool"
2. **Filter Combinations**: Price + beds + baths + sqft + type
3. **Architecture Style Search**: Synonym mapping (e.g., "MCM" → mid_century_modern)
4. **Example Queries**: One-click to fill search bar
5. **Real-Time Results**: Instant search as filters change

### Feedback Features

1. **Property Ratings**: Star ratings + comments per property
2. **Search Quality Feedback**: Overall search satisfaction
3. **Issue Reporting**: Bug reports and feature requests

### Display Features

1. **Property Cards**: Images, specs, features, architecture style
2. **Matched Tags Highlighting**: Shows which tags matched query
3. **Architecture Style Display**: Tier 1 + Tier 2 styles shown
4. **Pagination**: Efficient infinite scroll with search_after

### Analytics Features (Internal UI Only)

1. **Search Logs**: Query history and frequency
2. **Rating Analytics**: Property rating distribution
3. **Quality Metrics**: Search quality over time

---

## UI Customization

### Branding

**Colors**:
- Primary: #4CAF50 (green)
- Secondary: White
- Accent: rgba(76, 175, 80, 0.1) (light green)

**Fonts**:
- System font stack: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto

### Styling Guidelines

**Buttons**:
```css
.button-primary {
    background: #4CAF50;
    color: white;
    border: none;
    padding: 12px 24px;
    border-radius: 8px;
    cursor: pointer;
    font-weight: 600;
}

.button-secondary {
    background: white;
    color: #4CAF50;
    border: 2px solid #4CAF50;
    padding: 12px 24px;
    border-radius: 8px;
    cursor: pointer;
    font-weight: 600;
}
```

**Property Cards**:
```css
.property-card {
    background: white;
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    padding: 16px;
    margin-bottom: 16px;
    transition: transform 0.2s;
}

.property-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 4px 16px rgba(0,0,0,0.15);
}
```

---

## Troubleshooting

### Production UI Not Updating

**Issue**: Changes to ui/production.html not visible
**Cause**: Deployed to S3 instead of EC2

**Fix**:
```bash
./deploy_production_ui.sh  # Deploy to EC2, NOT S3
```

### Search Not Working

**Issue**: Search returns no results or errors
**Cause**: Wrong API endpoint or CORS issue

**Fix**:
```javascript
// Check API endpoint in JavaScript
console.log('Search endpoint:', API_ENDPOINTS.search);

// Should be: https://mqgsb4xb2g.execute-api.us-east-1.amazonaws.com/prod/search
```

### Rate Search Button Not Showing

**Issue**: "Rate this search" button not visible after search
**Cause**: Display/visibility CSS issue

**Fix** (ui/production.html:2290):
```javascript
function showSearchFeedbackButton() {
    const button = document.getElementById('searchFeedbackButton');
    if (button && !searchQualitySubmitted) {
        button.style.visibility = 'visible';  // Make visible
        button.style.opacity = '1';
    }
}
```

Called after search completes.

### Session Not Persisting

**Issue**: Session ID changes on page reload
**Cause**: Using localStorage instead of sessionStorage

**Fix**:
```javascript
// Use sessionStorage (persists for tab lifetime)
sessionStorage.setItem('hearth_session_id', sessionId);

// NOT localStorage (persists forever)
// localStorage.setItem('hearth_session_id', sessionId);
```

---

## Future Enhancements

### Planned Features

1. **Saved Searches**: Save favorite searches for later
2. **Property Comparison**: Side-by-side property comparison
3. **Map View**: Properties displayed on interactive map
4. **Advanced Filters**: More granular filtering options
5. **User Accounts**: Save preferences, favorites, search history

### Performance Improvements

1. **Image Lazy Loading**: Load images as user scrolls
2. **Result Caching**: Cache recent searches client-side
3. **Debounced Search**: Reduce API calls while typing

---

## See Also

- [API.md](API.md) - API endpoints used by UI
- [DEPLOYMENT.md](DEPLOYMENT.md) - UI deployment procedures
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common UI issues
