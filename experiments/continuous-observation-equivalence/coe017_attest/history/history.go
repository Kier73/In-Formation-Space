// Package history independently replays signed COE-017 authority decisions.
// It draws the append-only / externally anchored distinction from RE-014.
// No journal head or producer-supplied checkpoint is an independent trust anchor.
package history

import (
 "bytes"
 "crypto/ed25519"
 "crypto/sha256"
 "encoding/base64"
 "encoding/hex"
 "encoding/json"
 "fmt"
 "os"
 "regexp"
 "sort"
 "strings"

 attest "coe017_attest"
)

const (
 JournalSchema = "ifs.coe018.authority-journal/v1"
 DecisionSchema = "ifs.coe018.authority-decision/v1"
 AnchorSchema = "ifs.coe018.journal-anchor/v1"
 ResultSchema = "ifs.coe018.independent-authority-replay/v1"
 GovernanceDomain = "IFS-COE018-GOVERNANCE-V1\n"
 NewKeyProofDomain = "IFS-COE018-NEW-KEY-PROOF-V1\n"
 maxJournal = 8 << 20
 maxEvents = 128
)
var hexPattern = regexp.MustCompile(`^[0-9a-f]{64}$`)
var keyPattern = regexp.MustCompile(`^[a-z][a-z0-9-]{1,63}$`)

type Decision struct {
 Schema string `json:"schema"`
 Kind string `json:"kind"`
 Sequence uint64 `json:"sequence"`
 Previous string `json:"previous"`
 StatementSHA256 string `json:"statement_sha256"`
 EnvelopeSHA256 string `json:"envelope_sha256"`
 EvidenceSHA256 string `json:"evidence_sha256"`
 NextPolicy *attest.Policy `json:"next_policy,omitempty"`
 Reason string `json:"reason,omitempty"`
}
type Entry struct {
 Decision Decision `json:"decision"`
 OldSignatures []attest.Signature `json:"old_signatures"`
 NewSignatures []attest.Signature `json:"new_signatures,omitempty"`
}
type Anchor struct {
 Schema string `json:"schema"`
 Count int `json:"count"`
 Head string `json:"head"`
}
type Journal struct {
 Schema string `json:"schema"`
 Entries []Entry `json:"entries"`
 Anchor Anchor `json:"anchor"`
}
type Result struct {
 Schema string `json:"schema"`
 Status string `json:"status"`
 PolicyMode string `json:"policy_mode"`
 Issuer string `json:"issuer"`
 OriginalStatementSHA256 string `json:"original_statement_sha256"`
 OriginalEvidenceSHA256 string `json:"original_evidence_sha256"`
 OriginalEnvelopeSHA256 string `json:"original_envelope_sha256"`
 JournalCount int `json:"journal_count"`
 JournalHead string `json:"journal_head"`
 FinalPolicySHA256 string `json:"final_policy_sha256"`
 FinalSequence uint64 `json:"final_sequence"`
 ActiveSigners []string `json:"active_signers"`
 ReceiptRevoked bool `json:"receipt_revoked"`
 ComparedExpectedAnchor bool `json:"compared_expected_anchor"`
 ExternalAnchorAuthenticated bool `json:"external_anchor_authenticated"`
 RealWorldIdentityAuthenticated bool `json:"real_world_identity_authenticated"`
 GroundAdmitted bool `json:"ground_admitted"`
 TrustScope string `json:"trust_scope"`
}

func fail(msg string)error{return fmt.Errorf("COE-018 rejected: %s",msg)}
func sha(raw []byte)string{s:=sha256.Sum256(raw);return hex.EncodeToString(s[:])}
func Canonical(v any)([]byte,error){return attest.Canonical(v)}
func strict(raw []byte,out any)error{
 if len(raw)==0||len(raw)>maxJournal||raw[len(raw)-1]!='\n'{return fail("invalid canonical JSON size or ending")}
 decoder:=json.NewDecoder(bytes.NewReader(raw));decoder.DisallowUnknownFields()
 if err:=decoder.Decode(out);err!=nil{return fail("invalid or unknown JSON field")}
 // Canonical typed equality excludes unknown keys, duplicate names, alternate encodings.
 again,err:=Canonical(out)
 if err!=nil||!bytes.Equal(raw,again){return fail("noncanonical, duplicate-key or extra JSON content")}
 return nil
}
func ParseJournal(raw []byte)(Journal,error){
 var j Journal
 if err:=strict(raw,&j);err!=nil{return j,err}
 if j.Schema!=JournalSchema||len(j.Entries)==0||len(j.Entries)>maxEvents||
    j.Anchor.Schema!=AnchorSchema{return j,fail("unsupported journal schema or event count")}
 return j,nil
}
func ParseAnchor(raw []byte)(Anchor,error){
 var a Anchor
 if err:=strict(raw,&a);err!=nil{return a,err}
 if a.Schema!=AnchorSchema||a.Count<0||a.Count>maxEvents||!hexPattern.MatchString(a.Head){
    return a,fail("invalid expected witness anchor")
 }
 return a,nil
}
func payload(d Decision,domain string)([]byte,error){
 b,err:=Canonical(d);if err!=nil{return nil,err}
 return append([]byte(domain),b...),nil
}
func matchQuorum(signatures []attest.Signature,p attest.Policy,sequence uint64,domain string,d Decision)error{
 if len(signatures)<p.Threshold||len(signatures)>len(p.Keys){return fail("governance signer quorum absent")}
 keys:=map[string]attest.Key{}
 for _,key:=range p.Keys{keys[key.ID]=key}
 message,err:=payload(d,domain);if err!=nil{return err}
 last:=""
 for _,sig:=range signatures{
    if !keyPattern.MatchString(sig.KeyID)||(last!=""&&sig.KeyID<=last){
       return fail("duplicated, malformed or unsorted signing key")
    }
    last=sig.KeyID
    key,ok:=keys[sig.KeyID]
    if !ok||key.State!="active"||sequence<key.ValidFrom||
       (key.ValidUntil!=0&&sequence>=key.ValidUntil){
       return fail("untrusted, revoked, expired or future governance signer")
    }
    signature,err:=base64.StdEncoding.Strict().DecodeString(sig.Value)
    if err!=nil||len(signature)!=ed25519.SignatureSize{return fail("invalid governance signature length")}
    pub,err:=base64.StdEncoding.Strict().DecodeString(key.PublicKey)
    if err!=nil||!ed25519.Verify(ed25519.PublicKey(pub),message,signature){
       return fail("invalid Ed25519 governance signature")
    }
 }
 return nil
}
func validateRotation(current,next attest.Policy,sequence uint64)error{
 raw,err:=Canonical(next);if err!=nil{return err}
 validated,err:=attest.ParsePolicy(raw);if err!=nil{return fmt.Errorf("rotated policy: %w",err)}
 next=validated
 if current.Schema!=next.Schema||current.Mode!=next.Mode||current.Issuer!=next.Issuer||
    current.Context!=next.Context||next.Threshold<current.Threshold||
    next.MinimumSequence<=current.MinimumSequence||next.MinimumSequence>sequence+1||
    len(current.ExpectedNetworkSHA256)!=len(next.ExpectedNetworkSHA256){
    return fail("policy transition changes issuer, scope, threshold floor or network pins")
 }
 for id,hash:=range current.ExpectedNetworkSHA256{
    if next.ExpectedNetworkSHA256[id]!=hash{return fail("rotated authority substituted source network")}
 }
 nextKeys:=map[string]attest.Key{}
 for _,k:=range next.Keys{nextKeys[k.ID]=k}
 hasNew:=false
 for _,old:=range current.Keys{
    n,ok:=nextKeys[old.ID]
    if !ok||n.PublicKey!=old.PublicKey||n.Algorithm!=old.Algorithm||
       n.ValidFrom!=old.ValidFrom||
       (old.State=="revoked"&&n.State!="revoked")||
       (old.ValidUntil!=0&&(n.ValidUntil==0||n.ValidUntil>old.ValidUntil)){
       return fail("removed, mutated, resurrected or extended old verifier signing identity")
    }
 }
 oldIDs:=map[string]bool{};for _,k:=range current.Keys{oldIDs[k.ID]=true}
 for _,k:=range next.Keys{if !oldIDs[k.ID] {hasNew=true}}
 if !hasNew{return fail("rotation must introduce a separately authorized signing key")}
 return nil
}
func policyHash(p attest.Policy)string{
 raw,_:=Canonical(p);return sha(raw)
}
func anchorEqual(a,b Anchor)bool{return a.Schema==b.Schema&&a.Count==b.Count&&a.Head==b.Head}

// Replay never accepts journal/policy metadata as a trusted genesis. initialPolicy
// and initialState are receiver-owned inputs. The independently obtained
// expected anchor is OPTIONAL, but without it truncation can remain invisible.
func Replay(journalRaw,signedRaw,evidenceRaw,initialPolicyRaw,initialStateRaw []byte,
 certificateDir string, expectedAnchor *Anchor, allowDemo bool)(Result,error){
 var empty Result
 policy,err:=attest.ParsePolicy(initialPolicyRaw);if err!=nil{return empty,err}
 if policy.Mode=="test-only"&&!allowDemo{return empty,fail("demo authority refused without opt-in")}
 state,err:=attest.ParseState(initialStateRaw);if err!=nil{return empty,err}
 if state.Issuer!=policy.Issuer{return empty,fail("receiver genesis replay state issuer differs from trusted policy")}
 original,_,err:=attest.Verify(signedRaw,evidenceRaw,initialPolicyRaw,initialStateRaw,certificateDir,allowDemo)
 if err!=nil{return empty,fmt.Errorf("COE-017 source receipt: %w",err)}
 journal,err:=ParseJournal(journalRaw);if err!=nil{return empty,err}
 previous:=strings.Repeat("0",64)
 sequence:=original.Sequence-1
 accepted:=false;revoked:=false
 for i,entry:=range journal.Entries{
    d:=entry.Decision
    if d.Schema!=DecisionSchema||d.Previous!=previous||
       d.Sequence!=sequence+1||d.Sequence>attest.MaxSequence||
       !hexPattern.MatchString(d.Previous)||
       d.StatementSHA256!=original.StatementSHA256||
       d.EvidenceSHA256!=original.EvidenceSHA256||
       d.EnvelopeSHA256!=sha(signedRaw){
       return empty,fail("noncontinuous history, unexpected source, or replaced evidence")
    }
    if d.Sequence<policy.MinimumSequence{return empty,fail("governance decision falls below receiver policy sequence floor")}
    if err:=matchQuorum(entry.OldSignatures,policy,d.Sequence,GovernanceDomain,d);err!=nil{
       return empty,err
    }
    switch d.Kind{
    case "accept":
       if i!=0||accepted||d.Sequence!=original.Sequence||d.NextPolicy!=nil||
          d.Reason!=""||len(entry.NewSignatures)!=0 {
          return empty,fail("invalid or duplicate COE-017 accept decision")
       }
       accepted=true
    case "rotate":
       if !accepted||revoked||d.NextPolicy==nil||d.Reason!=""||
          d.Sequence<original.Sequence+1{
          return empty,fail("unsupported or premature governance rotation")
       }
       if err:=validateRotation(policy,*d.NextPolicy,d.Sequence);err!=nil{return empty,err}
       if err:=matchQuorum(entry.NewSignatures,*d.NextPolicy,d.Sequence+1,NewKeyProofDomain,d);err!=nil{
          return empty,fmt.Errorf("new-key possession proof: %w",err)
       }
       policy=*d.NextPolicy
    case "revoke":
       if !accepted||revoked||d.NextPolicy!=nil||len(entry.NewSignatures)!=0||
          d.Reason!="verifier-credential-retired" {
          return empty,fail("invalid, repeated or unscoped revocation")
       }
       revoked=true
    default:
       return empty,fail("unknown governance transition")
    }
    raw,err:=Canonical(entry);if err!=nil{return empty,err}
    previous=sha(raw)
    sequence=d.Sequence
 }
 if !accepted{return empty,fail("receipt was never accepted")}
 local:=Anchor{Schema:AnchorSchema,Count:len(journal.Entries),Head:previous}
 if !anchorEqual(journal.Anchor,local){return empty,fail("journal self-declared head or count mismatch")}
 if expectedAnchor!=nil && !anchorEqual(*expectedAnchor,local){
    return empty,fail("independently supplied witness anchor rejects truncation or fork")
 }
 active:=[]string{}
 for _,k:=range policy.Keys{if k.State=="active"&&sequence>=k.ValidFrom&&
    (k.ValidUntil==0||sequence<k.ValidUntil){active=append(active,k.ID)}}
 sort.Strings(active)
 status:="active-under-policy"
 if revoked{status="revoked-under-policy"}
 return Result{
    Schema:ResultSchema,Status:status,PolicyMode:policy.Mode,Issuer:policy.Issuer,
    OriginalStatementSHA256:original.StatementSHA256,
    OriginalEnvelopeSHA256:sha(signedRaw),OriginalEvidenceSHA256:original.EvidenceSHA256,
    JournalCount:local.Count,JournalHead:local.Head,
    FinalPolicySHA256:policyHash(policy),FinalSequence:sequence,
    ActiveSigners:active,ReceiptRevoked:revoked,
    ComparedExpectedAnchor:expectedAnchor!=nil,
    ExternalAnchorAuthenticated:false,RealWorldIdentityAuthenticated:false,
    GroundAdmitted:false,
    TrustScope:"Receiver-owned genesis and signed old/new signer quorums allow deterministic authority reconstruction. A journal-producer supplied expected anchor is not externally authenticated; an independently preserved anchor is necessary to detect full-history rollback. Public demo signers are not production identities.",
 },nil
}

// DemoSign is deliberately limited to publicly known test keys; it is never
// a production signing API. The protocol decoder itself needs no private keys.
func DemoSign(d Decision,domain string,seeds ...byte)[]attest.Signature{
 payload,err:=payload(d,domain);if err!=nil{panic(err)}
 out:=make([]attest.Signature,0,len(seeds))
 for _,s:=range seeds{
    private:=ed25519.NewKeyFromSeed(bytes.Repeat([]byte{s},ed25519.SeedSize))
    out=append(out,attest.Signature{
       KeyID:fmt.Sprintf("demo-vr-%02x",s),
       Value:base64.StdEncoding.EncodeToString(ed25519.Sign(private,payload)),
    })
 }
 sort.Slice(out,func(i,j int)bool{return out[i].KeyID<out[j].KeyID})
 return out
}
func demoPolicy(old attest.Policy)attest.Policy{
 next:=old
 next.MinimumSequence=4
 next.Keys=append([]attest.Key{},old.Keys...)
 for i:=range next.Keys{if next.Keys[i].ID=="demo-vr-52"{next.Keys[i].State="revoked"}}
 private:=ed25519.NewKeyFromSeed(bytes.Repeat([]byte{0x63},ed25519.SeedSize))
 next.Keys=append(next.Keys,attest.Key{
    ID:"demo-vr-63",Algorithm:"ed25519",
    PublicKey:base64.StdEncoding.EncodeToString(private.Public().(ed25519.PublicKey)),
    State:"active",ValidFrom:4,
 })
 return next
}
func GenerateDemo(signedRaw,evidenceRaw,initialPolicyRaw,initialStateRaw []byte,certDir string)(Journal,error){
 var result Journal
 policy,err:=attest.ParsePolicy(initialPolicyRaw);if err!=nil{return result,err}
 if policy.Mode!="test-only"||policy.Issuer!="ifs-coe017-demo-verifier"{
    return result,fail("demo journal only supports public COE-017 test authority")
 }
 original,_,err:=attest.Verify(signedRaw,evidenceRaw,initialPolicyRaw,initialStateRaw,certDir,true)
 if err!=nil{return result,err}
 if original.Sequence!=3{return result,fail("demo expects initial verifier receipt sequence 3")}
 next:=demoPolicy(policy)
 result=Journal{Schema:JournalSchema,Entries:[]Entry{}}
 previous:=strings.Repeat("0",64)
 insert:=func(kind string,sequence uint64,successors *attest.Policy,reason string,oldKeys,newKeys []byte)error{
   d:=Decision{
      Schema:DecisionSchema,Kind:kind,Sequence:sequence,Previous:previous,
      StatementSHA256:original.StatementSHA256,
      EnvelopeSHA256:sha(signedRaw),EvidenceSHA256:original.EvidenceSHA256,
      NextPolicy:successors,Reason:reason,
   }
   entry:=Entry{Decision:d,OldSignatures:DemoSign(d,GovernanceDomain,oldKeys...)}
   if len(newKeys)>0{entry.NewSignatures=DemoSign(d,NewKeyProofDomain,newKeys...)}
   raw,err:=Canonical(entry);if err!=nil{return err}
   previous=sha(raw)
   result.Entries=append(result.Entries,entry)
   return nil
 }
 if err:=insert("accept",3,nil,"",[]byte{0x41,0x52},nil);err!=nil{return result,err}
 if err:=insert("rotate",4,&next,"",[]byte{0x41,0x52},[]byte{0x41,0x63});err!=nil{return result,err}
 if err:=insert("revoke",5,nil,"verifier-credential-retired",[]byte{0x41,0x63},nil);err!=nil{return result,err}
 result.Anchor=Anchor{Schema:AnchorSchema,Count:3,Head:previous}
 raw,err:=Canonical(result);if err!=nil{return result,err}
 if _,err=Replay(raw,signedRaw,evidenceRaw,initialPolicyRaw,initialStateRaw,certDir,&result.Anchor,true);err!=nil{
    return result,fmt.Errorf("demo replay self-check: %w",err)
 }
 return result,nil
}
func ReadLimited(path string)([]byte,error){
 info,err:=os.Lstat(path);if err!=nil{return nil,err}
 if !info.Mode().IsRegular()||info.Size()<1||info.Size()>maxJournal{return nil,fail("unsafe or oversized verifier input")}
 return os.ReadFile(path)
}
