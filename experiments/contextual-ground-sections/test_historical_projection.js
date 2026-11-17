"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const crypto=require("node:crypto");
const {future,yParity,sortedJSON,digest}=require("./verify_historical_projection.js");
test("GCI-003 far horizon equals an independently derived 1-step orbit",()=>{
  const h=1000000000000137;
  assert.equal(h%8,1);
  for(let phase=0;phase<8;phase++){
    const one=(5*phase+1)%8;
    assert.equal(future(phase,h),one);
    assert.equal(yParity(phase),phase%2);
  }
});
test("phase-blind threshold x parity fibers each select two of eight states",()=>{
  for(const threshold of [0,1])for(const bit of [0,1]){
    const possibilities=Array.from({length:8},(_,x)=>x)
      .filter(x=>Number(x>=4)===threshold)
      .filter(x=>x%2===bit);
    assert.equal(possibilities.length,2);
    assert.deepEqual([...new Set(possibilities.map(yParity))],[bit]);
  }
});
test("canonical digest matches Python sorted compact JSON convention for ASCII",()=>{
  const data={z:1,nested:{y:2,x:"value"},a:[{q:1,p:0},false]};
  const reference='{"a":[{"p":0,"q":1},false],"nested":{"x":"value","y":2},"z":1}';
  assert.equal(sortedJSON(data),reference);
  assert.equal(digest(data),crypto.createHash("sha256").update(reference).digest("hex"));
});
