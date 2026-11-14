// Package attest verifies independently signed verifier-evidence receipts.
// COE-017 is an explicit policy-scoped Ed25519 experiment, NOT a theorem about
// Ed25519, an external human/host identity, or remote Ground admission.
package attest

import (
 "bytes"
 "crypto/ed25519"
 "crypto/sha256"
 "encoding/base64"
 "encoding/hex"
 "encoding/json"
 "errors"
 "fmt"
 "io"
 "os"
 "path/filepath"
 "regexp"
 "sort"
 "strings"
)

const (
 Domain = "IFS-COE017-VERIFIER-ATTESTATION-V1\n"
 signedSchema = "ifs.coe017.signed-verifier-receipt/v1"
 statementSchema = "ifs.coe017.verifier-statement/v1"
 policySchema = "ifs.coe017.receiver-policy/v1"
 stateSchema = "ifs.coe017.receiver-state/v1"
 evidenceSchema = "ifs.coe016.same-received-source-evidence/v1"
 certificateSchema = "in-formation-space.coe002.activation-cell-certificate/0.1"
 MaxFile = 8 << 20
 MaxSequence = 1 << 53 // Cross-language JSON interoperability; no floating-point ambiguity.
)

var ident = regexp.MustCompile(`^[a-z][a-z0-9-]{1,63}$`)
var model = regexp.MustCompile(`^[a-z][a-z0-9_]{1,63}$`)
var hex64 = regexp.MustCompile(`^[0-9a-f]{64}$`)

type Signature struct {
 KeyID string `json:"key_id"`
 Value string `json:"value"`
}
type Statement struct {
 Schema string `json:"schema"`
 Issuer string `json:"issuer"`
 Context string `json:"context"`
 Sequence uint64 `json:"sequence"`
 EvidenceSHA256 string `json:"evidence_sha256"`
 OriginalCertificateSHA256 map[string]string `json:"original_certificate_sha256"`
 NetworkSHA256 map[string]string `json:"network_sha256"`
 SemanticSHA256 map[string]string `json:"semantic_sha256"`
}
type Signed struct {
 Schema string `json:"schema"`
 Statement Statement `json:"statement"`
 Signatures []Signature `json:"signatures"`
}
type Key struct {
 ID string `json:"id"`
 Algorithm string `json:"algorithm"`
 PublicKey string `json:"public_key"`
 State string `json:"state"`
 ValidFrom uint64 `json:"valid_from"`
 ValidUntil uint64 `json:"valid_until"` // exclusive; zero means no end
}
type Policy struct {
 Schema string `json:"schema"`
 Mode string `json:"mode"`
 Issuer string `json:"issuer"`
 Context string `json:"context"`
 MinimumSequence uint64 `json:"minimum_sequence"`
 Threshold int `json:"threshold"`
 Keys []Key `json:"keys"`
 ExpectedNetworkSHA256 map[string]string `json:"expected_network_sha256"`
}
type State struct {
 Schema string `json:"schema"`
 Issuer string `json:"issuer"`
 LastSequence uint64 `json:"last_sequence"`
 LastStatementSHA256 string `json:"last_statement_sha256"`
}
type Evidence struct {
 Schema string `json:"schema"`
 Status string `json:"status"`
 SourceCount int `json:"source_count"`
 OriginalCertificateSHA256 map[string]string `json:"original_certificate_sha256"`
 NetworkSHA256 map[string]string `json:"network_sha256"`
 SemanticSHA256 map[string]string `json:"semantic_sha256"`
 SignedAuthority string `json:"signed_authority"`
 SignedManifestVersion uint64 `json:"signed_manifest_version"`
 SignatureQuorum int `json:"signature_quorum"`
 SignedBy []string `json:"signed_by"`
 GroundAdmitted bool `json:"ground_admitted"`
 OriginAuthenticated bool `json:"origin_authenticated"`
 TrustScope string `json:"trust_scope"`
}
type Result struct {
 Schema string `json:"schema"`
 Status string `json:"status"`
 PolicyMode string `json:"policy_mode"`
 Issuer string `json:"issuer"`
 Sequence uint64 `json:"sequence"`
 StatementSHA256 string `json:"statement_sha256"`
 EvidenceSHA256 string `json:"evidence_sha256"`
 CertificateSHA256 map[string]string `json:"original_certificate_sha256"`
 VerifiedSigners []string `json:"verified_signers"`
 KeyPossessionVerified bool `json:"key_possession_verified"`
 RealWorldIdentityAuthenticated bool `json:"real_world_identity_authenticated"`
 GroundAdmitted bool `json:"ground_admitted"`
 TrustScope string `json:"trust_scope"`
}

func fail(msg string) error { return fmt.Errorf("COE-017 rejected: %s",msg) }
func validHash(s string) bool {return hex64.MatchString(s)}
func sum(raw []byte) string {d:=sha256.Sum256(raw);return hex.EncodeToString(d[:])}
func sortedKeys(m map[string]string) []string {
 names:=make([]string,0,len(m));for name:=range m{names=append(names,name)}
 sort.Strings(names);return names
}
func equalMap(a,b map[string]string) bool{
 if len(a)!=len(b){return false}
 for k,v:=range a{if b[k]!=v{return false}}
 return true
}

// Canonical is stable canonical JSON with sorted fields and exactly one LF.
// All wire inputs must round-trip byte-for-byte; duplicate JSON keys fail.
func Canonical(v any)([]byte,error){
 raw,e:=json.Marshal(v);if e!=nil{return nil,e}
 dec:=json.NewDecoder(bytes.NewReader(raw));dec.UseNumber()
 var obj any
 if e=dec.Decode(&obj);e!=nil{return nil,e}
 normalized,e:=json.Marshal(obj);if e!=nil{return nil,e}
 return append(normalized,'\n'),nil
}
func strict(raw []byte,out any)error{
 if len(raw)==0||len(raw)>MaxFile||raw[len(raw)-1]!='\n'{return fail("noncanonical JSON length or line ending")}
 var generic any
 dec:=json.NewDecoder(bytes.NewReader(raw));dec.UseNumber()
 if e:=dec.Decode(&generic);e!=nil{return fail("invalid JSON syntax")}
 var extra any
 if e:=dec.Decode(&extra);!errors.Is(e,io.EOF){return fail("extra JSON value")}
 norm,e:=Canonical(generic);if e!=nil||!bytes.Equal(raw,norm){return fail("noncanonical JSON, duplicate key or extra whitespace")}
 decoder:=json.NewDecoder(bytes.NewReader(raw));decoder.DisallowUnknownFields()
 if e:=decoder.Decode(out);e!=nil{return fail("unknown, invalid or missing typed JSON data")}
 return nil
}
func ParseEvidence(raw []byte)(Evidence,error){
 var e Evidence
 if err:=strict(raw,&e);err!=nil{return e,err}
 if e.Schema!=evidenceSchema||e.Status!="test-only-verified-evidence-convergence"||
    e.SourceCount==0||e.GroundAdmitted||e.OriginAuthenticated||
    e.SignedAuthority==""||e.SignedManifestVersion==0||e.SignatureQuorum<2||
    len(e.SignedBy)<e.SignatureQuorum||e.TrustScope=="" {
     return e,fail("invalid, unsupported or overly authoritative COE-016 evidence")
 }
 seen:=map[string]bool{}
 for _,s:=range e.SignedBy {if !ident.MatchString(s)||seen[s]{return e,fail("COE-016 signer list invalid")};seen[s]=true}
 if len(e.OriginalCertificateSHA256)!=e.SourceCount ||
    len(e.NetworkSHA256)!=e.SourceCount||len(e.SemanticSHA256)!=e.SourceCount{
    return e,fail("COE-016 source count mismatch")
 }
 for name,h:=range e.OriginalCertificateSHA256{
    if !model.MatchString(name)||!validHash(h)||!validHash(e.NetworkSHA256[name])||!validHash(e.SemanticSHA256[name]){
       return e,fail("COE-016 invalid source identities")
    }
 }
 return e,nil
}
func ParsePolicy(raw []byte)(Policy,error){
 var p Policy
 if err:=strict(raw,&p);err!=nil{return p,err}
 if p.Schema!=policySchema||(p.Mode!="test-only"&&p.Mode!="production")||
    !ident.MatchString(p.Issuer)||p.Context!="continuous-observation-equivalence"||
    p.MinimumSequence==0||p.MinimumSequence>MaxSequence||
    p.Threshold<2||p.Threshold>len(p.Keys)||
    len(p.ExpectedNetworkSHA256)==0||len(p.ExpectedNetworkSHA256)>128 {
    return p,fail("invalid receiver policy")
 }
 for name,h:=range p.ExpectedNetworkSHA256{if !model.MatchString(name)||!validHash(h){return p,fail("invalid receiver pin")}}
 ids:=map[string]bool{};pubs:=map[string]bool{};active:=0
 for _,k:=range p.Keys{
    if !ident.MatchString(k.ID)||ids[k.ID]||k.Algorithm!="ed25519"||
       (k.State!="active"&&k.State!="revoked")||k.ValidFrom==0||
       k.ValidFrom>MaxSequence||k.ValidUntil>MaxSequence||
       (k.ValidUntil!=0&&k.ValidUntil<=k.ValidFrom){
        return p,fail("invalid receiver signing-key policy")
    }
    ids[k.ID]=true
    b,err:=base64.StdEncoding.Strict().DecodeString(k.PublicKey)
    if err!=nil||len(b)!=ed25519.PublicKeySize{return p,fail("malformed trusted Ed25519 key")}
    canonical:=base64.StdEncoding.EncodeToString(b)
    if pubs[canonical]{return p,fail("duplicate trusted public keys bypass signing quorum")}
    pubs[canonical]=true
    if k.State=="active"{active++}
    if p.Mode=="production"&&isPublicDemoKey(b){return p,fail("public demonstration key used in production policy")}
 }
 if active<p.Threshold{return p,fail("not enough active keys to satisfy quorum")}
 return p,nil
}
func isPublicDemoKey(pub []byte)bool{
 for _,b:=range []byte{0x31,0x41,0x52,0x63,0x74,0x85}{
    seed:=bytes.Repeat([]byte{b},ed25519.SeedSize)
    demo:=ed25519.NewKeyFromSeed(seed).Public().(ed25519.PublicKey)
    if bytes.Equal(demo,pub){return true}
 }
 return false
}
func ParseState(raw []byte)(State,error){
 var s State
 if err:=strict(raw,&s);err!=nil{return s,err}
 if s.Schema!=stateSchema||!ident.MatchString(s.Issuer)||
    s.LastSequence>=MaxSequence||!validHash(s.LastStatementSHA256){
    return s,fail("invalid receiver replay state")
 }
 return s,nil
}
func Payload(statement Statement)([]byte,error){
 b,e:=Canonical(statement);if e!=nil{return nil,e}
 return append([]byte(Domain),b...),nil
}
func CreateStatement(evidenceBytes []byte,certDir,issuer string,sequence uint64)(Statement,error){
 e,err:=ParseEvidence(evidenceBytes);if err!=nil{return Statement{},err}
 files,network,err:=CheckCertificates(certDir,e.OriginalCertificateSHA256,e.NetworkSHA256)
 if err!=nil{return Statement{},err}
 if !equalMap(network,e.NetworkSHA256){return Statement{},fail("source network mismatch")}
 if !ident.MatchString(issuer)||sequence==0||sequence>MaxSequence{return Statement{},fail("invalid verifier identity or sequence")}
 return Statement{Schema:statementSchema,Issuer:issuer,Context:"continuous-observation-equivalence",
    Sequence:sequence,EvidenceSHA256:sum(evidenceBytes),OriginalCertificateSHA256:files,
    NetworkSHA256:network,SemanticSHA256:e.SemanticSHA256},nil
}
func CheckCertificates(certDir string,expectedFiles,expectedNetwork map[string]string)(map[string]string,map[string]string,error){
 if len(expectedFiles)==0||len(expectedFiles)!=len(expectedNetwork){return nil,nil,fail("certificate manifest mismatch")}
 entries,err:=os.ReadDir(certDir);if err!=nil{return nil,nil,err}
 if len(entries)!=len(expectedFiles){return nil,nil,fail("unexpected received certificate count")}
 files:=map[string]string{};networks:=map[string]string{}
 for _,entry:=range entries{
    name:=strings.TrimSuffix(entry.Name(),".json")
    if entry.IsDir()||!strings.HasSuffix(entry.Name(),".json")||!model.MatchString(name){
       return nil,nil,fail("unexpected certificate entry")
    }
    expected,ok:=expectedFiles[name];if !ok||!validHash(expected){return nil,nil,fail("unrecognized certificate name")}
    path:=filepath.Join(certDir,entry.Name())
    info,e:=os.Lstat(path);if e!=nil{return nil,nil,e}
    if !info.Mode().IsRegular()||info.Size()<1||info.Size()>MaxFile{return nil,nil,fail("unsafe or oversized original certificate")}
    raw,e:=os.ReadFile(path);if e!=nil{return nil,nil,e}
    hash:=sum(raw);if hash!=expected{return nil,nil,fail("original certificate SHA-256 differs from attested receipt")}
    var doc map[string]json.RawMessage
    if e:=strict(raw,&doc);e!=nil{return nil,nil,fail("noncanonical original certificate")}
    if len(doc)!=6{return nil,nil,fail("unexpected certificate fields")}
    for _,field:=range []string{"schema","network","network_sha256","atomic_cells","semantic_atlas","semantic_sha256"}{
       if _,ok:=doc[field];!ok{return nil,nil,fail("missing required certificate field")}
    }
    var schema,claimed string
    if json.Unmarshal(doc["schema"],&schema)!=nil||schema!=certificateSchema||
       json.Unmarshal(doc["network_sha256"],&claimed)!=nil{return nil,nil,fail("invalid original certificate schema")}
    actual:=sum(bytes.TrimSpace(doc["network"]))
    if !validHash(claimed)||actual!=claimed||actual!=expectedNetwork[name]{
       return nil,nil,fail("receiver source bytes disagree with network policy")
    }
    files[name]=hash;networks[name]=actual
 }
 if len(files)!=len(expectedFiles){return nil,nil,fail("incomplete source set")}
 return files,networks,nil
}
func Verify(signedRaw,evidenceRaw,policyRaw,stateRaw []byte,certDir string,allowDemo bool)(Result,State,error){
 var zero Result;var empty State
 policy,err:=ParsePolicy(policyRaw);if err!=nil{return zero,empty,err}
 if policy.Mode=="test-only"&&!allowDemo{return zero,empty,fail("public demonstration verifier keys are not production identity")}
 state,err:=ParseState(stateRaw);if err!=nil{return zero,empty,err}
 if state.Issuer!=policy.Issuer{return zero,empty,fail("receiver state issuer mismatch")}
 e,err:=ParseEvidence(evidenceRaw);if err!=nil{return zero,empty,err}
 if !equalMap(e.NetworkSHA256,policy.ExpectedNetworkSHA256){return zero,empty,fail("COE-016 sources not pinned by receiver")}
 var signed Signed
 if err:=strict(signedRaw,&signed);err!=nil{return zero,empty,err}
 st:=signed.Statement
 if signed.Schema!=signedSchema||st.Schema!=statementSchema||
    st.Issuer!=policy.Issuer||st.Context!=policy.Context||
    st.Sequence<policy.MinimumSequence||st.Sequence<=state.LastSequence||
    st.Sequence>MaxSequence{return zero,empty,fail("wrong issuer, context or stale/replayed sequence")}
 if !validHash(st.EvidenceSHA256)||st.EvidenceSHA256!=sum(evidenceRaw)||
    !equalMap(st.OriginalCertificateSHA256,e.OriginalCertificateSHA256)||
    !equalMap(st.NetworkSHA256,e.NetworkSHA256)||
    !equalMap(st.SemanticSHA256,e.SemanticSHA256){
    return zero,empty,fail("signed statement not bound to exact COE-016 evidence")
 }
 if len(signed.Signatures)<policy.Threshold||len(signed.Signatures)>len(policy.Keys){
    return zero,empty,fail("insufficient signature quorum")
 }
 trusted:=map[string]Key{}
 for _,k:=range policy.Keys{trusted[k.ID]=k}
 payload,err:=Payload(st);if err!=nil{return zero,empty,err}
 verified:=make([]string,0,len(signed.Signatures))
 for i,sig:=range signed.Signatures{
    if !ident.MatchString(sig.KeyID)||
       (i>0&&signed.Signatures[i-1].KeyID>=sig.KeyID){
        return zero,empty,fail("unordered or repeated signing identity")
    }
    key,found:=trusted[sig.KeyID]
    if !found||key.State!="active"||st.Sequence<key.ValidFrom||
       (key.ValidUntil!=0&&st.Sequence>=key.ValidUntil){
       return zero,empty,fail("untrusted, revoked, future or retired verifier signer")
    }
    raw,e:=base64.StdEncoding.Strict().DecodeString(sig.Value)
    if e!=nil||len(raw)!=ed25519.SignatureSize{return zero,empty,fail("malformed Ed25519 signature")}
    pub,_:=base64.StdEncoding.Strict().DecodeString(key.PublicKey)
    if !ed25519.Verify(ed25519.PublicKey(pub),payload,raw){
       return zero,empty,fail("verifier signature mismatch")
    }
    verified=append(verified,sig.KeyID)
 }
 if len(verified)<policy.Threshold{return zero,empty,fail("unmet independent verifier signing quorum")}
 files,networks,err:=CheckCertificates(certDir,st.OriginalCertificateSHA256,policy.ExpectedNetworkSHA256)
 if err!=nil{return zero,empty,err}
 if !equalMap(files,st.OriginalCertificateSHA256)||!equalMap(networks,st.NetworkSHA256){
    return zero,empty,fail("attested originals differ from received bytes")
 }
 statementBytes,_:=Canonical(st)
 statementHash:=sum(statementBytes)
 next:=State{Schema:stateSchema,Issuer:policy.Issuer,LastSequence:st.Sequence,LastStatementSHA256:statementHash}
 result:=Result{
    Schema:"ifs.coe017.receiver-verification-result/v1",
    Status:"verified-policy-scoped-verifier-key-possession-and-evidence-bytes",
    PolicyMode:policy.Mode,Issuer:st.Issuer,Sequence:st.Sequence,
    StatementSHA256:statementHash,EvidenceSHA256:st.EvidenceSHA256,
    CertificateSHA256:files,VerifiedSigners:verified,
    KeyPossessionVerified:true,RealWorldIdentityAuthenticated:false,GroundAdmitted:false,
    TrustScope:"The receiver independently chooses signing-key policy and checks exact original file bytes. Demonstration keys are public; no human or host identity, trusted remote execution, or mathematical/Ground admission is established by these signatures.",
 }
 return result,next,nil
}

// SaveState provides a single-process/local-filesystem replay checkpoint.
// It does not provide a distributed CAS, exclusive locking, or independently
// authenticated durable consensus across competing hosts.
func SaveState(path string,next State)error{
 if path==""{return fail("missing receiver replay-state path")}
 if info,e:=os.Lstat(path);e==nil{
    if !info.Mode().IsRegular(){return fail("unsafe replay-state destination")}
 }else if !os.IsNotExist(e){return e}
 dir:=filepath.Dir(path)
 temp,e:=os.CreateTemp(dir,".coe017-state-*");if e!=nil{return e}
 defer os.Remove(temp.Name())
 if e=temp.Chmod(0600);e!=nil{temp.Close();return e}
 b,e:=Canonical(next);if e!=nil{temp.Close();return e}
 if _,e=temp.Write(b);e!=nil{temp.Close();return e}
 if e=temp.Sync();e!=nil{temp.Close();return e}
 if e=temp.Close();e!=nil{return e}
 return os.Rename(temp.Name(),path)
}
