package attest

import (
 "bytes"
 "crypto/ed25519"
 "crypto/sha256"
 "encoding/base64"
 "encoding/hex"
 "encoding/json"
 "os"
 "path/filepath"
 "strings"
 "testing"
)

func testPrivate(seed byte) ed25519.PrivateKey {
 return ed25519.NewKeyFromSeed(bytes.Repeat([]byte{seed},ed25519.SeedSize))
}
func testPublic(seed byte)string{return base64.StdEncoding.EncodeToString(testPrivate(seed).Public().(ed25519.PublicKey))}
type fixture struct {
 directory string
 evidence []byte
 signed Signed
 policy Policy
 state State
}
func fixtureFor(t *testing.T) fixture{
 t.Helper()
 dir:=t.TempDir()
 network:=map[string]any{"layers":[]any{map[string]any{
  "activation":"linear","weights":[][]string{{"1"}},"bias":[]string{"0"},
 }}}
 netRaw,e:=json.Marshal(network);if e!=nil{t.Fatal(e)}
 netHash:=sum(netRaw)
 semHash:=sum([]byte("synthetic-math-checker-fixture"))
 doc:=map[string]any{
  "schema":certificateSchema,"network":network,"network_sha256":netHash,
  "atomic_cells":[]any{},"semantic_atlas":[]any{},"semantic_sha256":semHash,
 }
 raw,e:=Canonical(doc);if e!=nil{t.Fatal(e)}
 if e=os.WriteFile(filepath.Join(dir,"identity.json"),raw,0600);e!=nil{t.Fatal(e)}
 evi:=Evidence{
  Schema:evidenceSchema,Status:"test-only-verified-evidence-convergence",
  SourceCount:1,OriginalCertificateSHA256:map[string]string{"identity":sum(raw)},
  NetworkSHA256:map[string]string{"identity":netHash},
  SemanticSHA256:map[string]string{"identity":semHash},
  SignedAuthority:"coe015-public-test-only",SignedManifestVersion:3,
  SignatureQuorum:2,SignedBy:[]string{"demo-22","demo-33"},
  GroundAdmitted:false,OriginAuthenticated:false,
  TrustScope:"synthetic fixture; no independent Lean proof for these test bytes",
 }
 evidence,e:=Canonical(evi);if e!=nil{t.Fatal(e)}
 statement,e:=CreateStatement(evidence,dir,"ifs-coe017-demo-verifier",3)
 if e!=nil{t.Fatal(e)}
 f:=fixture{directory:dir,evidence:evidence,
  signed:Signed{Schema:signedSchema,Statement:statement},
  policy:Policy{Schema:policySchema,Mode:"test-only",Issuer:statement.Issuer,
   Context:statement.Context,MinimumSequence:3,Threshold:2,
   Keys:[]Key{
    {ID:"demo-vr-31",Algorithm:"ed25519",PublicKey:testPublic(0x31),State:"revoked",ValidFrom:1},
    {ID:"demo-vr-41",Algorithm:"ed25519",PublicKey:testPublic(0x41),State:"active",ValidFrom:3},
    {ID:"demo-vr-52",Algorithm:"ed25519",PublicKey:testPublic(0x52),State:"active",ValidFrom:3},
   },
   ExpectedNetworkSHA256:map[string]string{"identity":netHash},
  },
  state:State{Schema:stateSchema,Issuer:statement.Issuer,LastSequence:2,
    LastStatementSHA256:strings.Repeat("0",64)},
 }
 f.sign(0x41,0x52)
 return f
}
func (f *fixture)sign(seeds ...byte){
 payload,e:=Payload(f.signed.Statement);if e!=nil{panic(e)}
 f.signed.Signatures=nil
 for _,seed:=range seeds{
  f.signed.Signatures=append(f.signed.Signatures,Signature{
    KeyID:"demo-vr-"+hex.EncodeToString([]byte{seed}),
    Value:base64.StdEncoding.EncodeToString(ed25519.Sign(testPrivate(seed),payload)),
  })
 }
}
func testVerify(t *testing.T,f fixture,allow bool)(Result,State,error){
 t.Helper()
 signed,e:=Canonical(f.signed);if e!=nil{t.Fatal(e)}
 policy,e:=Canonical(f.policy);if e!=nil{t.Fatal(e)}
 state,e:=Canonical(f.state);if e!=nil{t.Fatal(e)}
 return Verify(signed,f.evidence,policy,state,f.directory,allow)
}
func testClone(f fixture)fixture{
 out:=f
 raw,_:=json.Marshal(f.policy);_ = json.Unmarshal(raw,&out.policy)
 raw,_=json.Marshal(f.signed);_=json.Unmarshal(raw,&out.signed)
 raw,_=json.Marshal(f.state);_=json.Unmarshal(raw,&out.state)
 out.evidence=append([]byte{},f.evidence...)
 return out
}
func expectReject(t *testing.T,f fixture){
 t.Helper()
 if _,_,err:=testVerify(t,f,true);err==nil{t.Fatal("accepted invalid verifier attestation")}
}
func TestTwoSignerReceiverScopedSuccess(t *testing.T){
 f:=fixtureFor(t)
 result,next,e:=testVerify(t,f,true)
 if e!=nil{t.Fatal(e)}
 if !result.KeyPossessionVerified||result.RealWorldIdentityAuthenticated||
    result.GroundAdmitted||result.PolicyMode!="test-only"||
    result.EvidenceSHA256!=sum(f.evidence)||len(result.VerifiedSigners)!=2||
    result.VerifiedSigners[0]!="demo-vr-41"||result.VerifiedSigners[1]!="demo-vr-52"{
    t.Fatalf("invalid claim or signer identity: %+v",result)
 }
 if next.LastSequence!=3||next.LastStatementSHA256!=result.StatementSHA256{
    t.Fatalf("invalid receiver state: %+v",next)
 }
 if _,_,e=testVerify(t,f,false);e==nil{t.Fatal("demo signing key accepted without explicit consent")}
}
func TestReplayAndRestart(t *testing.T){
 f:=fixtureFor(t)
 _,next,e:=testVerify(t,f,true);if e!=nil{t.Fatal(e)}
 statePath:=filepath.Join(t.TempDir(),"receiver-state.json")
 if e=SaveState(statePath,next);e!=nil{t.Fatal(e)}
 persisted,e:=os.ReadFile(statePath);if e!=nil{t.Fatal(e)}
 actual,e:=ParseState(persisted);if e!=nil{t.Fatal(e)}
 f.state=actual
 expectReject(t,f)
 // A previously valid receipt cannot be accepted twice after process restart.
 f.signed.Statement.Sequence=2
 f.sign(0x41,0x52)
 expectReject(t,f)
}
func TestAdversarialPolicyAndSignatureControls(t *testing.T){
 cases:=[]struct{name string;mutate func(*fixture)}{
  {"insufficient-quorum",func(f *fixture){f.signed.Signatures=f.signed.Signatures[:1]}},
  {"duplicate-signer",func(f *fixture){f.signed.Signatures[1]=f.signed.Signatures[0]}},
  {"forged-signature",func(f *fixture){f.signed.Signatures[0].Value=base64.StdEncoding.EncodeToString(make([]byte,64))}},
  {"wrong-issuer",func(f *fixture){f.signed.Statement.Issuer="someone-else";f.sign(0x41,0x52)}},
  {"wrong-context",func(f *fixture){f.signed.Statement.Context="unrelated";f.sign(0x41,0x52)}},
  {"stale-version",func(f *fixture){f.signed.Statement.Sequence=2;f.sign(0x41,0x52)}},
  {"revoked-signer",func(f *fixture){f.sign(0x31,0x52)}},
  {"unknown-signer",func(f *fixture){f.sign(0x41,0x74)}},
  {"future-key",func(f *fixture){f.policy.Keys[1].ValidFrom=4}},
  {"expired-key",func(f *fixture){f.policy.Keys[1].ValidUntil=3;f.policy.Keys[1].ValidFrom=2}},
  {"revoked-after-signing",func(f *fixture){f.policy.Keys[1].State="revoked"}},
  {"policy-substitutes-key",func(f *fixture){f.policy.Keys[1].PublicKey=testPublic(0x63)}},
  {"duplicate-public-key",func(f *fixture){f.policy.Keys[2].PublicKey=f.policy.Keys[1].PublicKey}},
  {"insufficient-active-policy",func(f *fixture){f.policy.Keys[2].State="revoked"}},
  {"downgraded-policy-epoch",func(f *fixture){f.policy.MinimumSequence=4}},
  {"policy-network-substitution",func(f *fixture){f.policy.ExpectedNetworkSHA256["identity"]=strings.Repeat("f",64)}},
  {"bad-signature-count",func(f *fixture){f.policy.Threshold=3}},
  {"mismatched-state-issuer",func(f *fixture){f.state.Issuer="other-issuer"}},
  {"production-demo-key",func(f *fixture){f.policy.Mode="production"}},
  {"attestation-evidence-hash",func(f *fixture){f.signed.Statement.EvidenceSHA256=strings.Repeat("0",64);f.sign(0x41,0x52)}},
  {"attestation-source-digest",func(f *fixture){f.signed.Statement.NetworkSHA256["identity"]=strings.Repeat("a",64);f.sign(0x41,0x52)}},
  {"attestation-semantic-digest",func(f *fixture){f.signed.Statement.SemanticSHA256["identity"]=strings.Repeat("b",64);f.sign(0x41,0x52)}},
 }
 for _,tc:=range cases{
  t.Run(tc.name,func(t *testing.T){f:=testClone(fixtureFor(t));tc.mutate(&f);expectReject(t,f)})
 }
}
func TestActualOriginalBytesAndEvidenceCannotBeSubstituted(t *testing.T){
 t.Run("original-file",func(t *testing.T){
  f:=fixtureFor(t)
  path:=filepath.Join(f.directory,"identity.json")
  raw,e:=os.ReadFile(path);if e!=nil{t.Fatal(e)}
  raw=bytes.Replace(raw,[]byte(`"weights":[["1"]]`),[]byte(`"weights":[["2"]]`),1)
  if e=os.WriteFile(path,raw,0600);e!=nil{t.Fatal(e)}
  expectReject(t,f)
 })
 t.Run("extra-file",func(t *testing.T){
  f:=fixtureFor(t)
  if e:=os.WriteFile(filepath.Join(f.directory,"extra.json"),[]byte("{}\n"),0600);e!=nil{t.Fatal(e)}
  expectReject(t,f)
 })
 t.Run("report-mutated",func(t *testing.T){
  f:=fixtureFor(t)
  f.evidence=bytes.Replace(f.evidence,[]byte("test-only-verified-evidence-convergence"),[]byte("all_verified"),1)
  expectReject(t,f)
 })
 t.Run("false-ground-admission",func(t *testing.T){
  f:=fixtureFor(t)
  f.evidence=bytes.Replace(f.evidence,[]byte(`"ground_admitted":false`),[]byte(`"ground_admitted":true`),1)
  expectReject(t,f)
 })
 t.Run("extra-signed-json-field",func(t *testing.T){
  f:=fixtureFor(t)
  signed,_:=Canonical(f.signed);policy,_:=Canonical(f.policy);state,_:=Canonical(f.state)
  altered:=bytes.Replace(signed,[]byte(`"schema":`),[]byte(`"extra":true,"schema":`),1)
  if _,_,e:=Verify(altered,f.evidence,policy,state,f.directory,true);e==nil{t.Fatal("accepted unknown signed field")}
 })
 t.Run("duplicate-signed-json-field",func(t *testing.T){
  f:=fixtureFor(t)
  signed,_:=Canonical(f.signed);policy,_:=Canonical(f.policy);state,_:=Canonical(f.state)
  altered:=bytes.Replace(signed,[]byte(`"schema":`),[]byte(`"schema":"forged","schema":`),1)
  if _,_,e:=Verify(altered,f.evidence,policy,state,f.directory,true);e==nil{t.Fatal("accepted duplicate signed field")}
 })
}
func TestKeyRotationAndVersionActivation(t *testing.T){
 f:=fixtureFor(t)
 _,state,e:=testVerify(t,f,true);if e!=nil{t.Fatal(e)}
 f.state=state
 // Policy holder separately retires 0x52 and admits new 0x63 from sequence 4.
 f.policy.MinimumSequence=4
 f.policy.Keys[2].State="revoked"
 f.policy.Keys=append(f.policy.Keys,Key{ID:"demo-vr-63",Algorithm:"ed25519",
    PublicKey:testPublic(0x63),State:"active",ValidFrom:4})
 f.signed.Statement.Sequence=4
 f.sign(0x41,0x63)
 result,next,e:=testVerify(t,f,true)
 if e!=nil{t.Fatalf("valid signed two-party rotation rejected: %v",e)}
 if next.LastSequence!=4||result.VerifiedSigners[1]!="demo-vr-63"{t.Fatal("rotation did not carry new signer")}
 // Retired identity must not be accepted at the new version, even when signed.
 f.sign(0x41,0x52);expectReject(t,f)
 // The new signing identity must not authorize an earlier version.
 f.policy.MinimumSequence=3
 f.state.LastSequence=2
 f.signed.Statement.Sequence=3
 f.sign(0x41,0x63)
 expectReject(t,f)
}
func TestStateAndUnsignedReceiptCannotHideProductionOrigin(t *testing.T){
 f:=fixtureFor(t)
 f.state.LastStatementSHA256="not-a-digest";expectReject(t,f)
 f=fixtureFor(t)
 var raw map[string]any
 if e:=json.Unmarshal(f.evidence,&raw);e!=nil{t.Fatal(e)}
 raw["origin_authenticated"]=true
 f.evidence,_=Canonical(raw)
 expectReject(t,f)
}
func TestKnownSHA256Reference(t *testing.T){
 v:=sha256.Sum256([]byte("abc"))
 if sum([]byte("abc"))!=hex.EncodeToString(v[:]){t.Fatal("digest mismatch")}
}
