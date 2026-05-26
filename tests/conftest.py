import pytest

from wr_mcp import server


@pytest.fixture(autouse=True)
def _reset_session_state():
    server._reset_for_tests()
    yield
    server._reset_for_tests()
