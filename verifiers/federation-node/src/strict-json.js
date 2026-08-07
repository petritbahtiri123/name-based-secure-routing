const decoder=new TextDecoder("utf-8",{fatal:true});
export function parseStrictJson(bytes,{maxBytes=2_000_000,maxDepth=64}={}){
  if(!Buffer.isBuffer(bytes)||bytes.length>maxBytes)throw new Error("JSON byte limit exceeded");
  let text;try{text=decoder.decode(bytes);}catch{throw new Error("invalid JSON UTF-8");}let i=0;
  const ws=()=>{while(/[\x20\t\r\n]/.test(text[i]??""))i++;};
  const string=()=>{if(text[i]!==`"`)throw new Error("expected JSON string");const start=i++;for(;i<text.length;i++){if(text[i]==="\\"){i++;continue;}if(text[i]===`"`){i++;try{return JSON.parse(text.slice(start,i));}catch{throw new Error("invalid JSON string");}}if(text.charCodeAt(i)<0x20)throw new Error("invalid JSON string");}throw new Error("unterminated JSON string");};
  const value=(depth)=>{
    if(depth>maxDepth)throw new Error("JSON depth limit exceeded");ws();const c=text[i];
    if(c===`"`)return string();
    if(c==="{"){i++;ws();const out={},keys=new Set();if(text[i]==="}"){i++;return out;}for(;;){const key=string();if(keys.has(key))throw new Error(`duplicate JSON key: ${key}`);keys.add(key);ws();if(text[i++]!==":")throw new Error("expected JSON colon");out[key]=value(depth+1);ws();if(text[i]==="}"){i++;return out;}if(text[i++]!==",")throw new Error("expected JSON object comma");ws();}}
    if(c==="["){i++;ws();const out=[];if(text[i]==="]"){i++;return out;}for(;;){out.push(value(depth+1));ws();if(text[i]==="]"){i++;return out;}if(text[i++]!==",")throw new Error("expected JSON array comma");}}
    for(const[literal,v]of[["true",true],["false",false],["null",null]])if(text.startsWith(literal,i)){i+=literal.length;return v;}
    const match=/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/.exec(text.slice(i));if(match){i+=match[0].length;const n=Number(match[0]);if(!Number.isFinite(n))throw new Error("invalid JSON number");if(Number.isInteger(n)&&!Number.isSafeInteger(n))throw new Error("JSON integer exceeds safe integer range");return n;}
    throw new Error("invalid JSON value");
  };
  const result=value(1);ws();if(i!==text.length)throw new Error("trailing JSON data");return result;
}
