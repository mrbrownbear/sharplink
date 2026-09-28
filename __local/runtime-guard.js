(function(){
const blocked='/__offline_blocked__';
const originalFetch=window.fetch;
const map=function(value){
  try{
    const raw=String(value&&value.url?value.url:value);
    if(!raw||raw.startsWith('data:')||raw.startsWith('blob:')||raw.startsWith('about:'))return raw;
    const u=new URL(raw,location.href);
    if(u.origin===location.origin)return raw;
    if(u.hostname==='www.sharplink.com'||u.hostname.endsWith('storyblok.com'))return blocked;
    return raw;
  }catch(e){return value;}
};
window.fetch=function(input,init){
  const raw=input&&input.url?input.url:input;
  const mapped=map(raw);
  if(mapped===blocked)return Promise.reject(new Error('Blocked remote runtime request: '+raw));
  if(typeof Request!=='undefined'&&input instanceof Request&&mapped!==raw)return originalFetch.call(this,new Request(mapped,input),init);
  return originalFetch.call(this,mapped,init);
};
const originalOpen=XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open=function(method,url){
  const mapped=map(url);
  if(mapped===blocked)throw new Error('Blocked remote runtime request: '+url);
  arguments[1]=mapped;
  return originalOpen.apply(this,arguments);
};
})();\n