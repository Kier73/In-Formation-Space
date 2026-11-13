// COE-003: independent Go standard-library checker for exact rational ReLU
// activation-cell certificates produced by COE-002's Python constructor.
// No Python algorithm, runtime, dependency or helper is invoked here.
package main

import (
 "bytes"
 "crypto/sha256"
 "encoding/hex"
 "encoding/json"
 "errors"
 "fmt"
 "math/big"
 "os"
 "path/filepath"
 "regexp"
 "sort"
 "strings"
)

const schema = "in-formation-space.coe002.activation-cell-certificate/0.1"
var rationalPattern = regexp.MustCompile("^(?:0|-?[1-9][0-9]*)(?:/[1-9][0-9]*)?$")
var digestPattern = regexp.MustCompile("^[0-9a-f]{64}$")
var zero = new(big.Rat)
var one = big.NewRat(1, 1)

var expectedModels = map[string]string{
 "identity": "4cdb6f67907dd5286cd9ef7b073761fe876ec61090ed6db92dd6b676fcdad09d",
 "relu_identity": "df076e896b0b2c760a1f3fd7731f33a2377cd850458a6bb5518bc80e36fb8508",
 "zero": "ee6c630e6497be8396be01184a555c6c4287d0d56fedab76e5b0f3bc089c632f",
 "triangular_bump": "19d42b0402acac39e255920842e73a28a3e364e96211dc623f8c717ed1285571",
 "rescaled_bump": "f6c4916fa52ca096ebd7de65f0cd9eb722fd581be06591b94fe52332fd717eb1",
}

type affine struct{ m, b *big.Rat }
type layer struct{ activation string; weights [][]*big.Rat; bias []*big.Rat }
type cell struct{ left, right *big.Rat; output []affine }

func fail(format string, args ...any) error { return fmt.Errorf(format,args...) }
func getMap(value any, keys ...string)(map[string]any,error){
 v,ok:=value.(map[string]any);if !ok || len(v)!=len(keys){return nil,errors.New("invalid object field count")}
 for _,key:=range keys{if _,found:=v[key];!found{return nil,fail("missing field %s",key)}}
 return v,nil
}
func getArray(value any)([]any,error){
 v,ok:=value.([]any);if !ok{return nil,errors.New("expected array")};return v,nil
}
func getString(value any)(string,error){
 v,ok:=value.(string);if !ok{return "",errors.New("expected string")};return v,nil
}
func parseRat(value any)(*big.Rat,error){
 s,err:=getString(value)
 if err!=nil||len(s)>128||!rationalPattern.MatchString(s){return nil,errors.New("noncanonical rational")}
 x,ok:=new(big.Rat).SetString(s)
 if !ok||x.RatString()!=s{return nil,errors.New("unreduced rational")}
 return x,nil
}
func parseEndpoint(value any,side string)(*big.Rat,error){
 s,err:=getString(value);if err!=nil{return nil,err}
 if (side=="left"&&s=="-inf")||(side=="right"&&s=="+inf"){return nil,nil}
 return parseRat(s)
}
func textOf(x *big.Rat)string{return x.RatString()}
func digest(data []byte)string{sum:=sha256.Sum256(data);return hex.EncodeToString(sum[:])}
func canonical(value any)([]byte,error){return json.Marshal(value)}

func parseLayer(value any,expectedWidth int)(layer,error){
 obj,err:=getMap(value,"activation","weights","bias");if err!=nil{return layer{},err}
 activation,err:=getString(obj["activation"])
 if err!=nil||(activation!="relu"&&activation!="linear"){return layer{},errors.New("unsupported activation")}
 rawWeights,err:=getArray(obj["weights"]);if err!=nil{return layer{},err}
 rawBias,err:=getArray(obj["bias"]);if err!=nil{return layer{},err}
 if len(rawWeights)==0||len(rawWeights)>128||len(rawWeights)!=len(rawBias){return layer{},errors.New("matrix dimension mismatch")}
 weights:=make([][]*big.Rat,len(rawWeights));biases:=make([]*big.Rat,len(rawBias))
 for i,rawRow:=range rawWeights{
  row,err:=getArray(rawRow);if err!=nil||len(row)!=expectedWidth{return layer{},errors.New("invalid matrix width")}
  weights[i]=make([]*big.Rat,len(row))
  for j,element:=range row{
   r,err:=parseRat(element);if err!=nil{return layer{},err};weights[i][j]=r
  }
  bias,err:=parseRat(rawBias[i]);if err!=nil{return layer{},err};biases[i]=bias
 }
 return layer{activation,weights,biases},nil
}
func parseCell(value any,outputWidth int)(cell,error){
 obj,err:=getMap(value,"left","right","affines");if err!=nil{return cell{},err}
 left,err:=parseEndpoint(obj["left"],"left");if err!=nil{return cell{},err}
 right,err:=parseEndpoint(obj["right"],"right");if err!=nil{return cell{},err}
 terms,err:=getArray(obj["affines"]);if err!=nil||len(terms)!=outputWidth{return cell{},errors.New("output vector width mismatch")}
 output:=make([]affine,len(terms))
 for i,v:=range terms{
  pair,err:=getArray(v);if err!=nil||len(pair)!=2{return cell{},errors.New("invalid affine pair")}
  m,err:=parseRat(pair[0]);if err!=nil{return cell{},err}
  b,err:=parseRat(pair[1]);if err!=nil{return cell{},err}
  output[i]=affine{m,b}
 }
 return cell{left,right,output},nil
}
func eqRat(a,b *big.Rat)bool{return a.Cmp(b)==0}
func eqAffine(a,b affine)bool{return eqRat(a.m,b.m)&&eqRat(a.b,b.b)}
func eqOutput(a,b []affine)bool{
 if len(a)!=len(b){return false}
 for i:=range a{if !eqAffine(a[i],b[i]){return false}}
 return true
}
func at(a affine,x *big.Rat)*big.Rat{return new(big.Rat).Add(new(big.Rat).Mul(a.m,x),a.b)}
func intervalPoint(c cell)*big.Rat{
 if c.left==nil&&c.right==nil{return new(big.Rat)}
 if c.left==nil{return new(big.Rat).Sub(c.right,one)}
 if c.right==nil{return new(big.Rat).Add(c.left,one)}
 return new(big.Rat).Quo(new(big.Rat).Add(c.left,c.right),big.NewRat(2,1))
}
func rootInside(root *big.Rat,c cell)bool{
 return (c.left==nil||c.left.Cmp(root)<0)&&(c.right==nil||root.Cmp(c.right)<0)
}
func verifyCell(c cell,layers []layer)error{
 location:=intervalPoint(c);active:=[]affine{{one,zero}}
 for _,l:=range layers{
  pre:=make([]affine,len(l.bias))
  for i,row:=range l.weights{
   m:=new(big.Rat);b:=new(big.Rat).Set(l.bias[i])
   for j,w:=range row{
    m.Add(m,new(big.Rat).Mul(w,active[j].m))
    b.Add(b,new(big.Rat).Mul(w,active[j].b))
   }
   pre[i]=affine{m,b}
  }
  if l.activation=="linear"{active=pre;continue}
  next:=make([]affine,len(pre))
  for i,term:=range pre{
   if term.m.Sign()!=0{
    root:=new(big.Rat).Quo(new(big.Rat).Neg(term.b),term.m)
    if rootInside(root,c){return errors.New("undisclosed ReLU sign transition")}
   }
   if at(term,location).Sign()>0{next[i]=term}else{next[i]=affine{zero,zero}}
  }
  active=next
 }
 if !eqOutput(active,c.output){return errors.New("incorrect cell affine output")}
 return nil
}
func cellJSON(c cell)map[string]any{
 l:="-inf";r:="+inf"
 if c.left!=nil{l=textOf(c.left)}
 if c.right!=nil{r=textOf(c.right)}
 outputs:=make([]any,len(c.output))
 for i,term:=range c.output{outputs[i]=[]string{textOf(term.m),textOf(term.b)}}
 return map[string]any{"left":l,"right":r,"affines":outputs}
}
func verify(raw []byte,expected string)(map[string]any,error){
 if len(raw)==0||len(raw)>8*1024*1024{return nil,errors.New("certificate byte limit")}
 var value any
 if err:=json.Unmarshal(raw,&value);err!=nil{return nil,err}
 rebuilt,err:=canonical(value);if err!=nil{return nil,err}
 if !bytes.Equal(raw,append(rebuilt,'\n')){return nil,errors.New("noncanonical JSON / duplicate keys / line endings")}
 cert,err:=getMap(value,"schema","network","network_sha256","atomic_cells","semantic_atlas","semantic_sha256")
 if err!=nil{return nil,err}
 if cert["schema"]!=schema{return nil,errors.New("unexpected certificate schema")}
 network,err:=getMap(cert["network"],"layers");if err!=nil{return nil,err}
 netBytes,err:=canonical(network);if err!=nil{return nil,err}
 netHash:=digest(netBytes)
 declaredNet,err:=getString(cert["network_sha256"])
 if err!=nil||!digestPattern.MatchString(declaredNet)||declaredNet!=netHash{return nil,errors.New("certificate network digest mismatch")}
 if expected!=""&&expected!=netHash{return nil,errors.New("independent expected network mismatch")}
 rawLayers,err:=getArray(network["layers"]);if err!=nil{return nil,err}
 if len(rawLayers)==0||len(rawLayers)>64{return nil,errors.New("layer count")}
 layers:=make([]layer,len(rawLayers));width:=1;opsPerCell:=0
 for i,item:=range rawLayers{
  l,err:=parseLayer(item,width);if err!=nil{return nil,err}
  layers[i]=l;opsPerCell+=len(l.weights)*width;width=len(l.weights)
 }
 rawCells,err:=getArray(cert["atomic_cells"]);if err!=nil{return nil,err}
 if len(rawCells)==0||len(rawCells)>4096||len(rawCells)*opsPerCell>3_000_000{return nil,errors.New("cell or work budget")}
 cells:=make([]cell,len(rawCells))
 for i,rawCell:=range rawCells{
  c,err:=parseCell(rawCell,width);if err!=nil{return nil,err}
  if c.left!=nil&&c.right!=nil&&c.left.Cmp(c.right)>=0{return nil,errors.New("empty or inverted cell")}
  if i==0&&c.left!=nil{return nil,errors.New("missing negative infinite tail")}
  if i>0&&(cells[i-1].right==nil||c.left==nil||!eqRat(cells[i-1].right,c.left)){return nil,errors.New("cell gap or overlap")}
  if err:=verifyCell(c,layers);err!=nil{return nil,fmt.Errorf("cell %d: %w",i,err)}
  if i>0{
   join:=c.left
   for j:=range c.output{
    if !eqRat(at(cells[i-1].output[j],join),at(c.output[j],join)){return nil,errors.New("discontinuous output at breakpoint")}
   }
  }
  cells[i]=c
 }
 if cells[len(cells)-1].right!=nil{return nil,errors.New("missing positive infinite tail")}
 reduced:=make([]cell,0,len(cells))
 for _,c:=range cells{
  if len(reduced)>0&&eqOutput(reduced[len(reduced)-1].output,c.output){
   reduced[len(reduced)-1].right=c.right
  }else{reduced=append(reduced,c)}
 }
 normalized:=make([]any,len(reduced))
 for i,c:=range reduced{normalized[i]=cellJSON(c)}
 canonAtlas,err:=canonical(normalized);if err!=nil{return nil,err}
 declaredAtlas,err:=canonical(cert["semantic_atlas"]);if err!=nil{return nil,err}
 if !bytes.Equal(canonAtlas,declaredAtlas){return nil,errors.New("wrong normalized semantic atlas")}
 semanticHash:=digest(canonAtlas)
 declaredSemantic,err:=getString(cert["semantic_sha256"])
 if err!=nil||!digestPattern.MatchString(declaredSemantic)||declaredSemantic!=semanticHash{return nil,errors.New("semantic digest mismatch")}
 return map[string]any{"status":"verified","network_sha256":netHash,"semantic_sha256":semanticHash,
  "atomic_cells_checked":len(cells),"semantic_regions":len(reduced),"certificate_sha256":digest(raw)},nil
}
func verifyBundle(path string)(map[string]any,error){
 entries,err:=os.ReadDir(path);if err!=nil{return nil,err}
 if len(entries)!=len(expectedModels){return nil,errors.New("unexpected certificate count")}
 names:=make([]string,0,len(expectedModels))
 for name:=range expectedModels{names=append(names,name)}
 sort.Strings(names)
 reports:=make(map[string]any,len(names));semantic:=make(map[string]string,len(names));total:=0
 for _,name:=range names{
  filename:=name+".json";raw,err:=os.ReadFile(filepath.Join(path,filename));if err!=nil{return nil,err}
  result,err:=verify(raw,expectedModels[name]);if err!=nil{return nil,fmt.Errorf("%s: %w",name,err)}
  reports[name]=result;semantic[name]=result["semantic_sha256"].(string);total+=result["atomic_cells_checked"].(int)
 }
 if semantic["identity"]!=semantic["relu_identity"]||semantic["triangular_bump"]!=semantic["rescaled_bump"]||semantic["zero"]==semantic["triangular_bump"]{
  return nil,errors.New("expected observational relationships not established")
 }
 for _,entry:=range entries{
  filename:=entry.Name()
  if entry.IsDir()||!strings.HasSuffix(filename,".json"){return nil,errors.New("unexpected non-JSON artifact")}
  name:=strings.TrimSuffix(filename,".json")
  if _,ok:=expectedModels[name];!ok{return nil,errors.New("unexpected certificate file")}
 }
 return map[string]any{"schema":"in-formation-space.coe003.go-independent-report/0.1",
  "status":"all_verified","claim_count":len(reports),
  "atomic_cells_checked":total,"language":"Go","claims":reports},nil
}
func main(){
 if len(os.Args)!=2{fmt.Fprintln(os.Stderr,"usage: go run go_checker/main.go <certificate-directory>");os.Exit(2)}
 result,err:=verifyBundle(os.Args[1])
 if err!=nil{fmt.Fprintln(os.Stderr,"certificate rejected:",err);os.Exit(1)}
 bytes,err:=json.MarshalIndent(result,"","  ");if err!=nil{panic(err)}
 fmt.Println(string(bytes))
}
