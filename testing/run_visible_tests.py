import sys
import unittest
import importlib.util
from pathlib import Path


def load_test_module(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load test module from {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    testing_dir = Path(__file__).resolve().parent
    project_root = testing_dir.parent
    sys.path.insert(0, str(project_root))

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    for index, module_path in enumerate(sorted(testing_dir.glob("test_*.py")), start=1):
        module_name = f"_visible_test_{index}_{module_path.stem}"
        module = load_test_module(module_name, module_path)
        suite.addTests(loader.loadTestsFromModule(module))

    print("=" * 72)
    print("Running unit tests from testing/test_*.py")
    print("=" * 72)

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("=" * 72)
    print(
        "Summary: "
        f"ran={result.testsRun}, "
        f"failures={len(result.failures)}, "
        f"errors={len(result.errors)}, "
        f"skipped={len(result.skipped)}"
    )
    print("=" * 72)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
