/** Delivery and campaign qualification are deliberately separate. */
export function deliveryLabel(state:string):string {
 const labels:Record<string,string>={receiving:'Receiving source snapshots',stale:'Source updates stale - retained evidence',final:'Source final received - not campaign qualification',invalid:'Invalid source evidence',waiting:'Waiting for advancing source data',unavailable:'Delivery status unavailable',snapshot:'Retained source snapshot'};
 return labels[state]??'Delivery status unavailable';
}
export function campaignNotice(identity?:string):{failed:boolean;text:string} {
 // Explicit campaign review overlay only; never modify the immutable source data.
 // Fresh30 post-calibration failure reported by campaign owner, 2026-11-14.
 if(identity==='nbsr-sphere-rxe2026111430'||identity==='nbsr-sphere-rxe2026111430.snapshot')
  return {failed:true,text:'Campaign INVALID_PARTIAL: post-calibration validation did not pass. These retained source charts are diagnostic only, not valid benchmark or capacity evidence.'};
 return {failed:false,text:'Campaign qualification not established by this view. Source progress, complete counters and a final marker do not prove calibration, cleanup or benchmark acceptance.'};
}

export function gateDetail(name:string,detail:string):string {
 return name==='Source connection' ? 'Retained source evidence. See Automatic deliveries for observed delivery freshness; receipt time alone does not establish remote liveness.' : detail;
}
