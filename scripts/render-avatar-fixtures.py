"""Render production avatar combinations for the isolated browser regression."""
import sys
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.profile_avatar import OPTIONS, render

destination = Path('.tmp/profile-avatar-fixtures')
destination.mkdir(parents=True, exist_ok=True)
for helmet, suit, background in product(*OPTIONS.values()):
    (destination / f'{helmet}-{suit}-{background}.png').write_bytes(render(helmet, suit, background))
