const {test}=require('node:test');const assert=require('node:assert/strict');const {validateRequest}=require('../desktop/contracts.cjs');
test('renderer IPC allows only local known endpoints',()=>{assert.equal(validateRequest('/profiles','GET'),'/profiles');assert.equal(validateRequest('/history?q=hello','GET'),'/history?q=hello');for(const p of ['https://evil.test/health','//evil.test/health','/admin','/profiles/../../../etc/passwd','/health#secret','/health\\bad'])assert.throws(()=>validateRequest(p,'GET'));});
test('IPC rejects methods and oversized payloads',()=>{assert.throws(()=>validateRequest('/health','DELETE'));assert.throws(()=>validateRequest('/settings','POST',{huge:'x'.repeat(9*1024*1024)}));});

test('queue and cover routes stay inside the local boundary',()=>{assert.equal(validateRequest('/jobs/clear','POST'),'/jobs/clear');assert.equal(validateRequest('/profiles/'+ 'a'.repeat(32) +'/artwork/12','GET'),'/profiles/'+ 'a'.repeat(32) +'/artwork/12');assert.throws(()=>validateRequest('/profiles/'+ 'a'.repeat(32) +'/artwork/../../health','GET'));});

test('library and history controls stay inside approved routes',()=>{for(const path of ['/history/clear','/profiles/'+ 'b'.repeat(32)+'/remove','/profiles/'+ 'b'.repeat(32)+'/playlist-cover','/profiles/'+'b'.repeat(32)+'/track-ids','/profiles/'+'b'.repeat(32)+'/playlist-order','/preview/library-action'])assert.equal(validateRequest(path,'POST'),path);assert.throws(()=>validateRequest('/profiles/anything/remove','POST'));});

test('Last.fm and discovery controls stay on approved local routes',()=>{
 for(const path of ['/lastfm/status','/lastfm/connect','/lastfm/disconnect','/lastfm/charts?view=albums&period=7day','/lastfm/image','/lastfm/picture','/lastfm/track-image','/discovery/remove','/discovery/restore'])assert.equal(validateRequest(path,'POST'),path);
 assert.throws(()=>validateRequest('/lastfm/proxy','GET'));
 assert.throws(()=>validateRequest('https://ws.audioscrobbler.com/2.0/','GET'));
});
