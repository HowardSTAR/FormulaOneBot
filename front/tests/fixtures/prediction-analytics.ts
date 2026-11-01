// Isolated visual data: no production requests or persistent mutations.
export function analyticsPreview(query: URLSearchParams) {
  const removed = new Set<string>();
  const now = Date.now()/1000;
  const season = new Date().getFullYear();
  let activeSeason = season;
  const future = new Date((now+86400)*1000).toISOString();
  const events = [
    {round:21,event_name:'Гран-при Бразилии',race_start_utc:future,quali_start_utc:future},
    {round:20,event_name:'Гран-при Мексики',race_start_utc:new Date((now-86400)*1000).toISOString(),quali_start_utc:new Date((now-172800)*1000).toISOString()},
  ];
  const summaries = [
    {id:'design-demo',season,round:21,session:'race',created_at:now,status:'ready',settled_at:null as number|null},
    {id:'design-quali',season,round:21,session:'qualifying',created_at:now-3600,status:'ready',settled_at:null as number|null},
    {id:'design-result',season,round:20,session:'race',created_at:now-172800,status:'ready',settled_at:now-7200},
  ];
  return async (url: URL, init?: RequestInit): Promise<Response|null> => {
    const json = (data:unknown,status=200) => new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});
    if(url.pathname === '/api/admin/me') return query.get('state') === 'analytics-denied' ? json({detail:'Доступ запрещён'},403) : json({role:'admin'});
    if(!url.pathname.startsWith('/api/admin/prediction-analytics')) return null;
    if(url.pathname === '/api/admin/prediction-analytics') {
      if(init?.method === 'POST') { removed.delete('design-demo'); return json({id:'design-demo'}); }
      activeSeason = Number(url.searchParams.get('season')||season);
      return json({events,snapshots:query.get('state') === 'analytics-empty' ? [] : summaries.filter(s => !removed.has(s.id)).map(s=>({...s,season:Number(url.searchParams.get('season')||season)})),warning:'Предпросмотр · все расчёты и результаты иллюстративные.'});
    }
    const summary = summaries.find(s => url.pathname.endsWith('/'+s.id));
    if(!summary || removed.has(summary.id)) return json({detail:'Прогноз не найден'},404);
    if(init?.method === 'DELETE') {
      if(query.get('state') === 'analytics-delete-error') return json({detail:'Не удалось удалить расчёт. Попробуйте снова.'},503);
      removed.add(summary.id);return json({deleted:summary.id});
    }
    const names = ['Ландо Норрис','Макс Ферстаппен','Шарль Леклер','Оскар Пиастри','Джордж Расселл'];
    const codes = ['NOR','VER','LEC','PIA','RUS'];
    const teams = ['McLaren','Red Bull Racing','Ferrari','McLaren','Mercedes'];
    const drivers = names.map((name,i)=>({code:codes[i],name,team:teams[i],win:.3-i*.05,podium:.7-i*.1,top10:.9,expected:i+3,range:[1,10],dnf:.08,reasons:['Демонстрация объяснения модели.'],factors:[{key:'form',label:'Свежая форма',value:.7,weight:.2,contribution:.04,samples:6,effective_samples:4}],timeline:[]}));
    return json({...summary,season:activeSeason,error:null,actual:summary.settled_at ? {rows:drivers.map((d,i)=>({code:d.code,name:d.name,position:[2,1,4,3,5][i]})),metrics:{matched:5,total:5,mae:2,winner_brier:.18}} : null,payload:{event:events.find(e=>e.round===summary.round),cutoff:summary.created_at,current_label:summary.session==='race'?'Гонка':'Квалификация',warnings:[],news_policy:'Новости показаны как контекст.',model:{version:'DEMO',trials:12000,drivers,scenarios:['Победа фаворита','Борьба лидеров','Неожиданный исход'].map((label,i)=>({label,probability:[.5,.3,.2][i],why:'Иллюстративный сценарий для проверки отчёта.',top5:codes}))},inputs:{history:[],weather:{available:false,reason:'В демонстрации погода не загружена'},news_available:false,news:[]}}});
  };
}
