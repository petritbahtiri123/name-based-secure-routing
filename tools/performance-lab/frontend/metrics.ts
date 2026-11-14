/** Percentage rounded to four places; never impute missing counts. */
export function completionPercent(offered: string|null, completed: string|null): number|null {
 if(offered===null || completed===null)return null;
 const total=BigInt(offered), done=BigInt(completed);
 if(total<=0n || done<0n || done>total)return null;
 return Number((done*1000000n+total/2n)/total)/10000;
}

export function stableSelection(current:string, available:string[]):string {
 return available.includes(current)?current:(available[0]??'');
}
