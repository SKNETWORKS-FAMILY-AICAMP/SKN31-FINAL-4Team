"""Thread-safe console progress and structured event log; no credentials are logged."""
from __future__ import annotations
from datetime import datetime
import json
from threading import RLock
from time import perf_counter


def display(value, limit=1000):
    text = json.dumps(value, ensure_ascii=False, default=str) if isinstance(value,(dict,list,tuple)) else str(value)
    text = text.replace('\r',' ').replace('\n',' ')
    return text if len(text)<=limit else text[:limit]+' …'


class ProgressReporter:
    def __init__(self, *, log=print, verbose=True):
        self.log = log
        self.verbose = verbose
        self.events = []
        self.started = perf_counter()
        self.lock = RLock()

    def emit(self, stage, message, *, detail=False, **data):
        if detail and not self.verbose:
            return
        with self.lock:
            event = dict(time=datetime.now().astimezone().isoformat(timespec='seconds'),
                         elapsed_seconds=round(perf_counter()-self.started,2),stage=stage,message=message,data=data)
            self.events.append(event)
            extra = ' | '.join(f'{key}={display(value)}' for key,value in data.items())
            line = f"[{event['time'][11:19]} +{event['elapsed_seconds']:.2f}s] [{stage}] {message}"
            if extra:
                line += ' | '+extra
            if self.log is not None:
                self.log(line)
