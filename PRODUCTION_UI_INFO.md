# Hearth Production UI

Beautiful, sleek production interface for user feedback and testing.

## URLs

- **Production UI**: http://54.226.26.203/
- **Development/Testing UI**: http://54.234.198.245/ (existing instance)

## Features

### Production UI (User-Facing)
- Clean, modern design with gradient purple theme
- Simple search interface - just a search bar
- AI-powered multi-query search (automatic)
- Beautiful property cards with hover effects
- Property detail modals with image galleries
- No editing capabilities (read-only)
- Mobile responsive
- Optimized for user feedback

### Development UI (Testing)
- Full feature set with all controls
- Multiple search modes and strategies
- Score breakdown and debugging tools
- CRUD operations for listings
- Analytics dashboard
- Testing tools (BM25, KNN, etc.)
- Comparison views

## Infrastructure

### Production Instance
- **Instance ID**: i-044e6ddd7ab8353f9
- **Instance Type**: t3.nano
- **Public IP**: 54.226.26.203
- **OS**: Amazon Linux 2
- **Web Server**: Nginx
- **IAM Role**: EC2-SSM-Role (for deployment via SSM)

### Shared Backend
Both UIs use the same backend:
- **API Gateway**: https://f2o144zh31.execute-api.us-east-1.amazonaws.com/search
- **Lambda Functions**:
  - hearth-search-v2
  - hearth-search-detailed-scoring
- **OpenSearch**: listings-v2 index
- **DynamoDB**: SearchQueryLogs table

## Deployment

### Deploy Production UI Updates

```bash
./deploy_production_ui.sh
```

This will:
1. Upload production.html to S3
2. Deploy to EC2 via SSM
3. Reload nginx

### Deploy Development UI Updates

```bash
./deploy_ui.sh i-03e61f15aa312c332
```

## File Structure

```
ui/
├── production.html          # Production UI (user-facing)
├── search.html             # Development main search
├── admin.html              # Admin tools
├── crud.html               # CRUD operations
├── analytics.html          # Analytics dashboard
├── multi_query_comparison.html  # Multi-query testing
└── test_*.html            # Various testing tools
```

## Production UI Design

### Color Scheme
- **Primary Gradient**: Purple/Indigo (#667eea to #764ba2)
- **Accent**: Gold gradient for match scores
- **Background**: White cards on gradient
- **Text**: Dark (#333) on white, White on gradient

### Key Design Elements
- Large, centered search bar with rounded corners
- Tagline: "Find your perfect home with AI-powered search"
- Grid layout for property cards (responsive)
- Card hover effects (lift and shadow)
- Modal overlays for property details
- Full-screen image gallery with thumbnails
- Clean typography (San Francisco/Helvetica)

### User Experience
- Auto-focus on search input
- Enter key to search
- Loading spinner during search
- Smooth scrolling to results
- Click anywhere outside modal to close
- Keyboard navigation (arrows, escape)
- Mobile-friendly responsive design

## Search Features

### Multi-Query Search (Automatic)
All searches use the advanced multi-query mode:
- LLM-based query splitting
- Context-specific fallbacks for exterior/interior features
- Greedy image selection for diversification
- Adaptive image weight boosting
- RRF score combination

### Example Queries
- "White homes with granite countertops and wood floors"
- "Modern homes with pool and mountain views"
- "Craftsman style houses with large kitchen"
- "Brick exterior homes with hardwood floors"

## Monitoring

Both UIs log searches to DynamoDB (SearchQueryLogs table) for:
- Search analytics
- Query performance tracking
- Result quality monitoring
- User behavior analysis

## Security

- No authentication (public demo)
- Read-only access (production UI)
- No sensitive data exposed
- CORS enabled for API
- HTTPS for API calls (HTTP for UI)

## Future Enhancements

### Planned Features
- Custom domain (e.g., search.hearth.com)
- HTTPS with SSL certificate
- User accounts and saved searches
- Property comparison feature
- Email notifications for new matches
- Advanced filters (price, beds, baths, location)
- Map view integration
- Share search results

### Technical Improvements
- CloudFront CDN distribution
- Load balancer for high availability
- Auto-scaling for traffic spikes
- CloudWatch monitoring and alerts
- A/B testing framework

## Troubleshooting

### UI Not Loading
```bash
# Check instance status
aws ec2 describe-instance-status --instance-ids i-044e6ddd7ab8353f9

# Check nginx status via SSM
aws ssm send-command \
  --instance-ids i-044e6ddd7ab8353f9 \
  --document-name "AWS-RunShellScript" \
  --parameters 'commands=["sudo systemctl status nginx"]'
```

### Search Not Working
```bash
# Test API directly
curl -X POST 'https://f2o144zh31.execute-api.us-east-1.amazonaws.com/search' \
  -H 'Content-Type: application/json' \
  -d '{"q":"white homes","size":5,"index":"listings-v2","use_multi_query":true}'

# Check Lambda logs
aws logs tail /aws/lambda/hearth-search-v2 --since 10m
```

### Redeploy from Scratch
```bash
# Upload to S3
aws s3 cp ui/production.html s3://demo-hearth-data/ui/production.html

# Deploy via SSM
./deploy_production_ui.sh
```

## Cost Estimates

### Monthly Costs
- **EC2 t3.nano**: ~$3.80/month (production)
- **EC2 t3.nano**: ~$3.80/month (development)
- **Lambda**: ~$1-5/month (depending on usage)
- **OpenSearch**: (existing cost, shared)
- **DynamoDB**: ~$1/month (SearchQueryLogs)
- **S3**: <$1/month (UI files)
- **Data Transfer**: ~$1-2/month

**Total Additional Cost**: ~$4-8/month for production UI

## Support

For issues or questions:
- Check CloudWatch logs
- Review DynamoDB search logs
- Test API endpoint directly
- Verify EC2 instance health
