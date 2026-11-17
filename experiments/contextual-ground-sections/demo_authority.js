"use strict";
const a=require("./authority.js");
function createDemo(){
  const root1=a.generateIdentity(),root2=a.generateIdentity();
  const receiver=a.generateIdentity();
  const alice=a.generateIdentity(),bob=a.generateIdentity(),charlie=a.generateIdentity();
  const grant=(observer,key)=>({observer,public_key:a.publicPEM(key.publicKey),features:["parity"]});
  const trust={schema:"ifs.cgs008-trust/0.1",realm:"cgs008-test-domain",
    ground:a.digest({model:"VGI-ground-reference",revision:"CGS-008-demo"}),
    roots:[a.publicPEM(root1.publicKey),a.publicPEM(root2.publicKey)],
    threshold:2,receiver:a.publicPEM(receiver.publicKey)};
  const policy1=a.signed({schema:"ifs.cgs008-policy/0.1",realm:trust.realm,
    ground:trust.ground,version:1,previous:a.ZERO,
    valid_from:100,expires:250,grants:[grant("alice",alice),grant("bob",bob)],
    revoked:[]},[root1,root2]);
  const policy2=a.signed({schema:"ifs.cgs008-policy/0.1",realm:trust.realm,
    ground:trust.ground,version:2,previous:a.digest(policy1.body),
    valid_from:230,expires:600,grants:[grant("alice",alice),grant("charlie",charlie)],
    revoked:["bob"]},[root1,root2]);
  const checkpoint0=a.bootstrap(trust,receiver);
  const checkpoint1=a.advance(trust,[policy1],checkpoint0,receiver,150);
  const request1=a.challenge(trust,[policy1],checkpoint1,receiver,160,"aa".repeat(16));
  const receipts1=[a.observe(request1,"alice",1,alice),a.observe(request1,"bob",1,bob)];
  const round1=a.consume(trust,[policy1],checkpoint1,request1,receipts1,receiver,161);
  const checkpoint2=a.advance(trust,[policy1,policy2],round1.next_checkpoint,receiver,260);
  const request2=a.challenge(trust,[policy1,policy2],checkpoint2,receiver,261,"bb".repeat(16));
  const receipts2=[a.observe(request2,"alice",1,alice),a.observe(request2,"charlie",0,charlie)];
  const round2=a.consume(trust,[policy1,policy2],checkpoint2,request2,receipts2,receiver,262);
  const history=a.historical(trust,[policy1,policy2],1,request1,receipts1);
  return {schema:"ifs.cgs008-demo/0.1",trust,policies:[policy1,policy2],
    checkpoint0,checkpoint1,request1,receipts1,
    checkpoint_after1:round1.next_checkpoint,
    checkpoint2,request2,receipts2,
    checkpoint_after2:round2.next_checkpoint,
    outcomes:{first:{status:round1.status,value:round1.returned_value},
      second:{status:round2.status,value:round2.returned_value},history}};
}
module.exports={createDemo};
if(require.main===module)process.stdout.write(JSON.stringify(createDemo(),null,2)+"\n");
