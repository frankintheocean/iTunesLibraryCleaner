export type Json = any;
declare global {interface Window {libraryManager?: {request:(path:string,method:string,body?:unknown)=>Promise<Json>;choose:(kind:string)=>Promise<string|null>;legacy:(name:string)=>Promise<void>;window:(action:string)=>Promise<void>;repository:()=>Promise<void>;};}}
export async function api(path:string,method='GET',body?:unknown):Promise<Json>{
 if(!window.libraryManager) throw new Error('Open this interface in the Electron desktop app to connect to your library.');
 return window.libraryManager.request(path,method,body);
}
export async function choose(kind:string){return window.libraryManager?.choose(kind) ?? null;}
