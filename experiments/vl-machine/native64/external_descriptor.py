"""Bounded descriptive experience adapter. Reading is not execution authority."""
import json,re,ssl,urllib.request
from hashlib import sha256
from pathlib import Path
from experience_contract import canonical,digest,require

MAX=65536
HOST='huggingface.co'
MODEL=re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}/[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z')
REV=re.compile(r'[0-9a-f]{40}\Z')

def identity(model,rev):
    require(type(model) is str and MODEL.fullmatch(model) and type(rev) is str and REV.fullmatch(rev),'model/revision')
    require(all(v not in ('.','..') for v in model.split('/')),'model path')
    return 'https://'+HOST+'/api/models/'+model+'/revision/'+rev

def text(x):
    require(type(x) is str and 0<len(x)<=128,'descriptor text');return x

def projection(data,model,rev):
    identity(model,rev);require(type(data) is dict and data.get('id')==model and data.get('sha')==rev,'descriptor source identity')
    cfg=data.get('config',{});require(type(cfg) is dict,'config')
    arch=cfg.get('architectures',[]);require(type(arch) is list and len(arch)<=32,'architecture extent');arch=[text(v) for v in arch]
    siblings=data.get('siblings',[]);require(type(siblings) is list and len(siblings)<=4096,'inventory extent')
    names=[]
    for v in siblings:
        require(type(v) is dict and type(v.get('rfilename')) is str and 0<len(v['rfilename'])<=512,'inventory entry');names.append(v['rfilename'])
    require(len(set(names))==len(names),'duplicate file')
    tensors=data.get('safetensors',{});require(type(tensors) is dict,'tensor metadata');total=tensors.get('total')
    require(total is None or type(total) is int and 0<=total<1<<63,'parameter count')
    return {'model':model,'revision':rev,'architecture':arch,'model_type':text(cfg['model_type']) if 'model_type' in cfg else None,'pipeline':text(data['pipeline_tag']) if 'pipeline_tag' in data else None,'config_declared':'config.json' in names,'safetensors_declared':any(x.endswith('.safetensors') for x in names),'parameter_count_declared':total}

def _unique(pairs):
    d={}
    for k,v in pairs:
        require(k not in d,'duplicate JSON field');d[k]=v
    return d

def parse(raw,model,rev):
    require(type(raw) is bytes and 0<len(raw)<=MAX,'response bounds')
    data=json.loads(raw.decode('utf-8'),object_pairs_hook=_unique)
    return projection(data,model,rev)

def record(desc,provenance,source_url,raw_sha=None):
    model,rev=desc['model'],desc['revision'];pinned=identity(model,rev)
    require(provenance in ('raw-https-json','web-field-projection'),'provenance')
    if provenance=='raw-https-json':
        require(source_url==pinned and type(raw_sha) is str and re.fullmatch(r'[0-9a-f]{64}',raw_sha),'raw source binding')
    else:require(source_url=='https://'+HOST+'/api/models/'+model and raw_sha is None,'projection source binding')
    # Only a proposed, revision-pinned next observation. No model/weight execution.
    next_action={'operator':'descriptor.read.v1','url':'https://'+HOST+'/'+model+'/resolve/'+rev+'/config.json','max_bytes':MAX} if desc['config_declared'] else None
    body={'schema':'vlm.external-descriptor.v1','source_url':source_url,'provenance':provenance,'descriptor':desc,'raw_response_sha256':raw_sha,'authority':'descriptive-only','next_observation':next_action}
    return body|{'record_id':digest(body)}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):return None

def capture(model,rev):
    url=identity(model,rev);req=urllib.request.Request(url,headers={'Accept':'application/json','Accept-Encoding':'identity','User-Agent':'VLM-015/1'})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect,urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    with opener.open(req,timeout=10) as response:
        require(response.status==200 and response.geturl()==url,'response identity')
        require(response.headers.get('Content-Encoding','identity')=='identity','content encoding')
        raw=response.read(MAX+1);length=response.headers.get('Content-Length')
        require(length is None or length.isdigit() and int(length)==len(raw),'response length')
    return record(parse(raw,model,rev),'raw-https-json',url,sha256(raw).hexdigest())

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--fixture',type=Path);p.add_argument('--model');p.add_argument('--revision');a=p.parse_args()
    if a.fixture:
        f=json.loads(a.fixture.read_bytes());d=projection(f['observed_fields'],f['model'],f['revision']);r=record(d,'web-field-projection',f['source_url'])
    else:r=capture(a.model,a.revision)
    print(json.dumps(r,indent=2,sort_keys=True))
