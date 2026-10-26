const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[2],'utf8');
const api=source.slice(source.indexOf('async function api('),source.indexOf('\nfunction node('));
function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};}
async function run(bodyDelay){
  const headers=deferred(),body=deferred();let effects=0;
  const sandbox={fetch:()=>headers.promise,AbortSignal:{timeout:()=>null},$:()=>({set hidden(v){effects++;}})};
  vm.createContext(sandbox);
  vm.runInContext("let accessToken='synthetic-only',authRequired=false,authEpoch=0;"+api,sandbox);
  const result=vm.runInContext("api('/api/state')",sandbox);
  if(bodyDelay){headers.resolve({status:200,ok:true,json:()=>body.promise});await Promise.resolve();}
  vm.runInContext("authEpoch++;accessToken='';",sandbox);
  if(!bodyDelay)headers.resolve({status:200,ok:true,json:async()=>({private:'data'})});
  else body.resolve({private:'data'});
  await assert.rejects(result,/stale response discarded/);
  assert.equal(effects,0);
}
(async()=>{await run(false);await run(true);console.log('auth epoch tests passed');})().catch(e=>{console.error(e);process.exitCode=1;});
