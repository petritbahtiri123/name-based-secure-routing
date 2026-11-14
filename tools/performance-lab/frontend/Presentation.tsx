import {deliveryLabel,campaignNotice} from './status';
import React from 'react';
import type {Run} from './types';
import {Timeline} from './Timeline';

const fmt=(v:number)=>v.toLocaleString(undefined,{maximumFractionDigits:3});
const labels:Record<string,string>={receiving:'Receiving new snapshots',stale:'Updates stale — last evidence retained',final:'Final marker reconciled',invalid:'Invalid evidence — charts withheld',waiting:'Waiting for another snapshot',unavailable:'Delivery status unavailable',snapshot:'Recorded snapshot — not a live feed'};

export function Presentation({run,state,following,campaign}:{run?:Run;state:string;following:boolean;campaign:{failed:boolean;text:string}}){
 const stream=run?.stream;
 const invalid=stream?.validity==='invalid';
 const latest=stream?.windows.at(-1),previous=stream?.windows.at(-2);
 const delta=latest&&previous&&latest.phase===previous.phase?latest.goodput_mbps_bidirectional-previous.goodput_mbps_bidirectional:null;
 const status=invalid?'invalid':state;
 return <section className={'presentation-stage '+status} aria-label="Measurement presentation">
 <div className="presentation-top"><span>NBSR / MEASUREMENT STAGE</span><strong role="status">{deliveryLabel(status)}</strong></div>
 <p className={campaign.failed?'alert':'notice'}>{campaign.text}</p>
 <h2>{run?.label??'Waiting for real measurements'}</h2>
 <p>{following?'Following the selected experiment.':'Choose an experiment above to follow automatic deliveries.'} Values change only when source windows arrive.</p>
 {!stream?<div className="presentation-empty">No selected progress evidence yet. No simulated activity.</div>:invalid?<div className="presentation-empty">Source checks failed. Inspect the snapshot checks and original artifact below.</div>:<>
 <div className="presentation-values" key={run!.sha256}>
 <div><span>Latest bidirectional payload rate</span><strong>{latest?fmt(latest.goodput_mbps_bidirectional):'Not recorded'}<small> Mbit/s</small></strong><p>{delta===null?'No comparable preceding window':`${delta>0?'↑':delta<0?'↓':'→'} ${fmt(Math.abs(delta))} Mbit/s versus preceding ${latest!.phase} window`}</p></div>
 <div><span>Latest sampled window p99</span><strong>{latest?.p99_us==null?'Not sampled':fmt(latest.p99_us)}<small>{latest?.p99_us==null?'':' µs'}</small></strong><p>Window percentile, not a pooled percentile</p></div>
 <div><span>Completed operations</span><strong>{BigInt(stream.source_counters.completed).toLocaleString()}</strong><p>Source elapsed: {fmt(Number(stream.elapsed_ns)/1e9)} s · {latest?.phase??'No window'}</p></div>
 </div>
 <div className="presentation-plots"><div><h3>Payload rate by window</h3><Timeline windows={stream.windows} phase="all" deadline={stream.issue_deadline_ns}/></div><div><h3>Sampled p99 by window</h3><Timeline windows={stream.windows} phase="all" deadline={stream.issue_deadline_ns} initialMetric="p99_us"/></div></div>
 <p className="presentation-boundary">Axes scale to retained data; source-relative time. Missing samples remain gaps. Mixed/drain windows are shaded. Receipt freshness does not prove remote liveness. No interpolation or estimated capacity.</p>
 </>}
 </section>;
}
