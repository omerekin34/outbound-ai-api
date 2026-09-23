"""n8n toplu keşifte işler sırayla ve aralarında boşlukla yürür."""

from __future__ import annotations

import threading
import time

from api.services.research_queue import ResearchQueue


def test_jobs_never_run_in_parallel() -> None:
    current = 0
    peak = 0
    lock = threading.Lock()
    finished: list[str] = []

    def runner(company_id: str, _website: str) -> None:
        nonlocal current, peak
        with lock:
            current += 1
            peak = max(peak, current)
        time.sleep(0.04)
        with lock:
            current -= 1
            finished.append(company_id)

    queue = ResearchQueue(runner=runner, sleeper=lambda _s: None, gap_seconds=0)
    queue.enqueue("a", "https://a.example")
    queue.enqueue("b", "https://b.example")
    queue.enqueue("c", "https://c.example")
    queue.join(timeout=3)

    assert finished == ["a", "b", "c"]
    assert peak == 1


def test_gap_sleeps_between_companies_not_before_first() -> None:
    ran: list[str] = []
    sleeps: list[float] = []
    hold_first = threading.Event()

    def runner(company_id: str, _website: str) -> None:
        if company_id == "a":
            hold_first.wait(timeout=2)
        ran.append(company_id)

    queue = ResearchQueue(runner=runner, sleeper=sleeps.append, gap_seconds=2.5)
    queue.enqueue("a", "https://a.example")
    time.sleep(0.05)
    queue.enqueue("b", "https://b.example")
    queue.enqueue("c", "https://c.example")
    hold_first.set()
    queue.join(timeout=3)

    assert ran == ["a", "b", "c"]
    assert sleeps == [2.5, 2.5]


def test_worker_survives_a_failed_job() -> None:
    ran: list[str] = []

    def runner(company_id: str, _website: str) -> None:
        ran.append(company_id)
        if company_id == "boom":
            raise RuntimeError("rate limit")

    queue = ResearchQueue(runner=runner, sleeper=lambda _s: None, gap_seconds=0)
    queue.enqueue("boom", "https://boom.example")
    queue.enqueue("ok", "https://ok.example")
    queue.join(timeout=3)

    assert ran == ["boom", "ok"]
