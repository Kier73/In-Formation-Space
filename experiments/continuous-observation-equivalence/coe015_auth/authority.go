// Package authority validates Ed25519 source-manifest signatures under receiver-owned policy.
package authority

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
    manifestSchema = "ifs.coe015.source-manifest/v1"
    signedSchema = "ifs.coe015.signed-source-manifest/v1"
    policySchema = "ifs.coe015.trust-policy/v1"
    Domain = "IFS-COE015-ED25519-SOURCE-MANIFEST-V1\n"
    maxFile = 8 << 20
)

var keyIDPattern = regexp.MustCompile(`^[a-z][a-z0-9-]{1,63}$`)
var modelPattern = regexp.MustCompile(`^[a-z][a-z0-9_]{1,63}$`)
var digestPattern = regexp.MustCompile(`^[0-9a-f]{64}$`)

type Manifest struct {
    Schema string `json:"schema"`
    Authority string `json:"authority"`
    Version uint64 `json:"version"`
    Networks map[string]string `json:"networks"`
}
type Signature struct {
    KeyID string `json:"key_id"`
    Signature string `json:"signature"` // standard base64
}
type Signed struct {
    Schema string `json:"schema"`
    Manifest Manifest `json:"manifest"`
    Signatures []Signature `json:"signatures"`
}
type Key struct {
    ID string `json:"id"`
    Algorithm string `json:"algorithm"`
    PublicKey string `json:"public_key"`
    State string `json:"state"` // active or revoked
    ValidFrom uint64 `json:"valid_from"`
    ValidUntil uint64 `json:"valid_until"` // exclusive, 0 = indefinitely
}
type Policy struct {
    Schema string `json:"schema"`
    Mode string `json:"mode"` // test-only or production
    Authority string `json:"authority"`
    MinimumVersion uint64 `json:"minimum_version"`
    Threshold int `json:"threshold"`
    Keys []Key `json:"keys"`
    ExpectedNetworks map[string]string `json:"expected_network_sha256"`
}
type Receipt struct {
    Schema string `json:"schema"`
    Status string `json:"status"`
    Authority string `json:"authority"`
    ManifestVersion uint64 `json:"manifest_version"`
    VerifiedSigners []string `json:"verified_signers"`
    Threshold int `json:"threshold"`
    NetworkHashes map[string]string `json:"network_hashes"`
    PolicyMode string `json:"policy_mode"`
    OriginAuthenticated bool `json:"origin_authenticated"`
    GroundAdmitted bool `json:"ground_admitted"`
    TrustScope string `json:"trust_scope"`
}
func reject(msg string) error { return fmt.Errorf("COE-015 rejected: %s", msg) }

// Canonical source manifests include a final LF. Canonicality avoids
// cross-parser disagreements over duplicate keys, JSON escapes and spacing.
func Canonical(v any) ([]byte,error) {
    b,e:=json.Marshal(v)
    if e!=nil{return nil,e}
    return append(b,'\n'),nil
}
func parseCanonical(raw []byte, output any) error {
    if len(raw)==0 || len(raw)>maxFile || raw[len(raw)-1]!='\n' {return reject("noncanonical size or trailing linefeed")}
    dec:=json.NewDecoder(bytes.NewReader(raw))
    dec.DisallowUnknownFields()
    if e:=dec.Decode(output);e!=nil{return fmt.Errorf("manifest JSON: %w",e)}
    var trailing any
    if e:=dec.Decode(&trailing);!errors.Is(e,io.EOF){return reject("trailing JSON content")}
    canonical,e:=Canonical(output)
    if e!=nil{return e}
    if !bytes.Equal(raw,canonical){return reject("noncanonical JSON, duplicate key or unknown field")}
    return nil
}
func StrictSigned(raw []byte) (Signed,error) {
    var out Signed
    if e:=parseCanonical(raw,&out);e!=nil{return out,e}
    if out.Schema!=signedSchema || out.Manifest.Schema!=manifestSchema {
        return out,reject("unsupported signed-manifest schema")
    }
    return out,nil
}
func StrictPolicy(raw []byte) (Policy,error) {
    var p Policy
    dec:=json.NewDecoder(bytes.NewReader(raw))
    dec.DisallowUnknownFields()
    if e:=dec.Decode(&p);e!=nil{return p,e}
    var extra any
    if e:=dec.Decode(&extra);!errors.Is(e,io.EOF){return p,reject("policy trailing content")}
    if p.Schema!=policySchema || (p.Mode!="test-only"&&p.Mode!="production") {
        return p,reject("unsupported policy schema or mode")
    }
    if p.Authority=="" || p.MinimumVersion==0 || p.Threshold<1 || len(p.Keys)==0 || p.Threshold>len(p.Keys) {
        return p,reject("invalid authority, version or threshold")
    }
    if len(p.ExpectedNetworks)==0 || len(p.ExpectedNetworks)>128 {
        return p,reject("invalid source set")
    }
    for name,h:=range p.ExpectedNetworks{
        if !modelPattern.MatchString(name)||!digestPattern.MatchString(h){return p,reject("invalid expected source record")}
    }
    seen:=make(map[string]bool)
    for _,k:=range p.Keys{
        if !keyIDPattern.MatchString(k.ID)||seen[k.ID]||k.Algorithm!="ed25519" || (k.State!="active"&&k.State!="revoked") ||k.ValidFrom==0 ||(k.ValidUntil!=0 && k.ValidUntil<=k.ValidFrom){
            return p,reject("invalid, duplicate or unsupported trusted key record")
        }
        seen[k.ID]=true
        pk,e:=base64.StdEncoding.Strict().DecodeString(k.PublicKey)
        if e!=nil||len(pk)!=ed25519.PublicKeySize{return p,reject("invalid trusted Ed25519 public key")}
    }
    return p,nil
}
func Payload(m Manifest) ([]byte,error){
    b,e:=Canonical(m)
    if e!=nil{return nil,e}
    return append([]byte(Domain),b...),nil
}
func MatchNetworks(received, expected map[string]string) bool{
    if len(received)!=len(expected){return false}
    for name,expectedSHA:=range expected{
        got,ok:=received[name]
        if !ok||got!=expectedSHA||!digestPattern.MatchString(got){return false}
    }
    return true
}
func verifySignatures(s Signed,p Policy) ([]string,error){
    if s.Manifest.Authority!=p.Authority||s.Manifest.Version<p.MinimumVersion||s.Manifest.Version==0{
        return nil,reject("authority mismatch or rollback")
    }
    if !MatchNetworks(s.Manifest.Networks,p.ExpectedNetworks){return nil,reject("signed network set does not match receiver pins")}
    if len(s.Signatures)<p.Threshold ||len(s.Signatures)>len(p.Keys){return nil,reject("signature quorum")}
    trusted:=make(map[string]Key)
    for _,k:=range p.Keys{trusted[k.ID]=k}
    payload,e:=Payload(s.Manifest)
    if e!=nil{return nil,e}
    verified:=make([]string,0,len(s.Signatures))
    for i,item:=range s.Signatures{
        if !keyIDPattern.MatchString(item.KeyID){return nil,reject("invalid signing key id")}
        if i>0&&s.Signatures[i-1].KeyID>=item.KeyID{return nil,reject("duplicate or unordered signer")}
        key,ok:=trusted[item.KeyID]
        if !ok||key.State!="active"||s.Manifest.Version<key.ValidFrom||
           (key.ValidUntil!=0&&s.Manifest.Version>=key.ValidUntil){
            return nil,reject("unknown, revoked or inactive signing key")
        }
        signature,e:=base64.StdEncoding.Strict().DecodeString(item.Signature)
        if e!=nil||len(signature)!=ed25519.SignatureSize{return nil,reject("malformed signature")}
        public,_:=base64.StdEncoding.Strict().DecodeString(key.PublicKey)
        if !ed25519.Verify(ed25519.PublicKey(public),payload,signature){return nil,reject("Ed25519 signature mismatch")}
        verified=append(verified,item.KeyID)
    }
    if len(verified)<p.Threshold{return nil,reject("insufficient distinct authorized signers")}
    return verified,nil
}
func CertificateNetworks(directory string, names map[string]string) (map[string]string,error){
    entries,e:=os.ReadDir(directory)
    if e!=nil{return nil,e}
    if len(entries)!=len(names){return nil,reject("certificate file set mismatch")}
    results:=make(map[string]string,len(names))
    for _,entry:=range entries{
        if entry.IsDir()||!strings.HasSuffix(entry.Name(),".json"){return nil,reject("unexpected certificate file")}
        name:=strings.TrimSuffix(entry.Name(),".json")
        expected,ok:=names[name]
        if !ok{return nil,reject("unexpected model label")}
        info,e:=entry.Info()
        if e!=nil{return nil,e}
        if info.Size()<1||info.Size()>maxFile{return nil,reject("certificate file size")}
        raw,e:=os.ReadFile(filepath.Join(directory,entry.Name()))
        if e!=nil{return nil,e}
        // Canonical COE-002 JSON, including exact nested original network bytes.
        var doc map[string]json.RawMessage
        if e:=json.Unmarshal(raw,&doc);e!=nil{return nil,reject("invalid certificate JSON")}
        if len(doc)!=6{return nil,reject("unexpected certificate fields")}
        for _,field:=range []string{"schema","atomic_cells","network","network_sha256","semantic_atlas","semantic_sha256"}{
            if _,ok:=doc[field];!ok{return nil,reject("missing certificate field")}
        }
        canon,e:=Canonical(doc)
        if e!=nil{return nil,e}
        if !bytes.Equal(raw,canon){return nil,reject("noncanonical certificate bytes")}
        var schema,claimed string
        if json.Unmarshal(doc["schema"],&schema)!=nil || schema!="in-formation-space.coe002.activation-cell-certificate/0.1"{
            return nil,reject("unsupported mathematical certificate")}
        if json.Unmarshal(doc["network_sha256"],&claimed)!=nil || !digestPattern.MatchString(claimed){return nil,reject("malformed certificate digest")}
        networkBytes:=bytes.TrimSpace(doc["network"])
        digest:=sha256.Sum256(networkBytes)
        actual:=hex.EncodeToString(digest[:])
        if actual!=expected||claimed!=actual {return nil,reject("actual network bytes differ from signed, pinned or claimed identity")}
        results[name]=actual
    }
    return results,nil
}
// Verify enforces a separately supplied receiver policy before checking
// signatures and the actual certificate bytes. No policy is read from Signed.
func Verify(signedBytes,policyBytes []byte,certificateDir string,allowTest bool)(Receipt,error){
    var receipt Receipt
    policy,e:=StrictPolicy(policyBytes)
    if e!=nil{return receipt,e}
    if policy.Mode=="test-only"&&!allowTest{return receipt,reject("demo keys are not production authority")}
    signed,e:=StrictSigned(signedBytes)
    if e!=nil{return receipt,e}
    signers,e:=verifySignatures(signed,policy)
    if e!=nil{return receipt,e}
    networks,e:=CertificateNetworks(certificateDir,policy.ExpectedNetworks)
    if e!=nil{return receipt,e}
    if !MatchNetworks(networks,signed.Manifest.Networks){return receipt,reject("signed source and physical certificates disagree")}
    sort.Strings(signers)
    // A production policy can be externally controlled. This receipt
    // attests the listed policy, not the real-world owner of its keys.
    receipt=Receipt{
        Schema:"ifs.coe015.source-authority-receipt/v1",
        Status:"verified-policy-scoped-signatures-and-network-bytes",
        Authority:policy.Authority,ManifestVersion:signed.Manifest.Version,
        VerifiedSigners:signers,Threshold:policy.Threshold,
        NetworkHashes:networks,PolicyMode:policy.Mode,
        OriginAuthenticated:false,GroundAdmitted:false,
        TrustScope:"Ed25519 verifier trust is limited to externally managed receiver policy; proof of human/host identity is not established",
    }
    return receipt,nil
}
