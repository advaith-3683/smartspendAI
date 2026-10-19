"""Fixed-field, flushed startup diagnostics; never logs configuration or rows."""
import json
import time
from contextlib import contextmanager


@contextmanager
def startup_stage(stage):
    started = time.monotonic()
    print(json.dumps({'event': 'startup_stage', 'stage': stage, 'status': 'started'}), flush=True)
    try:
        yield
    except Exception:
        print(json.dumps({'event': 'startup_stage', 'stage': stage, 'status': 'failed',
                          'elapsed_seconds': round(time.monotonic() - started, 3)}), flush=True)
        raise
    else:
        print(json.dumps({'event': 'startup_stage', 'stage': stage, 'status': 'complete',
                          'elapsed_seconds': round(time.monotonic() - started, 3)}), flush=True)
