const {_electron:electron}=require('playwright-core');
const fs=require('node:fs');const assert=require('node:assert/strict');
(async()=>{
 const path=require('node:path'),os=require('node:os');
 const root=path.resolve(__dirname,'..'),data=fs.mkdtempSync(path.join(os.tmpdir(),'uilm-desktop-'));
 const python=path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
 const fixture=require('node:child_process').spawnSync(python,[path.join(__dirname,'make_fixture.py'),data],{encoding:'utf8'});
 if(fixture.status!==0)throw new Error(fixture.stderr);
 const fixturePath=path.join(data,'Library.xml');
 const installed=process.env.LIBRARY_MANAGER_ELECTRON_EXECUTABLE;
 const screenshots=process.env.LIBRARY_MANAGER_SCREENSHOT_DIR||path.join(root,'docs');fs.mkdirSync(screenshots,{recursive:true});
 const app=await electron.launch({executablePath:installed||require('electron'),args:[...(installed?[]:[root]),...(process.env.LIBRARY_MANAGER_TEST_NO_SANDBOX==='1'?['--no-sandbox']:[])],cwd:root,env:{...process.env,XDG_CONFIG_HOME:data+'/config',XDG_CACHE_HOME:data+'/cache',LIBRARY_MANAGER_DATA_DIR:data+'/state'},timeout:30000});
 const errors=[];const page=await app.firstWindow();page.on('pageerror',e=>errors.push(e.message));
 try{
 await page.getByRole('button',{name:'Add your first library'}).click();
 await page.getByLabel('Library name').fill('Synthetic Studio');
 await page.getByLabel('Path',{exact:true}).fill(fixturePath);
 await page.getByRole('button',{name:'Add & scan'}).click();
 await page.waitForFunction(()=>document.querySelector('header select')?.value?.length===32);
 await page.getByRole('button',{name:'Overview',exact:true}).click();
 await page.waitForSelector('.hero',{timeout:15000});
 assert.equal(await page.getByLabel('Open GitHub repository').count(),0);
 await page.waitForFunction(()=>document.querySelector('.stat strong')?.textContent==='120');
 assert.ok((await page.locator('.stat').first().innerText()).includes('120'));
 assert.match(await page.locator('.genre-chart small').first().innerText(),/17% \(20\)/);
 const titleCenter=await page.locator('.titlebar').evaluate(node=>{const title=node.querySelector('.drag-region').getBoundingClientRect(),bar=node.getBoundingClientRect();return Math.abs((title.left+title.right)/2-(bar.left+bar.right)/2);});assert.ok(titleCenter<2);
 await page.screenshot({path:path.join(screenshots,'ui-overview.png')});
 // A background refresh must keep the active collection, including after adding a blank one.
 const loadedProfile=await page.getByLabel('Active library').inputValue();
 fs.writeFileSync(path.join(data,'Empty.xml'),'<?xml version="1.0"?><plist version="1.0"><dict><key>Tracks</key><dict/><key>Playlists</key><array/></dict></plist>');
 const blank=await page.evaluate(source=>window.libraryManager.request('/profiles','POST',{name:'A blank library',kind:'xml',source}),path.join(data,'Empty.xml'));
 await page.waitForFunction(identity=>Array.from(document.querySelector('header select').options).some(option=>option.value===identity),blank.id);
 assert.equal(await page.getByLabel('Active library').inputValue(),loadedProfile);
 await page.getByRole('button',{name:'File Organizer',exact:true}).click();
 await page.waitForSelector('.track-row');
 assert.equal(await page.getByLabel('Active library').inputValue(),loadedProfile);
 await page.getByLabel('Active library').selectOption(blank.id);
 await page.getByLabel('Active library').selectOption(loadedProfile);
 await page.waitForFunction(()=>document.querySelector('.table-footer')?.textContent.includes('120 tracks'));
 assert.equal((await page.evaluate(()=>window.libraryManager.request('/jobs','GET'))).filter(job=>job.kind==='scan').length,2);
 await page.getByRole('button',{name:'Metadata',exact:true}).click();
 await page.waitForSelector('.track-row');
 await page.waitForSelector('.track-art img');
 await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setSize(1360,1600));
 await page.waitForTimeout(150);
 const tableHeight=await page.locator('.track-scroll').evaluate(node=>node.getBoundingClientRect().height);assert.ok(tableHeight>1200);
 await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setSize(1360,920));
 assert.ok(await page.locator('.track-row').count()<120);
 const headingBefore=await page.locator('h1').boundingBox();
 await page.locator('.page-scroll').evaluate(node=>node.scrollTop=250);
 await page.waitForTimeout(150);
 const headingAfter=await page.locator('h1').boundingBox();assert.ok(headingAfter.y<headingBefore.y-100);
 await page.locator('.page-scroll').evaluate(node=>node.scrollTop=0);
 await page.getByLabel('Write target').selectOption('file');
 await page.locator('.track-row input').first().check();
 await page.locator('.edit-fields label input').first().fill('Indie');
 await page.getByRole('button',{name:/Preview 1 changes/}).click();
 await page.waitForSelector('.preview-data');
 assert.ok((await page.locator('.preview-data').innerText()).includes('Indie'));
 await page.getByRole('button',{name:'Confirm & queue operation'}).click();
 await page.waitForFunction(()=>Array.from(document.querySelectorAll('.job')).some(job=>job.querySelector('h3')?.textContent==='Metadata'&&job.querySelector('.pill')?.textContent==='complete'),null,{timeout:30000});
 assert.ok((await page.locator('.task-time').first().innerText()).includes('Elapsed'));
 page.once('dialog',dialog=>dialog.accept());await page.getByRole('button',{name:'Clear queue',exact:true}).click();
 await page.waitForFunction(()=>!document.querySelector('.job'));
 await page.getByRole('button',{name:'Settings',exact:true}).click();
 assert.equal(await page.getByLabel('Open GitHub repository').count(),1);
 await page.getByRole('button',{name:'Apple Dark',exact:true}).click();
 await page.waitForFunction(()=>document.documentElement.dataset.theme==='Apple Dark');
 await page.getByRole('button',{name:'OLED Ocean',exact:true}).click();
 await page.waitForFunction(()=>document.documentElement.dataset.theme==='OLED Ocean');
 assert.equal(await page.evaluate(()=>getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()),'#000');
 await page.getByLabel('Interface font').selectOption('Verdana');
 await page.getByRole('button',{name:'A+ Larger',exact:true}).click();
 await page.waitForFunction(()=>document.documentElement.style.getPropertyValue('--text-scale')==='1.25');
 await page.getByRole('button',{name:'Reset size',exact:true}).click();
 await page.getByRole('button',{name:'Apple Dark',exact:true}).click();
 await page.getByRole('button',{name:'Overview',exact:true}).click();
 await page.waitForSelector('.hero');
 const badgeColors=await page.locator('.mini-card b').evaluate(node=>({color:getComputedStyle(node).color,background:getComputedStyle(node.parentElement.parentElement).backgroundColor}));
 assert.notEqual(badgeColors.color,badgeColors.background);
 await page.screenshot({path:path.join(screenshots,'ui-overview-dark.png')});
 await page.getByRole('button',{name:'History',exact:true}).click();
 await page.waitForSelector('.history-item');
 page.once('dialog',dialog=>dialog.accept());await page.getByRole('button',{name:'Clear history',exact:true}).click();
 await page.waitForFunction(()=>!document.querySelector('.history-item'));
 assert.ok((await page.evaluate(()=>window.libraryManager.request('/edits','GET'))).length>0);
 await page.getByRole('button',{name:'Settings',exact:true}).click();
 await page.getByLabel('Default library XML path').fill(fixturePath);
 await page.getByRole('button',{name:'Save default path',exact:true}).click();
 await page.getByText('Default library path saved.',{exact:true}).waitFor();
 await page.getByRole('button',{name:'Libraries',exact:true}).click();
 const blankCard=page.locator('.profile-card').filter({has:page.getByRole('heading',{name:'A blank library',exact:true})});
 page.once('dialog',dialog=>dialog.accept());await blankCard.getByRole('button',{name:'Remove',exact:true}).click();
 await page.waitForFunction(()=>!Array.from(document.querySelector('header select').options).some(option=>option.text==='A blank library'));
 assert.equal(await page.getByLabel('Active library').inputValue(),loadedProfile);
 // Hide and restore discovered paths without changing the selected library.
 const found=page.locator('.health-row').filter({has:page.getByRole('button',{name:/Remove discovered location/})});
 const suggestions=await found.count();assert.ok(suggestions>0);
 const hiddenPath=await found.first().locator('.path').innerText();
 await found.first().getByRole('button',{name:/Remove discovered location/}).click();
 await page.waitForFunction(path=>!Array.from(document.querySelectorAll('.health-row .path')).some(node=>node.textContent===path),hiddenPath);
 assert.equal(await page.getByLabel('Active library').inputValue(),loadedProfile);
 await page.getByRole('button',{name:'Restore suggestions',exact:true}).click();
 await page.waitForFunction(path=>Array.from(document.querySelectorAll('.health-row .path')).some(node=>node.textContent===path),hiddenPath);
 // Provider data is simulated here; backend/provider contracts run in Python.
 // Existing library requests keep their real local service handler.
 const cover=await page.evaluate(path=>window.libraryManager.request('/artwork/read','POST',{path}),path.join(data,'song.flac'));assert.ok(cover.image);
 await app.evaluate(({ipcMain},image)=>{
  const original=ipcMain._invokeHandlers.get('library:request');let connected=false;
  const user={name:'TestListener',display_name:'Test Listener',image:'https://lastfm.freetls.fastly.net/i/u/profile.png',play_count:48000,country:'Test'};
  ipcMain.removeHandler('library:request');
  ipcMain.handle('library:request',async(event,request)=>{
   if(!request.path.startsWith('/lastfm/'))return original(event,request);
   if(request.path==='/lastfm/status')return {connected,user:connected?user:null};
   if(request.path==='/lastfm/connect'){if(request.body.username==='Unknown')throw new Error('Last.fm could not find that username.');connected=true;return {connected,user};}
   if(request.path==='/lastfm/disconnect'){connected=false;return {connected,user:null};}
   if(request.path==='/lastfm/image'||request.path==='/lastfm/track-image')return {image};
   if(request.path.startsWith('/lastfm/charts')){const q=new URL(request.path,'http://localhost').searchParams;return {items:[{name:'Demo '+q.get('view')+' '+q.get('period'),artist:'Demo artist',album:'Demo album',image:user.image,plays:123,now_playing:true,timestamp:1700000000}],page:Number(q.get('page')),pages:2};}
   throw new Error('Unexpected Last.fm fixture request');
  });
 },'data:image/png;base64,'+cover.image);
 await page.getByRole('button',{name:'Last.fm',exact:true}).click();
 assert.equal(await page.getByLabel('Open GitHub repository').count(),0);
 await page.getByLabel('Last.fm username').fill('Unknown');await page.getByLabel('Last.fm API key').fill('a'.repeat(32));
 await page.getByRole('button',{name:'Connect Last.fm',exact:true}).click();await page.getByRole('alert').filter({hasText:'could not find'}).waitFor();
 await page.getByLabel('Last.fm username').fill('TestListener');await page.getByRole('button',{name:'Connect Last.fm',exact:true}).click();
 await page.getByRole('heading',{name:'Test Listener',exact:true}).waitFor();await page.waitForFunction(()=>document.querySelector('.lastfm-avatar img')?.naturalWidth>0);
 assert.equal(await page.getByLabel('Last.fm API key').count(),0);
 assert.ok((await page.locator('.lastfm-avatar').boundingBox()).width>=96);
 for(const view of ['tracks','artists','albums']){await page.getByLabel('Last.fm listening view').selectOption(view);await page.getByLabel('Last.fm time period').selectOption('7day');await page.getByText('Demo '+view+' 7day',{exact:true}).waitFor();}
 await page.getByRole('button',{name:'Next',exact:true}).click();await page.getByText('Page 2 of 2',{exact:true}).waitFor();
 await page.waitForFunction(()=>document.querySelector('.lastfm-cover img')?.naturalWidth>0);
 await page.screenshot({path:path.join(screenshots,'ui-lastfm-demo.png')});
 await page.getByRole('button',{name:'Disconnect',exact:true}).click();await page.getByRole('heading',{name:'🎧 Connect Last.fm',exact:true}).waitFor();
 await page.getByRole('button',{name:'Metadata',exact:true}).click();
 await page.screenshot({path:path.join(screenshots,'ui-metadata-dark.png')});
 for(const section of ['Libraries','Library Cleaner','Consolidation','Duplicates','Playlists','File Organizer','Queue','History','Last.fm','Settings']){
  await page.getByRole('button',{name:section,exact:true}).click();
  await page.waitForTimeout(150);
  const heading=await page.locator('h1').innerText();assert.equal(heading,section);
 }
 await app.evaluate(({BrowserWindow})=>{const win=BrowserWindow.getAllWindows()[0];win.maximize();win.unmaximize();win.setSize(820,620);});
 await page.getByRole('button',{name:'Metadata',exact:true}).click();
 await page.getByRole('button',{name:'Settings',exact:true}).click();
 await page.getByLabel('Text size').fill('400');await page.getByLabel('Text size').press('ArrowRight');
 await page.waitForFunction(()=>document.documentElement.dataset.largeText==='true');
 const largeBounds=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));assert.ok(largeBounds.scroll<=largeBounds.width);
 await page.getByRole('button',{name:'Reset size',exact:true}).click();
 await page.getByRole('button',{name:'Metadata',exact:true}).click();
 const bounds=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));assert.ok(bounds.scroll<=bounds.width);
 assert.deepEqual(errors,[]);
 if(process.env.LIBRARY_MANAGER_DESKTOP_REPORT)fs.writeFileSync(process.env.LIBRARY_MANAGER_DESKTOP_REPORT,JSON.stringify({state:path.join(data,'state'),packaged:!!installed,result:'passed'},null,2));
 console.log('PASS: native desktop startup, real API library scan, 120-row virtualized table, file metadata preview/commit, dark theme persistence, 12-screen navigation, maximize/restore and narrow-window layout.');
 }finally{await app.close();}
})().catch(e=>{console.error(e);process.exit(1)});
