'use strict';
const {DiscoveryManager}=require('./discovery-state');
const {playingMetadata}=require('./details-state');
class LibraryManager {
  constructor({worker=new DiscoveryManager(),now=Date.now,changed=()=>{}}={}) {
    this.worker=worker;this.now=now;this.changed=changed;this.key='';this.value={library_status:'unknown'};this.pending=null;this.expires=0;this.busy=false;
  }
  setTarget(target) {if(JSON.stringify(target)===JSON.stringify(this.worker.target))return;this.worker.setTarget(target);this.key='';this.expires=0;this.value={library_status:'unknown'};}
  request(zone) {const m=playingMetadata(zone);return {zoneId:zone?.zone_id,album:m.album,track:m.track};}
  identity(zone) {return JSON.stringify(this.request(zone));}
  getLibraryStatus(zone) {
    const key=this.identity(zone);
    if(key!==this.key){this.key=key;this.value={library_status:'unknown'};this.expires=0;}
    if(this.worker.target&&zone?.now_playing&&this.request(zone).album&&!this.pending&&!this.busy&&this.expires<=this.now()) {
      const target=this.worker.target;
      const job=this.worker.run(target,'library','',{...this.request(zone),action:'status'}).then(data=>{
        if(this.key!==key||this.worker.target!==target)return;
        this.value=data.status==='ready'?data:{library_status:'unknown',library_error:'Roon library status is unavailable.'};this.expires=this.now()+30000;
      }).finally(()=>{if(this.pending===job)this.pending=null;this.changed();});this.pending=job;
    }
    return {...this.value,library_busy:this.busy};
  }
  async mutate(zone,{action,albumId,favorite}) {
    if(this.busy||this.pending)throw Error('Library status is still loading. Try again shortly.');
    if(!['add','favorite'].includes(action)||!albumId||albumId!==this.value.album_id||this.identity(zone)!==this.key)throw Error('The playing album changed. Try again.');
    if(!this.worker.target)throw Error('Roon is not connected');
    const key=this.key,target=this.worker.target;this.busy=true;this.changed();
    try {
      const data=await this.worker.run(target,'library','',{...this.request(zone),action,albumId,favorite});
      if(data.status!=='ready')throw Error('Roon did not confirm the library change. Check Roon before retrying.');
      if(this.key===key&&this.worker.target===target){this.value=data;this.expires=this.now()+30000;}
      return data;
    } catch(error) {if(this.key===key)this.expires=0;throw error;
    } finally {this.busy=false;this.changed();}
  }
}
module.exports={LibraryManager};
