'use strict';
/* VK Parser 1.4 — двухэтапный поиск авторов и накопительная база.
   Хранение: приватные JSON-шарды в личном GitHub пользователя.
   Никакие токены не записываются в базу или localStorage. */
(function(){
const el=id=>document.getElementById(id);
const MAX_SHARDS=8, MAX_PER_SHARD=420, INDEX_PATH='vk-research/author-base';
const checkedFreshDays=21, profileFreshDays=30;
const store=new Map(), dirty=new Set();
let loaded=false,busy=false,halt=false,lastSearchIds=new Set(),lastProblems=[];
const sleep=ms=>new Promise(r=>setTimeout(r,ms)), timestamp=()=>new Date().toISOString();
const num=v=>v==null?null:(Number.isFinite(Number(v))?Number(v):null);
const rate=(x,n=2)=>x==null?null:Number(x.toFixed(n));
const median=xs=>{let a=xs.filter(x=>x!=null&&Number.isFinite(x)).sort((a,b)=>a-b);return !a.length?null:a.length%2?a[(a.length-1)/2]:(a[a.length/2-1]+a[a.length/2])/2;};
const progress=el('fastProgress'),info=el('fastStatus'),errbox=el('fastErrors');
const normRepo=()=>el('syncRepo').value.normalize('NFKC').trim().replace(/\s*\/\s*/g,'/').replace(/^https?:\/\/github\.com\//,'').replace(/\/$/,'').replace(/\.git$/,'');
const ghToken=()=>el('syncToken').value.trim();
const basePath=i=>INDEX_PATH+'/part-'+i+'.json';
const bucket=id=>Math.abs(Number(id))%MAX_SHARDS;
function fmtError(e){return e?.message||safeError(e);}
function mark(row){dirty.add(bucket(row.id));}
function entry(id){
 id=Number(id);if(!Number.isSafeInteger(id)||id===0)return null;
 if(!store.has(id)){
  const now=timestamp();
  const rec={id,kind:id>0?'user':'group',name:'',url:id>0?'https://vk.ru/id'+id:'https://vk.ru/club'+(-id),
   followers:null,closed:false,signals:[],sources:[],hits:0,score:0,seed_views:0,example_post_url:'',
   first_seen:now,last_seen:now,profile_checked_at:'',checked_at:'',qualification:'',reason:'',
   median_views:null,views_per_follower:null,engagement_per_view_percent:null,story_ratio:null,original_posts_180d:0};
  store.set(id,rec);mark(rec);
 }
 return store.get(id);
}
function add(id,kind,source,post=null,weight=1){
 const before=store.has(Number(id)),r=entry(id);if(!r)return;
 if(!before)lastSearchIds.add(r.id);
 r.hits=Math.min(50000,(r.hits||0)+1);
 r.score=Math.min(50000,(r.score||0)+Math.max(0,Math.min(8,weight)));
 r.seed_views=Math.max(r.seed_views||0,Number(post?.views?.count)||0);
 if(kind&&!r.signals.includes(kind))r.signals.push(kind);
 if(source&&!r.sources.includes(source))r.sources.push(source);
 if(post?.id&&post?.owner_id&&!r.example_post_url)r.example_post_url='https://vk.ru/wall'+post.owner_id+'_'+post.id;
 r.last_seen=timestamp();mark(r);
}
function fromPost(post,source){
 if(!post)return;
 if(post.owner_id)add(post.owner_id,'тематический пост',source,post,8);
 if(Number(post.owner_id)<0&&Number(post.signer_id)>0)add(post.signer_id,'подписанный автор',source,post,7);
 for(const cp of (post.copy_history||[]).slice(0,2))add(cp.owner_id??cp.from_id,'первоисточник репоста',source,post,5);
}
function qualityReject(r){
 const str=(r.name||'').toLocaleLowerCase('ru-RU');
 return /(пвз|пункт(?:ы|а)? выдачи|администраци[яи]|ваканси[ия]|оптовые продажи|ремонт квартир|салон красоты|автомойк[аи]|доставк[аи] еды|магазин|купить|служба доставки)/iu.test(str);
}
function eligible(r){
 if(r.closed||qualityReject(r))return false;
 if(r.kind==='group'&&!el('authorIncludeGroups').checked)return false;
 const cap=Number(el('authorMaxSubs').value);
 if(cap>0&&r.followers!==null&&Number(r.followers)>cap)return false;
 return true;
}
function scoreCompare(a,b){return (b.score||0)-(a.score||0)||(b.seed_views||0)-(a.seed_views||0);}
function fresh(date,days){return date&&Date.now()-Date.parse(date)<days*86400000;}
function updateView(){
 const all=[...store.values()],eligibleAll=all.filter(eligible).sort(scoreCompare);
 const qualified=all.filter(r=>r.qualification==='qualified').sort((a,b)=>(b.views_per_follower??-1)-(a.views_per_follower??-1));
 el('baseCount').textContent=store.size+' кандидатов в базе · '+eligibleAll.length+' с учётом текущих фильтров · '+qualified.length+' проверенных авторов';
 const tbody=el('candidateRows');tbody.replaceChildren();
 if(!eligibleAll.length){let cell=tbody.insertRow().insertCell();cell.colSpan=7;cell.textContent='Пока кандидатов нет';}
 for(const r of eligibleAll.slice(0,45)){
  const tr=tbody.insertRow();const state=r.qualification==='qualified'?'подошёл':r.qualification==='rejected'?'не подошёл':r.qualification==='error'?'ошибка проверки':'не проверен';
  for(const val of [r.name||('ID '+r.id),r.kind==='user'?'Личный':'Сообщество',r.followers??'неизвестно',r.score??0,r.seed_views??'—',state]){const td=tr.insertCell();td.textContent=val;}
  const td=tr.insertCell(),a=document.createElement('a');a.href=r.url;a.target='_blank';a.rel='noopener noreferrer';a.textContent='Открыть';td.append(a);
 }
 const results=el('authorRows');results.replaceChildren();
 for(const r of qualified.slice(0,80)){
  const tr=results.insertRow();
  for(const v of [r.name,r.followers??'—',r.median_views??'—',r.views_per_follower??'—',r.engagement_per_view_percent==null?'—':r.engagement_per_view_percent+'%',r.story_ratio==null?'—':r.story_ratio+'%',r.original_posts_180d])tr.insertCell().textContent=v;
  const td=tr.insertCell(),a=document.createElement('a');a.href=r.url;a.target='_blank';a.rel='noopener noreferrer';a.textContent='Открыть';td.append(a);
 }
 if(!qualified.length){let td=results.insertRow().insertCell();td.colSpan=8;td.textContent='Проверенных авторов пока нет';}
 el('authorCount').textContent=String(qualified.length);
 el('candidateCount').textContent=String(eligibleAll.length);
 el('candidateExport').disabled=!store.size;
 el('authorExport').disabled=!qualified.length;
 el('authorPostExport').disabled=!authorPostRecords.length;
}
function parseTokenRepository(){
 const repo=normRepo();
 if(!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repo))throw Error('Укажите закрытый репозиторий: владелец/название');
 if(!ghToken())throw Error('В поле передачи в GitHub укажите токен. В чат его не присылайте.');
 return repo;
}
async function gh(path,options={}){
 const repo=parseTokenRepository();
 const url='https://api.github.com/repos/'+repo+(path.startsWith('/')?path:'/'+path);
 const res=await fetch(url,{...options,headers:{'Authorization':'Bearer '+ghToken(),'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28',...(options.headers||{})},cache:'no-store'});
 const body=await res.json().catch(()=>({}));
 if(res.status===404&&options.allow404)return null;
 if(!res.ok)throw Error('GitHub HTTP '+res.status+': '+(body.message||'Ошибка'));
 return body;
}
function from64(str){
 const raw=atob(str.replace(/\s/g,'')),bytes=Uint8Array.from(raw,ch=>ch.charCodeAt(0));
 return new TextDecoder().decode(bytes);
}
function to64(str){
 const bytes=new TextEncoder().encode(str);let raw='';
 for(let i=0;i<bytes.length;i+=8192)raw+=String.fromCharCode(...bytes.subarray(i,i+8192));
 return btoa(raw);
}
async function verifyRepoPrivate(){
 const data=await gh('');
 if(data?.private!==true)throw Error('Репозиторий для базы должен быть Private.');
}
function safeEntries(j){
 if(Array.isArray(j))return j;
 return Array.isArray(j?.candidates)?j.candidates:[];
}
async function readPart(i){
 const file=await gh('contents/'+basePath(i),{allow404:true});
 if(!file)return [];
 if(!file.content)throw Error('Не удалось прочесть большой файл базы #'+i+'. Нужно уменьшить размер шарда.');
 return safeEntries(JSON.parse(from64(file.content)));
}
async function loadBase({silent=false}={}){
 if(!silent)info.textContent='Читаем накопительную базу из закрытого GitHub...';
 await verifyRepoPrivate();
 const incoming=(await Promise.all(Array.from({length:MAX_SHARDS},(_,i)=>readPart(i)))).flat();
 // Если пользователь уже нашёл новых кандидатов в текущем сеансе, не теряем их.
 for(const row of incoming){
  const id=Number(row.id);if(!Number.isSafeInteger(id)||!id)continue;
  const existing=store.get(id);
  if(!existing){store.set(id,row);continue;}
  const oldNewer=Date.parse(existing.checked_at||0)>Date.parse(row.checked_at||0);
  store.set(id,{...existing,...row,
   checked_at:oldNewer?existing.checked_at:row.checked_at,
   qualification:oldNewer?existing.qualification:row.qualification,
   reason:oldNewer?existing.reason:row.reason,
   signals:[...new Set([...(existing.signals||[]),...(row.signals||[])])],
   sources:[...new Set([...(existing.sources||[]),...(row.sources||[])])],
   score:Math.max(existing.score||0,row.score||0),
   hits:Math.max(existing.hits||0,row.hits||0)});
 }
 loaded=true;updateView();
 if(!silent)info.textContent='База загружена: '+store.size+' кандидатов. Проверенных не нужно опрашивать повторно в ближайшие '+checkedFreshDays+' дней.';
 return incoming.length;
}
async function saveBase(){
 if(!loaded)await loadBase({silent:true});
 await verifyRepoPrivate();
 let saved=0;
 for(const i of [...dirty].sort((a,b)=>a-b)){
  const all=[...store.values()].filter(r=>bucket(r.id)===i);
  // Ограничение размера шардов для надёжного чтения через GitHub Contents API.
  all.sort((a,b)=>Number(b.qualification==='qualified')-Number(a.qualification==='qualified')||Date.parse(b.last_seen||0)-Date.parse(a.last_seen||0));
  if(all.length>MAX_PER_SHARD){
   const remove=all.slice(MAX_PER_SHARD);for(const r of remove)store.delete(r.id);
   lastProblems.push('Часть старых кандидатов удалена из ограниченной базы: '+remove.length+' (шард '+i+')');
  }
  const rows=all.slice(0,MAX_PER_SHARD);
  const content=to64(JSON.stringify({version:1,saved_at:timestamp(),candidates:rows},null,2));
  const path='contents/'+basePath(i),existing=await gh(path,{allow404:true});
  const body={message:'VK author base: update shard '+i,content};
  if(existing?.sha)body.sha=existing.sha;
  await gh(path,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  dirty.delete(i);saved++;
 }
 el('syncStatus').textContent='Накопительная база сохранена в закрытый GitHub: '+store.size+' кандидатов, обновлено файлов: '+saved+'.';
 return saved;
}
async function saveIfEnabled(){
 if(!el('syncEnabled').checked)return 'Автосохранение выключено';
 if(!ghToken())return 'Нужен GitHub-токен в разделе 2, база пока только на экране';
 try{const n=await saveBase();return 'База отправлена в GitHub ('+n+' частей)';}
 catch(e){return 'База в GitHub НЕ сохранена: '+fmtError(e);}
}
function markProfile(r,p,type){
 if(!p||!r)return;
 r.kind=type;
 r.name=type==='user'?[p.first_name,p.last_name].filter(Boolean).join(' '):(p.name||r.name);
 r.url='https://vk.ru/'+(p.screen_name||(type==='user'?'id'+r.id:'club'+(-r.id)));
 const value=num(type==='user'?p.followers_count:p.members_count);
 if(value!==null)r.followers=value;
 r.closed=Boolean(p.is_closed===true||p.is_closed===1||p.is_closed===2||p.deactivated);
 if(type==='user'||value!==null)r.profile_checked_at=timestamp();
 mark(r);
}
async function refreshProfiles(ids,token,delay){
 const only=[...new Set(ids)].map(i=>store.get(i)).filter(Boolean)
  .filter(r=>!fresh(r.profile_checked_at,profileFreshDays));
 const person=only.filter(r=>r.id>0),groups=only.filter(r=>r.id<0 && el('authorIncludeGroups').checked);
 const batches=(rows,size)=>Array.from({length:Math.ceil(rows.length/size)},(_,k)=>rows.slice(k*size,(k+1)*size));
 for(const list of batches(person,100)){
  if(halt)break;
  try{
   const raw=await apiCall('users.get',{user_ids:list.map(x=>x.id).join(','),fields:'screen_name,followers_count,is_closed,verified'},token);
   for(const p of (Array.isArray(raw)?raw:raw?.items||[]))markProfile(store.get(Number(p.id)),p,'user');
  }catch(e){lastProblems.push('users.get (пакет): '+fmtError(e));}
  await sleep(delay);
 }
 for(const list of batches(groups,80)){
  if(halt)break;
  try{
   const raw=await apiCall('groups.getById',{group_ids:list.map(x=>-x.id).join(','),fields:'members_count,description'},token);
   const rows=Array.isArray(raw)?raw:(raw?.groups||raw?.items||[]);
   for(const p of rows)markProfile(store.get(-Number(p.id)),p,'group');
  }catch(e){lastProblems.push('groups.getById (пакет): '+fmtError(e));}
  await sleep(delay);
 }
}
async function vkToken(){
 if(typeof vkBridge==='undefined')throw Error('Откройте приложение внутри ВКонтакте.');
 const a=await vkBridge.send('VKWebAppGetAuthToken',{app_id:APP_ID,scope:'wall'});
 if(!a?.access_token)throw Error('ВКонтакте не выдал токен доступа');
 return a.access_token;
}
function allKeywordLines(id,max){
 return [...new Set(el(id).value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean))].slice(0,max);
}
async function discover(token){
 const mode=el('authorMode').value,delay=Number(el('delay').value);
 const topics=allKeywordLines('authorKeywords',12),communities=allKeywordLines('authorCommunities',30),terms=allKeywordLines('groupKeywords',12);
 const tasks=[];
 if(mode==='both'||mode==='keywords')for(const topic of topics)tasks.push({kind:'news',query:topic});
 if(mode==='both'||mode==='communities')for(const source of communities)tasks.push({kind:'wall',query:source});
 if(el('enableGroupSearch').checked)for(const term of terms)tasks.push({kind:'groups',query:term});
 if(!tasks.length)throw Error('Заполните поисковые темы, сообщества или запросы для поиска групп');
 let completed=0;progress.max=tasks.length;progress.value=0;
 for(const task of tasks){
  if(halt)break;
  info.textContent='Быстрый поиск '+(completed+1)+'/'+tasks.length+' · '+task.kind+': '+task.query;
  try{
   if(task.kind==='news'){
    let next='',last='';
    for(let i=0;i<3&&!halt;i++){
     const data=await apiCall('newsfeed.search',{q:task.query,extended:1,count:100,start_time:Math.floor(Date.now()/1000)-180*86400,...(next?{start_from:next}:{})},token);
     const posts=Array.isArray(data?.items)?data.items:[];
     for(const post of posts)fromPost(post,'тема: '+task.query);
     last=next;next=data?.next_from||'';
     if(!posts.length||!next||next===last)break;
     await sleep(delay);
    }
   }else if(task.kind==='wall'){
    const src=parseSource(task.query);
    const data=await apiCall('wall.get',{...paramsFor(src),count:100},token);
    for(const p of (data?.items||[])){
     if(Number(p.signer_id)>0)add(p.signer_id,'подписанный пост','группа: '+src.key,p,7);
     if(Number(p.owner_id)<0&&Number(p.from_id)>0)add(p.from_id,'публикация участника','группа: '+src.key,p,6);
     for(const cp of (p.copy_history||[]).slice(0,3))add(cp.owner_id??cp.from_id,'первоисточник репоста','группа: '+src.key,p,6);
    }
    if(el('authorCommenters').checked){
     for(const p of (data?.items||[]).slice(0,5)){
      if(halt)break;if((p.comments?.count||0)<1)continue;
      try{
       const resp=await apiCall('wall.getComments',{owner_id:p.owner_id,post_id:p.id,count:50},token);
       for(const c of (resp?.items||[]))if(Number(c.from_id)>0)add(c.from_id,'комментарий','группа: '+src.key,p,0.3);
      }catch(e){lastProblems.push('Комментарии '+src.key+': '+fmtError(e));}
      await sleep(delay);
     }
    }
   }else if(task.kind==='groups'){
    for(let pg=0;pg<2&&!halt;pg++){
     const data=await apiCall('groups.search',{q:task.query,count:100,offset:pg*100},token);
     const rows=Array.isArray(data?.items)?data.items:[];
     for(const g of rows){
      if(!g?.id)continue;
      add(-Number(g.id),'найдено сообщество','поиск групп: '+task.query,null,2);
      const cand=store.get(-Number(g.id));if(cand&&!cand.name)markProfile(cand,g,'group');
     }
     if(rows.length<100)break;
     await sleep(delay);
    }
   }
  }catch(e){lastProblems.push(task.kind+' «'+task.query+'»: '+fmtError(e));}
  completed++;progress.value=completed;await sleep(delay);
 }
 return completed;
}
function sampleStoryRatio(posts){
 const story=/(?:^|[^\p{L}])(?:я|мне|меня|мой|моя|мы|муж|жена|мама|реб[её]нок|дочка|сын|однажды|вчера|потом|оказалось|сказала|подумала|расскажу|история)(?=$|[^\p{L}])/iu;
 const long=posts.filter(p=>(p.text||'').trim().length>=130);
 if(!posts.length)return null;
 return rate(100*long.filter(p=>story.test(p.text||'')).length/posts.length,1);
}
async function inspect(r,token,minimum,samples){
 // Проверяем только открытую стену. Результаты не трактуем как репрезентативную выборку для автора.
 const postData=await apiCall('wall.get',{owner_id:r.id,count:samples,offset:0},token);
 if(!Array.isArray(postData?.items))throw Error('wall.get вернул ответ без items');
 const newest=Math.floor(Date.now()/1000)-180*86400;
 const posts=postData.items.filter(p=>Number(p.owner_id)===r.id&&Number(p.date)>=newest&&!p.copy_history?.length);
 if(posts.length<2){r.qualification='rejected';r.reason='Мало оригинальных постов за 180 дней';return;}
 const mv=median(posts.map(p=>num(p.views?.count)).filter(v=>v!==null));
 if(mv===null){r.qualification='rejected';r.reason='Нет данных о просмотрах';return;}
 if(mv<minimum){r.qualification='rejected';r.reason='Низкая медиана просмотров: '+mv;return;}
 const ers=posts.map(p=>{
  const views=num(p.views?.count);
  return views>0?100*((num(p.likes?.count)||0)+(num(p.comments?.count)||0)+(num(p.reposts?.count)||0))/views:null;
 }).filter(v=>v!==null);
 Object.assign(r,{qualification:'qualified',reason:'',median_views:rate(mv,0),views_per_follower:r.followers>0?rate(mv/r.followers,2):null,
   engagement_per_view_percent:rate(median(ers),2),story_ratio:sampleStoryRatio(posts),original_posts_180d:posts.length,
   median_likes:median(posts.map(p=>num(p.likes?.count)||0)),median_comments:median(posts.map(p=>num(p.comments?.count)||0)),
   median_reposts:median(posts.map(p=>num(p.reposts?.count)||0))});
 for(const p of posts){
  const row={author_id:r.id,author_name:r.name,...normalize(p,{key:'author:'+r.id})};
  if(!authorPostRecords.some(x=>x.post_url===row.post_url))authorPostRecords.push(row);
 }
}
function candidateFields(){
 return ['id','kind','name','url','followers','closed','score','hits','seed_views','qualification','reason','checked_at','median_views','views_per_follower','engagement_per_view_percent','story_ratio','original_posts_180d','signals','sources','first_seen','last_seen','example_post_url'];
}
function exportRows(items,cols,name){
 if(!items.length)return;
 const line=(r,k)=>csvCell(Array.isArray(r[k])?r[k].join(' | '):r[k]);
 const rows=[cols.map(csvCell).join(';'),...items.map(r=>cols.map(k=>line(r,k)).join(';'))];
 const blob=new Blob(['\ufeff'+rows.join('\r\n')],{type:'text/csv;charset=utf-8'});
 const url=URL.createObjectURL(blob),a=document.createElement('a');
 a.href=url;a.download=name+'_'+new Date().toISOString().slice(0,10)+'.csv';
 document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
el('candidateExport').addEventListener('click',()=>exportRows([...store.values()].sort(scoreCompare),candidateFields(),'vk_candidates'));
el('authorExport').addEventListener('click',()=>exportRows([...store.values()].filter(r=>r.qualification==='qualified'),
 ['name','url','kind','followers','median_views','views_per_follower','engagement_per_view_percent','story_ratio','original_posts_180d','signals','sources','checked_at'],'vk_authors'));
el('authorPostExport').addEventListener('click',()=>exportRows(authorPostRecords,['author_id','author_name',...csvFields],'vk_author_posts'));
el('stopAuthors').addEventListener('click',()=>{halt=true;stopRequested=true;el('stopAuthors').disabled=true;info.textContent+=' \nОстанавливаем после текущего запроса...';});
function setBusy(value){
 busy=value;running=value;
 for(const id of ['fastFind','verifyAuthors','loadAuthorBase'])el(id).disabled=value;
 el('stopAuthors').disabled=!value;
}
function showProblems(){
 errbox.textContent=lastProblems.length?'Ограничения или ошибки ('+lastProblems.length+'):\n'+lastProblems.slice(0,18).join('\n'):'Ошибок VK API не обнаружено';
}
el('loadAuthorBase').addEventListener('click',async()=>{
 if(busy)return;setBusy(true);
 try{await loadBase();}catch(e){info.textContent='Не удалось загрузить базу: '+fmtError(e);}
 finally{setBusy(false);}
});
el('fastFind').addEventListener('click',async()=>{
 if(busy)return;setBusy(true);halt=false;stopRequested=false;lastProblems=[];lastSearchIds=new Set();
 const started=Date.now();
 try{
  if(!loaded&&ghToken())await loadBase({silent:true});
  const token=await vkToken();
  const completed=await discover(token);
  const seen=[...store.values()].filter(r=>r.last_seen&&Date.now()-Date.parse(r.last_seen)<10*60*1000).map(r=>r.id);
  info.textContent='Обновляем число подписчиков пачками (без загрузки каждой стены)...';
  await refreshProfiles(seen,token,Number(el('delay').value));
  updateView();
  const saved=await saveIfEnabled();
  info.textContent=(halt?'Остановлено.':'Быстрый поиск завершён.')+
   '\nТем обработано: '+completed+'; новых кандидатов: '+lastSearchIds.size+'; всего в базе: '+store.size+
   '\nПрошло '+Math.round((Date.now()-started)/1000)+' сек. · '+saved+
   '\nДля оценки охватов нажмите «Проверить лучших».';
  showProblems();
 }catch(e){info.textContent='Ошибка быстрого поиска: '+fmtError(e);showProblems();}
 finally{setBusy(false);halt=false;stopRequested=false;}
});
el('verifyAuthors').addEventListener('click',async()=>{
 if(busy)return;setBusy(true);halt=false;stopRequested=false;lastProblems=[];
 const started=Date.now(),max=Number(el('authorCandidateLimit').value),sample=Number(el('authorSample').value),minViews=Number(el('authorMinViews').value);
 try{
  if(!loaded&&ghToken())await loadBase({silent:true});
  if(!store.size)throw Error('База пуста. Сначала выполните быстрый поиск.');
  const list=[...store.values()].filter(eligible)
    .filter(r=>el('authorForceRecheck').checked||!fresh(r.checked_at,checkedFreshDays))
    .sort(scoreCompare).slice(0,max);
  if(!list.length){info.textContent='Новых для проверки нет. База уже проверена недавно; можно включить повторную проверку.';return;}
  const token=await vkToken();
  await refreshProfiles(list.map(r=>r.id),token,Number(el('delay').value));
  const selected=list.filter(eligible);
  progress.max=Math.max(1,selected.length);progress.value=0;
  let qualifiedNow=0,checked=0;
  for(const r of selected){
   if(halt)break;
   info.textContent='Глубокая проверка '+(checked+1)+'/'+selected.length+
    '\n'+(r.name||r.url)+'\nНовых подходящих: '+qualifiedNow;
   try{
    await inspect(r,token,minViews,sample);
    r.checked_at=timestamp();
    if(r.qualification==='qualified')qualifiedNow++;
    mark(r);
   }catch(e){r.qualification='error';r.reason=fmtError(e);mark(r);lastProblems.push('Автор '+r.id+': '+fmtError(e));}
   checked++;progress.value=checked;
   updateView();await sleep(Number(el('delay').value));
  }
  const saved=await saveIfEnabled();
  info.textContent=(halt?'Проверка остановлена.':'Проверка завершена.')+
   '\nПроверено: '+checked+'; подошло новых: '+qualifiedNow+'; всего проверенных подходящих: '+[...store.values()].filter(r=>r.qualification==='qualified').length+
   '\nПрошло '+Math.round((Date.now()-started)/1000)+' сек. · '+saved;
  if(el('syncEnabled').checked&&ghToken()&&authorPostRecords.length){
   // Отдельно сохраняем полные тексты подтверждённых авторов для анализа.
   authorsRecords=[...store.values()].filter(r=>r.qualification==='qualified').map(r=>({
     author_id:r.id,author_url:r.url,name:r.name,type:r.kind==='user'?'личный профиль':'сообщество',
     followers:r.followers,median_views:r.median_views,views_per_follower:r.views_per_follower,
     engagement_per_view_percent:r.engagement_per_view_percent,story_ratio:r.story_ratio,
     original_posts_180d:r.original_posts_180d,discovery_sources:r.sources.join(' | ')
   }));
   try{await githubSaveResults();info.textContent+='\nТексты проверенных авторов сохранены отдельной выгрузкой.';}
   catch(e){info.textContent+='\nНе удалось сохранить тексты: '+fmtError(e);}
  }
  showProblems();
 }catch(e){info.textContent='Ошибка проверки: '+fmtError(e);showProblems();}
 finally{setBusy(false);halt=false;stopRequested=false;}
});
el('authorIncludeGroups').addEventListener('change',updateView);
el('authorMaxSubs').addEventListener('change',updateView);
window.VKAuthorBase={save:saveBase,load:loadBase,count:()=>store.size,render:updateView};
updateView();
})();
