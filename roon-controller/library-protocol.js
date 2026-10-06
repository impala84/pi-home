'use strict';
const {field,resolve,list,text}=require('./discovery-model');
const {waitFor}=require('./discovery-read');
const ns='Sooloos.Broker.Api';
// ProfileData<bool> is a count followed by (length-prefixed Sooid, bool).
// Missing entries mean false; malformed/unknown encodings are not false.
function profileBoolean(bytes,profile) {
  if(!Buffer.isBuffer(bytes)||!Buffer.isBuffer(profile))return null;
  let p=0;
  const integer=()=>{let n=0;for(let i=0;i<5;i++){if(p>=bytes.length)throw Error();const b=bytes[p++];n=n*128+(b&127);if(b<128)return n;}throw Error();};
  try {
    const count=integer();if(count>256) return null;
    let value=false;
    for(let i=0;i<count;i++) {
      const length=integer();if(length<1||length>80||p+length>=bytes.length)return null;
      const id=bytes.subarray(p,p+length);p+=length;const flag=bytes[p++];if(flag>1)return null;
      if(id.equals(profile))value=flag===1;
    }
    return p===bytes.length?value:null;
  } catch{return null;}
}
function playingAlbum(client,{zoneId,album,track}) {
  if(!/^[a-f0-9]{36}$/i.test(zoneId||''))throw Error('Invalid Roon zone');
  const zones=[...client.graph.objects.values()].filter(o=>o.typeName===`${ns}.Zone`&&Buffer.isBuffer(field(o,'ZoneId'))&&field(o,'ZoneId').toString('hex')===zoneId.toLowerCase());
  if(zones.length!==1)return undefined;
  const current=resolve(client.graph,field(zones[0],'NowPlaying'));
  const tracks=list(client.graph,field(current,'Tracks'),20).filter(o=>field(o,'IsCurrent')===true);
  if(tracks.length!==1)return undefined;
  const playing=resolve(client.graph,field(tracks[0],'Track'));
  const item=resolve(client.graph,field(playing,'Album'));
  if(!playing||!item||!field(item,'AlbumId'))return undefined;
  // Never substitute a search result or mutate the new song after a tap.
  if(text(field(item,'Title'))!==album||text(field(playing,'Title'))!==track)throw Error('The playing album changed. Try again.');
  const profileId=field(tracks[0],'ProfileId');
  if(!Buffer.isBuffer(profileId))return undefined;
  const profiles=[...client.graph.objects.values()].filter(o=>o.typeName===`${ns}.Profile`&&Buffer.isBuffer(field(o,'ProfileId'))&&field(o,'ProfileId').equals(profileId));
  if(profiles.length!==1)return undefined;
  return {album:item,profile:profiles[0],profileId};
}
function libraryStatus(client,context) {
  const item=client.graph.getObject(context.album.oid);
  const libraryId=field(item,'LibraryAlbumId');
  const inLibrary=libraryId!=null&&BigInt(libraryId)>0n;
  const favoriteItem=context.libraryAlbum?client.graph.getObject(context.libraryAlbum.oid):item;
  return {library_status:inLibrary?'in_library':'not_in_library',album_id:String(field(item,'AlbumId')),favorite:profileBoolean(field(favoriteItem,'IsFavorite'),context.profileId)};
}
async function hydrateLibraryAlbum(client,sdk,context) {
  const id=field(client.graph.getObject(context.album.oid),'LibraryAlbumId');
  if(id==null||BigInt(id)<=0n)return;
  // The recording shows favourites belong to the library edition, not the
  // streaming metadata object. GetAlbumLite(long) was also observed on add.
  const result=await client.remoting.callMethod(client.serviceOid('Library'),`${ns}.Library::GetAlbumLite(long, Base.ResultCallback<${ns}.AlbumLite>)`,sdk.buildArgs([sdk.Arg.long(BigInt(id))]));
  if(!result.success)throw Error('Roon library edition is unavailable');
  const ref=client.graph.decodeReturnValue(Uint8Array.from(result.payload));
  context.libraryAlbum=await waitFor(()=>{const item=resolve(client.graph,ref);return item&&String(field(item,'AlbumId'))===String(id)&&Buffer.isBuffer(field(item,'IsFavorite'))?item:undefined;});
}
async function libraryOperation(client,sdk,request) {
  const context=await waitFor(()=>playingAlbum(client,request));
  await hydrateLibraryAlbum(client,sdk,context);
  const status=()=>libraryStatus(client,context);
  const before=status();
  if(request.action==='status')return before;
  const current=playingAlbum(client,request);
  if(!current||current.album.oid!==context.album.oid||!current.profileId.equals(context.profileId))throw Error('The playing album changed. Try again.');
  if(request.albumId!==before.album_id)throw Error('The playing album changed. Try again.');
  const {Arg,buildArgs}=sdk;
  if(request.action==='add') {
    if(before.library_status==='in_library')return {...before,already_in_library:true};
    // Observed official-client call, 2026-10-05: no callback or reply.
    client.remoting.callMethodNoReply(client.serviceOid('Library'),`${ns}.Library::AddToLibrary(${ns}.Profile, ${ns}.AlbumBase)`,buildArgs([Arg.ref(context.profile.oid),Arg.ref(context.album.oid)]));
    await waitFor(()=>{const state=status();return state.library_status==='in_library'?state:undefined;},8000);
    await hydrateLibraryAlbum(client,sdk,context);
    return {...status(),added:true};
  }
  if(request.action!=='favorite'||typeof request.favorite!=='boolean'||before.library_status!=='in_library')throw Error('Invalid library action');
  if(before.favorite===null)throw Error('Roon favourite status is unavailable');
  const result=await client.remoting.callMethod(client.serviceOid('Library'),`${ns}.Library::FavoriteOrBan(System.Sooid, ${ns}.AlbumBase, ${ns}.FavoriteBanState, Base.ResultCallback)`,buildArgs([Arg.sooid(context.profileId),Arg.ref(context.libraryAlbum.oid),Arg.enum_(request.favorite?1:0)]));
  if(!result.success)throw Error('Roon did not accept the favourite action');
  return await waitFor(()=>{const state=status();return state.favorite===request.favorite?state:undefined;},5000);
}
module.exports={profileBoolean,playingAlbum,libraryStatus,libraryOperation};
