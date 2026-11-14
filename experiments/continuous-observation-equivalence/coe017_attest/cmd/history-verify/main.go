// COE-018 independent receiver; no certificate producer or history signer import.
package main

import (
 "flag"
 "fmt"
 "os"
 history "coe017_attest/history"
)

func fatal(err error){fmt.Fprintln(os.Stderr,err);os.Exit(1)}
func main(){
 journal:=flag.String("journal","","untrusted governance journal")
 signed:=flag.String("signed","","original signed COE-017 verifier receipt")
 evidence:=flag.String("evidence","","original COE-016 convergence receipt")
 policy:=flag.String("policy","","RECEIVER-owned genesis public keys and source pins")
 state:=flag.String("state","","RECEIVER-owned initial replay state")
 certs:=flag.String("certs","","actual original certificate files")
 anchor:=flag.String("expected-anchor","","optional INDEPENDENTLY preserved anchor, never trust producer anchor as external")
 output:=flag.String("output","","independent verified report")
 allowDemo:=flag.Bool("allow-demo",false,"allow PUBLIC DEMONSTRATION verifier keys")
 flag.Parse()
 if *journal==""||*signed==""||*evidence==""||*policy==""||*state==""||*certs==""||*output==""{
    fmt.Fprintln(os.Stderr,"-journal -signed -evidence -policy -state -certs -output are required")
    os.Exit(2)
 }
 paths:=[]string{*journal,*signed,*evidence,*policy,*state}
 inputs:=make([][]byte,len(paths))
 for i,p:=range paths{
    b,e:=history.ReadLimited(p);if e!=nil{fatal(e)};inputs[i]=b
 }
 var expected *history.Anchor
 if *anchor!=""{
    raw,e:=history.ReadLimited(*anchor);if e!=nil{fatal(e)}
    parsed,e:=history.ParseAnchor(raw);if e!=nil{fatal(e)}
    expected=&parsed
 }
 receipt,e:=history.Replay(inputs[0],inputs[1],inputs[2],inputs[3],inputs[4],*certs,expected,*allowDemo)
 if e!=nil{fatal(e)}
 encoded,e:=history.Canonical(receipt);if e!=nil{fatal(e)}
 if e=os.WriteFile(*output,encoded,0600);e!=nil{fatal(e)}
 fmt.Printf("COE-018 independent replay accepted: %s, events=%d, anchor-comparison=%t\n",
 receipt.Status,receipt.JournalCount,receipt.ComparedExpectedAnchor)
}
