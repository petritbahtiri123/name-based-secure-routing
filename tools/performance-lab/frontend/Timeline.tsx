import React,{useState} from 'react';
import type {ProgressWindow} from './types';
const num=(v:number,d=3)=>v.toLocaleString(undefined,{maximumFractionDigits:d});
const integer=(v:string)=>BigInt(v).toLocaleString();
const seconds=(v:string)=>Number(v)/1e9;
export function Timeline({windows,phase,deadline,initialMetric='goodput_mbps_bidirectional'}:{windows:ProgressWindow[];phase:string;deadline:string;initialMetric?:'goodput_mbps_bidirectional'|'p99_us'}){
 const selected=windows.filter(w=>phase==='all'||w.phase===phase);
 const [metric,setMetric]=useState<'goodput_mbps_bidirectional'|'p99_us'>(initialMetric);
 const [limit,setLimit]=useState(50);
 const width=880,height=200,left=65,right=20,top=20,bottom=35;
 const end=Math.max(...windows.map(w=>seconds(w.end_ns)),1e-9);
 const max=Math.max(...selected.map(w=>w[metric]??0),1e-9);
 const x=(t:number)=>left+t/end*(width-left-right);
 const y=(v:number)=>height-bottom-v/max*(height-top-bottom);
 const unit=metric==='p99_us'?'μs':'Mbit/s';
 const linePoints=selected.filter(w=>w[metric]!==null);
 return <><div className="timeline-metric"><button className={metric==='goodput_mbps_bidirectional'?'active':''} onClick={()=>setMetric('goodput_mbps_bidirectional')}>Bidirectional payload rate</button><button className={metric==='p99_us'?'active':''} onClick={()=>setMetric('p99_us')}>Sampled window p99</button></div>
 {selected.length?<div className="timeline-chart"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${metric==='p99_us'?'Sampled window p99 latency':'Bidirectional application payload goodput'} over ${num(end)} source-relative seconds. ${selected.length} windows.`}>{[0,.5,1].map(t=><g key={t}><line x1={left} x2={width-right} y1={y(t*max)} y2={y(t*max)} stroke="#e8ede3"/><text x={left-10} y={y(t*max)+4} textAnchor="end">{num(t*max,2)}</text></g>)}<text x={left} y={12}>{unit}</text>
 {selected.map(w=><rect key={'phase'+w.index} x={x(seconds(w.start_ns))} y={top} width={Math.max(.2,x(seconds(w.end_ns))-x(seconds(w.start_ns)))} height={height-top-bottom} fill={w.phase==='drain'?'#e7d8b955':w.phase==='mixed'?'#e3c99855':'transparent'}/>)}
 {metric==='goodput_mbps_bidirectional'?linePoints.map(w=><rect key={w.index} x={x(seconds(w.start_ns))+.5} y={y(w[metric]!)} width={Math.max(.5,x(seconds(w.end_ns))-x(seconds(w.start_ns))-1)} height={height-bottom-y(w[metric]!)} fill="#628b6b"><title>Window {w.index}: {num(w[metric]!,6)} {unit} · {w.phase}</title></rect>):linePoints.map(w=><g key={w.index}><line x1={x(seconds(w.start_ns))} x2={x(seconds(w.end_ns))} y1={y(w[metric]!)} y2={y(w[metric]!)} stroke="#466d50" strokeWidth="2"/><circle cx={x((seconds(w.start_ns)+seconds(w.end_ns))/2)} cy={y(w[metric]!)} r="3" fill="#315f44"><title>Window {w.index}: {num(w[metric]!,3)} μs · {w.sample_count} sampled completions</title></circle></g>)}
 {seconds(deadline)<=end&&<g><line x1={x(seconds(deadline))} x2={x(seconds(deadline))} y1={top} y2={height-bottom} stroke="#9d7948" strokeDasharray="4 4"/><text x={Math.max(left,x(seconds(deadline))-5)} y={top+10} textAnchor="end">issue deadline</text></g>}
 {[0,.25,.5,.75,1].map(t=><text key={t} x={x(t*end)} y={height-12} textAnchor="middle">{num(t*end,3)}s</text>)}</svg><p className="caption">{metric==='p99_us'?'Each segment is a sampled percentile for one window; gaps stay gaps. No pooled p99 or interpolation.':'Goodput counts request + response application payload. It is neither per-direction goodput nor interface traffic.'} Warmup is outside this series. Beige shading marks mixed/drain windows.</p></div>:<div className="empty">No imported windows in this phase.</div>}
 <div className="table-scroll"><table><thead><tr><th>WINDOW / RECORD</th><th>INTERVAL (s)</th><th>PHASE</th><th>COMPLETED Δ</th><th>BIDIRECTIONAL</th><th>SAMPLED p99</th><th>SAMPLES / STRIDE</th></tr></thead><tbody>{selected.slice(0,limit).map(w=><tr key={w.index}><td>{w.index}<small>record {w.record_number}</small></td><td>{num(seconds(w.start_ns),6)}–{num(seconds(w.end_ns),6)}</td><td>{w.phase}</td><td>{integer(w.completed_delta)}</td><td>{num(w.goodput_mbps_bidirectional)} Mbit/s</td><td>{w.p99_us==null?'Not sampled':num(w.p99_us,3)+' μs'}</td><td>{integer(w.sample_count)} / {integer(w.sample_stride)}</td></tr>)}</tbody></table></div>{selected.length>limit&&<button className="show-more" onClick={()=>setLimit(n=>n+50)}>Show 50 more windows ({selected.length-limit} remaining)</button>}</>;
}
