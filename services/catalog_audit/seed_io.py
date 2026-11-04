"""Load seed constants/helpers without importing database or running seed_components."""
import ast
from pathlib import Path


def load_seed(path):
    path = Path(path)
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    helper_names = {'_benchmark', 'component'}
    constants = {'_CATEGORY_IMAGE', 'COMPONENTS'}
    body = [node for node in tree.body if (
        isinstance(node, ast.FunctionDef) and node.name in helper_names or
        isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) and t.id in constants for t in node.targets))]
    # This loads trusted project source, not an arbitrary downloaded seed/plugin.
    namespace = {'__builtins__': {'round': round, 'float': float, 'str': str, 'int': int}}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace['COMPONENTS']
