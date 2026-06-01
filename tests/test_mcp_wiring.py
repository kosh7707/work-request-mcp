from wr_mcp.server import main, mcp


EXPECTED_TOOLS = {
    "wr_register",
    "wr_unregister",
    "wr_send",
    "wr_read",
    "wr_complete",
    "wr_list_open",
    "wr_info",
}


def test_main_is_callable():
    assert callable(main)


def test_tools_registered():
    # FastMCP exposes tools via _tool_manager._tools mapping (mcp>=1.0)
    names = set(mcp._tool_manager._tools.keys())
    assert names == EXPECTED_TOOLS, f"got {names}"
