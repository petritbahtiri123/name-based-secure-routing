const LIMITS = { bytes: 1_048_576, depth: 24, array: 512, map: 256, string: 262_144 };
export class Tagged { constructor(tag, value) { this.tag = tag; this.value = value; } }
function fail(message) { throw new Error(`CBOR ${message}`); }
function head(major, n) {
  n = BigInt(n); const base = major << 5;
  if (n < 24n) return Buffer.from([base | Number(n)]);
  for (const [ai, width, max] of [[24,1,0xffn],[25,2,0xffffn],[26,4,0xffffffffn],[27,8,0xffffffffffffffffn]]) if (n <= max) { const b=Buffer.alloc(1+width); b[0]=base|ai; for(let i=width;i;i--){b[i]=Number(n&255n);n>>=8n;} return b; }
  fail("integer range");
}
function enc(v, opts, depth, seen) {
  if (depth > (opts.maxDepth ?? LIMITS.depth)) fail("depth limit");
  if (v === null) return Buffer.from([0xf6]); if (v === false) return Buffer.from([0xf4]); if (v === true) return Buffer.from([0xf5]);
  if (typeof v === "number" || typeof v === "bigint") { if(typeof v === "number" && !Number.isSafeInteger(v)) fail("integer type"); const n=BigInt(v); return n>=0n?head(0,n):head(1,-1n-n); }
  if (Buffer.isBuffer(v)) return Buffer.concat([head(2,v.length),v]);
  if (typeof v === "string") { const b=Buffer.from(v,"utf8"); if(b.toString("utf8")!==v) fail("UTF-8"); return Buffer.concat([head(3,b.length),b]); }
  if (seen.has(v)) fail("cycle"); seen.add(v);
  try {
    if (v instanceof Tagged) { if(!opts.allowTag18 || v.tag!==18) fail("unsupported tag"); return Buffer.concat([head(6,18),enc(v.value,opts,depth+1,seen)]); }
    if (Array.isArray(v)) { if(v.length>(opts.maxArrayItems??LIMITS.array)) fail("array limit"); return Buffer.concat([head(4,v.length),...v.map(x=>enc(x,opts,depth+1,seen))]); }
    if (v instanceof Map) { if(v.size>(opts.maxMapPairs??LIMITS.map)) fail("map limit"); const entries=[...v].map(([k,x])=>[enc(k,opts,depth+1,seen),x]).sort((a,b)=>Buffer.compare(a[0],b[0])); for(let i=1;i<entries.length;i++) if(entries[i-1][0].equals(entries[i][0])) fail("duplicate map key"); return Buffer.concat([head(5,entries.length),...entries.flatMap(([k,x])=>[k,enc(x,opts,depth+1,seen)])]); }
  } finally { seen.delete(v); }
  fail("unsupported value");
}
export function encodeCanonical(value, options={}) { const b=enc(value,options,1,new Set()); if(b.length>(options.maxBytes??LIMITS.bytes)) fail("byte limit"); return b; }
class Decoder {
  constructor(b,o){this.b=b;this.o=o;this.i=0;}
  take(n){if(this.i+n>this.b.length)fail("truncated");const x=this.b.subarray(this.i,this.i+n);this.i+=n;return x;}
  arg(ai){if(ai<24)return BigInt(ai);const widths={24:1,25:2,26:4,27:8},w=widths[ai];if(!w)fail("indefinite/reserved");let n=0n;for(const x of this.take(w))n=(n<<8n)|BigInt(x);const min={24:24n,25:256n,26:65536n,27:4294967296n}[ai];if(n<min)fail("non-shortest integer/length");return n;}
  count(n,max){if(n>BigInt(max)||n>BigInt(Number.MAX_SAFE_INTEGER))fail("resource limit");return Number(n);}
  item(d=1){if(d>(this.o.maxDepth??LIMITS.depth))fail("depth limit");const x=this.take(1)[0],m=x>>5,ai=x&31,n=()=>this.arg(ai);if(m===0){const z=n();return z<=BigInt(Number.MAX_SAFE_INTEGER)?Number(z):z;}if(m===1){const z=-1n-n();return z>=BigInt(Number.MIN_SAFE_INTEGER)?Number(z):z;}if(m===2||m===3){const z=this.count(n(),this.o.maxStringBytes??LIMITS.string),b=this.take(z);if(m===2)return Buffer.from(b);const s=new TextDecoder("utf-8",{fatal:true}).decode(b);return s;}if(m===4){const z=this.count(n(),this.o.maxArrayItems??LIMITS.array),a=[];while(a.length<z)a.push(this.item(d+1));return a;}if(m===5){const z=this.count(n(),this.o.maxMapPairs??LIMITS.map),map=new Map();let prev=null;for(let j=0;j<z;j++){const start=this.i,k=this.item(d+1),raw=this.b.subarray(start,this.i);if(prev&&Buffer.compare(prev,raw)>=0)fail("duplicate or map key order");prev=raw;map.set(k,this.item(d+1));}return map;}if(m===6){const tag=n();if(!this.o.allowTag18||tag!==18n)fail("unsupported tag");return new Tagged(18,this.item(d+1));}if(m===7&&ai===20)return false;if(m===7&&ai===21)return true;if(m===7&&ai===22)return null;fail("simple/float");}
}
export function decodeCanonical(bytes,options={}){if(!Buffer.isBuffer(bytes))fail("input type");if(bytes.length>(options.maxBytes??LIMITS.bytes))fail("byte limit");const d=new Decoder(bytes,options),v=d.item();if(d.i!==bytes.length)fail("trailing bytes");if(!encodeCanonical(v,options).equals(bytes))fail("non-canonical encoding");return v;}
