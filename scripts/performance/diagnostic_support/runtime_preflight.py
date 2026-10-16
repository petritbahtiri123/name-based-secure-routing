"""Isolated diagnostic gate; no project imports or native operations on import."""
PINS={'cryptography':'45.0.7','cffi':'2.1.0','pycparser':'3.0','cbor2':'5.9.0'}
REQUIRES_PYTHON='>=3.12,<3.15'
def errors(facts,requirement=REQUIRES_PYTHON):
    result=[]
    if requirement!=REQUIRES_PYTHON:result.append('unreviewed Python requirement')
    version=facts.get('python',[])
    if (not isinstance(version,(tuple,list)) or len(version)!=3 or any(type(v) is not int or v<0 for v in version)
            or not (3,12,0)<=tuple(version)<(3,15,0)):result.append('Python outside '+requirement)
    if facts.get('implementation')!='cpython' or facts.get('platform')!='linux' or facts.get('machine') not in ('x86_64','amd64'):result.append('unsupported runtime platform')
    for name,expected in PINS.items():
        actual=facts.get('versions',{}).get(name)
        if actual!=expected:result.append(name+': expected '+expected+', observed '+str(actual))
    if not facts.get('git'):result.append('Git unavailable')
    return result
def gate(facts,import_check,integrity_check,requirement=REQUIRES_PYTHON):
    problems=errors(facts,requirement)
    if problems:raise ValueError('; '.join(problems))
    import_check()  # ABI/import failures propagate; no metadata-only readiness.
    return integrity_check()  # Original source/Git/binary checks still mandatory.
