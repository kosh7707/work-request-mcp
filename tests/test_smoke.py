def test_pytest_runs():
    assert 1 + 1 == 2


def test_package_importable():
    import wr_mcp

    assert wr_mcp.__name__ == "wr_mcp"
