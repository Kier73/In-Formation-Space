"""RCG-007: real E-CPU M1 pages and immutable quotient atlas checkpoint.

No new page store or session authority. Uses native ComputationalObjectStore and
StructuralMemoryPageBacking. A portable local checkpoint is not M3 quorum.
"""
from __future__ import annotations
import hashlib,json
from typing import Any
from connectome_ground import ConnectomeGround
from observer_quotient import ExpandedSyntheticGround,QuotientRefused
from temporal_ground import canonical,hash_object
from atlas import verify_atlas,execute_batch,verify_batch

SCHEMA='ifs.rcg007.m1-atlas.v1'
MAX_CAPSULE_BYTES=100_000


def require(cond,reason):
    if not cond:raise QuotientRefused(reason)


def _decode(raw:bytes)->dict:
    require(type(raw) is bytes and 0<len(raw)<=MAX_CAPSULE_BYTES,
            'M1 stored certificate outside bounds')
    def unique(items):
        d={}
        for k,v in items:
            require(k not in d,'M1 capsule contains duplicate JSON key')
            d[k]=v
        return d
    try:
        content=json.loads(raw,object_pairs_hook=unique,
                           parse_constant=lambda _:(1/0))
    except (UnicodeError,ValueError,ZeroDivisionError) as exc:
        raise QuotientRefused('M1 stored object is invalid JSON') from exc
    require(type(content) is dict and raw==canonical(content),
            'M1 object must use byte-exact canonical encoding')
    return content


class NativeM1Atlas:
    """Native M1 object and receiver-owned source, mathematical proof, and policy."""
    def __init__(self,source:bytes,source_pin:str,certificate:dict,atlas:dict,
                 *,require_original:bool=True,backing=None,manifest=None):
        from mailcpu.computational_objects import ComputationalObjectStore
        from mailcpu.structural_memory_pages import StructuralMemoryPageBacking
        require(type(source_pin) is str and hashlib.sha256(source).hexdigest()==source_pin,
                'receiver-owned source SHA-256 differs')
        self.source=ConnectomeGround.from_csv(source,require_original=require_original)
        c=certificate.get('expanded') if type(certificate) is dict else None
        require(type(c) is dict and set(['groups','copies','seed'])<=set(c),
                'incomplete typed procedural Ground')
        self.operator=ExpandedSyntheticGround(self.source,groups=c['groups'],copies=c['copies'],seed=c['seed'])
        self.trusted=verify_atlas(self.operator,certificate,atlas,deep=True)
        self.source_pin,self.certificate,self.atlas=source_pin,certificate,atlas
        self.backing=backing if backing is not None else StructuralMemoryPageBacking()
        require(isinstance(self.backing,StructuralMemoryPageBacking),
                'M1 requires native StructuralMemoryPageBacking')
        self.store=ComputationalObjectStore(self.backing,chunk_size=4096,max_object_bytes=MAX_CAPSULE_BYTES)
        body={'schema':SCHEMA+'.object.v1','source_sha256':source_pin,
              'source_ground':self.source.fingerprint,'certificate':certificate,'atlas':atlas}
        raw=canonical(body)
        require(len(raw)<=MAX_CAPSULE_BYTES,'M1 atlas exceeds admitted byte budget')
        if manifest is None:
            self.manifest=self.store.put_bytes(raw,media_type='application/vnd.ifs.rcg007+json')
        else:
            from mailcpu.computational_objects import ComputationalObjectManifest
            self.manifest=ComputationalObjectManifest.from_dict(manifest)
            require(self.store.read_bytes(self.manifest,max_bytes=MAX_CAPSULE_BYTES)==raw,
                    'M1 object bytes did not restore correctly')
        require(_decode(self.store.read_bytes(self.manifest,max_bytes=MAX_CAPSULE_BYTES))==body,
                'M1 source certificate or atlas bytes changed')

    @property
    def identity(self)->str:
        return self.manifest.manifest_digest

    def run(self,batch:list[dict[str,Any]])->dict[str,Any]:
        # A cache hit does not bypass the independently verified Ground.
        answer=execute_batch(self.operator,self.certificate,self.atlas,batch,trusted=self.trusted)
        verify_batch(self.operator,self.certificate,self.atlas,batch,answer,trusted=self.trusted)
        return answer

    def checkpoint(self)->dict[str,Any]:
        body={'schema':SCHEMA+'.local-checkpoint.v1',
              'source_sha256':self.source_pin,
              'source_ground':self.source.fingerprint,
              'atlas_digest':self.atlas['digest'],
              'm1_manifest':self.manifest.to_dict(),
              'page_backing':self.backing.snapshot(),
              'scope':'local-snapshot-external-highwater-required-not-M3-quorum'}
        return {**body,'digest':hash_object(body)}

    @classmethod
    def restore(cls,source:bytes,checkpoint:dict,expected_head:str,*,require_original:bool=True):
        from mailcpu.computational_objects import ComputationalObjectStore,ComputationalObjectManifest
        from mailcpu.structural_memory_pages import StructuralMemoryPageBacking
        require(type(expected_head) is str and len(expected_head)==64 and
                type(checkpoint) is dict and set(checkpoint)=={
                'schema','source_sha256','source_ground','atlas_digest',
                'm1_manifest','page_backing','scope','digest'} and
                checkpoint['schema']==SCHEMA+'.local-checkpoint.v1' and
                checkpoint['scope']=='local-snapshot-external-highwater-required-not-M3-quorum' and
                checkpoint['digest']==expected_head and
                hash_object({k:v for k,v in checkpoint.items() if k!='digest'})==expected_head,
                'checkpoint fails independent high-water pin')
        backing=StructuralMemoryPageBacking.from_snapshot(checkpoint['page_backing'])
        store=ComputationalObjectStore(backing,chunk_size=4096,max_object_bytes=MAX_CAPSULE_BYTES)
        manifest=ComputationalObjectManifest.from_dict(checkpoint['m1_manifest'])
        payload=_decode(store.read_bytes(manifest,max_bytes=MAX_CAPSULE_BYTES))
        require(set(payload)=={'schema','source_sha256','source_ground','certificate','atlas'} and
                payload['schema']==SCHEMA+'.object.v1' and
                payload['source_sha256']==checkpoint['source_sha256'] and
                payload['source_ground']==checkpoint['source_ground'] and
                payload['atlas']['digest']==checkpoint['atlas_digest'] and
                hashlib.sha256(source).hexdigest()==checkpoint['source_sha256'],
                'checkpoint M1 object or original source differs')
        restored=cls(source,checkpoint['source_sha256'],payload['certificate'],payload['atlas'],
                     require_original=require_original,backing=backing,manifest=manifest.to_dict())
        require(restored.checkpoint()==checkpoint,
                'reconstructed M1 state differs from pinned checkpoint')
        return restored