import type {Identity,LoginResult,CitizenScan,CitizenResult,ComplaintReceipt,CaseSummary,CaseDetail,ComplianceMap,Analysis,Report,Pattern,Dashboard,Page,RepositoryItem,ListingResult,CopilotAnswer,Brief,DownloadedAssignment,CapturePlan,PackageFamily,Action,Value,SourceRef,Assignment,Followup,Evidence,Product} from './index';

export class ApiError extends Error {constructor(public code:string,message:string,public status:number,public retryable=false){super(message)}}
type Options={baseUrl:()=>string;token?:()=>Promise<string|null>;onUnauthorized?:()=>void};
export function createClient(options:Options){
  async function request<T>(path:string,init:RequestInit={}):Promise<T>{
    const headers=new Headers(init.headers);const token=await options.token?.();
    if(token)headers.set('Authorization',`Bearer ${token}`);
    if(init.body && !(init.body instanceof FormData))headers.set('Content-Type','application/json');
    const response=await fetch(options.baseUrl().replace(/\/$/,'')+path,{...init,headers});
    if(!response.ok){const error=await response.json().catch(()=>({code:'NETWORK_ERROR',message:`Request failed (${response.status})`,retryable:true}));if(response.status===401)options.onUnauthorized?.();throw new ApiError(error.code,error.message,response.status,error.retryable)}
    return response.json() as Promise<T>;
  }
  const post=<T>(path:string,body:unknown={})=>request<T>(path,{method:'POST',body:JSON.stringify(body)});
  const patch=<T>(path:string,body:unknown)=>request<T>(path,{method:'PATCH',body:JSON.stringify(body)});
  function query(filters:Record<string,string|number|undefined>){const p=new URLSearchParams();Object.entries(filters).forEach(([k,v])=>{if(v!==undefined&&v!=='')p.set(k,String(v))});return p.toString()}
  return {
    login:(email:string,password:string)=>post<LoginResult>('/auth/login',{email,password}),
    me:()=>request<Identity>('/me'),citizenSession:()=>post<{access_token:string;session_id:string}>('/auth/citizen-session'),
    scan:(package_family:PackageFamily,product_name?:string)=>post<CitizenScan>('/citizen/scans',{package_family,product_name:product_name||'Unidentified package'}),
    citizenAnalyse:(id:string)=>post<Analysis>(`/citizen/scans/${id}/analysis`),
    citizenAnalysis:(id:string)=>request<Analysis>(`/citizen/analysis/${id}`),
    citizenResult:(id:string)=>request<CitizenResult>(`/citizen/scans/${id}/result`),
    complaint:(body:unknown)=>post<ComplaintReceipt>('/citizen/complaints',body),
    track:(reference:string,token:string)=>request<{reference:string;status:string;updated_at:string}>(`/citizen/complaints/${reference}/status`,{headers:{'X-Tracking-Token':token}}),
    assignments:()=>request<{items:{assignment:Assignment;case:CaseSummary}[];followups:Followup[]}>('/assignments/me'),
    downloadAssignment:(id:string)=>post<DownloadedAssignment>(`/assignments/${id}/download`),
    case:(id:string)=>request<CaseDetail>(`/cases/${id}`),plan:(id:string)=>request<CapturePlan>(`/cases/${id}/evidence-plan`),
    profile:(id:string,package_family:PackageFamily,reason:string,product_snapshot?:Product)=>patch<CapturePlan>(`/cases/${id}/capture-profile`,{package_family,reason,product_snapshot}),
    coverage:(id:string,body:unknown)=>post<CapturePlan>(`/cases/${id}/coverage-confirmations`,body),
    evidence:(id:string,body:unknown)=>post<Evidence>(`/cases/${id}/evidence`,body),
    upload:(id:string,form:FormData)=>request<Evidence>(`/evidence/${id}/content`,{method:'PUT',body:form}),
    sync:(id:string,evidence_ids:string[])=>post<{status:string;acknowledged_evidence_ids:string[]}>(`/cases/${id}/sync-complete`,{evidence_ids}),
    analyse:(id:string)=>post<Analysis>(`/cases/${id}/analysis`),analysis:(id:string)=>request<Analysis>(`/analysis/${id}`),
    map:(id:string)=>request<ComplianceMap>(`/cases/${id}/compliance-map`),
    reviewDeclaration:(id:string,group:string,action:Action,reason:string,source_refs:SourceRef[],corrected_value?:Value)=>post<unknown>(`/cases/${id}/declarations/${group}/verification`,{action,reason,source_refs:source_refs.map(s=>({evidence_id:s.evidence_id,bbox:s.bbox,...(s.candidate_id?{candidate_id:s.candidate_id}:{})})),corrected_value}),
    verify:(id:string,action:Action,reason:string,corrected_value?:Value)=>post<unknown>(`/findings/${id}/verification`,{action,reason,corrected_value}),
    generateReport:(id:string)=>post<{report_id:string;status:string}>(`/cases/${id}/reports`),report:(id:string)=>request<Report>(`/reports/${id}`),
    dashboard:()=>request<Dashboard>('/government/dashboard'),cases:(filters:Record<string,string>={})=>request<{items:CaseSummary[]}>(`/government/cases?${query(filters)}`),
    priority:(id:string,priority_band:string,reason:string)=>patch<CaseSummary>(`/cases/${id}/priority`,{priority_band,reason}),
    assign:(id:string,inspector_id:string,reason:string,brief_id?:string)=>post<Assignment>(`/cases/${id}/assign`,{inspector_id,reason,brief_id}),
    patterns:()=>request<{items:Pattern[]}>('/patterns'),pattern:(id:string)=>request<Pattern>(`/patterns/${id}`),
    decidePattern:(id:string,decision:'APPROVE'|'REJECT',reason:string)=>post<Pattern>(`/patterns/${id}/decision`,{decision,reason}),
    systemic:(id:string)=>post<CaseSummary>(`/patterns/${id}/systemic-case`),
    followup:(id:string,assigned_to:string,note:string,brief_id?:string)=>post<Followup>(`/systemic-cases/${id}/followups`,{assigned_to,note,brief_id}),
    updateFollowup:(id:string,status:Followup['status'],note:string)=>patch<Followup>(`/followups/${id}`,{status,note}),
    copilot:(context_type:'case'|'pattern',context_id:string,prompt_key_or_text:string)=>post<CopilotAnswer>('/copilot/query',{context_type,context_id,prompt_key_or_text}),
    brief:(context_type:'case'|'pattern',context_id:string,draft_id?:string,content?:string)=>post<Brief>('/copilot/inspection-brief',{context_type,context_id,draft_id,content}),
    approveBrief:(id:string,decision:'APPROVE'|'REJECT',reason:string)=>post<Brief>(`/inspection-briefs/${id}/approval`,{decision,reason}),
    listing:(form:FormData)=>request<ListingResult>('/copilot/analyse-image',{method:'POST',body:form}),
    repository:(filters:Record<string,string|number|undefined>)=>request<Page<RepositoryItem>>(`/government/repository?${query(filters)}`),
    reports:(filters:Record<string,string|number|undefined>)=>request<Page<{report_id:string;case_id:string;product_name:string;generated_at:string;status:string;pdf_available:boolean;editable_available:boolean}>>(`/government/reports?${query(filters)}`),
    evidenceUrl:(id:string)=>options.baseUrl().replace(/\/$/,'')+`/evidence/${id}/content`,
    reportUrl:(id:string,format:'pdf'|'docx')=>options.baseUrl().replace(/\/$/,'')+`/reports/${id}?format=${format}`,
  };
}
