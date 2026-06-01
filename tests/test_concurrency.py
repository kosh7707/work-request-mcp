"""Cross-process concurrency: the lane-claim guard + root lock must let exactly
ONE process hold a lane. This is the two-sessions-claim-same-lane incident.

Without the claim guard (or without the lock serializing check-and-write) both
processes would register successfully — this test fails in that case.
"""
import multiprocessing as mp


def _claim_worker(root: str, q: mp.Queue) -> None:
    import time

    from wr_mcp import server as srv

    try:
        srv.wr_register("s1", root)
        # Stay alive so the rival process sees us holding the lane (a live pid
        # is not stealable without force) when it runs its claim check.
        time.sleep(1.0)
        q.put("OK")
    except srv.LaneClaimedError:
        q.put("CLAIMED")
    except Exception as e:  # surface anything unexpected
        q.put(("ERR", repr(e)))


def test_concurrent_register_same_lane_one_winner(tmp_path):
    ctx = mp.get_context("spawn")
    q: mp.Queue = ctx.Queue()
    procs = [
        ctx.Process(target=_claim_worker, args=(str(tmp_path), q))
        for _ in range(2)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=20)
        assert p.exitcode == 0, f"worker crashed: exit {p.exitcode}"

    results = sorted(q.get(timeout=5) for _ in range(2))
    # exactly one winner, one rejected — never two winners
    assert results == ["CLAIMED", "OK"], results
