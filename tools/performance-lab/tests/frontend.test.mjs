import test from 'node:test';
import assert from 'node:assert/strict';
import {completionPercent,stableSelection} from '../frontend/metrics.ts';
test('missing completions never become zero percent',()=>{
 assert.equal(completionPercent('10',null),null);
 assert.equal(completionPercent(null,'5'),null);
 assert.equal(completionPercent('0','0'),null);
 assert.equal(completionPercent('10','0'),0);
 assert.equal(completionPercent('10','11'),null);
 assert.equal(completionPercent('2400000','2397718'),99.9049);
});
test('polling retains the first displayed snapshot',()=>{
 const first=stableSelection('', ['old']);
 assert.equal(first,'old');
 assert.equal(stableSelection(first,['new','old']),'old');
 assert.equal(stableSelection('new',['new','old']),'new');
 assert.equal(stableSelection('',[]),'');
});
import {deliveryLabel,campaignNotice} from '../frontend/status.ts';
test('source final never means campaign pass',()=>{
 assert.match(deliveryLabel('final'),/Source final/);
 assert.match(deliveryLabel('final'),/not campaign/);
 assert.match(campaignNotice('nbsr-sphere-rxe2026111430').text,/INVALID_PARTIAL/);
 assert.equal(campaignNotice('nbsr-sphere-rxe2026111430').failed,true);
 assert.equal(campaignNotice('nbsr-sphere-rxe2026111431').failed,false);
 assert.match(campaignNotice('nbsr-sphere-rxe2026111431').text,/not established/);
 assert.equal(campaignNotice('nbsr-sphere-rxe2026111430.snapshot').failed,true);
 assert.equal(campaignNotice('prefix-nbsr-sphere-rxe2026111430').failed,false);
});

import {gateDetail} from '../frontend/status.ts';
test('snapshot gate does not deny independently observed delivery',()=>{
 assert.match(gateDetail('Source connection','no live feed is connected'),/does not establish remote liveness/);
 assert.equal(gateDetail('Accounting','original detail'),'original detail');
});
