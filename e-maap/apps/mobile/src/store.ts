import {pbkdf2Async} from '@noble/hashes/pbkdf2';
import {mobileRuntime} from '../../../shared/contracts/runtime-config';
import * as SQLite from 'expo-sqlite';
import * as SecureStore from 'expo-secure-store';
import * as Crypto from 'expo-crypto';
import * as FileSystem from 'expo-file-system/legacy';
import {sha256} from '@noble/hashes/sha256';
import {bytesToHex} from '@noble/hashes/utils';
import {toByteArray} from 'base64-js';
import type {SyncStatus,DownloadedAssignment} from '../../../shared/contracts';
let database:SQLite.SQLiteDatabase;
export interface LocalEvidence {id:string;caseId:string;uri:string;status:SyncStatus;metadata:Record<string,unknown>;error?:string}
export async function initStore(){let key=await SecureStore.getItemAsync('database-key');if(!key){key=bytesToHex(Crypto.getRandomBytes(32));await SecureStore.setItemAsync('database-key',key)}if(!/^[a-f0-9]{64}$/.test(key))throw Error('Invalid protected database key');database=await SQLite.openDatabaseAsync('emaap.db');await database.execAsync(`PRAGMA key = "x'${key}'";`);const cipher=await database.getFirstAsync<Record<string,string>>('PRAGMA cipher_version;');if(!cipher)throw Error('This app requires a SQLCipher-enabled native build. Use the development build or APK, not Expo Go.');await database.execAsync('PRAGMA journal_mode=WAL; CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY,value TEXT NOT NULL); CREATE TABLE IF NOT EXISTS evidence (id TEXT PRIMARY KEY, case_id TEXT NOT NULL, value TEXT NOT NULL);');await FileSystem.makeDirectoryAsync(FileSystem.documentDirectory+'evidence/',{intermediates:true})}
export async function cache(key:string,value:unknown){await database.runAsync('INSERT OR REPLACE INTO cache(key,value) VALUES (?,?)',key,JSON.stringify(value))}
export async function cached<T>(key:string):Promise<T|null>{const r=await database.getFirstAsync<{value:string}>('SELECT value FROM cache WHERE key=?',key);return r?JSON.parse(r.value):null}
export async function rememberAssignment(a:DownloadedAssignment){const previous=await cached<string[]>('downloaded')||[];for(const id of previous){if(id===a.assignment.id)continue;const old=await cached<DownloadedAssignment>('assignment:'+id);if(old&&(await evidenceFor(old.case.id)).some(e=>e.status!=='SYNCHRONISED'))throw Error('Synchronise the active downloaded assignment before switching offline work.');await database.runAsync('DELETE FROM cache WHERE key=?','assignment:'+id)}await cache('assignment:'+a.assignment.id,a);await cache('downloaded',[a.assignment.id])}
export async function localAssignments(){return Promise.all((await cached<string[]>('downloaded')||[]).map(id=>cached<DownloadedAssignment>('assignment:'+id)))}
export async function saveEvidence(e:LocalEvidence){await database.runAsync('INSERT OR REPLACE INTO evidence(id,case_id,value) VALUES (?,?,?)',e.id,e.caseId,JSON.stringify(e))}
export async function evidenceFor(caseId:string){return (await database.getAllAsync<{value:string}>('SELECT value FROM evidence WHERE case_id=? ORDER BY rowid',caseId)).map(r=>JSON.parse(r.value) as LocalEvidence)}
export async function preserve(uri:string){const id=Crypto.randomUUID();const target=FileSystem.documentDirectory+'evidence/'+id+'.jpg';await FileSystem.copyAsync({from:uri,to:target});const bytes=toByteArray(await FileSystem.readAsStringAsync(target,{encoding:FileSystem.EncodingType.Base64}));return {id,uri:target,sha256:bytesToHex(sha256(bytes)),size:bytes.length}}
export const token=()=>SecureStore.getItemAsync('access-token');
export async function setToken(t:string){await SecureStore.setItemAsync('access-token',t)}

export async function rememberInspector(email:string,password:string,user:{id:string;name:string;role:string;access_token:string}){const salt=Crypto.randomUUID();const hash=bytesToHex(await pbkdf2Async(sha256,password,salt,{c:mobileRuntime.unlockKdfIterations,dkLen:32}));await SecureStore.setItemAsync('inspector-unlock',JSON.stringify({email,salt,hash,id:user.id,token:user.access_token}));await cache('inspector',{id:user.id,name:user.name,role:user.role})}
export async function unlockInspector(email:string,password:string){const stored=await SecureStore.getItemAsync('inspector-unlock');if(!stored)throw Error('Sign in online and download assignments first.');const u=JSON.parse(stored);const hash=bytesToHex(await pbkdf2Async(sha256,password,u.salt,{c:mobileRuntime.unlockKdfIterations,dkLen:32}));if(email!==u.email||hash!==u.hash)throw Error('Inspector credentials do not match the protected offline session.');await setToken(u.token);return u.id as string}
