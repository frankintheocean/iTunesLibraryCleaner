const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('libraryManager',Object.freeze({
 request:(path,method='GET',body)=>ipcRenderer.invoke('library:request',{path,method,body}),
 choose:kind=>ipcRenderer.invoke('library:choose',kind),
 legacy:name=>ipcRenderer.invoke('library:legacy',name),
 repository:()=>ipcRenderer.invoke('library:repository'),lastfmKey:()=>ipcRenderer.invoke('library:lastfm-key'),
 window:action=>ipcRenderer.invoke('library:window',action)
}));
