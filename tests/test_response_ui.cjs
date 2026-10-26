const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[2],'utf8');
const start=source.indexOf('const responseRequests = new Map();');
const end=source.indexOf('restoreResponseIds();renderResponseRequests();',start);
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
async function testLatePoll(){
 const d=deferred(),s={api:()=>d.promise,sessionStorage:{setItem(){}},crypto:{randomUUID:()=> 'a'.repeat(32)}};
 vm.createContext(s);vm.runInContext(source.slice(start,end)+";renderResponseRequests=()=>{};responseRequests.set('a'.repeat(32),{id:'a'.repeat(32),state:'running',after:0});",s);
 const pending=vm.runInContext('refreshResponses()',s);
 vm.runInContext("responseRequests.set('a'.repeat(32),{id:'a'.repeat(32),state:'cancelled',after:2});",s);
 d.resolve({request:{id:'a'.repeat(32),state:'running'},events:[{seq:1,kind:'status',text:'old'}]});await pending;
 assert.equal(vm.runInContext("responseRequests.get('a'.repeat(32)).state",s),'cancelled');
}
async function testReplay(){
 const s={api:async()=>({request:{id:'b'.repeat(32),state:'waiting'},events:[{seq:2,kind:'status',text:'duplicate'},{seq:1,kind:'status',text:'old'},{seq:3,kind:'status',text:'new'}]}),sessionStorage:{setItem(){}}};
 vm.createContext(s);vm.runInContext(source.slice(start,end)+";renderResponseRequests=()=>{};responseRequests.set('b'.repeat(32),{id:'b'.repeat(32),state:'running',after:2});",s);
 await vm.runInContext('refreshResponses()',s);assert.equal(vm.runInContext("responseRequests.get('b'.repeat(32)).notice",s),'new');assert.equal(vm.runInContext("responseRequests.get('b'.repeat(32)).after",s),3);
}
async function testForgetWhileSubmit(){
 const d=deferred(),el={value:'',disabled:false,textContent:''};const s={api:()=>d.promise,$:()=>el,sessionStorage:{setItem(){}},crypto:{randomUUID:()=> 'a'.repeat(32)},bubble:()=>{throw Error('must not render stale reply');}};
 vm.createContext(s);vm.runInContext("let sending=false,latest={setup:{response_tracking:true}};"+source.slice(start,end)+";renderResponseRequests=()=>{};",s);
 const pending=vm.runInContext("send('hello')",s);vm.runInContext('responseRequests.clear();unresolvedSubmission=null;',s);d.reject(Error('Access changed; stale response discarded'));await pending;
 assert.equal(vm.runInContext('unresolvedSubmission',s),null);assert.equal(vm.runInContext('responseRequests.size',s),0);
}

async function testDelayedAcceptance(dismiss){
 const d=deferred(),el={value:'',disabled:false,textContent:''};let bubbles=0;
 const s={api:()=>d.promise,$:()=>el,sessionStorage:{setItem(){}},crypto:{randomUUID:()=> 'a'.repeat(32)},bubble:()=>{bubbles++;}};
 vm.createContext(s);vm.runInContext("let sending=false,latest={setup:{response_tracking:true}};"+source.slice(start,end)+";renderResponseRequests=()=>{};",s);
 const pending=vm.runInContext("send('hello')",s);
 vm.runInContext(dismiss?"responseRequests.clear();":"responseRequests.set('a'.repeat(32),{id:'a'.repeat(32),state:'cancelled',after:4});",s);
 d.resolve({created:true,request:{id:'a'.repeat(32),state:'accepted',after:1}});await pending;
 if(dismiss){assert.equal(vm.runInContext('responseRequests.size',s),0);assert.equal(bubbles,0);}
 else{assert.equal(vm.runInContext("responseRequests.get('a'.repeat(32)).state",s),'cancelled');assert.equal(vm.runInContext("responseRequests.get('a'.repeat(32)).after",s),4);}
}
async function testUncertaintyBeforeFallback(restored){
 let sends=0;const el={value:'',textContent:''};const s={$:()=>el,api:async(path,body)=>{if(body)sends++;throw Error('unavailable');},sessionStorage:{setItem(){}}};
 vm.createContext(s);vm.runInContext("let sending=false,latest={setup:{response_tracking:false}};"+source.slice(start,end)+";renderResponseRequests=()=>{};",s);
 vm.runInContext(restored?"responseRequests.set('b'.repeat(32),{id:'b'.repeat(32),state:'reconnecting',after:0});":"unresolvedSubmission='b'.repeat(32);",s);
 await vm.runInContext("send('do not duplicate')",s);assert.equal(sends,0);
}
(async()=>{await testLatePoll();await testReplay();await testForgetWhileSubmit();await testDelayedAcceptance(false);await testDelayedAcceptance(true);await testUncertaintyBeforeFallback(false);await testUncertaintyBeforeFallback(true);console.log('response UI lifecycle tests passed');})().catch(e=>{console.error(e);process.exitCode=1;});
