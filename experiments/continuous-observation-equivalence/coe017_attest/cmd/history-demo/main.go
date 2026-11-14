// Public test-only COE-018 journal producer. No production keys.
package main

import (
 "fmt"
 "os"
 "path/filepath"
 history "coe017_attest/history"
)

func fatal(err error){fmt.Fprintln(os.Stderr,err);os.Exit(1)}
func main(){
 if len(os.Args)!=7{
    fmt.Fprintln(os.Stderr,"usage: history-demo <signed-coe017.json> <coe016.json> <genesis-policy.json> <genesis-state.json> <certificates-dir> <output-dir>")
    os.Exit(2)
 }
 inputs:=make([][]byte,4)
 for i:=0;i<4;i++{
    b,e:=history.ReadLimited(os.Args[i+1]);if e!=nil{fatal(e)}
    inputs[i]=b
 }
 journal,e:=history.GenerateDemo(inputs[0],inputs[1],inputs[2],inputs[3],os.Args[5])
 if e!=nil{fatal(e)}
 raw,e:=history.Canonical(journal);if e!=nil{fatal(e)}
 witness,e:=history.Canonical(journal.Anchor);if e!=nil{fatal(e)}
 if e=os.MkdirAll(os.Args[6],0700);e!=nil{fatal(e)}
 if e=os.WriteFile(filepath.Join(os.Args[6],"untrusted-governance-journal.json"),raw,0600);e!=nil{fatal(e)}
 if e=os.WriteFile(filepath.Join(os.Args[6],"producer-claimed-anchor.json"),witness,0600);e!=nil{fatal(e)}
 fmt.Println("COE-018 generated PUBLIC DEMO policy rotation/revocation journal; producer anchor is NOT independently authenticated")
}
