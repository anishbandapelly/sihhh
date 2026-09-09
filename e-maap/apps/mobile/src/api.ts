import {createClient} from '../../../shared/contracts/client';import {token} from './store';
export const baseUrl=process.env.EXPO_PUBLIC_API_BASE_URL||'http://10.0.2.2:8000/api/v1';
export const api=createClient({baseUrl:()=>baseUrl,token});
