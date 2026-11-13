package main

import (
 "bytes"
 "encoding/json"
 "os"
 "path/filepath"
 "testing"
)

func fixtures(t *testing.T) string {
 t.Helper()
 dir:=os.Getenv("COE_CERT_DIR")
 if dir==""{t.Skip("COE_CERT_DIR not configured")}
 return dir
}
func readFixture(t *testing.T,name string) []byte {
 t.Helper()
 data,err:=os.ReadFile(filepath.Join(fixtures(t),name+".json"))
 if err!=nil{t.Fatal(err)}
 return data
}
func modify(t *testing.T,raw []byte,change func(map[string]any)) []byte {
 t.Helper();var cert map[string]any
 if err:=json.Unmarshal(raw,&cert);err!=nil{t.Fatal(err)}
 change(cert)
 data,err:=json.Marshal(cert);if err!=nil{t.Fatal(err)}
 return append(data,'\n')
}
func TestPythonProducedCertificatesVerifiedExactly(t *testing.T){
 summary,err:=verifyBundle(fixtures(t));if err!=nil{t.Fatal(err)}
 if summary["status"]!="all_verified"||summary["claim_count"]!=5||summary["atomic_cells_checked"]!=12{
  t.Fatalf("bad result: %v",summary)
 }
}
func TestTamperedAffineRejected(t *testing.T){
 raw:=readFixture(t,"triangular_bump")
 bad:=modify(t,raw,func(c map[string]any){
  cells:=c["atomic_cells"].([]any);aff:=cells[1].(map[string]any)["affines"].([]any)
  aff[0].([]any)[0]="2"
 })
 if _,err:=verify(bad,expectedModels["triangular_bump"]);err==nil{t.Fatal("accepted altered affine law")}
}
func TestCanceledHiddenReLUCannotBeOmitted(t *testing.T){
 raw:=readFixture(t,"relu_identity")
 bad:=modify(t,raw,func(c map[string]any){c["atomic_cells"]=c["semantic_atlas"]})
 if _,err:=verify(bad,expectedModels["relu_identity"]);err==nil{t.Fatal("accepted hidden activation transition")}
}
func TestSourceMustMatchIndependentIdentity(t *testing.T){
 raw:=readFixture(t,"identity")
 if _,err:=verify(raw,expectedModels["zero"]);err==nil{t.Fatal("accepted wrong expected source")}
 bad:=modify(t,raw,func(c map[string]any){
  layers:=c["network"].(map[string]any)["layers"].([]any)
  layers[0].(map[string]any)["bias"].([]any)[0]="1"
 })
 if _,err:=verify(bad,expectedModels["identity"]);err==nil{t.Fatal("accepted source modification")}
}
func TestMalformedClaimAndExactBytesRejected(t *testing.T){
 raw:=readFixture(t,"identity")
 for _,v:=range [][]byte{bytes.TrimSuffix(raw,[]byte{'\n'}),append(bytes.Clone(raw),'\n'),append([]byte(" "),raw...)}{
  if _,err:=verify(v,expectedModels["identity"]);err==nil{t.Fatal("accepted noncanonical byte encoding")}
 }
 bad:=modify(t,raw,func(c map[string]any){
  c["semantic_sha256"]="0000000000000000000000000000000000000000000000000000000000000000"
 })
 if _,err:=verify(bad,expectedModels["identity"]);err==nil{t.Fatal("accepted false semantic digest")}
}
func TestMissingPositiveTailRejected(t *testing.T){
 raw:=readFixture(t,"triangular_bump")
 bad:=modify(t,raw,func(c map[string]any){
  cells:=c["atomic_cells"].([]any)
  c["atomic_cells"]=cells[:len(cells)-1]
 })
 if _,err:=verify(bad,expectedModels["triangular_bump"]);err==nil{t.Fatal("accepted incomplete cover")}
}
