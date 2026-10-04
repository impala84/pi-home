'use strict';
const test=require('node:test');const assert=require('node:assert/strict');const {dailyPicks}=require('./discovery-read');
const sdk=require('./vendor/roon-research/sdk.cjs');
function client(status){const calls=[];return {calls,profile:()=>Buffer.alloc(16),serviceOid:()=>2n,structArg:(_type,fields)=>{assert.deepEqual(fields.map(f=>f.propType),[20,2,2,2]);return Buffer.alloc(1);},remoting:{callMethod:async(_oid,method)=>{calls.push(method);return {status:calls.length===1?status:'Success',success:true};}}};}
test('current DailyPicks parameter struct is tried once and retained when available',async()=>{const c=client('Success');await dailyPicks(c,sdk,'2026-01-01T00:00:00Z');assert.equal(c.calls.length,1);assert.match(c.calls[0],/DailyPicksParameters/);});
test('only MissingMethod permits the single legacy fallback',async()=>{const c=client('MissingMethod');await dailyPicks(c,sdk,'2026-01-01T00:00:00Z');assert.equal(c.calls.length,2);assert.match(c.calls[1],/string, bool/);const denied=client('Denied');await dailyPicks(denied,sdk,'time');assert.equal(denied.calls.length,1);});
const {readDiscovery,waitFor,waitForGraph,recentlyAdded}=require('./discovery-read');
test('mixes load independently without requesting Daily Picks',async()=>{
  const calls=[];const c={profile:()=>Buffer.alloc(16),serviceOid:()=>2n,graph:{decodeReturnValue:()=>({$count:0,$items:[]})},remoting:{callMethod:async(_id,method)=>{calls.push(method);return {success:true,payload:Buffer.alloc(0)};}}};
  assert.deepEqual(await readDiscovery(c,sdk,'daily'),{items:[]});assert.equal(calls.length,1);assert.match(calls[0],/GetMixes/);assert.doesNotMatch(calls[0],/GetDailyPicks/);
});
test('readiness waits for missing pushed objects and ignores unrelated broker graph',async()=>{
  const objects=new Map();const graph={getObject:id=>objects.get(id)};
  setTimeout(()=>objects.set(2n,{fields:{Title:'Album','object Album::Broker':{$ref:99n}}}),5);
  await waitForGraph(graph,{$count:1,$items:[{$ref:2n}]});assert.equal(objects.size,1);
  await assert.rejects(waitFor(()=>undefined,1),/did not finish/);
});
function addedClient(fail=false){
  const objects=new Map([[1n,{oid:1n,fields:{'int Query::Count':2}}],[9n,{oid:9n,typeName:'Sooloos.Broker.Api.AlbumLite',fields:{Title:'Unrelated album'}}]]),calls=[],structs=[];
  return {objects,calls,structs,profile:()=>Buffer.alloc(16),serviceOid:()=>2n,structArg:(type,fields)=>{structs.push({type,fields});return Buffer.alloc(0)},graph:{objects,getObject:id=>objects.get(id),decodeReturnValue:()=>({$ref:1n})},remoting:{callMethod:async(_id,method)=>{
    calls.push(method);if(method.includes('RetainPage')){if(fail)return {success:false};for(const [i,title] of [[0,'Newest'],[1,'Older']]){objects.set(BigInt(10+i),{oid:BigInt(10+i),typeName:'Sooloos.Broker.Api.VirtualQueryElement<Sooloos.Broker.Api.AlbumLite>',fields:{'AlbumLite Element::Data':{$ref:BigInt(20+i)}}});objects.set(BigInt(20+i),{oid:BigInt(20+i),fields:{Title:title,PerformedBy:'Artist'}});}}return {success:true,payload:Buffer.alloc(0)};},callMethodNoReply:(_id,method)=>calls.push(method)}};
}
test('Added retains only a compact first page, sorted by import date, and releases resources',async()=>{
  const c=addedClient();const data=await recentlyAdded(c,sdk);assert.deepEqual(data.items.map(i=>i.title),['Newest','Older']);assert.equal(data.total,2);
  const order=c.structs[0].fields;assert.deepEqual(order.map(f=>f.value),[sdk.buildArgs([sdk.Arg.enum_(1)]),sdk.buildArgs([sdk.Arg.enum_(2)])]);
  assert.deepEqual(c.structs[2].fields[0].value,new sdk.BinaryWriter().integer(12).toBuffer());assert.match(c.calls.at(-2),/ReleasePage/);assert.match(c.calls.at(-1),/Dispose/);assert.equal(c.calls.filter(s=>s.includes('RetainPage')).length,1);
});
test('Added disposes a failed query without presenting an empty success',async()=>{const c=addedClient(true);await assert.rejects(recentlyAdded(c,sdk),/page unavailable/);assert.match(c.calls.at(-1),/Dispose/);assert.equal(c.calls.some(s=>s.includes('ReleasePage')),false);});
