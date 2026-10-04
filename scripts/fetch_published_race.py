"""Download a verified public classification for a server unable to reach Formula1.com."""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.f1_data import _cache_dir, formula1_get_race_for_round


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season', type=int, required=True)
    parser.add_argument('--round', type=int, required=True)
    args = parser.parse_args()
    result = await formula1_get_race_for_round.__wrapped__(args.season, args.round)
    if result.empty:
        raise SystemExit('The official source has no complete classification.')
    path = _cache_dir / 'published_race_results' / f'{args.season}-{args.round}.json'
    if not path.is_file():
        raise SystemExit('No published snapshot was saved.')
    print(f'Official classification: {len(result)} drivers; {path}')


if __name__ == '__main__':
    asyncio.run(main())
