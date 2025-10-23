"""
reembed_listings.py - Bulk re-embedding script for existing listings

This script updates all existing listings in OpenSearch to use multimodal embeddings
(amazon.titan-embed-image-v1) instead of text-only embeddings (amazon.titan-embed-text-v2:0).

This enables proper cross-modal search where text queries can match image embeddings.

Usage:
    # Dry run (shows what would be updated, doesn't modify anything)
    python3 reembed_listings.py --index listings-v2 --dry-run

    # Update first 10 listings (for testing)
    python3 reembed_listings.py --index listings-v2 --batch-size 10 --max-listings 10

    # Full re-embedding (all listings)
    python3 reembed_listings.py --index listings-v2

    # Resume from specific scroll_id
    python3 reembed_listings.py --index listings-v2 --scroll-id <id>

What this does:
1. Scrolls through all documents in the index
2. For each document with a description:
   - Generates new text embedding using embed_text_multimodal()
   - Updates the vector_text field in OpenSearch
3. Shows progress and estimated time remaining
4. Handles errors gracefully (logs failures, continues processing)

Cost estimate:
- ~1000 listings = ~$0.10 (Bedrock embedding cost)
- Uses DynamoDB caching to avoid re-embedding identical descriptions
"""

import argparse
import json
import logging
import os
import sys
import time
from typing import Dict, List, Optional

# Set environment variables before importing common
os.environ.setdefault('OS_HOST', 'search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com')
os.environ.setdefault('OS_INDEX', 'listings-v2')

# Add parent directory to path for imports
sys.path.insert(0, '/Users/andrewcarras/hearth_backend_new')

from common import os_client, embed_text_multimodal

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_listing_count(index: str) -> int:
    """Get total count of listings in the index."""
    try:
        result = os_client.count(index=index)
        return result['count']
    except Exception as e:
        logger.error(f"Error counting documents: {e}")
        return 0


def scroll_listings(index: str, batch_size: int = 100, scroll_id: Optional[str] = None):
    """
    Generator that yields batches of listings from OpenSearch using scroll API.

    Args:
        index: Index name
        batch_size: Number of documents per batch
        scroll_id: Optional scroll_id to resume from

    Yields:
        (scroll_id, list of documents)
    """
    scroll_time = '5m'  # Keep scroll context alive for 5 minutes

    if scroll_id:
        # Resume from existing scroll
        logger.info(f"Resuming from scroll_id: {scroll_id[:50]}...")
        try:
            response = os_client.scroll(scroll_id=scroll_id, scroll=scroll_time)
        except Exception as e:
            logger.error(f"Error resuming scroll: {e}")
            return
    else:
        # Start new scroll
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"exists": {"field": "description"}},  # Only docs with descriptions
                        {"exists": {"field": "vector_text"}}   # Only docs with existing embeddings
                    ]
                }
            },
            "_source": ["zpid", "description", "visual_features_text", "vector_text"]
        }

        try:
            response = os_client.search(
                index=index,
                body=query,
                scroll=scroll_time,
                size=batch_size
            )
        except Exception as e:
            logger.error(f"Error initiating scroll: {e}")
            return

    scroll_id = response.get('_scroll_id')
    hits = response.get('hits', {}).get('hits', [])

    while hits:
        yield scroll_id, hits

        # Get next batch
        try:
            response = os_client.scroll(scroll_id=scroll_id, scroll=scroll_time)
            scroll_id = response.get('_scroll_id')
            hits = response.get('hits', {}).get('hits', [])
        except Exception as e:
            logger.error(f"Error during scroll: {e}")
            break

    # Clear scroll context
    if scroll_id:
        try:
            os_client.clear_scroll(scroll_id=scroll_id)
        except Exception as e:
            logger.warning(f"Error clearing scroll: {e}")


def reembed_batch(index: str, documents: List[Dict], dry_run: bool = False) -> Dict[str, int]:
    """
    Re-embed a batch of documents.

    Returns:
        Dict with counts: {updated, skipped, errors}
    """
    stats = {"updated": 0, "skipped": 0, "errors": 0}

    for doc in documents:
        zpid = doc['_id']
        source = doc.get('_source', {})
        description = source.get('description', '')
        visual_features_text = source.get('visual_features_text', '')

        if not description:
            stats['skipped'] += 1
            continue

        try:
            # Combine description + visual_features_text (same as indexing)
            text_for_embed = description.strip()
            if visual_features_text:
                combined_text = f"{text_for_embed} {visual_features_text}".strip()
            else:
                combined_text = text_for_embed

            # Generate new multimodal embedding
            new_vector = embed_text_multimodal(combined_text)

            if not new_vector or len(new_vector) == 0:
                logger.warning(f"Empty vector for zpid={zpid}")
                stats['errors'] += 1
                continue

            if dry_run:
                logger.info(f"[DRY RUN] Would update zpid={zpid} (combined text: {len(combined_text)} chars)")
                stats['updated'] += 1
            else:
                # Update only the vector_text field
                os_client.update(
                    index=index,
                    id=zpid,
                    body={
                        "doc": {
                            "vector_text": new_vector,
                            "updated_at": int(time.time())
                        }
                    }
                )
                stats['updated'] += 1
                logger.debug(f"Updated zpid={zpid}")

        except Exception as e:
            logger.error(f"Error processing zpid={zpid}: {e}")
            stats['errors'] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(description='Bulk re-embed listings with multimodal embeddings')
    parser.add_argument('--index', default='listings-v2', help='OpenSearch index name')
    parser.add_argument('--batch-size', type=int, default=100, help='Number of docs per batch')
    parser.add_argument('--max-listings', type=int, help='Maximum number of listings to process (for testing)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without making changes')
    parser.add_argument('--scroll-id', help='Resume from existing scroll_id')

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("Bulk Re-embedding Script")
    logger.info("=" * 80)
    logger.info(f"Index: {args.index}")
    logger.info(f"Batch size: {args.batch_size}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"Max listings: {args.max_listings or 'unlimited'}")

    if args.dry_run:
        logger.info("🔍 DRY RUN MODE - No changes will be made")

    # Get total count
    total_count = get_listing_count(args.index)
    logger.info(f"Total documents in index: {total_count:,}")

    if args.max_listings:
        total_count = min(total_count, args.max_listings)
        logger.info(f"Processing limit: {total_count:,}")

    # Confirm before proceeding
    if not args.dry_run:
        response = input(f"\n⚠️  This will update up to {total_count:,} listings. Continue? [y/N]: ")
        if response.lower() != 'y':
            logger.info("Aborted by user")
            return

    # Process batches
    total_stats = {"updated": 0, "skipped": 0, "errors": 0}
    processed = 0
    start_time = time.time()

    logger.info("\n" + "=" * 80)
    logger.info("Starting re-embedding process...")
    logger.info("=" * 80 + "\n")

    try:
        for scroll_id, hits in scroll_listings(args.index, args.batch_size, args.scroll_id):
            batch_stats = reembed_batch(args.index, hits, args.dry_run)

            # Update totals
            for key in total_stats:
                total_stats[key] += batch_stats[key]

            processed += len(hits)

            # Progress update
            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (total_count - processed) / rate if rate > 0 else 0

            logger.info(
                f"Progress: {processed:,}/{total_count:,} ({processed/total_count*100:.1f}%) | "
                f"Updated: {total_stats['updated']:,} | "
                f"Skipped: {total_stats['skipped']:,} | "
                f"Errors: {total_stats['errors']:,} | "
                f"Rate: {rate:.1f} docs/sec | "
                f"ETA: {eta/60:.1f} min"
            )

            # Check if we've hit the max
            if args.max_listings and processed >= args.max_listings:
                logger.info(f"\n✓ Reached max listings limit ({args.max_listings:,})")
                logger.info(f"Resume with: --scroll-id {scroll_id}")
                break

    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Interrupted by user")
        logger.info(f"Resume with: --scroll-id {scroll_id}")

    except Exception as e:
        logger.error(f"\n\n❌ Fatal error: {e}", exc_info=True)

    # Final summary
    elapsed = time.time() - start_time
    logger.info("\n" + "=" * 80)
    logger.info("SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total processed: {processed:,}")
    logger.info(f"Updated: {total_stats['updated']:,}")
    logger.info(f"Skipped: {total_stats['skipped']:,}")
    logger.info(f"Errors: {total_stats['errors']:,}")
    logger.info(f"Time elapsed: {elapsed/60:.1f} minutes")
    logger.info(f"Average rate: {processed/elapsed:.1f} docs/sec")

    if args.dry_run:
        logger.info("\n🔍 This was a DRY RUN - no changes were made")
        logger.info("Remove --dry-run flag to perform actual updates")
    else:
        logger.info("\n✅ Re-embedding complete!")


if __name__ == "__main__":
    main()
