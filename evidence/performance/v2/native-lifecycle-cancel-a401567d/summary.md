# Native lifecycle runner live cancellation

Six genuine SIGTERM controls pass at a401567d: three source wrappers cancelled
while native UDP sockets exist during pending connection, and three destination
wrappers cancelled while listening. Each test first verifies live PID/start/
executable/FD/inode binding, signals only its owned unreaped wrapper, then checks
InterruptedError/SIGTERM rejection, invalid forced-cleanup metadata, nonzero
wrapper exit, missing success result, and absence of the original child identity.
Every owned child group is killed and reaped; all copied indexes verify.

The source uses an unused fixture endpoint; no completed admission, TLS negative
case or destination availability claim is inferred. These are cancellation
controls, not performance runs. Forced process cleanup is distinct from graceful
eleven-counter ownership cleanup. SIGKILL/host failure remain outside catchable
signal handling. No protocol, security or production source changed.

The existing stopped, campaign-owned 512-test containers were restarted only for
these controls. New output/private fixture paths are under distinct /tmp roots;
original bind-mounted evidence was not rewritten. Public output was copied and
verified after each role. Both containers are stopped again. Private generated
fixture keys stay outside the published output roots.
