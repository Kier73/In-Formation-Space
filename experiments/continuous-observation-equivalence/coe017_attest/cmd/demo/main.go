// Public, deterministic demonstration signer. Seeds are KNOWN, NONSECRET and
// cannot be treated as real verifier credentials or a production trust anchor.
package main
import (
 "bytes"
 "crypto/ed25519"
 "encoding/base64"
 "fmt"
 "os"
 "path/filepath"
 attest "coe017_attest"
)
func main(){
 if len(os.Args)!=4 {fmt.Fprintln(os.Stderr,"usage: demo <coe016-receipt.json> <cert-dir> <output-dir>");os.Exit(2)}
 raw,e:=os.ReadFile(os.Args[1]);if e!=nil{fatal(e)}
 statement,e:=attest.CreateStatement(raw,os.Args[2],"ifs-coe017-demo-verifier",3)
 if e!=nil{fatal(e)}
 payload,e:=attest.Payload(statement);if e!=nil{fatal(e)}
 signed:=attest.Signed{Schema:"ifs.coe017.signed-verifier-receipt/v1",Statement:statement}
 for _,seed:=range []struct{id string;seed byte}{{"demo-vr-41",0x41},{"demo-vr-52",0x52}} {
  priv:=ed25519.NewKeyFromSeed(bytes.Repeat([]byte{seed.seed},ed25519.SeedSize))
  sig:=ed25519.Sign(priv,payload)
  signed.Signatures=append(signed.Signatures,attest.Signature{KeyID:seed.id,Value:base64.StdEncoding.EncodeToString(sig)})
 }
 out,e:=attest.Canonical(signed);if e!=nil{fatal(e)}
 if e=os.MkdirAll(os.Args[3],0700);e!=nil{fatal(e)}
 path:=filepath.Join(os.Args[3],"signed-verifier-receipt.json")
 if e=os.WriteFile(path,out,0600);e!=nil{fatal(e)}
 fmt.Println("COE-017 wrote PUBLIC TEST-ONLY verifier signature claims:",path)
}
func fatal(e error){fmt.Fprintln(os.Stderr,e);os.Exit(1)}
