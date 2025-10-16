from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum


class TaskType(Enum):
    """Supported execution modes for tasks."""

    CONCURRENT = "concurrent"
    SEQUENTIAL = "sequential"


@dataclass
class Task:
    """Container wrapping a callable for threaded or inline execution."""

    target: Callable[..., object]
    args: tuple[object, ...] = ()
    kwargs: dict[str, object] = field(default_factory=dict)
    name: str | None = None
    task_type: TaskType = TaskType.CONCURRENT
    daemon: bool = True

    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _started: bool = field(default=False, init=False, repr=False)
    _exception: BaseException | None = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )

    def start(self) -> None:
        """Start the task respecting the configured execution mode."""

        with self._lock:
            if self._started:
                raise RuntimeError("Task has already started")
            self._started = True

            if self.task_type is TaskType.CONCURRENT:
                thread_name = self.name or getattr(self.target, "__name__", "task")
                self._thread = threading.Thread(
                    target=self._run,
                    name=thread_name,
                    daemon=self.daemon,
                )
                self._thread.start()
                return

        if self.task_type is TaskType.SEQUENTIAL:
            self._run()

    def join(self, timeout: float | None = None) -> None:
        """Wait for the task to finish when running concurrently."""

        thread = self._thread
        if thread is None:
            return

        thread.join(timeout)

    def is_alive(self) -> bool:
        thread = self._thread
        return thread.is_alive() if thread else False

    @property
    def exception(self) -> BaseException | None:
        return self._exception

    def _run(self) -> None:
        try:
            _ = self.target(*self.args, **self.kwargs)
        except BaseException as exc:  # noqa: BLE001 - propagate stored exceptions
            self._exception = exc
            raise


class TaskExecutionError(RuntimeError):
    """Raised when one or more tasks fail during execution."""

    task: Task
    error: BaseException
    __cause__: BaseException | None

    def __init__(self, task: Task, error: BaseException) -> None:
        super().__init__(f"Task '{task.name or task.target.__name__}' failed: {error}")
        self.task = task
        self.error = error
        self.__cause__ = error


class TaskManager:
    """Coordinate the lifecycle of multiple tasks."""

    def __init__(self, tasks: Iterable[Task] | None = None) -> None:
        self._tasks: list[Task] = list(tasks) if tasks is not None else []

    def add(self, task: Task) -> None:
        self._tasks.append(task)

    def extend(self, tasks: Iterable[Task]) -> None:
        for task in tasks:
            self.add(task)

    def start_all(self) -> None:
        for task in self._tasks:
            task.start()

    def join_all(self, timeout: float | None = None) -> None:
        if timeout is None:
            for task in self._tasks:
                task.join()
            return

        deadline = time.monotonic() + timeout
        for task in self._tasks:
            remaining = deadline - time.monotonic()
            task.join(max(0.0, remaining))

    def raise_failures(self) -> None:
        for task in self._tasks:
            if task.exception is not None:
                raise TaskExecutionError(task, task.exception)

    def iter_tasks(self) -> Iterable[Task]:
        return tuple(self._tasks)
