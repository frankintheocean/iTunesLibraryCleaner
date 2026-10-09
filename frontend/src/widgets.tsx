import React,{useEffect,useRef,useState} from 'react';
import {Music2,ArrowUp,ArrowDown,GripVertical} from 'lucide-react';
import {api} from './api';
const covers=new Map<string,Promise<string|null>>();
let active=0;const waiting:Array<()=>void>=[];
async function cover(key:string,path:string){
 if(!covers.has(key)){
  const work=new Promise<string|null>(resolve=>{const start=async()=>{active++;try{resolve((await api(path)).image||null);}catch{resolve(null);}finally{active--;waiting.shift()?.();}};if(active<3)start();else waiting.push(start);});
  covers.set(key,work);if(covers.size>512)covers.delete(covers.keys().next().value!);
 }
 return covers.get(key)!;
}
export function AlbumArt({profile,track,revision}:{profile:string;track:any;revision:number}){
 const ref=useRef<HTMLSpanElement>(null),[image,setImage]=useState<string|null>(null);
 useEffect(()=>{let alive=true;setImage(null);const node=ref.current;if(!node)return;const observer=new IntersectionObserver(entries=>{if(!entries.some(e=>e.isIntersecting))return;observer.disconnect();const key=`${profile}:${track.path||track.id}:${revision}`;cover(key,`/profiles/${profile}/artwork/${track.id}`).then(value=>{if(alive)setImage(value);});},{rootMargin:'100px'});observer.observe(node);return()=>{alive=false;observer.disconnect();};},[profile,track.id,track.path,revision]);
 return <span className="track-art" ref={ref}>{image?<img src={image} alt={`Album art for ${track.name||'this song'}`} onError={()=>setImage(null)}/>:<Music2 size={17} aria-label="No album art available"/>}</span>;
}
export function PlaylistSongs({profile,tracks,revision,orderMode='buttons',canReorder=false,onReorder}:{profile:string;tracks:any[];revision:number;orderMode?:'buttons'|'drag';canReorder?:boolean;onReorder?:(ids:number[])=>Promise<any>}){
 const [page,setPage]=useState(0),[dragIndex,setDragIndex]=useState<number|null>(null),[orderedTracks,setOrderedTracks]=useState<any[]>(tracks);
 useEffect(()=>{setOrderedTracks(tracks);setPage(0);setDragIndex(null);},[tracks,revision]);
 async function move(from:number,to:number){if(!canReorder||!onReorder||from===to||to<0||to>=orderedTracks.length)return;const previous=orderedTracks,next=[...orderedTracks];const [item]=next.splice(from,1);next.splice(to,0,item);setOrderedTracks(next);const result=await onReorder(next.map(track=>Number(track.id)));if(!result)setOrderedTracks(previous);}
 const start=page*50,visible=tracks.slice(start,(page+1)*50);
 return <div className="playlist-songs">{visible.map((track,index)=>{const absoluteIndex=start+index;return <div className={'playlist-song '+(dragIndex===absoluteIndex?'dragging':'')} key={String(track.id)+':'+absoluteIndex} draggable={Boolean(canReorder&&orderMode==='drag')} onDragStart={()=>setDragIndex(absoluteIndex)} onDragOver={event=>{if(canReorder&&orderMode==='drag')event.preventDefault();}} onDrop={event=>{event.preventDefault();if(dragIndex!==null)void move(dragIndex,absoluteIndex);setDragIndex(null);}} onDragEnd={()=>setDragIndex(null)}>{canReorder&&orderMode==='drag'?<span className="playlist-drag-handle" title="Drag this song to a new playlist position"><GripVertical size={16}/></span>:null}<AlbumArt profile={profile} track={track} revision={revision}/><span className="playlist-song-label">{track.name}<small>{track.artist}</small></span>{canReorder&&orderMode==='buttons'?<span className="playlist-order-buttons"><button aria-label={'Move '+track.name+' up'} title="Move up" disabled={absoluteIndex===0} onClick={()=>void move(absoluteIndex,absoluteIndex-1)}><ArrowUp size={14}/></button><button aria-label={'Move '+track.name+' down'} title="Move down" disabled={absoluteIndex===tracks.length-1} onClick={()=>void move(absoluteIndex,absoluteIndex+1)}><ArrowDown size={14}/></button></span>:null}</div>})}{!orderedTracks.length&&<p>Empty playlist</p>}{orderedTracks.length>50&&<div className="inline-actions"><button disabled={!page} onClick={()=>setPage(page-1)}>Previous songs</button><small>Page {page+1} of {Math.ceil(orderedTracks.length/50)}</small><button disabled={(page+1)*50>=orderedTracks.length} onClick={()=>setPage(page+1)}>Next songs</button></div>}{!canReorder&&tracks.length>0?<p className="footnote">Manual reordering is only available for a regular playlist in the current live iTunes profile. If classic iTunes COM cannot safely persist the new order, the queue reports that no tracks were changed.</p>:null}</div>;
}
export function formatTime(seconds:number){const value=Math.max(0,Math.floor(seconds));return `${Math.floor(value/3600)?Math.floor(value/3600)+'h ':''}${Math.floor(value/60)%60}m ${value%60}s`;}
export function TaskTime({job}:{job:any}){
 const [now,setNow]=useState(Date.now()/1000);
 useEffect(()=>{setNow(Date.now()/1000);if(job.status!=='running')return;const timer=setInterval(()=>setNow(Date.now()/1000),1000);return()=>clearInterval(timer);},[job.status,job.sampled_at]);
 const elapsed=(job.elapsed_seconds||0)+(job.status==='running'?Math.max(0,now-(job.sampled_at||now)):0);
 const remaining=job.eta_end==null?null:Math.max(0,job.eta_end-elapsed);
 const eta=job.status==='queued'?'Waiting':job.status==='paused'?'Paused':job.status==='running'?(job.kind==='scan'&&job.current==='Saving and indexing the library'?'Saving library…':remaining===null?(job.kind==='scan'?'Measuring scan speed…':'Starting…'):remaining<=0?'Taking longer than estimated…':'~'+formatTime(remaining)):job.status==='complete'?'Done':'Stopped';
 return <small className="task-time">⏱️ Elapsed {formatTime(elapsed)}<br/>🏁 ETA {eta}</small>;
}
