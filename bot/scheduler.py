"""의존성 없는 소형 스케줄러.

각 잡의 마지막 실행 시각을 SQLite 에 남겨서, 봇이 재시작돼도 같은 슬롯을
두 번 발행하지 않는다. 봇이 오래 꺼져 있었다면 지난 슬롯은 조용히 건너뛴다
(밀린 사진 10장이 한꺼번에 쏟아지는 걸 막기 위함).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

log = logging.getLogger("sched")

# 예정 시각을 이만큼 넘겨서 발견된 잡은 실행하지 않는다.
#
# 상시 실행할 때는 몇 초 안에 발견되므로 이 값이 거의 쓰이지 않지만,
# GitHub Actions 처럼 30분 간격으로 --tick 을 도는 경우에는 예정 시각과
# 실제 실행 사이에 그만큼 간격이 생긴다. 그 지연을 흡수할 만큼 넉넉해야
# 06:30 미션 같은 정시 발행이 통째로 누락되지 않는다.
GRACE = timedelta(minutes=int(os.environ.get("JOB_GRACE_MINUTES", "60")))


@dataclass
class Job:
    name: str
    fn: Callable[[datetime], None]

    def due(self, now: datetime, last: datetime | None) -> bool:
        raise NotImplementedError


@dataclass
class DailyJob(Job):
    hour: int = 0
    minute: int = 0
    weekdays: tuple[int, ...] | None = None  # None = 매일, 0=월
    every_n_weeks: int | None = None
    anchor_week: int = 0

    def due(self, now: datetime, last: datetime | None) -> bool:
        if self.weekdays is not None and now.weekday() not in self.weekdays:
            return False
        if self.every_n_weeks and (now.isocalendar().week - self.anchor_week) % self.every_n_weeks:
            return False

        scheduled = now.replace(hour=self.hour, minute=self.minute, second=0, microsecond=0)
        if now < scheduled or now - scheduled > GRACE:
            return False
        return last is None or last < scheduled


@dataclass
class IntervalJob(Job):
    minutes: int = 60
    start_hour: int = 7
    end_hour: int = 22

    def due(self, now: datetime, last: datetime | None) -> bool:
        if not (self.start_hour <= now.hour <= self.end_hour):
            return False
        if last is None:
            return True
        return now - last >= timedelta(minutes=self.minutes) - timedelta(seconds=30)


class Scheduler:
    def __init__(self, store, tz):
        self._store = store
        self._tz = tz
        self._jobs: list[Job] = []

    def add(self, job: Job) -> None:
        self._jobs.append(job)

    def job_names(self) -> list[str]:
        return [j.name for j in self._jobs]

    def run_named(self, name: str, now: datetime | None = None) -> bool:
        """수동 실행 (--once). 스케줄과 무관하게 즉시 발행한다."""
        now = now or datetime.now(self._tz)
        for job in self._jobs:
            if job.name == name:
                job.fn(now)
                return True
        return False

    def tick(self, now: datetime | None = None) -> None:
        """예정된 잡을 확인해서 실행한다.

        실행 *전에* claim_run 으로 슬롯을 원자적으로 선점한다 (먼저 실행하고
        나중에 표시하면, Render 상시 실행과 GitHub Actions --tick 이 겹쳐
        들어올 때 둘 다 due 로 보고 둘 다 발행해버리는 경합이 생긴다).
        선점에 실패하면(다른 트리거가 방금 가져감) 조용히 건너뛴다.
        """
        now = now or datetime.now(self._tz)
        for job in self._jobs:
            try:
                last = self._store.last_run(job.name)
                if last is not None and last.tzinfo is None:
                    last = last.replace(tzinfo=self._tz)
                if not job.due(now, last):
                    continue
                if not self._store.claim_run(job.name, now):
                    log.info("선점 실패(다른 트리거가 이미 처리) — 건너뜀: %s", job.name)
                    continue
                log.info("실행: %s", job.name)
                job.fn(now)
            except Exception:
                log.exception("잡 실패: %s", job.name)
