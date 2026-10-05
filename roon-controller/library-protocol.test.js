'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const sdk=require('./vendor/roon-research/sdk.cjs');
const {profileBoolean,playingAlbum,libraryOperation}=require('./library-protocol');
const zoneId='16'+'01'.repeat(17),profileId=Buffer.from('3f'+'02'.repeat(17),'hex');
function fixture(inLibrary=false) {
  const objects=new Map();
  const add=(oid,type,fields)=>{const o={oid:BigInt(oid),typeName:`Sooloos.Broker.Api.${type}`,fields};objects.set(o.oid,o);return o;};
  add(1,'Zone',{ZoneId:Buffer.from(zoneId,'hex'),NowPlaying:{$ref:'2'}});
  add(2,'TransportItem',{Tracks:{$items:[{$ref:'3'}]}});
  add(3,'TransportTrack',{IsCurrent:true,Track:{$ref:'4'},ProfileId:profileId});
  add(4,'TrackLite',{Title:'Track',Album:{$ref:'5'}});
  const album=add(5,'AlbumLite',{Title:'Album',AlbumId:123n,LibraryAlbumId:inLibrary?456n:null,IsFavorite:Buffer.from([0])});
  add(6,'Profile',{ProfileId:profileId});
  const canonical=add(8,'AlbumLite',{Title:'Album',AlbumId:456n,LibraryAlbumId:456n,IsFavorite:Buffer.from([0])});
  const calls=[];
  const client={graph:{objects,getObject:id=>objects.get(id),decodeReturnValue:()=>({$ref:'8'})},serviceOid:()=>41n,remoting:{
    callMethodNoReply:(oid,name,args)=>{calls.push({name,args});album.fields.LibraryAlbumId=456n;},
    callMethod:async(oid,name,args)=>{calls.push({name,args});if(name.includes('FavoriteOrBan'))canonical.fields.IsFavorite=args.at(-1)===1?Buffer.concat([Buffer.from([1,18]),profileId,Buffer.from([1])]):Buffer.from([0]);return {success:true,payload:Buffer.alloc(0)};}
  }};
  return {client,calls,album,canonical,request:{zoneId,album:'Album',track:'Track'}};
}
test('captured ProfileData bool encoding distinguishes profile membership and rejects malformed data',()=>{
  assert.equal(profileBoolean(Buffer.from([0]),profileId),false);
  assert.equal(profileBoolean(Buffer.concat([Buffer.from([1,18]),profileId,Buffer.from([1])]),profileId),true);
  assert.equal(profileBoolean(Buffer.from([1,18,2]),profileId),null);
  assert.equal(profileBoolean(Buffer.from([0,1]),profileId),null);
});
test('playing album uses exact zone and current transport track, never fuzzy title lookup',()=>{
  const f=fixture();assert.equal(playingAlbum(f.client,f.request).album.oid,5n);
  assert.throws(()=>playingAlbum(f.client,{...f.request,track:'Changed'}),/changed/);
  assert.equal(playingAlbum(f.client,{...f.request,zoneId:'17'+'01'.repeat(17)}),undefined);
});
test('add uses captured Profile+AlbumBase bare references and confirms pushed membership',async()=>{
  const f=fixture();const result=await libraryOperation(f.client,sdk,{...f.request,action:'add',albumId:'123'});
  assert.equal(result.added,true);assert.equal(result.library_status,'in_library');
  assert.equal(f.calls[0].name,'Sooloos.Broker.Api.Library::AddToLibrary(Sooloos.Broker.Api.Profile, Sooloos.Broker.Api.AlbumBase)');
  assert.deepEqual(f.calls[0].args,sdk.buildArgs([sdk.Arg.ref(6n),sdk.Arg.ref(5n)]));
});
test('already in library does not add again; stale album ID never mutates',async()=>{
  const f=fixture(true);assert.equal((await libraryOperation(f.client,sdk,{...f.request,action:'add',albumId:'123'})).already_in_library,true);
  assert.ok(!f.calls.some(c=>c.name.includes('AddToLibrary')));
  await assert.rejects(libraryOperation(f.client,sdk,{...f.request,action:'add',albumId:'999'}),/changed/);
});
test('favourite targets canonical library edition and confirms both captured enum directions',async()=>{
  const f=fixture(true);
  for(const favorite of [true,false]) {
    const result=await libraryOperation(f.client,sdk,{...f.request,action:'favorite',albumId:'123',favorite});
    assert.equal(result.favorite,favorite);
    const call=f.calls.at(-1);assert.match(call.name,/FavoriteOrBan/);
    assert.deepEqual(call.args,sdk.buildArgs([sdk.Arg.sooid(profileId),sdk.Arg.ref(8n),sdk.Arg.enum_(favorite?1:0)]));
  }
});
test('favourite cannot imply library-add',async()=>{
  const f=fixture();await assert.rejects(libraryOperation(f.client,sdk,{...f.request,action:'favorite',albumId:'123',favorite:true}),/Invalid library action/);
  assert.equal(f.calls.length,0);
});
