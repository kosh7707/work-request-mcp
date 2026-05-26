import multiprocessing as mp
from pathlib import Path

from wr_mcp import server
from wr_mcp.server import _read_md


def test_full_round_trip(tmp_path):
    # 1. s1 register
    server.wr_register("s1", str(tmp_path))
    # 2. send s1 -> s2
    sent = server.wr_send("s2", "# Need review\n\nPlease look at X")
    wr_id = sent["wr_id"]
    # 3. inbox has exactly one notify line for s2
    s2_log = (tmp_path / "inbox" / "s2.log").read_text(encoding="utf-8")
    assert s2_log.count("\n") == 1
    assert s2_log.startswith(f"notify wr_id={wr_id} from=s1 ")
    # 4. s1 info: 1 sent, 0 received
    info1 = server.wr_info()
    assert info1["sent_open"] == 1
    assert info1["received_open"] == 0
    # 5-7. simulate s2 session
    server._reset_for_tests()
    server.wr_register("s2", str(tmp_path))
    open_list = server.wr_list_open()
    assert len(open_list) == 1
    assert open_list[0]["wr_id"] == wr_id
    assert open_list[0]["from"] == "s1"
    # 8. read
    read = server.wr_read(wr_id)
    assert read["body"] == "# Need review\n\nPlease look at X"
    assert read["frontmatter"]["status"] == "open"
    # 9. complete with note
    server.wr_complete(wr_id, note="lgtm")
    # 10. list now empty
    assert server.wr_list_open() == []
    # 11. info as s2: received_open 0
    info_s2 = server.wr_info()
    assert info_s2["received_open"] == 0
    # 12-13. switch back to s1: sent_open 0 (completed)
    server._reset_for_tests()
    server.wr_register("s1", str(tmp_path))
    info_s1 = server.wr_info()
    assert info_s1["sent_open"] == 0
    # 14. re-read file, confirm completed_note and completed_at
    fm, _ = _read_md(Path(sent["path"]))
    assert fm["completed_note"] == "lgtm"
    assert "completed_at" in fm


# ---------- Cross-process workers ----------

def _worker_sender(root: str, queue: mp.Queue) -> None:
    from wr_mcp import server as srv
    srv.wr_register("s1", root)
    result = srv.wr_send("s2", "# CrossProc\n\nbody from worker1")
    queue.put(result["wr_id"])


def _worker_recipient(root: str, wr_id: str, queue: mp.Queue) -> None:
    from wr_mcp import server as srv
    srv.wr_register("s2", root)
    open_list = srv.wr_list_open()
    if len(open_list) != 1 or open_list[0]["wr_id"] != wr_id:
        queue.put(("FAIL", "list mismatch", open_list))
        return
    read = srv.wr_read(wr_id)
    if read["body"] != "# CrossProc\n\nbody from worker1":
        queue.put(("FAIL", "body mismatch", read["body"]))
        return
    srv.wr_complete(wr_id, note="cross-process ok")
    queue.put(("OK",))


def test_two_process_round_trip(tmp_path):
    ctx = mp.get_context("spawn")
    queue: mp.Queue = ctx.Queue()

    # worker 1: register s1, send to s2
    p1 = ctx.Process(target=_worker_sender, args=(str(tmp_path), queue))
    p1.start()
    p1.join(timeout=20)
    assert p1.exitcode == 0, f"sender exit {p1.exitcode}"
    wr_id = queue.get(timeout=5)

    # worker 2: register s2, list, read, complete
    p2 = ctx.Process(target=_worker_recipient, args=(str(tmp_path), wr_id, queue))
    p2.start()
    p2.join(timeout=20)
    assert p2.exitcode == 0, f"recipient exit {p2.exitcode}"
    status = queue.get(timeout=5)
    assert status == ("OK",), status

    # parent assertions
    md_files = list((tmp_path / "messages").glob("*.md"))
    assert len(md_files) == 1
    fm, body = _read_md(md_files[0])
    assert fm["status"] == "completed"
    assert fm["completed_note"] == "cross-process ok"
    assert fm["from"] == "s1"
    assert fm["to"] == "s2"
    assert body == "# CrossProc\n\nbody from worker1"

    s2_log = (tmp_path / "inbox" / "s2.log").read_text(encoding="utf-8")
    assert s2_log.startswith(f"notify wr_id={wr_id} from=s1 ")
