"""Local visual QA with fixture values from the user's screenshots, no API/DB."""
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from app.utils.default import DRIVER_CODE_TO_FILE
from app.utils.image_render import create_driver_standings_image, create_constructor_standings_image, create_comparison_image

DRIVERS = [("ANT", 302), ("RUS", 236), ("HAM", 199), ("NOR", 186), ("LEC", 170), ("VER", 163),
           ("PIA", 120), ("HAD", 83), ("LAW", 59), ("GAS", 41), ("LIN", 37), ("COL", 27), ("BEA", 20),
           ("BOR", 10), ("HUL", 7), ("OCO", 7), ("SAI", 7), ("ALB", 5), ("ALO", 3), ("TSU", 1),
           ("STR", 0), ("BOT", 0), ("PER", 0)]
TEAMS = [("mercedes", "Mercedes", 538), ("ferrari", "Ferrari", 378), ("mclaren", "McLaren", 306),
         ("red_bull", "Red Bull", 263), ("rb", "RB F1 Team", 83), ("alpine", "Alpine F1 Team", 68),
         ("haas", "Haas F1 Team", 27), ("audi", "Audi", 17), ("williams", "Williams", 12),
         ("aston_martin", "Aston Martin", 3), ("cadillac", "Cadillac F1 Team", 0)]
TEAM_CODES = {"Mercedes": ["ANT", "RUS"], "Ferrari": ["HAM", "LEC"], "McLaren": ["NOR", "PIA"],
              "Red Bull": ["VER", "HAD"], "Racing Bulls": ["LAW", "LIN"], "Alpine": ["GAS", "COL"],
              "Haas": ["BEA", "OCO"], "Audi": ["BOR", "HUL"], "Williams": ["SAI", "ALB"],
              "Aston Martin": ["ALO", "STR"], "Cadillac": ["BOT", "PER"]}


def driver_rows():
    return [{"pos": str(i + 1), "code": code, "name": Path(DRIVER_CODE_TO_FILE[code]).stem,
             "points": str(points), "team": next((name for name, codes in TEAM_CODES.items() if code in codes), ""),
             "favorite": code == "ALO"} for i, (code, points) in enumerate(DRIVERS)]


def team_rows():
    return [{"pos": str(i + 1), "code": code, "name": name, "points": str(points), "favorite": code == "ferrari"}
            for i, (code, name, points) in enumerate(TEAMS)]


if __name__ == "__main__":
    output = PROJECT / ".tmp/bot-standings-qa"
    output.mkdir(parents=True, exist_ok=True)
    previews = {
        "drivers.png": create_driver_standings_image("Личный зачёт 2026", "", driver_rows(), 2026),
        "teams.png": create_constructor_standings_image("Кубок конструкторов 2026", "", team_rows(), 2026),
        "comparison.png": create_comparison_image(
            {"name": "Andrea Kimi Antonelli", "season": 2026, "kind": "drivers", "cumulative": True,
             "history": [25, 43, 76, 94, 110, 140, 155, 163, 188, 201, None, 239, 264, 286, 302], "total_points": 302, "color": "#ff625d"},
            {"name": "George Russell", "cumulative": True,
             "history": [18, 43, 61, 86, 102, 127, 131, 137, 162, 180, None, 198, 208, 218, 236], "total_points": 236, "color": "#00d2be"},
            ["Australia", "China", "Japan", "Miami", "Canada", "Monaco", "Barcelona", "Austria", "Britain",
             "Belgium", "Hungary", "Netherlands", "Italy", "Madrid", "Azerbaijan"]),
    }
    for name, data in previews.items():
        (output / name).write_bytes(data.getvalue())
        print(output / name)
