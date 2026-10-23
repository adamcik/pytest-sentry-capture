import re
from pathlib import Path

import pytest

pytest_plugins = ["pytester"]


def test_readme_examples(pytester: pytest.Pytester) -> None:
    readme = Path(__file__).resolve().parents[1] / "README.md"
    examples = re.findall(r"```python\n(.*?)```", readme.read_text(), flags=re.DOTALL)
    assert len(examples) == 2
    pytester.makepyfile("\n\n".join(examples))
    result = pytester.runpytest_subprocess("-q")
    result.assert_outcomes(passed=2)
