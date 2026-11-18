import {cp,mkdir,readFile,readdir,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
async function files(dir){let result=[];for(const entry of await readdir(dir,{withFileTypes:true})){const path=dir+'/'+entry.name;result.push(...(entry.isDirectory()?await files(path):[path]));}return result;}
const hash=createHash('sha256');
for(const path of (await files('src')).sort()){hash.update('frontend/'+path);hash.update(await readFile(path));}
await mkdir('public',{recursive:true});
await writeFile('public/build-info.json',JSON.stringify({revision:hash.digest('hex').slice(0,16)}));
for(const folder of ['cmaps','standard_fonts','wasm']){
 await mkdir('public',{recursive:true});
 await cp(`node_modules/pdfjs-dist/${folder}`,`public/${folder}`,{recursive:true});
}
