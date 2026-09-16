from pathlib import Path
root=Path(__file__).resolve().parent
source=Path('C:/NBSR-build/b3-event-paced-70210e48/event_monitor.rs').read_text()
start=source.index('fn poll_pending(')
end=source.index('\nasync fn scan',start)
source=source[:start]+'''fn poll_pending(pending: &mut Vec<Request>) {
    poll_selected(pending, None);
}
fn poll_selected(pending: &mut Vec<Request>, changed: Option<&std::collections::HashSet<PathBuf>>) -> usize {
    let mut index=0;
    let mut checked=0;
    while index<pending.len() {
        if pending[index].ready.is_closed() { pending.swap_remove(index); continue; }
        if changed.is_none_or(|paths|paths.contains(&pending[index].path)) {
            checked+=1;
            if pending[index].path.is_file() {
                let request=pending.swap_remove(index);
                let _=request.ready.send(());
                continue;
            }
        }
        index+=1;
    }
    checked
}
''' + source[end:]
source=source.replace('let changed = gate.as_mut().is_none_or(|g|g.changed());\n        if added || changed { poll_pending(&mut pending); }\n        else { pending.retain(|r|!r.ready.is_closed()); }',
'''let changed = gate.as_mut().and_then(|g|g.changes());
        if added { poll_pending(&mut pending); }
        else { poll_selected(&mut pending, changed.as_ref()); }''')
insert=source.index('    struct Fixture(PathBuf);')
source=source[:insert]+'''    #[test]
    fn only_changed_paths_are_statted_and_cancellation_is_still_removed() {
        let (a, mut a_rx)=oneshot::channel();
        let (b, mut b_rx)=oneshot::channel();
        let (cancelled, cancelled_rx)=oneshot::channel();
        drop(cancelled_rx);
        let mut pending=vec![Request {path:PathBuf::from("missing-a"),ready:a},
                             Request {path:PathBuf::from("missing-b"),ready:b},
                             Request {path:PathBuf::from("cancelled"),ready:cancelled}];
        let names=std::collections::HashSet::from([PathBuf::from("missing-a")]);
        assert_eq!(poll_selected(&mut pending,Some(&names)),1);
        assert_eq!(pending.len(),2);
        assert!(a_rx.try_recv().is_err()); assert!(b_rx.try_recv().is_err());
        assert_eq!(poll_selected(&mut pending,None),2);
    }

''' +source[insert:]
(root/'event_monitor.rs').write_text(source)
