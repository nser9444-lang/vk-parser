'use strict';
/* VK Story Hunter 1.8 — scouting 100 long-form authors, independent of Ozon filter.
   Public counts are not evidence of organic reach or actual purchases. */
(function(){
 const E=id=>document.getElementById(id);
 const vk=window.VKAuthorBase;
 const lsKey='vk_story_hunter_v18';
 const map=new Map();
 let running=false,stopped=false,token='',errList=[],ghLoaded=false;
 const now=()=>new Date().toISOString();
 const wait=ms=>new Promise(r=>setTimeout(r,ms));
 const numeric=v=>v==null?null:(Number.isFinite(Number(v))?Number(v):null);
 const median=a=>{const q=a.filter(x=>x!=null&&Number.isFinite(x)).sort((x,y)=>x-y);return q.length?(q.length%2?q[(q.length-1)/2]:(q[q.length/2-1]+q[q.length/2])/2):null;};
 const round=x=>x==null?null:Math.round(x);
 const status=s=>E('huntStatus').textContent=s;
 const html='<section id="huntPanel" class="panel">'+
 '<h2>🎯 Поиск 100 авторов: длинные истории, 20 000+ просмотров</h2>'+
 '<p class="hint">Отбираем авторов до 50 тыс. подписчиков. Сначала смотрим просмотры и длинные тексты; реклама Ozon не обязательна. Отдельно отмечаем товарные интеграции. Длина текста — только первый признак сторителлинга, окончательную проверку делаем вручную.</p>'+
 '<label for="huntText">Ссылки сообществ и личных страниц, по одной на строку</label>'+
 '<textarea id="huntText" placeholder="https://vk.ru/club241058375\nhttps://vk.ru/polinabiz" style="min-height:90px"></textarea>'+
 '<div class="grid"><div><label for="huntFile">Или загрузить CSV / TXT из Церебро</label><input id="huntFile" type="file" accept=".csv,.txt,text/plain,text/csv"></div>'+
 '<div><label for="huntScope">Очередь проверки</label><select id="huntScope"><option value="imported">Только добавленные ссылки</option><option value="all">Все кандидаты из базы GitHub</option></select></div></div>'+
 '<div class="grid"><div><label for="huntBatch">Количество авторов за запуск</label><select id="huntBatch"><option value="20">20</option><option value="50" selected>50</option><option value="100">100</option><option value="200">200</option><option value="350">350 (все наши новые)</option><option value="1000">1000 (вся база)</option></select></div>'+
 '<div><label for="huntRecheck">Проверять повторно</label><select id="huntRecheck"><option value="no" selected>Только новые или старше 14 дней</option><option value="yes">Всех, в том числе проверенных</option></select></div></div>'+
 '<div class="actions"><button id="huntLoad" class="secondary" type="button">Загрузить базу GitHub</button><button id="huntImportSeeds" class="secondary" type="button">Загрузить наши 317 ссылок</button><button id="huntImport" type="button">1. Добавить ссылки</button><button id="huntScan" type="button">2. Проверить охваты</button><button id="huntExport" class="secondary" type="button">Скачать результаты CSV</button><button id="huntStop" class="danger" type="button" disabled>Стоп</button></div>'+
 '<progress id="huntProgress" value="0" max="1"></progress>'+
 '<div id="huntStatus" class="status">Загрузите базу из GitHub или добавьте список. Ключи доступа не сохраняются.</div>'+
 '<div class="stats" id="huntCounts">—</div>'+
 '<div class="table-wrap"><table><thead><tr><th>Автор</th><th>Подписчики</th><th>Длинных</th><th>Доля</th><th>Медиана длинных</th><th>Длинных ≥20к</th><th>Интеграции*</th><th>Итог</th><th>Пост</th></tr></thead><tbody id="huntRows"></tbody></table></div>'+
 '<p class="hint">Критерии прохождения предварительного скрининга: 1–50 тыс. подписчиков, хотя бы 10 оригинальных текстов от 800 символов, доля длинных не ниже 40%, медиана их просмотров от 20 000. Анализируем публикации возрастом 7–180 дней. *Ссылки и рекламные маркеры — не подтверждение продаж. Просмотры не равны уникальным охватам.</p></section>';
 E('authorFinder').insertAdjacentHTML('afterend',html);
 try{
  const saved=JSON.parse(localStorage.getItem(lsKey)||'[]');
  if(Array.isArray(saved))for(const x of saved)if(Number.isSafeInteger(Number(x.id)))map.set(Number(x.id),x);
 }catch(_){}
 function persist(){
  try{localStorage.setItem(lsKey,JSON.stringify([...map.values()]));}
  catch(e){status('Не удалось сохранить локальную копию: '+e.message+'. Скачайте CSV.');}
 }
 function merge(x){if(!x||!Number.isSafeInteger(Number(x.id))||Number(x.id)===0)return null;
  const id=Number(x.id),old=map.get(id)||{id,url:id<0?'https://vk.ru/club'+(-id):'https://vk.ru/id'+id};
  const out={...old,...x,id};
  if(out.hunt_checked_at&&out.followers>0&&out.followers<=50000&&out.hunt_long_count>=10&&out.hunt_median_views>=20000){
   out.hunt_potential=out.hunt_long_share<.4;
   if(out.hunt_potential)out.hunt_reason='Есть 10+ длинных постов ≥20к по медиане; доля длинных <40%';
  }
  map.set(id,out);return out;}
 function rows(){return [...map.values()].filter(x=>x.hunt_checked_at).sort((a,b)=>Number(!!b.hunt_pass)-Number(!!a.hunt_pass)||Number(!!b.hunt_potential)-Number(!!a.hunt_potential)||(b.hunt_median_views||0)-(a.hunt_median_views||0));}
 function render(){
  const all=[...map.values()],done=rows(),passed=done.filter(x=>x.hunt_pass),body=E('huntRows');
  E('huntCounts').textContent='В базе: '+all.length+' · проверено: '+done.length+' · основной список: '+passed.length+' · дополнительные перспективные: '+done.filter(x=>x.hunt_potential).length+' / цель 100';
  body.replaceChildren();
  for(const r of done.slice(0,200)){
   const tr=document.createElement('tr');
   if(r.hunt_pass)tr.style.background='#e9f9ef';else if(r.hunt_potential)tr.style.background='#fff5d7';
   const values=[r.name||r.url,r.followers??'—',r.hunt_long_count??'—',r.hunt_long_share==null?'—':Math.round(100*r.hunt_long_share)+'%',r.hunt_median_views??'—',r.hunt_over20_count??'—',r.hunt_ad_count??'—',r.hunt_reason??''];
   values.forEach((v,i)=>{const td=tr.insertCell();if(i===0){const a=document.createElement('a');a.href=r.url;a.target='_blank';a.rel='noopener noreferrer';a.textContent=String(v);td.append(a);}else td.textContent=String(v);});
   const td=tr.insertCell();if(r.hunt_example_url){const a=document.createElement('a');a.href=r.hunt_example_url;a.target='_blank';a.rel='noopener noreferrer';a.textContent='Посмотреть';td.append(a);}
   body.append(tr);
  }
 }
 function extract(s){
  const links=[...String(s||'').matchAll(/(?:https?:\/\/)?(?:m\.)?vk\.(?:ru|com)\/(?:club\d+|public\d+|id\d+|(?:clip|wall)-?\d+_\d+|[a-zA-Z0-9_.-]{3,100})/giu)].map(x=>x[0]);
  const bare=String(s||'').split(/\r?\n/).map(x=>x.trim()).filter(x=>/^(?:club|public|id)\d+$/i.test(x));
  return [...new Set([...links,...bare])];
 }
 async function getToken(){
  if(token)return token;
  if(typeof vkBridge==='undefined')throw Error('Откройте парсер внутри ВКонтакте.');
  const x=await vkBridge.send('VKWebAppGetAuthToken',{app_id:APP_ID,scope:'wall'});
  if(!x?.access_token)throw Error('ВК не выдал доступ к API.');
  token=x.access_token;return token;
 }
 async function idFor(raw){
  const key=String(raw).trim().replace(/^https?:\/\/(?:m\.)?vk\.(?:com|ru)\//i,'').split(/[?#]/)[0].split('/')[0];
  let m=key.match(/^(?:club|public)(\d+)$/i);if(m)return -Number(m[1]);
  m=key.match(/^id(\d+)$/i);if(m)return Number(m[1]);
  m=key.match(/^(?:clip|wall)(-?\d+)_\d+$/i);if(m)return Number(m[1]);
  if(!/^[\w.-]{3,100}$/.test(key))return null;
  let x=null;try{x=await apiCall('utils.resolveScreenName',{screen_name:key},await getToken());}catch(_){}
  if(['group','page','event'].includes(x?.type))return -Number(x.object_id);
  if(x?.type==='user')return Number(x.object_id);
  const wall=await apiCall('wall.get',{domain:key,count:1},await getToken());
  return Number(wall?.items?.[0]?.owner_id)||null;
 }
 async function ghSaveBase(){
  if(!E('syncEnabled').checked||!E('syncToken').value.trim())return 'Автосохранение в GitHub выключено';
  if(!ghLoaded){await vk.load();ghLoaded=true;syncFromBase();}
  for(const r of map.values())if(r.hunt_imported||r.hunt_checked_at)
   vk.upsertFromHunter({...r,hunter_imported:!!r.hunt_imported});
  await vk.save();return 'База обновлена в закрытом GitHub';
 }
 function syncFromBase(){
  const all=vk.list();
  for(const x of all)merge({...x,...map.get(Number(x.id))});
  persist();render();
  return all.length;
 }
 E('huntLoad').addEventListener('click',async()=>{
  if(running)return;running=true;
  try{await vk.load();ghLoaded=true;const n=syncFromBase();status('Загружено из GitHub: '+n+' кандидатов. Можно проверить уже найденных или добавить список Церебро.');}
  catch(e){status('Ошибка загрузки базы: '+(e.message||e));}
  finally{running=false;}
 });
 
 E('huntImportSeeds').addEventListener('click',async()=>{
  if(running)return;
  const ghToken=E('syncToken').value.trim();
  if(!ghToken){status('Введите GitHub-токен в разделе 2. Он нужен для чтения нашей закрытой базы из 317 ссылок.');return;}
  E('huntImportSeeds').disabled=true;
  try{
   const j=await githubRequest('https://api.github.com/repos/nser9444-lang/vk-parser-data/contents/vk-research/author-seeds-2026-11-12.csv',ghToken);
   if(!j.content)throw Error('GitHub не вернул список ссылок');
   const raw=atob(j.content.replace(/\s/g,''));
   const bytes=Uint8Array.from(raw,c=>c.charCodeAt(0));
   const txt=new TextDecoder().decode(bytes);
   const found=extract(txt);
   if(found.length<300)throw Error('Список неполный: '+found.length+' ссылок');
   E('huntText').value=found.join('\n');
   status('Из GitHub получено '+found.length+' ссылок; добавляю в общую базу...');
   E('huntImport').click();
  }catch(e){status('Не удалось получить 317 ссылок: '+(e.message||e));}
  finally{E('huntImportSeeds').disabled=false;}
 });

 E('huntImport').addEventListener('click',async()=>{
  if(running)return;running=true;E('huntImport').disabled=true;
  try{
   const file=E('huntFile').files?.[0],s=E('huntText').value+'\n'+(file?await file.text():'');
   const found=extract(s);if(!found.length)throw Error('Не найдены ссылки. Выберите CSV или вставьте адреса ВК.');
   let created=0,failed=0,rank=0;for(const url of found){rank++;
    try{const id=await idFor(url);if(!Number.isSafeInteger(id)||id===0){failed++;continue;}
    const was=map.has(id);
    merge({id,hunt_imported:true,hunt_priority:found.length-rank+1,hunt_imported_at:now(),url:map.get(id)?.url||(id<0?'https://vk.ru/club'+(-id):'https://vk.ru/id'+id)});
    if(!was)created++;
    }catch(e){failed++;errList.push('Импорт '+url+': '+(e.message||e));}
   }
   persist();render();
   const saved=await ghSaveBase();
   status('Получено ссылок: '+found.length+'; новых: '+created+'; ошибок: '+failed+'. '+saved);
  }catch(e){status('Ошибка импорта: '+(e.message||e));}
  finally{running=false;E('huntImport').disabled=false;}
 });
 async function profiles(targets){
  const delay=Number(E('delay').value)||700,todo=targets.filter(r=>!r.followers);
  for(let start=0;start<todo.length;start+=80){
   if(stopped)break;
   const chunk=todo.slice(start,start+80);
   for(const group of [chunk.filter(x=>x.id<0),chunk.filter(x=>x.id>0)]){
    if(!group.length)continue;
    try{
     const data=group[0].id<0?
      await apiCall('groups.getById',{group_ids:group.map(x=>-x.id).join(','),fields:'members_count,description'},await getToken()):
      await apiCall('users.get',{user_ids:group.map(x=>x.id).join(','),fields:'screen_name,followers_count,is_closed'},await getToken());
     const list=Array.isArray(data)?data:(data?.groups||data?.items||[]);
     for(const v of list){
      const id=group[0].id<0?-Number(v.id):Number(v.id);
      const r=map.get(id);if(!r)continue;
      r.name=v.name||[v.first_name,v.last_name].filter(Boolean).join(' ')||r.name;
      r.followers=numeric(v.members_count??v.followers_count);
      r.url='https://vk.ru/'+(v.screen_name||(id<0?'club'+(-id):'id'+id));
      r.closed=Boolean(v.is_closed===true||v.is_closed===1||v.deactivated);
     }
    }catch(e){errList.push('Профили: '+(e.message||e));}
    await wait(delay);
   }
  }
 }
 function evaluate(r,posts){
  const sec=Date.now()/1000,min=sec-180*86400,max=sec-7*86400;
  const visible=posts.filter(p=>p&&Number(p.owner_id)===r.id&&!p.is_pinned&&!p.copy_history?.length&&Number(p.date)>=min&&Number(p.date)<=max);
  const long=visible.filter(p=>String(p.text||'').trim().length>=800&&numeric(p.views?.count)!=null);
  const mv=median(long.map(p=>numeric(p.views?.count)));
  const detector=window.VK_OZON;
  const ads=visible.filter(p=>{
   const s=String(p.text||'');let oz='none';
   try{oz=detector?.detect(p)?.grade||'none';}catch(_){}
   return oz!=='none'||/реклама[.: ]|информация о рекламодател|advref|s\.ozon\.ru|ozon\.ru/i.test(s);
  });
  Object.assign(r,{hunt_checked_at:now(),hunt_sample_count:visible.length,
   hunt_long_count:long.length,hunt_long_share:visible.length?Math.round(1000*long.length/visible.length)/1000:0,
   hunt_median_views:round(mv),hunt_over20_count:long.filter(p=>numeric(p.views?.count)>=20000).length,
   hunt_ad_count:ads.length,hunt_example_url:long.length?'https://vk.ru/wall'+r.id+'_'+(long.find(p=>numeric(p.views?.count)>=20000)||long[0]).id:'',
   hunt_ad_example_url:ads.length?'https://vk.ru/wall'+r.id+'_'+ads[0].id:''});
  r.hunt_pass=!!(r.followers>0&&r.followers<=50000&&long.length>=10&&r.hunt_long_share>=.4&&mv>=20000);
  r.hunt_potential=!!(r.followers>0&&r.followers<=50000&&long.length>=10&&r.hunt_long_share<.4&&mv>=20000);
  r.hunt_reason=r.hunt_pass?'Прошёл по метрикам · проверить вручную':(!r.followers?'подписчики не получены':r.followers>50000?'более 50к':long.length<10?'длинных меньше 10':r.hunt_long_share<.4?'длинных менее 40%':'медиана длинных <20к');
  if(r.hunt_pass||r.hunt_potential){
   for(const p of [...long.slice(0,45),...ads.slice(0,15)]){
    const row={author_id:r.id,author_name:r.name,...normalize(p,{key:'story-hunter:'+r.id})};
    if(!authorPostRecords.some(x=>x.post_url===row.post_url))authorPostRecords.push(row);
   }
  }
 }
 E('huntStop').addEventListener('click',()=>{stopped=true;status('Остановка после текущего запроса…');});
 E('huntScan').addEventListener('click',async()=>{
  if(running)return;running=true;stopped=false;errList=[];E('huntScan').disabled=true;E('huntStop').disabled=false;
  let checked=0,pCount=0,errors=0;
  try{
   if(E('syncToken').value.trim()&&!ghLoaded){await vk.load();ghLoaded=true;syncFromBase();}
   const scope=E('huntScope').value,recheck=E('huntRecheck').value==='yes',time=Date.now();
   const eligible=[...map.values()].filter(x=>(scope==='all'||x.hunt_imported)&&!x.closed&&
     (x.followers==null||x.followers<=50000)&&
     (recheck||!x.hunt_checked_at||time-Date.parse(x.hunt_checked_at)>14*86400000))
     .sort((a,b)=>Number(!!b.hunt_imported)-Number(!!a.hunt_imported)||
       (b.hunt_priority||0)-(a.hunt_priority||0)||
       (b.seed_views||0)-(a.seed_views||0)||
       (b.score||0)-(a.score||0)).slice(0,Number(E('huntBatch').value));
   if(!eligible.length){status('Новых кандидатов нет. Добавьте CSV, выберите «Все из базы» или включите перепроверку.');return;}
   await getToken();await profiles(eligible);
   E('huntProgress').value=0;E('huntProgress').max=eligible.length;
   for(const r of eligible){
    if(stopped)break;
    status('Проверка '+(checked+1)+'/'+eligible.length+': '+(r.name||r.url)+' · найдено подходящих: '+pCount);
    try{
     if(!(r.followers>0&&r.followers<=50000)){
      r.hunt_checked_at=now();r.hunt_pass=false;r.hunt_reason='не подтверждено 1–50к подписчиков';
     }else{
      const result=await apiCall('wall.get',{owner_id:r.id,count:100,offset:0},token);
      let ps=result?.items||[];
      if(!Array.isArray(ps))throw Error('VK wall.get не вернул публикации');
      const mature=ps.filter(p=>Number(p.date)<Date.now()/1000-7*86400);
      if(mature.length<15&&Number(result.count)>100){
       await wait(Number(E('delay').value)||700);
       const page=await apiCall('wall.get',{owner_id:r.id,count:100,offset:100},token);
       ps=ps.concat(page?.items||[]);
      }
      evaluate(r,ps);if(r.hunt_pass)pCount++;
     }
    }catch(e){
     errors++;r.hunt_checked_at=now();r.hunt_pass=false;r.hunt_reason='ошибка VK API: '+(e.message||e);
     errList.push(r.url+': '+(e.message||e));
    }
    checked++;E('huntProgress').value=checked;
    persist();render();
    if(rows().filter(x=>x.hunt_pass).length>=100){stopped=true;status('Цель 100 кандидатов по метрикам достигнута. Сохраняю результаты…');}
    if(checked%50===0)try{await ghSaveBase()}catch(e){errList.push('GitHub: '+(e.message||e));}
    await wait(Number(E('delay').value)||700);
   }
   const saved=await ghSaveBase();
   if(E('syncEnabled').checked&&E('syncToken').value.trim()&&authorPostRecords.length){
    authorsRecords=rows().filter(x=>x.hunt_pass||x.hunt_potential).map(r=>({
     author_id:r.id,author_url:r.url,name:r.name,followers:r.followers,screening_group:r.hunt_pass?'длинный формат':'смешанный формат',
     median_views:r.hunt_median_views,long_post_count:r.hunt_long_count,
     long_post_share:r.hunt_long_share,post_sample_count:r.hunt_sample_count,
     long_posts_20k:r.hunt_over20_count,ad_marked_posts:r.hunt_ad_count,
     example_post:r.hunt_example_url,ad_example_post:r.hunt_ad_example_url
    }));
    try{await githubSaveResults();}catch(e){errList.push('Тексты в GitHub: '+(e.message||e));}
   }
   status('Проверено: '+checked+'; прошли критерии: '+pCount+
    '; основной список: '+rows().filter(x=>x.hunt_pass).length+'; перспективные смешанные: '+rows().filter(x=>x.hunt_potential).length+' / цель 100; ошибки: '+errors+
    '. '+saved+(errList.length?'\n'+errList.slice(0,5).join('\n'):''));
  }catch(e){status('Ошибка скрининга: '+(e.message||e));}
  finally{running=false;E('huntScan').disabled=false;E('huntStop').disabled=true;persist();render();}
 });
 E('huntExport').addEventListener('click',()=>{
  const fields=['id','name','url','followers','hunt_checked_at','hunt_pass','hunt_reason','hunt_sample_count',
   'hunt_long_count','hunt_long_share','hunt_median_views','hunt_over20_count','hunt_potential','hunt_ad_count','hunt_example_url','hunt_ad_example_url'];
  const escape=x=>{let s=String(x??'');if(/^[\s\t\r\n]*[=+@-]/.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"';};
  const data=[fields.map(escape).join(';'),...rows().map(r=>fields.map(k=>escape(r[k])).join(';'))].join('\r\n');
  const blob=new Blob(['\uFEFF'+data],{type:'text/csv;charset=utf-8'});
  const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='vk_story_hunter_results.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 });
 render();
})();