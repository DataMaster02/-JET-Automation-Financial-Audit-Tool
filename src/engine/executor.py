# ================================================================
# engine/executor.py — JetExecutionEngine
# Task Queue | Worker Pool | Scheduler | Progress | Fault Isolation
# ================================================================

import os, time, uuid, logging, threading, traceback, psutil
from enum import Enum
from typing import Callable, Dict, List, Optional, Any
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from queue import PriorityQueue

logger = logging.getLogger("jet.executor")

CPU_COUNT = os.cpu_count() or 4

# ─────────────────────────────────────────────────────────────
# Enums & Dataclasses
# ─────────────────────────────────────────────────────────────

class TaskStatus(str, Enum):
    QUEUED    = "QUEUED"
    RUNNING   = "RUNNING"
    DONE      = "DONE"
    FAILED    = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class TaskProgress:
    task_id:       str
    jet_id:        str
    status:        TaskStatus      = TaskStatus.QUEUED
    pct:           int             = 0        # 0-100
    message:       str             = ""
    processed_rows:int             = 0
    total_rows:    int             = 0
    started_at:    float           = 0.0
    finished_at:   float           = 0.0
    error:         str             = ""
    result:        Any             = None
    cpu_pct:       float           = 0.0
    ram_mb:        float           = 0.0
    eta_sec:       float           = 0.0      # kalan tahmini süre

    def elapsed(self) -> float:
        if self.started_at == 0:
            return 0.0
        end = self.finished_at if self.finished_at else time.time()
        return round(end - self.started_at, 2)

    def to_dict(self) -> dict:
        return {
            'task_id':       self.task_id,
            'jet_id':        self.jet_id,
            'status':        self.status.value,
            'pct':           self.pct,
            'message':       self.message,
            'processed_rows':self.processed_rows,
            'total_rows':    self.total_rows,
            'elapsed':       self.elapsed(),
            'eta_sec':       round(self.eta_sec, 1),
            'error':         self.error,
            'result':        self.result,
            'cpu_pct':       self.cpu_pct,
            'ram_mb':        self.ram_mb,
        }


@dataclass(order=True)
class _QueueItem:
    priority:  int
    submit_at: float
    task_id:   str         = field(compare=False)
    fn:        Callable    = field(compare=False)
    args:      tuple       = field(compare=False)
    kwargs:    dict        = field(compare=False)


# ─────────────────────────────────────────────────────────────
# JetExecutionEngine
# ─────────────────────────────────────────────────────────────

class JetExecutionEngine:
    """
    Merkezi JET çalıştırma motoru.

    - Thread pool ile paralel JET çalıştırma
    - CPU çekirdek sayısına göre otomatik ölçekleme
    - Öncelik kuyruğu (PriorityQueue)
    - Her JET kendi TaskProgress nesnesiyle izlenir
    - Hata izolasyonu: bir JET çöksün, diğerleri devam eder
    - Bellek + CPU metrikleri her JET için ayrı raporlanır
    """

    _instance: Optional['JetExecutionEngine'] = None
    _lock = threading.Lock()

    @classmethod
    def get(cls) -> 'JetExecutionEngine':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self, max_workers: Optional[int] = None):
        self._max_workers = max_workers or max(CPU_COUNT, 2)
        self._executor    = ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix="JetWorker"
        )
        self._tasks:  Dict[str, TaskProgress] = {}
        self._futures: Dict[str, Future]       = {}
        self._tlock   = threading.RLock()
        self._queue   = PriorityQueue()

        # Arka plan scheduler
        self._running  = True
        self._sched    = threading.Thread(target=self._scheduler_loop,
                                          daemon=True, name="JetScheduler")
        self._sched.start()

        # Metrik toplayıcı
        self._metrics  = threading.Thread(target=self._metrics_loop,
                                          daemon=True, name="JetMetrics")
        self._metrics.start()

        logger.info(f"JetExecutionEngine başlatıldı — {self._max_workers} worker")

    # ── Görev Gönderme ────────────────────────────────────────

    def submit(self, jet_id: str, fn: Callable,
               *args, priority: int = 5, **kwargs) -> str:
        """
        Bir JET görevini kuyruğa ekle.
        Düşük priority değeri = daha yüksek öncelik.
        """
        task_id = f"{jet_id}_{uuid.uuid4().hex[:8]}"
        prog = TaskProgress(task_id=task_id, jet_id=jet_id,
                            status=TaskStatus.QUEUED)
        with self._tlock:
            self._tasks[task_id] = prog

        item = _QueueItem(
            priority  = priority,
            submit_at = time.time(),
            task_id   = task_id,
            fn        = fn,
            args      = args,
            kwargs    = kwargs,
        )
        self._queue.put(item)
        logger.info(f"[{task_id}] kuyruğa eklendi (jet={jet_id}, prio={priority})")
        return task_id

    def cancel(self, task_id: str) -> bool:
        with self._tlock:
            prog = self._tasks.get(task_id)
            if prog and prog.status == TaskStatus.QUEUED:
                prog.status = TaskStatus.CANCELLED
                return True
            fut = self._futures.get(task_id)
            if fut:
                fut.cancel()
                if prog:
                    prog.status = TaskStatus.CANCELLED
                return True
        return False

    # ── Durum Sorgulama ───────────────────────────────────────

    def status(self, task_id: str) -> Optional[dict]:
        with self._tlock:
            p = self._tasks.get(task_id)
            return p.to_dict() if p else None

    def all_tasks(self) -> List[dict]:
        with self._tlock:
            return [p.to_dict() for p in self._tasks.values()]

    def active_count(self) -> int:
        with self._tlock:
            return sum(1 for p in self._tasks.values()
                       if p.status == TaskStatus.RUNNING)

    def queue_size(self) -> int:
        return self._queue.qsize()

    # ── İç Mekanizma ──────────────────────────────────────────

    def _scheduler_loop(self):
        """Kuyruktan al → boş worker'a ver."""
        while self._running:
            try:
                item: _QueueItem = self._queue.get(timeout=0.3)
                with self._tlock:
                    prog = self._tasks.get(item.task_id)
                    if prog and prog.status == TaskStatus.CANCELLED:
                        self._queue.task_done()
                        continue

                fut = self._executor.submit(
                    self._run_task,
                    item.task_id, item.fn, item.args, item.kwargs
                )
                with self._tlock:
                    self._futures[item.task_id] = fut
                self._queue.task_done()

            except Exception:
                pass

    def _run_task(self, task_id: str, fn: Callable,
                  args: tuple, kwargs: dict):
        """Worker thread içinde çalışır — tam hata izolasyonu."""
        with self._tlock:
            prog = self._tasks.get(task_id)
            if prog:
                prog.status     = TaskStatus.RUNNING
                prog.started_at = time.time()
                prog.pct        = 0

        def _progress_cb(pct: int, msg: str = "", rows: int = 0, total: int = 0):
            with self._tlock:
                if prog:
                    prog.pct           = max(0, min(100, pct))
                    prog.message       = msg
                    prog.processed_rows= rows
                    prog.total_rows    = total
                    # ETA hesapla
                    if prog.started_at and pct > 0:
                        elapsed = time.time() - prog.started_at
                        prog.eta_sec = elapsed / (pct / 100) - elapsed

        try:
            kwargs['_progress_cb'] = _progress_cb
            result = fn(*args, **kwargs)
            with self._tlock:
                if prog:
                    prog.status      = TaskStatus.DONE
                    prog.pct         = 100
                    prog.result      = result
                    prog.finished_at = time.time()
                    prog.eta_sec     = 0.0
            logger.info(f"[{task_id}] DONE in {prog.elapsed():.2f}s")

        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"[{task_id}] FAILED: {e}\n{tb}")
            with self._tlock:
                if prog:
                    prog.status      = TaskStatus.FAILED
                    prog.error       = str(e)
                    prog.finished_at = time.time()

    def _metrics_loop(self):
        """Çalışan görevlerin CPU/RAM metriklerini güncelle."""
        proc = psutil.Process()
        while self._running:
            try:
                cpu   = proc.cpu_percent(interval=1)
                ram   = proc.memory_info().rss / 1024 / 1024
                with self._tlock:
                    for p in self._tasks.values():
                        if p.status == TaskStatus.RUNNING:
                            p.cpu_pct = round(cpu / max(self._max_workers, 1), 1)
                            p.ram_mb  = round(ram, 1)
            except Exception:
                pass
            time.sleep(2)

    def shutdown(self):
        self._running = False
        self._executor.shutdown(wait=False)


# ─────────────────────────────────────────────────────────────
# Progress helper — JET fonksiyonları içinde kullanmak için
# ─────────────────────────────────────────────────────────────

class ProgressReporter:
    """JET analiz fonksiyonlarına inject edilen progress callback wrapper."""

    def __init__(self, cb: Callable, total_rows: int = 0):
        self._cb         = cb
        self._total      = total_rows
        self._processed  = 0
        self._lock       = threading.Lock()

    def update(self, rows: int, msg: str = ""):
        with self._lock:
            self._processed += rows
            pct = int(self._processed / self._total * 100) if self._total else 0
            pct = max(0, min(99, pct))
        if self._cb:
            self._cb(pct, msg, self._processed, self._total)

    def done(self, msg: str = "Tamamlandı"):
        if self._cb:
            self._cb(100, msg, self._total, self._total)

    def set(self, pct: int, msg: str = ""):
        if self._cb:
            self._cb(pct, msg, self._processed, self._total)
