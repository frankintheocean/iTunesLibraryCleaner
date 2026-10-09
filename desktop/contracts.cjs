const allowed=[/^\/health$/,/^\/discovery$/,/^\/com\/status$/,/^\/profiles$/,/^\/profiles\/[a-f0-9]{32}\/(scan|tracks|overview|duplicates|playlists|options)$/,/^\/preview\/(metadata|cleaner|albums|merge|transfer|undo|relink|artwork|playlist|quarantine)$/,/^\/preview\/restore\/[a-f0-9]{32}$/,/^\/commit$/,/^\/verify$/,/^\/folder-health$/,/^\/jobs$/,/^\/jobs\/[a-f0-9]{32}\/control$/,/^\/(history|edits|transfers|settings|rules|changelog)$/,/^\/settings\/import$/,/^\/rules\/test$/,/^\/playlists\/export$/,/^\/metadata\/inspect$/,/^\/artwork\/read$/,/^\/spotify\/compare$/,/^\/reports\/export$/];
function validateRequest(path,method,body){
 if(typeof path!=='string'||path.length>8192||!['GET','POST'].includes(method)||!path.startsWith('/')||path.startsWith('//')||path.includes('\\')||path.includes('#'))throw new Error('Invalid request');
 const url=new URL(path,'http://127.0.0.1');
 if(url.origin!=='http://127.0.0.1'||!allowed.some(r=>r.test(url.pathname)))throw new Error('Endpoint not allowed');
 if(body!==undefined&&Buffer.byteLength(JSON.stringify(body))>8*1024*1024)throw new Error('Request is too large');
 return url.pathname+url.search;
}
module.exports={validateRequest};
