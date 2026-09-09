'use client';
import {useEffect,useState,useEffectEvent} from 'react';
import {AlertCircle,AlertTriangle,BadgeCheck,CheckCircle2,CircleHelp,Clock3,MinusCircle,RefreshCw,XCircle} from 'lucide-react';

const human=(s:string)=>s.toLowerCase().replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());
export function Status({value}:{value:string}){
  const state=value.toUpperCase();let tone='slate';let Icon=CircleHelp;
  if(state==='SUPPORTED'){tone='teal';Icon=CheckCircle2}
  else if(['ACCEPTED','CORRECTED','APPROVED','COMPLETED','READY'].includes(state)){tone='green';Icon=BadgeCheck}
  else if(['CONFLICTING','CANDIDATE','AWAITING_VERIFICATION','UNDER_REVIEW','DRAFT'].includes(state)){tone='amber';Icon=AlertTriangle}
  else if(state==='POTENTIAL'||state.startsWith('POTENTIAL_')||state==='HIGH'){tone='orange';Icon=AlertCircle}
  else if(state==='FAILED'){tone='red';Icon=XCircle}
  else if(['QUEUED','RUNNING','GENERATING','ASSIGNED','IN_PROGRESS','ANALYSING'].includes(state)){tone='blue';Icon=Clock3}
  else if(state==='NOT_APPLICABLE'||state==='REJECTED'){Icon=MinusCircle}
  return <span className={`status ${tone}`}><Icon size={14} aria-hidden/>{state==='SUPPORTED'?'Supported evidence':state==='ACCEPTED'?'Officer accepted':state==='CORRECTED'?'Officer corrected':human(value)}</span>
}
export function Loading({label='Loading records…'}:{label?:string}){return <div className="loading" role="status"><RefreshCw size={18} className="spin"/>{label}</div>}
export function ErrorBox({error,retry}:{error:string;retry?:()=>void}){return <div className="notice red" role="alert"><AlertCircle size={18}/><div>{error}{retry&&<button className="text-button" onClick={retry}>Retry</button>}</div></div>}
export function Empty({title,detail}:{title:string;detail:string}){return <div className="empty"><MinusCircle size={26}/><strong>{title}</strong><p>{detail}</p></div>}
export function Notice({children}:{children:React.ReactNode}){return <div className="notice amber"><AlertTriangle size={18}/><div>{children}</div></div>}
export function useResource<T>(loader:()=>Promise<T>,key:string){
  const [data,setData]=useState<T|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(true),[version,setVersion]=useState(0);
  const fetchResource=useEffectEvent(loader);
  useEffect(()=>{let active=true;const start=async()=>{setLoading(true);setError('');return fetchResource()};Promise.resolve().then(start).then(d=>{if(active)setData(d)}).catch(e=>{if(active)setError(e instanceof Error?e.message:String(e))}).finally(()=>{if(active)setLoading(false)});return()=>{active=false}},[key,version]); // loader inputs are represented by the stable resource key.
  return {data,error,loading,reload:()=>setVersion(v=>v+1),setData};
}
export function formatDate(value?:string|null){if(!value)return '—';return new Date(value).toLocaleDateString('en-IN',{day:'2-digit',month:'short',year:'numeric'})}
export function SmallLabel({children}:{children:React.ReactNode}){return <span className="eyebrow">{children}</span>}
