package authority

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

func private(seed byte) ed25519.PrivateKey {
    return ed25519.NewKeyFromSeed(bytes.Repeat([]byte{seed},32))
}
func pub(seed byte) string {
    return base64.StdEncoding.EncodeToString(private(seed).Public().(ed25519.PublicKey))
}
func signedFixture(m Manifest,signers ...struct{id string; seed byte}) Signed {
    payload,e:=Payload(m)
    if e!=nil{panic(e)}
    s:=Signed{Schema:signedSchema,Manifest:m}
    for _,item:=range signers{
        s.Signatures=append(s.Signatures,Signature{
            KeyID:item.id,Signature:base64.StdEncoding.EncodeToString(ed25519.Sign(private(item.seed),payload)),
        })
    }
    return s
}
type fixture struct {
    signed Signed
    policy Policy
    dir string
    network string
    digest string
}
func setup(t *testing.T) fixture {
    t.Helper()
    network:=`{"layers":[{"activation":"linear","bias":["0"],"weights":[["1"]]}]}`
    h:=sha256.Sum256([]byte(network))
    digest:=hex.EncodeToString(h[:])
    doc:=map[string]any{
        "schema":"in-formation-space.coe002.activation-cell-certificate/0.1",
        "network":json.RawMessage(network),
        "network_sha256":digest,
        "atomic_cells":[]any{},
        "semantic_atlas":[]any{},
        "semantic_sha256":strings.Repeat("0",64),
    }
    raw,e:=Canonical(doc)
    if e!=nil{t.Fatal(e)}
    dir:=t.TempDir()
    if e=os.WriteFile(filepath.Join(dir,"identity.json"),raw,0600);e!=nil{t.Fatal(e)}
    manifest:=Manifest{
        Schema:manifestSchema,Authority:"unit-fixture-not-a-real-owner",
        Version:3,Networks:map[string]string{"identity":digest},
    }
    signers:=[]struct{id string; seed byte}{{"demo-22",0x22},{"demo-33",0x33}}
    signed:=signedFixture(manifest,signers...)
    policy:=Policy{
        Schema:policySchema,Mode:"test-only",
        Authority:manifest.Authority,MinimumVersion:3,Threshold:2,
        Keys:[]Key{
            {ID:"demo-11",Algorithm:"ed25519",PublicKey:pub(0x11),
                State:"revoked",ValidFrom:1},
            {ID:"demo-22",Algorithm:"ed25519",PublicKey:pub(0x22),
                State:"active",ValidFrom:3},
            {ID:"demo-33",Algorithm:"ed25519",PublicKey:pub(0x33),
                State:"active",ValidFrom:3},
        },
        ExpectedNetworks:map[string]string{"identity":digest},
    }
    return fixture{signed:signed,policy:policy,dir:dir,network:network,digest:digest}
}
func runTest(t *testing.T,f fixture,allowDemo bool) (Receipt,error){
    t.Helper()
    body,e:=Canonical(f.signed)
    if e!=nil{t.Fatal(e)}
    policy,e:=json.Marshal(f.policy)
    if e!=nil{t.Fatal(e)}
    return Verify(body,policy,f.dir,allowDemo)
}
func clone(f fixture) fixture{
    c:=f
    b,_:=json.Marshal(f.signed)
    _=json.Unmarshal(b,&c.signed)
    b,_=json.Marshal(f.policy)
    _=json.Unmarshal(b,&c.policy)
    return c
}
func TestAuthorizedTwoOfTwo(t *testing.T){
    f:=setup(t)
    receipt,e:=runTest(t,f,true)
    if e!=nil{t.Fatal(e)}
    if receipt.Threshold!=2||receipt.PolicyMode!="test-only"||
       receipt.OriginAuthenticated||receipt.GroundAdmitted||
       receipt.NetworkHashes["identity"]!=f.digest||
       len(receipt.VerifiedSigners)!=2||
       receipt.VerifiedSigners[0]!="demo-22"||
       receipt.VerifiedSigners[1]!="demo-33"{
        t.Fatalf("unexpected signed source authorization receipt: %+v",receipt)
    }
    if _,e:=runTest(t,f,false);e==nil{t.Fatal("demo key incorrectly trusted in production")}
}
func TestAdversarialSignatures(t *testing.T){
    tests:=[]struct{name string;mutate func(*fixture)}{
        {"insufficient-quorum",func(f *fixture){f.signed.Signatures=f.signed.Signatures[:1]}},
        {"duplicate-signer",func(f *fixture){f.signed.Signatures[1]=f.signed.Signatures[0]}},
        {"revoked-key",func(f *fixture){
            f.signed.Signatures[0]=signedFixture(f.signed.Manifest,struct{id string; seed byte}{"demo-11",0x11}).Signatures[0]}},
        {"untrusted-key",func(f *fixture){f.signed.Signatures[0].KeyID="demo-44"}},
        {"bad-signature",func(f *fixture){f.signed.Signatures[0].Signature=base64.StdEncoding.EncodeToString(make([]byte,64))}},
        {"bad-signature-length",func(f *fixture){f.signed.Signatures[0].Signature="AQ=="}},
        {"wrong-signed-model",func(f *fixture){f.signed.Manifest.Networks["identity"]=strings.Repeat("a",64)}},
        {"wrong-authority",func(f *fixture){f.signed.Manifest.Authority="another-issuer"}},
        {"wrong-version",func(f *fixture){f.signed.Manifest.Version=2}},
        {"not-yet-valid",func(f *fixture){f.policy.Keys[1].ValidFrom=4}},
        {"expired-key",func(f *fixture){f.policy.Keys[1].ValidUntil=3;f.policy.Keys[1].ValidFrom=1}},
        {"revoked-after-signing",func(f *fixture){f.policy.Keys[1].State="revoked"}},
        {"changed-public-key",func(f *fixture){f.policy.Keys[1].PublicKey=pub(0x44)}},
        {"policy-replaces-hash",func(f *fixture){f.policy.ExpectedNetworks["identity"]=strings.Repeat("a",64)}},
        {"higher-threshold",func(f *fixture){f.policy.Threshold=3}},
        {"duplicate-trusted-key",func(f *fixture){f.policy.Keys[2].ID="demo-22"}},
        {"duplicate-public-key-distinct-ids",func(f *fixture){f.policy.Keys[2].PublicKey=pub(0x22)}},
    }
    for _,tc:=range tests {
        t.Run(tc.name,func(t *testing.T){
            f:=clone(setup(t))
            tc.mutate(&f)
            if _,e:=runTest(t,f,true);e==nil{t.Fatal("accepted invalid or unauthorized signature/policy")}
        })
    }
}
func TestRotationAndRollback(t *testing.T) {
    f:=setup(t)
    original:=f.signed
    f.policy.MinimumVersion=4
    if _,e:=runTest(t,f,true);e==nil{t.Fatal("old signed epoch replayed after policy revision")}
    // Rotate signer set: retire demo-33, admit a distinct new demo-44 key
    // ONLY from version 4, and require a fresh 2-of-2 authorization.
    f.policy.Keys[2].State="revoked"
    f.policy.Keys=append(f.policy.Keys,Key{
        ID:"demo-44",Algorithm:"ed25519",PublicKey:pub(0x44),
        State:"active",ValidFrom:4,
    })
    f.signed.Manifest.Version=4
    f.signed=signedFixture(f.signed.Manifest,
        struct{id string; seed byte}{"demo-22",0x22},
        struct{id string; seed byte}{"demo-44",0x44})
    if receipt,e:=runTest(t,f,true);e!=nil{
        t.Fatalf("authorized two-signer key rotation rejected: %v",e)
    }else if receipt.VerifiedSigners[1]!="demo-44"{
        t.Fatalf("new rotated signer absent from verified receipt: %+v",receipt)
    }
    // Previously signed artifacts cannot be replayed under the new policy.
    f.signed=original
    if _,e:=runTest(t,f,true);e==nil{t.Fatal("old signed manifest replayed after rotation")}
    // The retired signer is prohibited even on a newly signed version 4.
    f.signed.Manifest.Version=4
    f.signed=signedFixture(f.signed.Manifest,
        struct{id string; seed byte}{"demo-22",0x22},
        struct{id string; seed byte}{"demo-33",0x33})
    if _,e:=runTest(t,f,true);e==nil{t.Fatal("retired signer authorized a new manifest")}
    // A new key is not valid prior to its declared activation version.
    f.policy.MinimumVersion=3
    f.signed.Manifest.Version=3
    f.signed=signedFixture(f.signed.Manifest,
        struct{id string; seed byte}{"demo-22",0x22},
        struct{id string; seed byte}{"demo-44",0x44})
    if _,e:=runTest(t,f,true);e==nil{t.Fatal("future rotation key accepted before activation")}
}
func TestCertificateAndManifestTamper(t *testing.T){
    f:=setup(t)
    path:=filepath.Join(f.dir,"identity.json")
    original,e:=os.ReadFile(path)
    if e!=nil{t.Fatal(e)}
    for _,tc:=range []struct{name string;raw []byte}{
        {"different-numeric-network",bytes.Replace(original,[]byte(`"weights":[["1"]]`),[]byte(`"weights":[["2"]]`),1)},
        {"forged-network-digest",bytes.Replace(original,[]byte(f.digest),[]byte(strings.Repeat("0",64)),1)},
        {"noncanonical-whitespace",append([]byte{' '},original...)},
        {"duplicate-source-field",bytes.Replace(original,[]byte(`"network_sha256":`),
            []byte(`"network_sha256":"deadbeef","network_sha256":`),1)},
        {"unsupported-schema",bytes.Replace(original,[]byte("activation-cell-certificate/0.1"),
            []byte("activation-cell-certificate/0.9"),1)},
    } {
        t.Run(tc.name,func(t *testing.T){
            if bytes.Equal(original,tc.raw){t.Fatal("fixture mutation was inert")}
            if e:=os.WriteFile(path,tc.raw,0600);e!=nil{t.Fatal(e)}
            defer os.WriteFile(path,original,0600)
            if _,e:=runTest(t,f,true);e==nil{t.Fatal("accepted modified original certificate bytes")}
        })
    }
    if e:=os.WriteFile(filepath.Join(f.dir,"unexpected.json"),original,0600);e!=nil{t.Fatal(e)}
    if _,e:=runTest(t,f,true);e==nil{t.Fatal("accepted unapproved extra certificate file")}
}
func TestNoncanonicalSignedManifest(t *testing.T){
    f:=setup(t)
    policy,_:=json.Marshal(f.policy)
    signed,_:=Canonical(f.signed)
    for _,raw:=range [][]byte{
        signed[:len(signed)-1],
        append(append([]byte{},signed...), '\n'),
        append([]byte{' '},signed...),
        bytes.Replace(signed,[]byte(`"schema":`),[]byte(`"schema":"spoof","schema":`),1),
        bytes.Replace(signed,[]byte(`"version":3`),[]byte(`"version":3,"extra":false`),1),
    }{
        if _,e:=Verify(raw,policy,f.dir,true);e==nil{t.Fatal("accepted noncanonical signed manifest")}
    }
}
