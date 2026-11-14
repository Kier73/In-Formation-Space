// This command is a test fixture producer. Its deterministic signing secrets
// are PUBLIC DEMONSTRATION VALUES. NEVER trust them for production authority.
package main

import (
    "bytes"
    "crypto/ed25519"
    "encoding/base64"
    "encoding/json"
    "fmt"
    "os"
    "path/filepath"
    "sort"

    authority "coe015_auth"
)
const demoAuthority = "ifs.coe015.demo-only.not-an-external-identity"

func run(certDir, destination string) error {
    entries,e:=os.ReadDir(certDir)
    if e!=nil{return e}
    sources:=map[string]string{}
    for _,entry:=range entries {
        if entry.IsDir()||filepath.Ext(entry.Name())!=".json" {return fmt.Errorf("unexpected fixture %s",entry.Name())}
        raw,e:=os.ReadFile(filepath.Join(certDir,entry.Name()))
        if e!=nil{return e}
        var cert struct { NetworkSHA string `json:"network_sha256"` }
        if e:=json.Unmarshal(raw,&cert);e!=nil{return e}
        sources[entry.Name()[:len(entry.Name())-5]]=cert.NetworkSHA
    }
    if len(sources)!=5{return fmt.Errorf("expected five demo models, got %d",len(sources))}
    manifest:=authority.Manifest{
        Schema:"ifs.coe015.source-manifest/v1",Authority:demoAuthority,
        Version:3, Networks:sources,
    }
    msg,e:=authority.Payload(manifest)
    if e!=nil{return e}
    signed:=authority.Signed{
        Schema:"ifs.coe015.signed-source-manifest/v1", Manifest:manifest,
    }
    for _,pair:=range []struct{id string; seed byte}{{"demo-22",0x22},{"demo-33",0x33}}{
        // Public, deterministic testing-only key material, NEVER a real key.
        priv:=ed25519.NewKeyFromSeed(bytes.Repeat([]byte{pair.seed},32))
        signed.Signatures=append(signed.Signatures,authority.Signature{
            KeyID:pair.id,
            Signature:base64.StdEncoding.EncodeToString(ed25519.Sign(priv,msg)),
        })
    }
    sort.Slice(signed.Signatures,func(i,j int)bool{return signed.Signatures[i].KeyID<signed.Signatures[j].KeyID})
    data,e:=authority.Canonical(signed)
    if e!=nil{return e}
    if e:=os.MkdirAll(destination,0700);e!=nil{return e}
    return os.WriteFile(filepath.Join(destination,"signed-manifest.json"),data,0600)
}
func main(){
    if len(os.Args)!=3{fmt.Fprintln(os.Stderr,"usage: demo <received-certificates> <out-dir>");os.Exit(2)}
    if e:=run(os.Args[1],os.Args[2]);e!=nil{fmt.Fprintln(os.Stderr,e);os.Exit(1)}
    fmt.Println("Generated PUBLIC test-only 2-of-2 Ed25519 authority claims; NOT external authorization")
}
