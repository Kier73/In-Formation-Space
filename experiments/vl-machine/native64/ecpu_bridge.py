"""VLM-005: pure capsule observation through existing E-CPU M2 authority."""
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

SCHEMA='vlm.capsule-observation.v1'
OP='vlm.capsule.observe'
FILES=('capsule.py','libcore.so','core.c','core.h','application.c','neural.c','Makefile','ecpu_bridge.py')
LIMIT=1_048_576

def run_worker(root,cap):
    """Fresh native receiver. No supplied code, executable path, or shell."""
    raw=json.dumps(cap,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
    if len(raw)>LIMIT:raise ValueError('capsule exceeds bound')
    p=subprocess.run([sys.executable,'-I','-B',str(Path(root).resolve()/'capsule.py')],input=raw,capture_output=True,timeout=10,check=True)
    if len(p.stdout)>1024:raise ValueError('worker output exceeds bound')
    result=json.loads(p.stdout)
    if type(result) is not dict or set(result)!={'value','work'} or any(type(v) is not int or not 0<=v<2**32 for v in result.values()):raise ValueError('invalid worker output')
    return {'schema':SCHEMA,'capsule_sha256':cap['sha256'],'observation':result}

def admit_runtime(root,object_store=None):
    from mailcpu.computational_host import admit_computational_artifact_directory
    root=Path(root)
    root.mkdir(parents=True,exist_ok=False)
    src=Path(__file__).resolve().parent
    for name in FILES:shutil.copyfile(src/name,root/name)
    manifest=admit_computational_artifact_directory(root,artifact_id='vlm/native64@1',artifact_kind='native-capsule-runtime',object_store=object_store,metadata={'protocol':SCHEMA},max_total_size=2*LIMIT,max_files=len(FILES))
    return manifest,root

def profile(manifest):
    from mailcpu.computational_host import ComputationalBackendProfile,ComputationalBackendError
    if manifest.metadata.get('protocol')!=SCHEMA or {c.path for c in manifest.components}!=set(FILES):raise ComputationalBackendError('VLM manifest inventory or protocol mismatch')
    digest=hashlib.sha256(SCHEMA.encode()+bytes.fromhex(manifest.manifest_digest)).hexdigest()
    return ComputationalBackendProfile(backend_id='vlm.native64',implementation_id='vlm.capsule.native-c',implementation_digest=digest,deterministic=True,effect_mode='pure',runtime_versions={'python':platform.python_version(),'machine':platform.machine(),'libc':':'.join(platform.libc_ver())},configuration={'operations':[OP]},max_input_bytes=LIMIT,max_output_bytes=1024)

class Adapter:
    def __init__(self):self.root=None;self.manifest=None
    def load(self,manifest,artifact_root,backend_profile):
        from mailcpu.computational_host import ComputationalBackendError,verify_computational_artifact_directory
        root=Path(artifact_root).resolve()
        if backend_profile!=profile(manifest) or not verify_computational_artifact_directory(manifest,root):raise ComputationalBackendError('VLM artifact/profile mismatch')
        if (root/'ecpu_bridge.py').read_bytes()!=Path(__file__).resolve().read_bytes():raise ComputationalBackendError('adapter source mismatch')
        self.root=root;self.manifest=manifest
    def execute(self,request):
        from mailcpu.computational_host import ComputationalBackendError,verify_computational_artifact_directory
        if self.root is None or request.operation!=OP:raise ComputationalBackendError('operation not in VLM catalogue')
        if not verify_computational_artifact_directory(self.manifest,self.root):raise ComputationalBackendError('VLM artifact changed')
        try:
            raw=json.loads(json.dumps(request.input_value,allow_nan=False))
            if type(raw) is not dict or set(raw)!={'capsule'}:raise ValueError('exact capsule field required')
            return run_worker(self.root,raw['capsule'])
        except (ValueError,KeyError,TypeError,subprocess.SubprocessError) as exc:raise ComputationalBackendError('VLM receiver rejected request') from exc
    def unload(self):self.root=None;self.manifest=None
