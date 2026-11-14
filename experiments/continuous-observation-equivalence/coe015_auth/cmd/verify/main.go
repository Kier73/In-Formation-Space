// Verification CLI: policy path is supplied by the RECEIVER separately
// from the signed untrusted manifest. Demo policy requires explicit consent.
package main
import (
    "flag"
    "fmt"
    "os"
    authority "coe015_auth"
)
func main(){
    policyPath:=flag.String("policy","","receiver-controlled trust policy JSON")
    signedPath:=flag.String("signed","","untrusted signed manifest JSON")
    certDir:=flag.String("certs","","original received certificate directory")
    output:=flag.String("report","","independent receipt JSON path")
    allowDemo:=flag.Bool("allow-demo",false,"EXPLICIT opt-in to PUBLIC test keys, never production")
    flag.Parse()
    if *policyPath==""||*signedPath==""||*certDir==""{fmt.Fprintln(os.Stderr,"-policy -signed and -certs are required");os.Exit(2)}
    policy,e:=os.ReadFile(*policyPath)
    if e!=nil{fmt.Fprintln(os.Stderr,e);os.Exit(1)}
    signed,e:=os.ReadFile(*signedPath)
    if e!=nil{fmt.Fprintln(os.Stderr,e);os.Exit(1)}
    receipt,e:=authority.Verify(signed,policy,*certDir,*allowDemo)
    if e!=nil{fmt.Fprintln(os.Stderr,e);os.Exit(1)}
    bytes,e:=authority.Canonical(receipt)
    if e!=nil{fmt.Fprintln(os.Stderr,e);os.Exit(1)}
    if *output!=""{
        if e:=os.WriteFile(*output,bytes,0600);e!=nil{fmt.Fprintln(os.Stderr,e);os.Exit(1)}
    }else{fmt.Print(string(bytes))}
}
