// A separate receiver checks policy-scoped verifier signatures and actual
// original bytes, then advances its LOCAL replay state on successful admission.
package main
import (
 "flag"
 "fmt"
 "os"
 attest "coe017_attest"
)
func main(){
 policy:=flag.String("policy","","receiver-owned public key policy")
 signed:=flag.String("signed","","untrusted signed verifier receipt")
 evidence:=flag.String("evidence","","untrusted COE-016 evidence receipt")
 certs:=flag.String("certs","","original received certificate files")
 state:=flag.String("state","","receiver-owned monotonic replay state")
 report:=flag.String("report","","output receipt path")
 allowDemo:=flag.Bool("allow-demo",false,"explicitly allow PUBLIC test-only signer keys")
 flag.Parse()
 if *policy==""||*signed==""||*evidence==""||*certs==""||*state==""||*report==""{
    fmt.Fprintln(os.Stderr,"-policy -signed -evidence -certs -state and -report required");os.Exit(2)
 }
 policyRaw,e:=os.ReadFile(*policy);if e!=nil{fatal(e)}
 signedRaw,e:=os.ReadFile(*signed);if e!=nil{fatal(e)}
 evidenceRaw,e:=os.ReadFile(*evidence);if e!=nil{fatal(e)}
 stateRaw,e:=os.ReadFile(*state);if e!=nil{fatal(e)}
 result,next,e:=attest.Verify(signedRaw,evidenceRaw,policyRaw,stateRaw,*certs,*allowDemo)
 if e!=nil{fatal(e)}
 if e=attest.SaveState(*state,next);e!=nil{fatal(e)}
 out,e:=attest.Canonical(result);if e!=nil{fatal(e)}
 if e=os.WriteFile(*report,out,0600);e!=nil{fatal(e)}
 fmt.Println("COE-017: verified receiver-owned verifier signing keys and exact received source bytes")
}
func fatal(e error){fmt.Fprintln(os.Stderr,e);os.Exit(1)}
