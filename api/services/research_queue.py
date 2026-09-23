"""Keşif işlerini tek sırada, şirket şirket yürüten kuyruk.

n8n toplu `POST /api/research` çağrıları aynı milisaniyede onlarca thread
açıyordu; Firecrawl/OpenAI/Apollo rate limit'e takılıyordu. Burada tek bir
işçi thread vardır: bir şirket bitmeden diğeri başlamaz ve işler arasında
`RESEARCH_JOB_GAP_SECONDS` kadar beklenir. Kuyruğa almak anlıktır — 202
yanıtı bloklanmaz.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable

from api.config import get_settings
from api.services.research_job import run_research_job

logger = logging.getLogger(__name__)

JobRunner = Callable[[str, str], None]
Sleeper = Callable[[float], None]


class ResearchQueue:
    """Tek işçili FIFO kuyruk. Testlerde sahte runner / sleeper verilebilir."""

    def __init__(
        self,
        *,
        runner: JobRunner = run_research_job,
        sleeper: Sleeper = time.sleep,
        gap_seconds: float | None = None,
    ) -> None:
        self._jobs: queue.Queue[tuple[str, str]] = queue.Queue()
        self._runner = runner
        self._sleep = sleeper
        self._gap_seconds = gap_seconds
        self._lock = threading.Lock()
        self._started = False

    def enqueue(self, company_id: str, website: str) -> None:
        self._ensure_worker()
        self._jobs.put((company_id, website))
        logger.info(
            "Keşif kuyruğa alındı: %s (bekleyen=%s)",
            company_id,
            self._jobs.qsize(),
        )

    def pending(self) -> int:
        return self._jobs.qsize()

    def join(self, timeout: float = 5.0) -> None:
        """Kuyruk boşalana kadar bekler. Testler için."""
        done = threading.Event()

        def _wait() -> None:
            self._jobs.join()
            done.set()

        threading.Thread(target=_wait, daemon=True, name="research-queue-join").start()
        if not done.wait(timeout):
            raise TimeoutError("Keşif kuyruğu zamanında boşalmadı.")

    def _gap(self) -> float:
        if self._gap_seconds is not None:
            return max(0.0, self._gap_seconds)
        return max(0.0, get_settings().research_job_gap_seconds)

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._started:
                return
            threading.Thread(
                target=self._worker,
                daemon=True,
                name="research-queue",
            ).start()
            self._started = True

    def _worker(self) -> None:
        while True:
            company_id, website = self._jobs.get()
            try:
                self._runner(company_id, website)
            except Exception:
                logger.exception(
                    "Kuyruk işçisi keşif görevini düşürdü (%s, %s)",
                    company_id,
                    website,
                )
            finally:
                self._jobs.task_done()
                gap = self._gap()
                # Sonraki şirket varsa (veya hemen gelecekse) rate limit için dur.
                if gap > 0 and not self._jobs.empty():
                    logger.info("Keşif kuyruğu %s sn bekliyor", gap)
                    self._sleep(gap)


_default_queue: ResearchQueue | None = None
_default_lock = threading.Lock()


def get_research_queue() -> ResearchQueue:
    global _default_queue
    with _default_lock:
        if _default_queue is None:
            _default_queue = ResearchQueue()
        return _default_queue


def enqueue_research_job(company_id: str, website: str) -> None:
    """HTTP katmanının çağırdığı giriş: kuyruğa bırak, hemen dön."""
    get_research_queue().enqueue(company_id, website)
