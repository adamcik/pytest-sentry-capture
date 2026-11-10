import re
from pathlib import Path

import pytest

pytest_plugins = ["pytester"]


@pytest.mark.parametrize("example", [0, 1], ids=["sdk", "application"])
def test_readme_examples(pytester: pytest.Pytester, example: int) -> None:
    readme = Path(__file__).resolve().parents[1] / "README.md"
    examples = re.findall(r"```python\n(.*?)```", readme.read_text(), flags=re.DOTALL)
    assert len(examples) == 2
    pytester.makepyfile(examples[example])
    result = pytester.runpytest_subprocess("-q")
    result.assert_outcomes(passed=1)
