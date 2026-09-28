const form=document.getElementById('intakeForm');
form.addEventListener('submit',async e=>{
  e.preventDefault();
  const button=form.querySelector('button[type="submit"]');button.disabled=true;button.textContent='Sending…';
  const body=Object.fromEntries(new FormData(form).entries());body.source='Website';
  try{
    const res=await fetch('/api/leads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data=await res.json();if(!res.ok)throw new Error(data.error||'Could not submit inquiry.');
    document.getElementById('intakeFormWrap').classList.add('hidden');document.getElementById('intakeSuccess').classList.remove('hidden');form.reset();
  }catch(err){alert(err.message)}finally{button.disabled=false;button.textContent='Send inquiry →'}
});
document.getElementById('submitAnother').addEventListener('click',()=>{document.getElementById('intakeSuccess').classList.add('hidden');document.getElementById('intakeFormWrap').classList.remove('hidden');});
