// Sign-in uses only the public appearance setting, never private configuration.
fetch('/api/status', {cache:'no-store'}).then(response=>response.json()).then(data=>{
  const theme=data.display_theme==='roon'?'roon':'fresh-mint';
  document.body.dataset.theme=theme;
  const icon=document.querySelector('link[rel="icon"]');if(icon)icon.href=theme==='roon'?'/favicon-roon.svg':'/favicon.svg';
}).catch(()=>{});
