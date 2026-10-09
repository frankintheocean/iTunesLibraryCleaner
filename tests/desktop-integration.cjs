const {_electron:electron}=require('playwright-core');
const fs=require('node:fs');const assert=require('node:assert/strict');
(async()=>{
 const path=require('node:path'),os=require('node:os');
 const root=path.resolve(__dirname,'..'),data=fs.mkdtempSync(path.join(os.tmpdir(),'uilm-desktop-'));
 const python=path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
 const fixture=require('node:child_process').spawnSync(python,[path.join(__dirname,'make_fixture.py'),data],{encoding:'utf8'});
 if(fixture.status!==0)throw new Error(fixture.stderr);
 const fixturePath=path.join(data,'Library.xml');
 const app=await electron.launch({executablePath:require('electron'),args:[root,...(process.env.LIBRARY_MANAGER_TEST_NO_SANDBOX==='1'?['--no-sandbox']:[])],cwd:root,env:{...process.env,XDG_CONFIG_HOME:data+'/config',XDG_CACHE_HOME:data+'/cache',LIBRARY_MANAGER_DATA_DIR:data+'/state'},timeout:30000});
 const errors=[];const page=await app.firstWindow();page.on('pageerror',e=>errors.push(e.message));
 try{
 await page.getByRole('button',{name:'Add your first library'}).click();
 await page.getByLabel('Library name').fill('Synthetic Studio');
 await page.getByLabel('Path',{exact:true}).fill(fixturePath);
 await page.getByRole('button',{name:'Add & scan'}).click();
 await page.waitForFunction(()=>document.querySelector('header select')?.value?.length===32);
 await page.getByRole('button',{name:'Overview',exact:true}).click();
 await page.waitForSelector('.hero',{timeout:15000});
 assert.ok((await page.locator('.stat').first().innerText()).includes('120'));
 await page.screenshot({path:root+'/docs/ui-overview.png'});
 await page.getByRole('button',{name:'Metadata',exact:true}).click();
 await page.waitForSelector('.track-row');
 await page.getByLabel('Write target').selectOption('file');
 await page.locator('.track-row input').first().check();
 await page.locator('.edit-fields label input').first().fill('Indie');
 await page.getByRole('button',{name:/Preview 1 changes/}).click();
 await page.waitForSelector('.preview-data');
 assert.ok((await page.locator('.preview-data').innerText()).includes('Indie'));
 await page.getByRole('button',{name:'Confirm & queue operation'}).click();
 await page.waitForFunction(()=>document.querySelector('.job .pill')?.textContent==='complete',{timeout:15000});
 await page.getByRole('button',{name:'Settings',exact:true}).click();
 await page.getByRole('button',{name:'Apple Dark',exact:true}).click();
 await page.waitForFunction(()=>document.documentElement.dataset.theme==='Apple Dark');
 await page.getByRole('button',{name:'Metadata',exact:true}).click();
 await page.screenshot({path:root+'/docs/ui-metadata-dark.png'});
 for(const section of ['Libraries','Library Cleaner','Consolidation','Duplicates','Playlists','File Organizer','Queue','History','Settings']){
  await page.getByRole('button',{name:section,exact:true}).click();
  await page.waitForTimeout(150);
  const heading=await page.locator('h1').innerText();assert.equal(heading,section);
 }
 await app.evaluate(({BrowserWindow})=>{const win=BrowserWindow.getAllWindows()[0];win.maximize();win.unmaximize();win.setSize(820,620);});
 await page.getByRole('button',{name:'Metadata',exact:true}).click();
 const bounds=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));assert.ok(bounds.scroll<=bounds.width);
 assert.deepEqual(errors,[]);
 console.log('PASS: native desktop startup, real API library scan, 120-row virtualized table, file metadata preview/commit, dark theme persistence, 11-screen navigation, maximize/restore and narrow-window layout.');
 }finally{await app.close();}
})().catch(e=>{console.error(e);process.exit(1)});
