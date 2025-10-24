"""
migrate_split_visual_features.py - Split visual_features_text into separate context fields

This script migrates existing listings to use separate exterior/interior visual feature fields
WITHOUT requiring a full reindex. It uses the CRUD API to update documents in batches.

New fields added:
- exterior_visual_features: Visual features from exterior images only
- interior_visual_features: Visual features from interior images only

Migration approach:
1. Uses scroll API to iterate through all documents
2. Parses existing visual_features_text to extract exterior/interior sections
3. Uses CRUD API (update) to add new fields to each document
4. Preserves all existing fields (backward compatible)
5. Can resume from checkpoint if interrupted

Usage:
    # Dry run (see what would be updated)
    python3 migrate_split_visual_features.py --dry-run

    # Update first 100 documents (testing)
    python3 migrate_split_visual_features.py --max-docs 100

    # Full migration
    python3 migrate_split_visual_features.py

    # Resume from checkpoint
    python3 migrate_split_visual_features.py --resume

Cost estimate:
- No LLM calls needed (just text parsing)
- Only OpenSearch update costs (~$0.000001 per update)
- Total cost for 4000 docs: ~$0.004 (negligible)
- Time: ~5-10 minutes for full migration
"""

import argparse
import json
import logging
import os
import sys
import time
from typing import Dict, List, Optional, Tuple

# Set environment variables
os.environ.setdefault('OS_HOST', 'search-hearth-opensearch-llfelt5zzkf2d7eead2ck6jm5a.us-east-1.es.amazonaws.com')
os.environ.setdefault('OS_INDEX', 'listings-v2')

from common import os_client

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CHECKPOINT_FILE = "migration_checkpoint.json"


def parse_visual_features_text(vft: str) -> Tuple[str, str]:
    """
    Parse visual_features_text into exterior and interior components.

    Args:
        vft: Original visual_features_text field

    Returns:
        (exterior_text, interior_text) tuple
    """
    if not vft:
        return "", ""

    exterior_text = ""
    interior_text = ""

    # Current format:
    # "Exterior: <style> style <color> exterior with <materials>. Interior features: <features>. Property includes: <general>"

    try:
        # Split by major sections
        if "Exterior:" in vft:
            parts = vft.split("Interior features:")
            if len(parts) >= 2:
                # Extract exterior section (everything after "Exterior:" up to "Interior features:")
                exterior_part = parts[0].replace("Exterior:", "").strip()
                exterior_text = exterior_part.rstrip('.')

                # Extract interior section (everything after "Interior features:" up to "Property includes:")
                interior_part = parts[1]
                if "Property includes:" in interior_part:
                    interior_text = interior_part.split("Property includes:")[0].strip().rstrip('.')
                else:
                    interior_text = interior_part.strip().rstrip('.')
            else:
                # Only exterior mentioned
                exterior_text = parts[0].replace("Exterior:", "").strip().rstrip('.')
        elif "Interior features:" in vft:
            # Only interior mentioned (rare)
            parts = vft.split("Interior features:")
            if "Property includes:" in parts[1]:
                interior_text = parts[1].split("Property includes:")[0].strip().rstrip('.')
            else:
                interior_text = parts[1].strip().rstrip('.')
        else:
            # No clear structure - treat as general features (put in exterior by default)
            exterior_text = vft.strip().rstrip('.')

    except Exception as e:
        logger.warning(f"Failed to parse visual_features_text: {e}")
        # Fallback: put everything in exterior
        exterior_text = vft.strip().rstrip('.')

    return exterior_text, interior_text


def migrate_batch(docs: List[Dict], dry_run: bool = False) -> Dict[str, int]:
    """
    Migrate a batch of documents by adding new split fields.

    Returns:
        Dict with counts: {updated, skipped, errors}
    """
    stats = {"updated": 0, "skipped": 0, "errors": 0}

    for doc in docs:
        zpid = doc['_id']
        source = doc.get('_source', {})
        vft = source.get('visual_features_text', '')

        if not vft:
            stats['skipped'] += 1
            continue

        try:
            # Parse into separate fields
            exterior_text, interior_text = parse_visual_features_text(vft)

            if not exterior_text and not interior_text:
                logger.warning(f"No exterior or interior text extracted for zpid={zpid}")
                stats['skipped'] += 1
                continue

            if dry_run:
                logger.info(f"[DRY RUN] Would update zpid={zpid}")
                logger.info(f"  Exterior: '{exterior_text[:60]}...'")
                logger.info(f"  Interior: '{interior_text[:60]}...'")
                stats['updated'] += 1
            else:
                # Update document with new fields
                update_body = {
                    "doc": {
                        "exterior_visual_features": exterior_text,
                        "interior_visual_features": interior_text,
                        "migration_timestamp": int(time.time())
                    }
                }

                os_client.update(
                    index='listings-v2',
                    id=zpid,
                    body=update_body
                )

                stats['updated'] += 1
                logger.debug(f"Updated zpid={zpid}")

        except Exception as e:
            logger.error(f"Error processing zpid={zpid}: {e}")
            stats['errors'] += 1

    return stats


def scroll_documents(batch_size: int = 100, resume_scroll_id: Optional[str] = None):
    """
    Generator that yields batches of documents using scroll API.

    Yields:
        (scroll_id, list of documents)
    """
    scroll_time = '5m'

    if resume_scroll_id:
        logger.info(f"Resuming from scroll_id: {resume_scroll_id[:50]}...")
        try:
            response = os_client.scroll(scroll_id=resume_scroll_id, scroll=scroll_time)
        except Exception as e:
            logger.error(f"Error resuming scroll: {e}")
            return
    else:
        # Start new scroll - get all documents with visual_features_text
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"exists": {"field": "visual_features_text"}},
                        # Only migrate docs that don't have new fields yet
                        {"bool": {"must_not": [{"exists": {"field": "exterior_visual_features"}}]}}
                    ]
                }
            },
            "_source": ["zpid", "visual_features_text"]
        }

        try:
            response = os_client.search(
                index='listings-v2',
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

    # Clear scroll
    if scroll_id:
        try:
            os_client.clear_scroll(scroll_id=scroll_id)
        except Exception as e:
            logger.warning(f"Error clearing scroll: {e}")


def save_checkpoint(scroll_id: str, processed: int):
    """Save migration checkpoint."""
    checkpoint = {
        "scroll_id": scroll_id,
        "processed": processed,
        "timestamp": int(time.time())
    }
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump(checkpoint, f)
    logger.info(f"💾 Saved checkpoint: {processed} docs processed")


def load_checkpoint() -> Optional[Dict]:
    """Load migration checkpoint if exists."""
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")
    return None


def get_migration_count() -> int:
    """Get count of documents needing migration."""
    try:
        result = os_client.count(
            index='listings-v2',
            body={
                "query": {
                    "bool": {
                        "must": [
                            {"exists": {"field": "visual_features_text"}},
                            {"bool": {"must_not": [{"exists": {"field": "exterior_visual_features"}}]}}
                        ]
                    }
                }
            }
        )
        return result['count']
    except Exception as e:
        logger.error(f"Error counting documents: {e}")
        return 0


def main():
    parser = argparse.ArgumentParser(description='Split visual_features_text into separate context fields')
    parser.add_argument('--batch-size', type=int, default=100, help='Documents per batch')
    parser.add_argument('--max-docs', type=int, help='Maximum documents to process (for testing)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without making changes')
    parser.add_argument('--resume', action='store_true', help='Resume from checkpoint')

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("Visual Features Text Migration - Split into Separate Contexts")
    logger.info("=" * 80)
    logger.info(f"Batch size: {args.batch_size}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"Max docs: {args.max_docs or 'unlimited'}")

    if args.dry_run:
        logger.info("🔍 DRY RUN MODE - No changes will be made")

    # Check for resume
    resume_scroll_id = None
    processed_so_far = 0
    if args.resume:
        checkpoint = load_checkpoint()
        if checkpoint:
            resume_scroll_id = checkpoint['scroll_id']
            processed_so_far = checkpoint['processed']
            logger.info(f"📂 Resuming from checkpoint: {processed_so_far} docs already processed")

    # Get total count
    total_count = get_migration_count()
    logger.info(f"Documents needing migration: {total_count:,}")

    if total_count == 0:
        logger.info("✅ All documents already migrated!")
        return

    if args.max_docs:
        total_count = min(total_count, args.max_docs)

    # Confirm before proceeding
    if not args.dry_run and not args.resume:
        response = input(f"\n⚠️  This will update up to {total_count:,} documents. Continue? [y/N]: ")
        if response.lower() != 'y':
            logger.info("Aborted by user")
            return

    # Process batches
    total_stats = {"updated": 0, "skipped": 0, "errors": 0}
    processed = processed_so_far
    start_time = time.time()

    logger.info("\n" + "=" * 80)
    logger.info("Starting migration...")
    logger.info("=" * 80 + "\n")

    try:
        for scroll_id, hits in scroll_documents(args.batch_size, resume_scroll_id):
            batch_stats = migrate_batch(hits, args.dry_run)

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

            # Save checkpoint every 500 docs
            if not args.dry_run and processed % 500 == 0:
                save_checkpoint(scroll_id, processed)

            # Check max docs limit
            if args.max_docs and processed >= args.max_docs:
                logger.info(f"\n✓ Reached max docs limit ({args.max_docs:,})")
                save_checkpoint(scroll_id, processed)
                break

    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Interrupted by user")
        if not args.dry_run:
            save_checkpoint(scroll_id, processed)
            logger.info(f"Resume with: --resume")

    except Exception as e:
        logger.error(f"\n\n❌ Fatal error: {e}", exc_info=True)

    # Final summary
    elapsed = time.time() - start_time
    logger.info("\n" + "=" * 80)
    logger.info("MIGRATION SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total processed: {processed:,}")
    logger.info(f"Updated: {total_stats['updated']:,}")
    logger.info(f"Skipped: {total_stats['skipped']:,}")
    logger.info(f"Errors: {total_stats['errors']:,}")
    logger.info(f"Time elapsed: {elapsed/60:.1f} minutes")
    logger.info(f"Average rate: {processed/elapsed:.1f} docs/sec")

    if args.dry_run:
        logger.info("\n🔍 This was a DRY RUN - no changes were made")
        logger.info("Remove --dry-run flag to perform actual migration")
    else:
        logger.info("\n✅ Migration complete!")
        # Clean up checkpoint
        if os.path.exists(CHECKPOINT_FILE):
            os.remove(CHECKPOINT_FILE)


if __name__ == "__main__":
    main()
