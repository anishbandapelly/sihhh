import {createClient} from '../../../../shared/contracts/client';
export const api=createClient({baseUrl:()=>'/api/proxy',onUnauthorized:()=>{if(typeof window!=='undefined')window.dispatchEvent(new Event('emaap:unauthorised'))}});
