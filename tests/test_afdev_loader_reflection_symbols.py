from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
LOADER = ROOT / "tools" / "server_spawner" / "AFDevLoader_v48_spawner_multi_instance.py"


class LoaderReflectionSymbolTests(unittest.TestCase):
    def test_reflection_constants_are_defined(self):
        source = LOADER.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)

        defined = set()
        loaded = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        defined.add(target.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                defined.add(node.target.id)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined.add(node.name)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id.startswith(("PVE_", "MAYA_")):
                    loaded.add(node.id)

        missing = sorted(name for name in loaded if name not in defined)
        self.assertEqual(
            missing,
            [],
            "AFDEV loader references undefined reflection constants: "
            + ", ".join(missing),
        )


if __name__ == "__main__":
    unittest.main()
