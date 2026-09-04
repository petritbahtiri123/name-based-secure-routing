"""External NPF_Loopback capture for Task 4h; never controls benchmark state."""
import contextlib
import csv
import json
from pathlib import Path
import signal
import subprocess
import time
import statistics


def flow_table(packets,server_port):
    grouped={}
    for packet in packets:
        outbound=int(packet['dstport'])==server_port
        client_port=int(packet['srcport'] if outbound else packet['dstport'])
        flow=grouped.setdefault(client_port,dict(client_port=client_port,server_port=server_port,
            first_outbound_timestamp=None,first_reply_timestamp=None,last_timestamp=None,
            outbound_packets=0,inbound_packets=0,initial_packets=0,retry_packets=0))
        stamp=float(packet['timestamp'])
        flow['last_timestamp']=stamp
        if outbound:
            flow['outbound_packets']+=1
            flow['first_outbound_timestamp'] = flow['first_outbound_timestamp'] or stamp
        else:
            flow['inbound_packets']+=1
            flow['first_reply_timestamp'] = flow['first_reply_timestamp'] or stamp
        if str(packet.get('packet_type',''))=='0': flow['initial_packets']+=1
        if str(packet.get('packet_type',''))=='3': flow['retry_packets']+=1
    return [grouped[key] for key in sorted(grouped)]


class ExternalCapture:
    def __init__(self,dumpcap,tshark,interface=r'\Device\NPF_Loopback'):
        self.dumpcap=Path(dumpcap); self.tshark=Path(tshark); self.interface=interface
        self.report={'enabled':True,'valid':False,'status':'not_started'}

    @contextlib.contextmanager
    def capture(self,endpoint,cell_dir):
        server_port=int(endpoint.rsplit(':',1)[1])
        pcap=Path(cell_dir)/'loopback.pcapng'; stderr_path=Path(cell_dir)/'dumpcap.stderr'
        stderr=stderr_path.open('wb')
        process=subprocess.Popen([str(self.dumpcap),'-q','-i',self.interface,'-f',f'udp port {server_port}','-w',str(pcap)],
            stdout=subprocess.DEVNULL,stderr=stderr,creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        time.sleep(.35)
        if process.poll() is not None:
            stderr.close(); raise RuntimeError(f'dumpcap exited before workload: {process.returncode}')
        self.report.update(status='capturing',server_port=server_port,pcap=str(pcap))
        try:
            yield self
        finally:
            graceful=True
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)
                process.wait(timeout=10)
            except (OSError,subprocess.TimeoutExpired):
                graceful=False; process.terminate(); process.wait(timeout=5)
            stderr.close()
            fields=['frame.time_epoch','ip.src','udp.srcport','ip.dst','udp.dstport','frame.len','quic.long.packet_type','quic.dcid']
            packet_path=Path(cell_dir)/'udp-packets.tsv'
            command=[str(self.tshark),'-r',str(pcap),'-Y',f'udp.port=={server_port}','-T','fields','-E','separator=/t','-E','occurrence=f']
            for field in fields: command.extend(['-e',field])
            result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            packet_path.write_text(result.stdout,encoding='utf-8',newline='\n')
            packets=[]
            if result.returncode==0:
                for row in csv.reader(result.stdout.splitlines(),delimiter='\t'):
                    if len(row)==len(fields) and row[0] and row[2] and row[4]:
                        packets.append(dict(timestamp=float(row[0]),src=row[1],srcport=int(row[2]),dst=row[3],dstport=int(row[4]),
                            frame_len=int(row[5] or 0),packet_type=row[6],dcid=row[7]))
            flows=flow_table(packets,server_port)
            (Path(cell_dir)/'udp-flows.json').write_text(json.dumps(flows,indent=2,sort_keys=True)+'\n',encoding='utf-8',newline='\n')
            reply_delays=[f['first_reply_timestamp']-f['first_outbound_timestamp'] for f in flows if f['first_reply_timestamp'] is not None and f['first_outbound_timestamp'] is not None]
            self.report.update(valid=graceful and process.returncode==0 and result.returncode==0 and pcap.is_file(),
                status='complete',dumpcap_returncode=process.returncode,tshark_returncode=result.returncode,
                packet_count=len(packets),flow_count=len(flows),flows_without_reply=sum(f['first_reply_timestamp'] is None for f in flows),
                repeated_initial_flows=sum(f['initial_packets']>1 for f in flows),retry_packet_count=sum(f['retry_packets'] for f in flows),
                first_reply_delay_median_seconds=statistics.median(reply_delays) if reply_delays else None,
                first_reply_delay_p95_seconds=sorted(reply_delays)[max(0,int(len(reply_delays)*.95)-1)] if reply_delays else None)
