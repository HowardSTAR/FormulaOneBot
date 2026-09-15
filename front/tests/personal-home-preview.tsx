// Development-only visual fixture. No authentication or server requests.
import React from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import '../src/assets/styles.css';
import '../src/assets/desktop-conversion.css';
import '../src/assets/redesign.css';
import { PersonalHome } from '../src/pages/index/PersonalHome';

window.fetch = async (input) => {
  const path = new URL(String(input),location.origin).pathname;
  const data = path.endsWith('/unread-count') ? { unread: 0 } : {
    status:'ok',event_name:'Azerbaijan Grand Prix',is_open:false,
    opens_at_utc:new Date(Date.now()+86400000).toISOString(),
    deadline_utc:new Date(Date.now()+172800000).toISOString(),prediction:null,
  };
  return new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});
};
createRoot(document.getElementById('root')!).render(<MemoryRouter><main style={{padding:12,maxWidth:1100,margin:'auto'}}>
  <p style={{fontSize:12,color:'#aeb3c0'}}>Тестовый экран · демонстрационные данные</p>
  <PersonalHome timezone="Europe/Moscow" auth={{loaded:true,signedIn:true,personalized:true,telegramMiniApp:false,role:'user'}} />
  <div style={{padding:32,borderRadius:16,background:'linear-gradient(110deg,#df1000,#221719)',color:'white'}}><small>ПРАКТИКА 1</small><h1 style={{fontSize:24}}>Azerbaijan Grand Prix</h1><p>Расписание и трасса — сразу под личной полосой</p></div>
</main></MemoryRouter>);
