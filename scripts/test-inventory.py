"""List every automated test definition without importing application code."""
import ast
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def inventory():
    for directory in ('tests','front/tests','race-game/tests','deploy/jenkins'):
        for path in sorted((ROOT/directory).glob('*test*')):
            if path.suffix=='.py' and path.name.startswith('test_'):
                tree = ast.parse(path.read_text(encoding='utf-8-sig'))
                cases = [node for node in ast.walk(tree) if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name.startswith('test_')]
                yield {'file':path.relative_to(ROOT).as_posix(),'definitions':len(cases),
                       'parametrized':sum(any(isinstance(dec,ast.Call) and isinstance(dec.func,ast.Attribute) and dec.func.attr=='parametrize' for dec in node.decorator_list) for node in cases)}
            elif path.suffix in {'.mjs','.ts'} and '.test.' in path.name:
                yield {'file':path.relative_to(ROOT).as_posix(),
                       'declarations':len(re.findall(r'\btest\(',path.read_text(encoding='utf-8-sig')))}


if __name__=='__main__':
    print(json.dumps(list(inventory()),ensure_ascii=False,indent=2))
