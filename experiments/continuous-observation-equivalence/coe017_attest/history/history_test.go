package history

import (
 "bytes"
 "crypto/ed25519"
 "encoding/base64"
 "encoding/json"
 "os"
 "path/filepath"
 "strings"
 "testing"

 attest "coe017_attest"
)

type fixture struct {
 journal Journal
 signed []byte
 evidence []byte
 policy []byte
 state []byte
 certDir string
}
func testingKey(seed byte)string{
 p:=ed25519.NewKeyFromSeed(bytes.Repeat([]byte{seed},ed25519.SeedSize))
 return base64.StdEncoding.EncodeToString(p.Public().(ed25519.PublicKey))
}
func buildFixture(t *testing.T)fixture{
 t.Helper()
 certDir:=t.TempDir()
 network:=map[string]any{"layers":[]any{map[string]any{
  "activation":"linear","bias":[]string{"0"},"weights":[][]string{{"1"}},
 }}}
 networkBytes,e:=json.Marshal(network);if e!=nil{t.Fatal(e)}
 networkHash:=sha(networkBytes)
 semanticHash:=sha([]byte("synthetic-math-result"))
 cert:=map[string]any{
  "schema":"in-formation-space.coe002.activation-cell-certificate/0.1",
  "network":network,"network_sha256":networkHash,
  "atomic_cells":[]any{},"semantic_atlas":[]any{},"semantic_sha256":semanticHash,
 }
 original,e:=Canonical(cert);if e!=nil{t.Fatal(e)}
 if e=os.WriteFile(filepath.Join(certDir,"identity.json"),original,0600);e!=nil{t.Fatal(e)}
 evidence:=attest.Evidence{
  Schema:"ifs.coe016.same-received-source-evidence/v1",
  Status:"test-only-verified-evidence-convergence",
  SourceCount:1,OriginalCertificateSHA256:map[string]string{"identity":sha(original)},
  NetworkSHA256:map[string]string{"identity":networkHash},
  SemanticSHA256:map[string]string{"identity":semanticHash},
  SignedAuthority:"test-only-coe015",SignedManifestVersion:3,
  SignatureQuorum:2,SignedBy:[]string{"demo-22","demo-33"},
  GroundAdmitted:false,OriginAuthenticated:false,
  TrustScope:"Synthetic test-only fixture; not an actual Lean kernel replay",
 }
 evidenceBytes,e:=Canonical(evidence);if e!=nil{t.Fatal(e)}
 policy:=attest.Policy{
  Schema:"ifs.coe017.receiver-policy/v1",Mode:"test-only",
  Issuer:"ifs-coe017-demo-verifier",Context:"continuous-observation-equivalence",
  MinimumSequence:3,Threshold:2,Keys:[]attest.Key{
   {ID:"demo-vr-31",Algorithm:"ed25519",PublicKey:testingKey(0x63),State:"revoked",ValidFrom:1},
   {ID:"demo-vr-41",Algorithm:"ed25519",PublicKey:testingKey(0x41),State:"active",ValidFrom:3},
   {ID:"demo-vr-52",Algorithm:"ed25519",PublicKey:testingKey(0x52),State:"active",ValidFrom:3},
  },
  ExpectedNetworkSHA256:map[string]string{"identity":networkHash},
 }
 policyBytes,e:=Canonical(policy);if e!=nil{t.Fatal(e)}
 state:=attest.State{Schema:"ifs.coe017.receiver-state/v1",Issuer:policy.Issuer,
  LastSequence:2,LastStatementSHA256:strings.Repeat("0",64)}
 stateBytes,e:=Canonical(state);if e!=nil{t.Fatal(e)}
 statement,e:=attest.CreateStatement(evidenceBytes,certDir,policy.Issuer,3);if e!=nil{t.Fatal(e)}
 message,e:=attest.Payload(statement);if e!=nil{t.Fatal(e)}
 signed:=attest.Signed{Schema:"ifs.coe017.signed-verifier-receipt/v1",Statement:statement}
 for _,seed:=range []byte{0x41,0x52}{
  private:=ed25519.NewKeyFromSeed(bytes.Repeat([]byte{seed},ed25519.SeedSize))
  signed.Signatures=append(signed.Signatures,attest.Signature{
   KeyID:"demo-vr-"+strings.ToLower(hexByte(seed)),
   Value:base64.StdEncoding.EncodeToString(ed25519.Sign(private,message)),
  })
 }
 signedBytes,e:=Canonical(signed);if e!=nil{t.Fatal(e)}
 journal,e:=GenerateDemo(signedBytes,evidenceBytes,policyBytes,stateBytes,certDir)
 if e!=nil{t.Fatalf("cannot generate fixture: %v",e)}
 return fixture{journal:journal,signed:signedBytes,evidence:evidenceBytes,
   policy:policyBytes,state:stateBytes,certDir:certDir}
}
func hexByte(b byte)string{
 const hex="0123456789abcdef"
 return string([]byte{hex[b>>4],hex[b&15]})
}
func (f fixture) verify(t *testing.T,witness *Anchor,allowDemo bool)(Result,error){
 t.Helper()
 raw,e:=Canonical(f.journal);if e!=nil{t.Fatal(e)}
 return Replay(raw,f.signed,f.evidence,f.policy,f.state,f.certDir,witness,allowDemo)
}
func cloneFixture(t *testing.T,f fixture)fixture{
 t.Helper()
 copy:=f
 raw,e:=Canonical(f.journal);if e!=nil{t.Fatal(e)}
 // Never unmarshal into a shallow-copied slice: that overwrites the original
 // fixture's shared backing array and can contaminate later subtests.
 var independent Journal
 if e=json.Unmarshal(raw,&independent);e!=nil{t.Fatal(e)}
 copy.journal=independent
 copy.evidence=append([]byte{},f.evidence...)
 copy.signed=append([]byte{},f.signed...)
 copy.state=append([]byte{},f.state...)
 copy.policy=append([]byte{},f.policy...)
 return copy
}
func rejected(t *testing.T,f fixture,witness *Anchor){
 t.Helper()
 if _,e:=f.verify(t,witness,true);e==nil{t.Fatal("invalid governance history accepted")}
}
func TestTwoIndependentReplaysAndExplicitlyBoundedClaims(t *testing.T){
 f:=buildFixture(t)
 a,e:=f.verify(t,&f.journal.Anchor,true);if e!=nil{t.Fatal(e)}
 b,e:=f.verify(t,&f.journal.Anchor,true);if e!=nil{t.Fatal(e)}
 if a.JournalHead!=b.JournalHead||a.FinalPolicySHA256!=b.FinalPolicySHA256||a.Status!=b.Status{
  t.Fatal("independent receiver reconstruction diverged")
 }
 if a.Status!="revoked-under-policy"||!a.ReceiptRevoked||
    !a.ComparedExpectedAnchor||a.ExternalAnchorAuthenticated||
    a.RealWorldIdentityAuthenticated||a.GroundAdmitted||
    a.JournalCount!=3||a.FinalSequence!=5||
    len(a.ActiveSigners)!=2||a.ActiveSigners[0]!="demo-vr-41"||
    a.ActiveSigners[1]!="demo-vr-74"{
    t.Fatalf("unexpected reconstructed authority: %+v",a)
 }
}
func TestDemoIdentityRejectedByDefault(t *testing.T){
 f:=buildFixture(t)
 if _,e:=f.verify(t,nil,false);e==nil{t.Fatal("public demo keys were accepted by default")}
}
func TestTruncationCannotBeDetectedWithoutSurvivingExternalCheckpoint(t *testing.T){
 f:=buildFixture(t)
 final:=f.journal.Anchor
 f.journal.Entries=f.journal.Entries[:2]
 penultimate,_:=Canonical(f.journal.Entries[1])
 f.journal.Anchor=Anchor{Schema:AnchorSchema,Count:2,Head:sha(penultimate)}
 local,e:=f.verify(t,nil,true)
 if e!=nil{t.Fatalf("legitimate historical prefix should replay without external witness: %v",e)}
 if local.Status!="active-under-policy"||local.ComparedExpectedAnchor{
    t.Fatal("unanchored prefix incorrectly advertised revocation or external checkpoint")
 }
 rejected(t,f,&final)
}
func TestNegativeMutations(t *testing.T){
 base:=buildFixture(t)
 cases:=[]struct{name string;mutate func(*fixture)}{
  {"journal-truncation",func(f *fixture){f.journal.Entries=f.journal.Entries[:2]}},
  {"reordered",func(f *fixture){f.journal.Entries[0],f.journal.Entries[1]=f.journal.Entries[1],f.journal.Entries[0]}},
  {"missing-middle",func(f *fixture){f.journal.Entries=append(f.journal.Entries[:1],f.journal.Entries[2:]...)}},
  {"wrong-prior",func(f *fixture){f.journal.Entries[1].Decision.Previous=strings.Repeat("f",64)}},
  {"wrong-head",func(f *fixture){f.journal.Anchor.Head=strings.Repeat("f",64)}},
  {"duplicate-signer",func(f *fixture){f.journal.Entries[0].OldSignatures[1]=f.journal.Entries[0].OldSignatures[0]}},
  {"missing-governance-quorum",func(f *fixture){f.journal.Entries[1].OldSignatures=f.journal.Entries[1].OldSignatures[:1]}},
  {"revoked-governance-signer",func(f *fixture){
    decision:=f.journal.Entries[0].Decision
    revoked:=DemoSign(decision,GovernanceDomain,0x63)[0]
    revoked.KeyID="demo-vr-31" // Historic receiver policy binds this ID to seed 0x63.
    stillActive:=DemoSign(decision,GovernanceDomain,0x52)[0]
    f.journal.Entries[0].OldSignatures=[]attest.Signature{revoked,stillActive}
  }},
  {"forged-signature",func(f *fixture){f.journal.Entries[2].OldSignatures[0].Value=base64.StdEncoding.EncodeToString(make([]byte,64))}},
  {"new-key-quorum-missing",func(f *fixture){f.journal.Entries[1].NewSignatures=f.journal.Entries[1].NewSignatures[:1]}},
  {"reused-old-new-proof",func(f *fixture){f.journal.Entries[1].NewSignatures=f.journal.Entries[1].OldSignatures}},
  {"new-key-not-yet-active",func(f *fixture){f.journal.Entries[1].Decision.NextPolicy.Keys[3].ValidFrom=6}},
  {"new-policy-changes-network-pin",func(f *fixture){f.journal.Entries[1].Decision.NextPolicy.ExpectedNetworkSHA256["identity"]=strings.Repeat("0",64)}},
  {"unrevoked-retired-signer",func(f *fixture){f.journal.Entries[2].OldSignatures=DemoSign(f.journal.Entries[2].Decision,GovernanceDomain,0x41,0x52)}},
  {"resurrect-revoked-key",func(f *fixture){f.journal.Entries[1].Decision.NextPolicy.Keys[0].State="active"}},
  {"replace-existing-public-key",func(f *fixture){f.journal.Entries[1].Decision.NextPolicy.Keys[1].PublicKey=testingKey(0x85)}},
  {"lower-governance-quorum",func(f *fixture){f.journal.Entries[1].Decision.NextPolicy.Threshold=1}},
  {"unscoped-revocation",func(f *fixture){f.journal.Entries[2].Decision.Reason="unknown-reason"}},
  {"wrong-evidence-hash",func(f *fixture){f.journal.Entries[0].Decision.EvidenceSHA256=strings.Repeat("f",64)}},
  {"wrong-signed-envelope",func(f *fixture){f.journal.Entries[0].Decision.EnvelopeSHA256=strings.Repeat("f",64)}},
  {"unexpected-reaccept",func(f *fixture){f.journal.Entries[2].Decision.Kind="accept"}},
  {"wrong-sequence",func(f *fixture){f.journal.Entries[2].Decision.Sequence=4}},
  {"unexpected-kind",func(f *fixture){f.journal.Entries[2].Decision.Kind="grant-ground"}},
 }
 for _,tc:=range cases{
  t.Run(tc.name,func(t *testing.T){
   f:=cloneFixture(t,base);tc.mutate(&f);rejected(t,f,&base.journal.Anchor)
  })
 }
}
func TestOriginalCertificateAndAttestationSubstitution(t *testing.T){
 f:=buildFixture(t)
 original:=filepath.Join(f.certDir,"identity.json")
 raw,_:=os.ReadFile(original)
 altered:=bytes.Replace(raw,[]byte(`"weights":[["1"]]`),[]byte(`"weights":[["2"]]`),1)
 if bytes.Equal(raw,altered){t.Fatal("test mutation inert")}
 if e:=os.WriteFile(original,altered,0600);e!=nil{t.Fatal(e)}
 rejected(t,f,&f.journal.Anchor)
 f=buildFixture(t)
 f.signed=bytes.Replace(f.signed,[]byte("demo-vr-41"),[]byte("demo-vr-31"),1)
 rejected(t,f,&f.journal.Anchor)
 f=buildFixture(t)
 f.evidence=bytes.Replace(f.evidence,[]byte(`"ground_admitted":false`),[]byte(`"ground_admitted":true`),1)
 rejected(t,f,&f.journal.Anchor)
}
func TestStrictJSONDuplicateAndUnknownKeys(t *testing.T){
 f:=buildFixture(t)
 raw,_:=Canonical(f.journal)
 for _,sample:=range [][]byte{
  bytes.Replace(raw,[]byte(`"schema":`),[]byte(`"schema":"false","schema":`),1),
  bytes.Replace(raw,[]byte(`"entries":`),[]byte(`"unexpected":true,"entries":`),1),
  append([]byte(" "),raw...),
  raw[:len(raw)-1],
 }{
  if _,err:=ParseJournal(sample);err==nil{t.Fatal("accepted noncanonical governance JSON")}
 }
}
func TestWitnessAnchorConflict(t *testing.T){
 f:=buildFixture(t)
 wrong:=f.journal.Anchor
 wrong.Head=strings.Repeat("a",64)
 rejected(t,f,&wrong)
 wrong=f.journal.Anchor;wrong.Count=2
 rejected(t,f,&wrong)
}


func TestTwoValidForksRequireWitnessAnchor(t *testing.T){
 // Both histories have legitimate signatures from demo keys. One revokes;
 // the other rotates again. Their common valid prefix is not sufficient to
 // decide which branch a remote witness saw most recently.
 original:=buildFixture(t)
 fork:=cloneFixture(t,original)
 lastPolicy:=*fork.journal.Entries[1].Decision.NextPolicy
 next:=lastPolicy
 next.MinimumSequence=5
 next.Keys=append([]attest.Key{},lastPolicy.Keys...)
 next.Keys=append(next.Keys,attest.Key{
  ID:"demo-vr-85",Algorithm:"ed25519",PublicKey:testingKey(0x85),
  State:"active",ValidFrom:5,
 })
 priorBytes,e:=Canonical(fork.journal.Entries[1]);if e!=nil{t.Fatal(e)}
 d:=fork.journal.Entries[2].Decision
 d.Kind="rotate"
 d.Sequence=5
 d.Previous=sha(priorBytes)
 d.NextPolicy=&next
 d.Reason=""
 alternative:=Entry{
  Decision:d,
  OldSignatures:DemoSign(d,GovernanceDomain,0x41,0x74),
  NewSignatures:DemoSign(d,NewKeyProofDomain,0x41,0x85),
 }
 fork.journal.Entries[2]=alternative
 encoded,e:=Canonical(alternative);if e!=nil{t.Fatal(e)}
 fork.journal.Anchor=Anchor{Schema:AnchorSchema,Count:3,Head:sha(encoded)}
 revoked,e:=original.verify(t,nil,true);if e!=nil{t.Fatal(e)}
 rotated,e:=fork.verify(t,nil,true);if e!=nil{t.Fatal(e)}
 if revoked.Status!="revoked-under-policy"||rotated.Status!="active-under-policy"||
    revoked.JournalHead==rotated.JournalHead{
    t.Fatalf("valid fork must make unanchored receiver decisions diverge: revoked=%+v rotated=%+v",revoked,rotated)
 }
 rejected(t,fork,&original.journal.Anchor)
 rejected(t,original,&fork.journal.Anchor)
}

func TestProductionPoliciesRejectAllPublicTestKeys(t *testing.T){
 f:=buildFixture(t)
 for _,seed:=range []byte{0x31,0x41,0x52,0x63,0x74,0x85}{
  t.Run(hexByte(seed),func(t *testing.T){
   var policy attest.Policy
   if e:=json.Unmarshal(f.policy,&policy);e!=nil{t.Fatal(e)}
   policy.Mode="production"
   policy.Keys[1].PublicKey=testingKey(seed)
   raw,e:=Canonical(policy);if e!=nil{t.Fatal(e)}
   if _,e=attest.ParsePolicy(raw);e==nil{
    t.Fatal("known public test-only seed incorrectly admitted as production trust key")
   }
  })
 }
}
