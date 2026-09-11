"""Fetch the image referenced by Honda's Tsunoda profile, for visual verification."""
from pathlib import Path
import requests
root = Path(__file__).resolve().parents[1]
url = 'https://global.honda/en/F1/driver/YukiTsunoda/img/bg_img2.jpg'
response = requests.get(url, timeout=30)
response.raise_for_status()
(root / 'artifacts/tsunoda-honda.jpg').write_bytes(response.content)
