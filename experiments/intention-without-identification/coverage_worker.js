"use strict";
// IWI-005 test-only OS subprocess: read a fixture model and signing key.
// No networking, E-CPU authority, physical sensors or live VGI Ground admission.
const fs=require("node:fs");
const crypto=require("node:crypto");
const coverage=require("./context_coverage.js");
if(require.main===module){
 if(process.argv.length!==4)throw Error("usage: node coverage_worker.js manifest.json key.pem");
 const manifest=JSON.parse(fs.readFileSync(process.argv[2],"utf8"));
 const key=crypto.createPrivateKey(fs.readFileSync(process.argv[3],"utf8"));
 const bundle=coverage.collect(manifest.model,manifest.scope,key);
 process.stdout.write(JSON.stringify({schema:"IWI-005/test-worker-output",
  producerPid:process.pid,bundle})+"\n");
}
