"""One fresh enumeration per directory per check; no cross-check metadata cache."""
import os,stat
def snapshot(root, groups):
    canonical=lambda p:os.path.normcase(os.path.abspath(p))
    root=canonical(root)
    selected={key:[canonical(p) for p in paths] for key,paths in groups.items()}
    if 'task' in selected:raise ValueError('reserved accounting group')
    for paths in selected.values():
        for path in paths:
            if os.path.commonpath([root,path])!=root:raise ValueError('group outside task tree')
    def safe(info):
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
            raise ValueError('reparse/link accounting uncertainty')
    info=os.lstat(root);safe(info)
    if not stat.S_ISDIR(info.st_mode):raise ValueError('task root not directory')
    sizes={}
    def visit(path):
        total=0
        with os.scandir(path) as entries:
            for entry in entries:
                info=entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):
                    # Match the old rglob/is_file accounting: file links count,
                    # directory links are not descended; dangling links count zero.
                    try:target=entry.stat(follow_symlinks=True)
                    except FileNotFoundError:continue
                    if stat.S_ISREG(target.st_mode):total+=target.st_size
                    elif not stat.S_ISDIR(target.st_mode):raise ValueError('unsupported link target')
                    continue
                safe(info)
                if stat.S_ISDIR(info.st_mode):total+=visit(entry.path)
                elif stat.S_ISREG(info.st_mode):total+=info.st_size
                else:raise ValueError('unsupported task entry type')
        sizes[canonical(path)]=total
        return total
    total=visit(root)
    return {'task':total,**{key:sum(sizes[path] for path in paths) for key,paths in selected.items()}}
