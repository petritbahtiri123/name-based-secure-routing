import { constants } from "node:fs";
import { lstat, open } from "node:fs/promises";

export async function readStableRegular(file,{maxBytes,label=file}={}){
  const link=await lstat(file);if(!link.isFile()||link.isSymbolicLink())throw new Error(`${label} is not a regular file`);
  if(!Number.isSafeInteger(maxBytes)||maxBytes<0||link.size>maxBytes)throw new Error(`${label} byte limit exceeded`);
  const flags=constants.O_RDONLY|(constants.O_NOFOLLOW??0),handle=await open(file,flags);let before,after,bytes;
  try{before=await handle.stat();if(!before.isFile()||before.size!==link.size||before.dev!==link.dev||before.ino!==link.ino)throw new Error(`${label} changed before verification`);bytes=await handle.readFile();after=await handle.stat();}
  finally{await handle.close();}
  if(before.size!==after.size||before.mtimeMs!==after.mtimeMs||before.ino!==after.ino||before.dev!==after.dev)throw new Error(`${label} changed during verification`);
  if(bytes.length!==before.size)throw new Error(`${label} short read`);return bytes;
}
