'use strict';
/* Ozon link evidence detector.
 * High confidence = Ozon URL explicitly carrying advRef.
 * Possible = Ozon short product URLs; these do NOT establish affiliate status.
 * We do not follow redirects or treat ordinary Ozon product links as affiliate.
 */
(function(){
const ozonHost=h=>h==='ozon.ru'||h==='www.ozon.ru'||h==='m.ozon.ru'||h==='s.ozon.ru';
function findLinks(text){
 if(typeof text!=='string'||!text)return [];
 const out=[],regex=/(?:https?:\/\/|www\.|s\.ozon\.ru\/|ozon\.ru\/)[^\s<>"'«»{}\[\]]+/giu;
 for(const m of text.matchAll(regex)){
  let raw=m[0].replace(/&amp;/gi,'&').replace(/[),.;!?»)\]}>]+$/u,'');
  if(raw.startsWith('www.')||raw.startsWith('s.ozon.ru/')||raw.startsWith('ozon.ru/'))raw='https://'+raw;
  let u;try{u=new URL(raw);}catch{continue;}
  if(!ozonHost(u.hostname.toLowerCase()))continue;
  const paramKeys=[...u.searchParams.keys()].map(x=>x.toLowerCase());
  let grade='ordinary',explanation='Обычная ссылка Ozon: партнёрство не подтверждено';
  if(paramKeys.includes('advref')){
   grade='advref';explanation='В ссылке обнаружен параметр advRef';
  }else if(/\/p\/o\d+\/?$/iu.test(u.pathname)){
   grade='possible';explanation='Короткая товарная ссылка Ozon: источник вознаграждения не установлен';
  }else if(u.hostname.toLowerCase()==='s.ozon.ru'){
   const preceding=text.slice(Math.max(0,m.index-120),m.index).toLowerCase();
   if(!/информаци[яи]\s+о\s+рекламодател|рекламодател|маркировк/iu.test(preceding)){
    grade='possible';explanation='Сокращённая ссылка Ozon: назначение не установлено';
   }else{
    grade='disclosure';explanation='Ссылка для информации о рекламодателе (не товарное подтверждение)';
   }
  }
  out.push({url:u.href,grade,reason:explanation});
 }
 return out;
}
function collect(post){
 const strings=[];
 if(typeof post?.text==='string')strings.push(post.text);
 for(const a of post?.attachments||[]){
  if(a?.type==='link'){
   if(typeof a.link?.url==='string')strings.push(a.link.url);
   if(typeof a.link?.button?.action?.url==='string')strings.push(a.link.button.action.url);
  }
  if(a?.type==='market'&&typeof a.market?.url==='string')strings.push(a.market.url);
 }
 return strings;
}
function detect(post){
 const all=collect(post).flatMap(findLinks);
 const unique=[...new Map(all.map(e=>[e.url,e])).values()];
 const best=unique.find(x=>x.grade==='advref')||unique.find(x=>x.grade==='possible')||unique.find(x=>x.grade==='ordinary')||unique.find(x=>x.grade==='disclosure')||null;
 return {
  grade:unique.some(x=>x.grade==='advref')?'advref':unique.some(x=>x.grade==='possible')?'possible':'none',
  evidence:unique,
  best:best?.url||'',
  label:best?.reason||'Ссылок Ozon не найдено'
 };
}
window.VK_OZON={detect,findLinks};
})();