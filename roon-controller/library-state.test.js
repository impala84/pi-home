'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {LibraryManager}=require('./library-state');
const zone={zone_id:'16'+'01'.repeat(17),now_playing:{three_line:{line1:'Track',line2:'Artist',line3:'Album'}}};
function fixture() {
  const jobs=[];const worker={target:{host:'test'},setTarget(t){this.target=t;},run(target,section,id,request){return new Promise(resolve=>jobs.push({resolve,request}));}};
  let now=0;const manager=new LibraryManager({worker,now:()=>now});return {manager,jobs,advance:()=>now+=30001};
}
test('render reads cached status, coalesces background requests and refreshes on expiry',async()=>{
  const f=fixture();for(let i=0;i<10;i++)assert.equal(f.manager.getLibraryStatus(zone).library_status,'unknown');
  assert.equal(f.jobs.length,1);f.jobs[0].resolve({status:'ready',library_status:'in_library',album_id:'123',favorite:false});await f.manager.pending;
  assert.equal(f.manager.getLibraryStatus(zone).favorite,false);assert.equal(f.jobs.length,1);
  f.advance();f.manager.getLibraryStatus(zone);assert.equal(f.jobs.length,2);
});
test('unpairing drops old-profile results',async()=>{
  const f=fixture();f.manager.getLibraryStatus(zone);const pending=f.manager.pending;
  f.manager.setTarget(null);f.jobs[0].resolve({status:'ready',library_status:'in_library',album_id:'123'});await pending;
  assert.equal(f.manager.getLibraryStatus(zone).library_status,'unknown');
});
test('mutation is single-flight and replaces cache only after confirmation',async()=>{
  const f=fixture();f.manager.getLibraryStatus(zone);f.jobs[0].resolve({status:'ready',library_status:'not_in_library',album_id:'123',favorite:false});await f.manager.pending;
  const operation=f.manager.mutate(zone,{action:'add',albumId:'123'});
  await assert.rejects(f.manager.mutate(zone,{action:'add',albumId:'123'}),/still loading/);
  f.jobs[1].resolve({status:'ready',library_status:'in_library',album_id:'123',favorite:false});await operation;
  assert.equal(f.manager.getLibraryStatus(zone).library_status,'in_library');
});
test('unconfirmed mutation is an error rather than optimistic success',async()=>{
  const f=fixture();f.manager.getLibraryStatus(zone);f.jobs[0].resolve({status:'ready',library_status:'not_in_library',album_id:'123'});await f.manager.pending;
  const operation=f.manager.mutate(zone,{action:'add',albumId:'123'});f.jobs[1].resolve({status:'unavailable'});
  await assert.rejects(operation,/did not confirm/);assert.equal(f.manager.value.library_status,'not_in_library');
});
