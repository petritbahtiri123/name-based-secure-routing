import re

def absence_confirmed(code, stdout, stderr, target, *, completed, handles_released):
    if (type(code) is not int or code != 1 or completed is not True
            or handles_released is not True or type(stdout) is not str or stdout.strip()
            or type(stderr) is not str or type(target) is not str
            or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', target) is None):
        return False
    message = stderr.strip()
    if not message.endswith(target):
        return False
    prefix = message[:-len(target)].casefold()
    return prefix in ('error: no such object: ', 'error response from daemon: no such container: ')
