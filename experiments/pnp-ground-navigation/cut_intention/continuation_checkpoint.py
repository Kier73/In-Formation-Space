"""Bounded local continuation checkpoint. Host execution authority is external."""
from pathlib import Path
from tempfile import NamedTemporaryFile
import json
import os
from temporal_image import Processor


def save(admission,path):
    """Flush and atomically replace the local checkpoint; return its digest."""
    packet=admission.snapshot()
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    payload=json.dumps(packet,sort_keys=True,separators=(',',':')).encode('ascii')
    if len(payload)>16384:raise ValueError('checkpoint budget')
    temporary=None
    try:
        with NamedTemporaryFile(dir=path.parent,delete=False) as f:
            temporary=Path(f.name);f.write(payload);f.flush();os.fsync(f.fileno())
        os.replace(temporary,path);temporary=None
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
    return packet['sha256']


def recover(admission,nav,initial,path,expected_digest,*,codec=None):
    """Create a new producer on a fresh receiver, using a trusted latest digest."""
    with Path(path).open('rb') as f:
        raw=f.read(16385)
    if len(raw)>16384:raise ValueError('checkpoint budget')
    packet=json.loads(raw)
    producer=Processor(nav,initial,codec=codec)
    if producer.key!=admission.capacity.image.key:
        raise ValueError('producer identity')
    if not admission.restore(packet,expected_digest):
        raise ValueError('checkpoint refused')
    producer.time=admission.capacity.image.time
    producer.rank=admission.capacity.image.rank
    return producer
