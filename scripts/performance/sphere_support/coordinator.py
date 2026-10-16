"""Task-local transport adapter; pinned protocol and result validators are unchanged."""
import json, pathlib, sys, time
from plan import config, remote_argv

def execute(root, ssh_config, started):
    from scripts.performance import linux_native_finite_run as finite
    from scripts.performance.linux_native_lifecycle_remote import download_archive, extract_public_archive
    from scripts.performance.linux_native_pair import verify_index
    from scripts.performance.process_cancellation import Cancellation
    c=config();finite.validate_config(c)
    def remote(target,argv):return remote_argv(target,argv,ssh_config)
    def collection_check():
        if time.monotonic()-started>=80:raise TimeoutError('collection cutoff; reserve final cleanup')
    def collect(target,role,output,*,check_cancelled):
        archive=output/(role+'.tar')
        result=download_archive(remote(target,['tar','-C',target['output'],'-cf','-','.']),archive,
            output/(role+'-transfer-stderr.log'),timeout=min(15,max(.01,80-(time.monotonic()-started))),maximum_bytes=16*1024**2,check_cancelled=collection_check)
        extract_public_archive(archive,output/role,maximum_bytes=16*1024**2,maximum_entries=1000)
        result['index_sha256']=verify_index(output/role)
        # Keep both original archive and extracted proof; bounded at 64MiB total.
        (output/(role+'-transfer.json')).write_text(json.dumps(result))
    finite.remote_command=remote;finite.collect=collect
    with Cancellation() as cancellation:
        def check():
            cancellation.check()
            if (root.parent/'cancel').exists():raise InterruptedError('parent cancellation')
            if time.monotonic()-started>=60:raise TimeoutError('work cutoff; no renewed budget')
        return finite.execute(c,root,check_cancelled=check)

if __name__=='__main__':
    request=json.loads(pathlib.Path(sys.argv[1]).read_text())
    execute(pathlib.Path(request['output']),request['ssh_config'],request['started'])
