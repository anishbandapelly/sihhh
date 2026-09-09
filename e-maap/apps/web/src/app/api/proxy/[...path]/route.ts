import {NextRequest,NextResponse} from 'next/server';
import {cookies} from 'next/headers';

const base=(process.env.API_BASE_URL||process.env.NEXT_PUBLIC_API_BASE_URL||'http://localhost:8000/api/v1').replace(/\/$/,'');
async function proxy(request:NextRequest,context:{params:Promise<{path:string[]}>}){
  const {path}=await context.params;const jar=await cookies();const route=path.map(encodeURIComponent).join('/');
  if(route==='auth/logout'){jar.delete('emaap_session');return NextResponse.json({ok:true})}
  const token=jar.get('emaap_session')?.value;
  const headers=new Headers();const contentType=request.headers.get('content-type');if(contentType)headers.set('content-type',contentType);
  if(token)headers.set('authorization',`Bearer ${token}`);
  try{
    const upstream=await fetch(`${base}/${route}${request.nextUrl.search}`,{method:request.method,headers,body:request.method==='GET'?undefined:await request.arrayBuffer(),cache:'no-store'});
    if(route==='auth/login'&&upstream.ok){
      const session=await upstream.json();
      if(session.role!=='GOVERNMENT_OFFICER')return NextResponse.json({code:'FORBIDDEN_ROLE_OR_CASE',message:'Use Inspector access in the e-Maap mobile app.',retryable:false},{status:403});
      jar.set('emaap_session',session.access_token,{httpOnly:true,sameSite:'strict',secure:process.env.NODE_ENV==='production',path:'/'});
      const {access_token:discarded,...safe}=session;void discarded;
      return NextResponse.json(safe);
    }
    if(upstream.status===401)jar.delete('emaap_session');
    const output=new Headers({'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'});
    for(const key of ['content-type','content-disposition']){const value=upstream.headers.get(key);if(value)output.set(key,value)}
    return new NextResponse(await upstream.arrayBuffer(),{status:upstream.status,headers:output});
  }catch{return NextResponse.json({code:'BACKEND_UNAVAILABLE',message:'The e-Maap API is unreachable. Check the backend connection and retry.',retryable:true},{status:503})}
}
export const GET=proxy;export const POST=proxy;export const PUT=proxy;export const PATCH=proxy;
