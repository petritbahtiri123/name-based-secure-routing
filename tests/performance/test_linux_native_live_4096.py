import pytest
from scripts.performance import linux_native_lifecycle as native
from scripts.performance.linux_native_lifecycle_coordinator import validate_config,endpoint_arguments
from scripts.performance.linux_native_lifecycle_remote import extract_public_archive
from tests.performance.test_linux_native_lifecycle import fixture
from tests.performance.test_linux_native_lifecycle_coordinator import config
from tests.performance.test_linux_native_lifecycle_remote import archive


def test_4096_only_live_bundle_mode():
    value=config()|dict(count=4096,bundle_mode='live-bundles')
    assert validate_config(value)==value
    assert native.argument_parser().parse_args(endpoint_arguments(value,'source')[4:]).count==4096
    argv,_=fixture(count=4096,bundle_mode='live-bundles')
    assert argv[argv.index('--lifecycle-clients')+1]=='4096'
    with pytest.raises(ValueError):
        fixture(count=4096)


def test_archive_count_bound_is_explicit_and_enforced(tmp_path):
    p=archive(tmp_path,[(f'file{i}','file',b'x') for i in range(3)])
    with pytest.raises(ValueError,match='count'):
        extract_public_archive(p,tmp_path/'too-small',maximum_entries=2)
    assert not (tmp_path/'too-small').exists()
    extract_public_archive(p,tmp_path/'accepted',maximum_entries=20000)
    assert len(list((tmp_path/'accepted').iterdir()))==3


@pytest.mark.parametrize('bound',[True,0,40001,None])
def test_invalid_entry_bound_rejects(tmp_path,bound):
    p=archive(tmp_path,[('file','file',b'x')])
    with pytest.raises(ValueError):
        extract_public_archive(p,tmp_path/'out',maximum_entries=bound)


@pytest.mark.parametrize('count,role,expected',[(2048,'source',10000),(4096,'source',20000),(4096,'destination',10000)])
def test_collection_bound_is_scoped_to_4096_source(tmp_path,monkeypatch,count,role,expected):
    from types import SimpleNamespace
    from scripts.performance import linux_native_lifecycle_run as run
    observed=[]
    class Manager:
        def __init__(self,*args,**kwargs):
            self.children={role:object()}
            self.ledger=SimpleNamespace(positions={role:1})
        def start_command(self,*args):
            raise InterruptedError('stop before launch')
        wait=send=finish=sleep=lambda *args:None
        def close(self):
            return {}
    monkeypatch.setattr(run,'Manager',Manager)
    monkeypatch.setattr(run,'collect',lambda *args,**kwargs:observed.append(kwargs.get('maximum_entries',10000)))
    with pytest.raises(InterruptedError):
        run.execute(config()|dict(count=count,bundle_mode='live-bundles'),tmp_path/'out')
    assert observed==[expected]
