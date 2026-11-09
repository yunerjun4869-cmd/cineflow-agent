"""单进程、跨会话的服务商并发限额；不改变原有片段线程池。"""
import threading
from contextlib import contextmanager

# 同一服务商的不同模型共用两个槽位。多进程部署需替换为共享任务队列。
PROVIDER_LIMIT = 2
_lock = threading.Lock()
_gates = {}


@contextmanager
def provider_slot(provider, cancelled):
    with _lock:
        gate = _gates.setdefault(provider, threading.BoundedSemaphore(PROVIDER_LIMIT))
    acquired = False
    try:
        while not acquired:
            if cancelled():
                raise RuntimeError("任务已取消")
            acquired = gate.acquire(timeout=0.1)
        if cancelled():
            raise RuntimeError("任务已取消")
        yield
    finally:
        if acquired:
            gate.release()
