from __future__ import annotations

import logging
import threading
import time

from .search import sync_one
from .service import SUPPORTED_JOB_KINDS, UnsupportedJobKind, ResearchError

logger = logging.getLogger(__name__)


def run_one(service, job_id=None, kinds=None, skip=None):
    """Process one job. Returns False only when nothing was claimable.

    A job whose kind this worker does not implement is released back to the queue instead of
    failing, so an outdated worker cannot consume a newer task or its attempts. The kind is
    added to ``skip`` (when provided) so a long-running worker stops re-claiming it.
    """
    job = service.claim_job(job_id, kinds)
    if not job:
        return False
    stop = threading.Event()
    lost = threading.Event()
    job['_lease_lost'] = lost

    def beat():
        failures = 0
        while not stop.wait(max(1, service.settings.lease_seconds / 3)):
            try:
                service.heartbeat(job)
                failures = 0
            except ResearchError as exc:
                if exc.code == 'JOB_NO_LONGER_OWNED':
                    lost.set()
                    return
                logger.warning('Research heartbeat failed: job=%s code=%s', job['id'], exc.code)
            except Exception:
                failures += 1
                logger.warning('Research heartbeat failed: job=%s attempt=%s', job['id'], failures)
                if failures >= 3:
                    lost.set()
                    return

    thread = threading.Thread(target=beat, daemon=True)
    thread.start()
    try:
        service.process_job(job)
    except UnsupportedJobKind as exc:
        if skip is not None:
            skip.add(exc.kind)
        if service.release(job):
            logger.error('Research worker does not implement job kind %s; job released to the queue. '
                         'Start a worker from the deployed build.', exc.kind)
        else:
            logger.error('Research job %s was reclaimed before it could be released.', job['id'])
    except Exception as exc:
        logger.warning('Research execution stopped: job=%s kind=%s code=%s',
                       job['id'], job['kind'], getattr(exc, 'code', type(exc).__name__))
        service.fail(job, exc)
    finally:
        stop.set()
        thread.join(timeout=2)
    return True


def work(service):
    unsupported = set()
    while True:
        kinds = SUPPORTED_JOB_KINDS - unsupported
        worked = run_one(service, kinds=kinds, skip=unsupported) if kinds else False
        indexed = sync_one(service)
        if not worked and not indexed:
            time.sleep(1)
