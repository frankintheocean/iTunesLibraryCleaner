const {app,BrowserWindow,ipcMain,dialog,shell}=require('electron');
const {spawn}=require('node:child_process');
const {randomBytes}=require('node:crypto');
const path=require('node:path');
const {validateRequest}=require('./contracts.cjs');
let win,backend,backendPort,closing=false;
const children=new Set();
const token=randomBytes(32).toString('hex');
const root=path.resolve(__dirname,'..');
// app.asar is a virtual archive; child processes need a real working directory.
const backendCwd=app.isPackaged?process.resourcesPath:root;
const dev=!!process.env.LIBRARY_MANAGER_DEV;
if(!process.env.LIBRARY_MANAGER_DATA_DIR)app.setPath('userData',path.join(app.getPath('appData'),'Unified iTunes Library Manager'));
if(process.env.LIBRARY_MANAGER_DATA_DIR)app.setPath('userData',path.resolve(process.env.LIBRARY_MANAGER_DATA_DIR));
function backendCommand(extra=[]){
 const dataDir=app.getPath('userData');
 if(app.isPackaged)return {exe:path.join(process.resourcesPath,'backend','library-backend.exe'),args:['--data-dir',dataDir,...extra]};
 return {exe:process.env.LIBRARY_MANAGER_PYTHON||path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python'),args:['-m','backend','--data-dir',dataDir,...extra]};
}
async function startBackend(){
 const c=backendCommand();
 backend=spawn(c.exe,c.args,{cwd:backendCwd,env:{...process.env,LIBRARY_MANAGER_TOKEN:token},windowsHide:true,stdio:['ignore','pipe','pipe']});children.add(backend);
 let stderr='';backend.stderr.on('data',b=>{stderr=(stderr+b.toString()).slice(-8000);});
 return new Promise((resolve,reject)=>{
  let buffer='';const timer=setTimeout(()=>{backend.kill();reject(new Error('Backend startup timed out. '+stderr));},45000);
  backend.on('error',e=>{clearTimeout(timer);reject(e);});
  backend.stdout.on('data',async b=>{buffer+=b.toString();let line;while((line=buffer.indexOf('\n'))>=0){const value=buffer.slice(0,line);buffer=buffer.slice(line+1);try{const status=JSON.parse(value);if(status.ready&&Number.isInteger(status.port)){backendPort=status.port;const r=await fetch(`http://127.0.0.1:${backendPort}/health`,{headers:{Authorization:'Bearer '+token}});if(!r.ok)throw new Error('Backend health check failed');clearTimeout(timer);resolve();}}catch{}}});
  backend.on('exit',code=>{children.delete(backend);clearTimeout(timer);if(!backendPort)reject(new Error('Backend failed to start. '+stderr));else if(!closing){dialog.showErrorBox('Library backend stopped',`The local service exited (${code}). Restart the app. Interrupted operations remain in history.`);if(win&&!win.isDestroyed())win.close();}});
 });
}
function assertSender(event){if(!win||event.sender!==win.webContents||event.senderFrame!==win.webContents.mainFrame)throw new Error('Untrusted IPC sender');}
const filters={xml:[{name:'iTunes XML library',extensions:['xml']}],image:[{name:'Artwork',extensions:['png','jpg','jpeg']}],playlist:[{name:'Playlists',extensions:['m3u','m3u8']}],json:[{name:'Settings',extensions:['json']}],database:[{name:'SQLite database',extensions:['db','sqlite','sqlite3']}],spotify:[{name:'Spotify export',extensions:['zip']}],'save-xml':[{name:'iTunes XML export',extensions:['xml']}],'save-playlist':[{name:'M3U8 playlist',extensions:['m3u8']}],'save-json':[{name:'JSON report',extensions:['json']}]};
ipcMain.handle('library:request',async(event,{path:route,method,body})=>{
 assertSender(event);const endpoint=validateRequest(route,method,body);
 const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),300000);
 try{const response=await fetch(`http://127.0.0.1:${backendPort}${endpoint}`,{method,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:controller.signal});const text=await response.text();let result;try{result=JSON.parse(text);}catch{throw new Error(`The library service returned an unreadable response (${response.status}). Check Queue and History before retrying a write.`);}if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:JSON.stringify(result.detail)||`Library service error ${response.status}`);return result;}finally{clearTimeout(timeout);}
});
ipcMain.handle('library:choose',async(event,kind)=>{assertSender(event);if(kind==='folder'){const r=await dialog.showOpenDialog(win,{properties:['openDirectory','dontAddToRecent']});return r.canceled?null:r.filePaths[0];}if(!filters[kind])throw new Error('Unsupported dialog');if(kind.startsWith('save-')){const r=await dialog.showSaveDialog(win,{filters:filters[kind],properties:['showOverwriteConfirmation','dontAddToRecent']});return r.canceled?null:r.filePath;}const r=await dialog.showOpenDialog(win,{filters:filters[kind],properties:['openFile','dontAddToRecent']});return r.canceled?null:r.filePaths[0];});
ipcMain.handle('library:legacy',async(event,name)=>{assertSender(event);if(!['cleaner','consolidator'].includes(name))throw new Error('Unknown legacy tool');const c=backendCommand(['--legacy',name]);const child=spawn(c.exe,c.args,{cwd:backendCwd,windowsHide:true,stdio:['ignore','ignore','pipe'],env:{...process.env,LIBRARY_MANAGER_TOKEN:''}});children.add(child);let errors='';child.stderr.on('data',b=>errors=(errors+b).slice(-4000));child.on('exit',code=>{children.delete(child);if(code&&!closing)dialog.showErrorBox('Legacy tool could not start',errors||`Exit code ${code}`);});await new Promise((resolve,reject)=>{child.once('spawn',resolve);child.once('error',reject);});});
ipcMain.handle('library:repository',async event=>{assertSender(event);await shell.openExternal('https://github.com/frankintheocean/iTunesLibraryCleaner');});
ipcMain.handle('library:lastfm-key',async event=>{assertSender(event);await shell.openExternal('https://www.last.fm/api/account/create');});
ipcMain.handle('library:window',(event,action)=>{assertSender(event);if(action==='minimize')win.minimize();else if(action==='maximize')win.isMaximized()?win.unmaximize():win.maximize();else if(action==='close')win.close();else throw new Error('Unknown window action');});
app.on('web-contents-created',(_,contents)=>{contents.setWindowOpenHandler(()=>({action:'deny'}));contents.on('will-attach-webview',e=>e.preventDefault());contents.session.setPermissionRequestHandler((_,__,callback)=>callback(false));});
app.whenReady().then(async()=>{
 try{await startBackend();win=new BrowserWindow({width:1360,height:920,minWidth:800,minHeight:600,frame:false,backgroundColor:'#f5f6fa',icon:path.join(app.isPackaged?process.resourcesPath:root,'resources','app.ico'),webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true,webSecurity:true,devTools:!app.isPackaged}});
 win.webContents.on('will-navigate',(e,url)=>{if(!dev||new URL(url).origin!=='http://127.0.0.1:5173')e.preventDefault();});
 if(dev)await win.loadURL('http://127.0.0.1:5173');else await win.loadFile(path.join(root,'frontend','dist','index.html'));
 }catch(e){dialog.showErrorBox('Unable to start iTunes Manager',String(e));app.quit();}
});
app.on('window-all-closed',()=>app.quit());
app.on('before-quit',event=>{
 if(closing)return;closing=true;event.preventDefault();
 const stops=[...children].map(child=>new Promise(resolve=>{
  if(child.exitCode!==null)return resolve();
  child.once('exit',resolve);
  if(process.platform==='win32'){spawn('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true}).once('exit',resolve);}else child.kill('SIGTERM');
  setTimeout(()=>{child.kill('SIGKILL');resolve();},5000).unref();
 }));Promise.all(stops).finally(()=>app.quit());
});
