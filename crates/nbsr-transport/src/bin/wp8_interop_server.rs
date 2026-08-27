use std::collections::{BTreeMap, VecDeque};
use std::env;
use std::fs;
use std::io::{Read, Write};
use std::net::{Ipv4Addr, SocketAddr};
use std::path::{Path, PathBuf};
#[cfg(not(windows))]
use std::process::{Command, Stdio};
#[cfg(feature = "benchmark-harness")]
use std::sync::Arc;
use std::sync::mpsc::{self, Receiver, Sender, TryRecvError};
use std::thread::JoinHandle;
use std::time::Duration;

#[cfg(feature = "benchmark-harness")]
use nbsr_transport::StreamCreditRefill;
use nbsr_transport::{
    AdmissionPolicy, AuthorizedServicePolicy, ControlSession, CoreV02Limits, DestinationAdmission,
    EdgeIdentity, EdgeRole, LocalFederationAdmissionAttestations,
    LocalFederationAdmissionAuthorities, PeerPolicy, RouteGrantIssuer, SessionReject, TlsMaterial,
    TransportListener, TrustProfileId, build_server_config, decode_control_envelope,
};
use rustls::RootCertStore;
use rustls::pki_types::{CertificateDer, PrivateKeyDer, PrivatePkcs8KeyDer};
use sha2::{Digest, Sha256};

fn cli_path(name: &str) -> PathBuf {
    let args: Vec<String> = env::args().collect();
    let index = args
        .iter()
        .position(|item| item == name)
        .unwrap_or_else(|| panic!("missing {name}"));
    PathBuf::from(
        args.get(index + 1)
            .unwrap_or_else(|| panic!("missing value for {name}")),
    )
}

fn optional_cli_value(name: &str) -> Option<String> {
    let args: Vec<String> = env::args().collect();
    args.iter()
        .position(|item| item == name)
        .and_then(|index| args.get(index + 1).cloned())
}

fn optional_cli_path_strict(name: &str) -> Option<PathBuf> {
    let args = env::args().collect::<Vec<_>>();
    let positions = args
        .iter()
        .enumerate()
        .filter_map(|(index, value)| (value == name).then_some(index))
        .collect::<Vec<_>>();
    match positions.as_slice() {
        [] => None,
        [index] => {
            let value = args
                .get(index + 1)
                .filter(|value| !value.starts_with("--"))
                .unwrap_or_else(|| panic!("missing value for {name}"));
            Some(PathBuf::from(value))
        }
        _ => panic!("duplicate {name}"),
    }
}

const DEMO_BACKEND_MAP_SCHEMA: &str = "NBSR-DEMO-BACKEND-MAP-v1";
const DEMO_BACKEND_MAX_MAP_BYTES: u64 = 4 * 1024;
const RUNTIME_ADMISSION_SCHEMA: &str = "NBSR-RUNTIME-ADMISSION-v1";
const RUNTIME_ADMISSION_MAX_BYTES: u64 = 16 * 1024;
const DEMO_BACKEND_MAX_EXECUTABLE_BYTES: u64 = 256 * 1024 * 1024;
const DEMO_BACKEND_MAX_REQUEST_BYTES: usize = 4 * 1024;
const DEMO_BACKEND_MAX_RESPONSE_BYTES: usize = 4 * 1024;
const DEMO_BACKEND_MAX_STATUS_BYTES: usize = 256;
const DEMO_BACKEND_OPERATION_TIMEOUT: Duration = Duration::from_secs(15);
const DEMO_BACKEND_COMPLETION_STATUS: &[u8] = b"NBSR_DEMO_BACKEND_COMPLETE requests=1 status=ok\n";

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct DemoBackendMap {
    service_id: String,
    executable: PathBuf,
    executable_sha256: [u8; 32],
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct RuntimeAdmissionConfig {
    pub(crate) policy: AdmissionPolicy,
    pub(crate) service_identity: String,
    pub(crate) service_digest: [u8; 32],
    pub(crate) transport: String,
    pub(crate) port: u16,
    pub(crate) proof_thumbprint: [u8; 32],
    pub(crate) trusted_issuer: RouteGrantIssuer,
}

#[derive(Clone, Copy)]
struct DemoBackendRouteConfig<'a> {
    backend: &'a DemoBackendMap,
    admission: Option<&'a RuntimeAdmissionConfig>,
}

pub(crate) fn accept_configured_route(
    session: &mut ControlSession,
    route: &nbsr_transport::CoreV02Envelope,
    attestations: &LocalFederationAdmissionAttestations,
    runtime_admission: Option<&RuntimeAdmissionConfig>,
) -> Result<nbsr_transport::ActiveChannel, SessionReject> {
    if runtime_admission.is_some() {
        session.accept_route_open(route)
    } else {
        session.accept_federated_route_open(route, attestations)
    }
}

#[derive(Debug)]
pub(crate) struct VerifiedExecutable {
    spawn_path: PathBuf,
    current_dir: PathBuf,
    #[cfg(any(windows, target_os = "linux"))]
    argv0: PathBuf,
    #[cfg(windows)]
    _staging: WindowsStagedExecutable,
    #[cfg(not(windows))]
    _guard: fs::File,
}

#[cfg(windows)]
#[derive(Debug)]
struct WindowsStagedExecutable {
    guard: Option<fs::File>,
    directory_guard: Option<fs::File>,
    path: PathBuf,
    directory: PathBuf,
}

#[cfg(windows)]
impl Drop for WindowsStagedExecutable {
    fn drop(&mut self) {
        self.guard.take();
        let _ = fs::remove_file(&self.path);
        self.directory_guard.take();
        let _ = fs::remove_dir(&self.directory);
    }
}

type BackendPipeWriter = Box<dyn Write + Send>;
type BackendPipeReader = Box<dyn Read + Send>;

#[cfg(not(windows))]
struct BackendProcess(std::process::Child);

#[cfg(not(windows))]
impl BackendProcess {
    fn kill(&mut self) -> std::io::Result<()> {
        #[cfg(target_os = "linux")]
        {
            unsafe extern "C" {
                fn kill(process: i32, signal: i32) -> i32;
            }
            if unsafe { kill(-(self.0.id() as i32), 9) } == 0 {
                return Ok(());
            }
        }
        self.0.kill()
    }

    fn terminate_descendants(&mut self) {
        #[cfg(target_os = "linux")]
        unsafe {
            unsafe extern "C" {
                fn kill(process: i32, signal: i32) -> i32;
            }
            let _ = kill(-(self.0.id() as i32), 9);
        }
    }

    fn wait(&mut self) -> std::io::Result<std::process::ExitStatus> {
        self.0.wait()
    }

    fn try_wait(&mut self) -> std::io::Result<Option<std::process::ExitStatus>> {
        self.0.try_wait()
    }
}

#[cfg(not(windows))]
fn spawn_backend_process(
    executable: &VerifiedExecutable,
    deadline: std::time::Instant,
    cancel: &Receiver<()>,
) -> Result<
    (
        BackendProcess,
        BackendPipeWriter,
        BackendPipeReader,
        BackendPipeReader,
    ),
    DemoBackendError,
> {
    worker_checkpoint(Some(deadline), Some(cancel))?;
    let mut command = Command::new(&executable.spawn_path);
    command
        .env_clear()
        .current_dir(&executable.current_dir)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(target_os = "linux")]
    {
        use std::os::unix::process::CommandExt;
        command.arg0(&executable.argv0);
        unsafe {
            command.pre_exec(|| {
                unsafe extern "C" {
                    fn syscall(number: std::os::raw::c_long, ...) -> std::os::raw::c_long;
                    fn setpgid(process: i32, group: i32) -> i32;
                }
                const SYS_CLOSE_RANGE: std::os::raw::c_long = 436;
                const CLOSE_RANGE_CLOEXEC: u32 = 1 << 2;
                if setpgid(0, 0) == -1
                    || syscall(SYS_CLOSE_RANGE, 3_u32, u32::MAX, CLOSE_RANGE_CLOEXEC) == -1
                {
                    return Err(std::io::Error::last_os_error());
                }
                Ok(())
            });
        }
    }
    let mut child = command.spawn().map_err(|_| DemoBackendError::SpawnFailed)?;
    if let Err(error) = worker_checkpoint(Some(deadline), Some(cancel)) {
        let _ = child.kill();
        let _ = child.wait();
        return Err(error);
    }
    let pipes = (child.stdin.take(), child.stdout.take(), child.stderr.take());
    let (Some(stdin), Some(stdout), Some(stderr)) = pipes else {
        let _ = child.kill();
        let _ = child.wait();
        return Err(DemoBackendError::SpawnFailed);
    };
    Ok((
        BackendProcess(child),
        Box::new(stdin),
        Box::new(stdout),
        Box::new(stderr),
    ))
}

#[cfg(windows)]
mod windows_backend_process {
    use super::{
        BackendPipeReader, BackendPipeWriter, DemoBackendError, Receiver, VerifiedExecutable,
        worker_checkpoint,
    };
    use std::ffi::c_void;
    use std::fs;
    use std::os::windows::ffi::OsStrExt;
    use std::os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle};
    use std::os::windows::process::ExitStatusExt;
    use std::process::ExitStatus;

    type Handle = *mut c_void;

    #[repr(C)]
    struct SecurityAttributes {
        length: u32,
        security_descriptor: *mut c_void,
        inherit_handle: i32,
    }

    #[repr(C)]
    struct StartupInfoW {
        cb: u32,
        reserved: *mut u16,
        desktop: *mut u16,
        title: *mut u16,
        x: u32,
        y: u32,
        x_size: u32,
        y_size: u32,
        x_chars: u32,
        y_chars: u32,
        fill_attribute: u32,
        flags: u32,
        show_window: u16,
        reserved2_size: u16,
        reserved2: *mut u8,
        stdin: Handle,
        stdout: Handle,
        stderr: Handle,
    }

    #[repr(C)]
    struct StartupInfoExW {
        startup: StartupInfoW,
        attributes: *mut c_void,
    }

    #[repr(C)]
    struct ProcessInformation {
        process: Handle,
        thread: Handle,
        process_id: u32,
        thread_id: u32,
    }

    #[repr(C)]
    struct JobObjectBasicLimitInformation {
        per_process_user_time_limit: i64,
        per_job_user_time_limit: i64,
        limit_flags: u32,
        minimum_working_set_size: usize,
        maximum_working_set_size: usize,
        active_process_limit: u32,
        affinity: usize,
        priority_class: u32,
        scheduling_class: u32,
    }

    #[repr(C)]
    struct IoCounters {
        read_operation_count: u64,
        write_operation_count: u64,
        other_operation_count: u64,
        read_transfer_count: u64,
        write_transfer_count: u64,
        other_transfer_count: u64,
    }

    #[repr(C)]
    struct JobObjectExtendedLimitInformation {
        basic_limit_information: JobObjectBasicLimitInformation,
        io_info: IoCounters,
        process_memory_limit: usize,
        job_memory_limit: usize,
        peak_process_memory_used: usize,
        peak_job_memory_used: usize,
    }

    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn CreatePipe(
            read_pipe: *mut Handle,
            write_pipe: *mut Handle,
            attributes: *mut SecurityAttributes,
            size: u32,
        ) -> i32;
        fn SetHandleInformation(handle: Handle, mask: u32, flags: u32) -> i32;
        fn InitializeProcThreadAttributeList(
            list: *mut c_void,
            count: u32,
            flags: u32,
            size: *mut usize,
        ) -> i32;
        fn UpdateProcThreadAttribute(
            list: *mut c_void,
            flags: u32,
            attribute: usize,
            value: *mut c_void,
            size: usize,
            previous: *mut c_void,
            return_size: *mut usize,
        ) -> i32;
        fn DeleteProcThreadAttributeList(list: *mut c_void);
        fn CreateProcessW(
            application_name: *const u16,
            command_line: *mut u16,
            process_attributes: *mut SecurityAttributes,
            thread_attributes: *mut SecurityAttributes,
            inherit_handles: i32,
            creation_flags: u32,
            environment: *mut c_void,
            current_directory: *const u16,
            startup: *mut StartupInfoW,
            process_information: *mut ProcessInformation,
        ) -> i32;
        fn WaitForSingleObject(handle: Handle, milliseconds: u32) -> u32;
        fn GetExitCodeProcess(process: Handle, exit_code: *mut u32) -> i32;
        fn TerminateProcess(process: Handle, exit_code: u32) -> i32;
        fn CreateJobObjectW(attributes: *mut SecurityAttributes, name: *const u16) -> Handle;
        fn SetInformationJobObject(
            job: Handle,
            information_class: u32,
            information: *mut c_void,
            information_length: u32,
        ) -> i32;
        fn AssignProcessToJobObject(job: Handle, process: Handle) -> i32;
        fn TerminateJobObject(job: Handle, exit_code: u32) -> i32;
        fn ResumeThread(thread: Handle) -> u32;
    }

    pub(super) struct BackendProcess {
        process: OwnedHandle,
        _thread: OwnedHandle,
        job: OwnedHandle,
    }

    impl BackendProcess {
        pub(super) fn kill(&mut self) -> std::io::Result<()> {
            if unsafe { TerminateJobObject(self.job.as_raw_handle(), 1) } == 0 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        }

        pub(super) fn terminate_descendants(&mut self) {
            let _ = unsafe { TerminateJobObject(self.job.as_raw_handle(), 1) };
        }

        pub(super) fn wait(&mut self) -> std::io::Result<ExitStatus> {
            let result = unsafe { WaitForSingleObject(self.process.as_raw_handle(), u32::MAX) };
            if result != 0 {
                return Err(std::io::Error::last_os_error());
            }
            self.status()
        }

        pub(super) fn try_wait(&mut self) -> std::io::Result<Option<ExitStatus>> {
            match unsafe { WaitForSingleObject(self.process.as_raw_handle(), 0) } {
                0 => self.status().map(Some),
                258 => Ok(None),
                _ => Err(std::io::Error::last_os_error()),
            }
        }

        fn status(&self) -> std::io::Result<ExitStatus> {
            let mut code = 0_u32;
            if unsafe { GetExitCodeProcess(self.process.as_raw_handle(), &mut code) } == 0 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(ExitStatus::from_raw(code))
        }
    }

    fn pipe() -> std::io::Result<(OwnedHandle, OwnedHandle)> {
        let mut attributes = SecurityAttributes {
            length: std::mem::size_of::<SecurityAttributes>() as u32,
            security_descriptor: std::ptr::null_mut(),
            inherit_handle: 1,
        };
        let mut read = std::ptr::null_mut();
        let mut write = std::ptr::null_mut();
        if unsafe { CreatePipe(&mut read, &mut write, &mut attributes, 0) } == 0 {
            return Err(std::io::Error::last_os_error());
        }
        Ok((unsafe { OwnedHandle::from_raw_handle(read) }, unsafe {
            OwnedHandle::from_raw_handle(write)
        }))
    }

    fn clear_inherit(handle: &OwnedHandle) -> std::io::Result<()> {
        if unsafe { SetHandleInformation(handle.as_raw_handle(), 1, 0) } == 0 {
            return Err(std::io::Error::last_os_error());
        }
        Ok(())
    }

    pub(super) fn spawn(
        executable: &VerifiedExecutable,
        deadline: std::time::Instant,
        cancel: &Receiver<()>,
    ) -> Result<
        (
            BackendProcess,
            BackendPipeWriter,
            BackendPipeReader,
            BackendPipeReader,
        ),
        DemoBackendError,
    > {
        worker_checkpoint(Some(deadline), Some(cancel))?;
        const JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: u32 = 0x0000_2000;
        const JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS: u32 = 9;
        const CREATE_SUSPENDED: u32 = 0x0000_0004;
        let job_raw = unsafe { CreateJobObjectW(std::ptr::null_mut(), std::ptr::null()) };
        if job_raw.is_null() {
            return Err(DemoBackendError::SpawnFailed);
        }
        let job = unsafe { OwnedHandle::from_raw_handle(job_raw) };
        let mut job_limits: JobObjectExtendedLimitInformation = unsafe { std::mem::zeroed() };
        job_limits.basic_limit_information.limit_flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if unsafe {
            SetInformationJobObject(
                job.as_raw_handle(),
                JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
                (&mut job_limits as *mut JobObjectExtendedLimitInformation).cast::<c_void>(),
                std::mem::size_of::<JobObjectExtendedLimitInformation>() as u32,
            )
        } == 0
        {
            return Err(DemoBackendError::SpawnFailed);
        }
        let (child_stdin, parent_stdin) = pipe().map_err(|_| DemoBackendError::SpawnFailed)?;
        let (parent_stdout, child_stdout) = pipe().map_err(|_| DemoBackendError::SpawnFailed)?;
        let (parent_stderr, child_stderr) = pipe().map_err(|_| DemoBackendError::SpawnFailed)?;
        for handle in [&parent_stdin, &parent_stdout, &parent_stderr] {
            clear_inherit(handle).map_err(|_| DemoBackendError::SpawnFailed)?;
        }
        worker_checkpoint(Some(deadline), Some(cancel))?;

        let mut attribute_bytes = 0_usize;
        unsafe {
            InitializeProcThreadAttributeList(std::ptr::null_mut(), 1, 0, &mut attribute_bytes);
        }
        if attribute_bytes == 0 {
            return Err(DemoBackendError::SpawnFailed);
        }
        let words = attribute_bytes.div_ceil(std::mem::size_of::<usize>());
        let mut attribute_storage = vec![0_usize; words];
        let attribute_list = attribute_storage.as_mut_ptr().cast::<c_void>();
        if unsafe { InitializeProcThreadAttributeList(attribute_list, 1, 0, &mut attribute_bytes) }
            == 0
        {
            return Err(DemoBackendError::SpawnFailed);
        }
        let mut inherited = [
            child_stdin.as_raw_handle(),
            child_stdout.as_raw_handle(),
            child_stderr.as_raw_handle(),
        ];
        if unsafe {
            UpdateProcThreadAttribute(
                attribute_list,
                0,
                0x0002_0002,
                inherited.as_mut_ptr().cast::<c_void>(),
                std::mem::size_of_val(&inherited),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
            )
        } == 0
        {
            unsafe { DeleteProcThreadAttributeList(attribute_list) };
            return Err(DemoBackendError::SpawnFailed);
        }

        let startup = StartupInfoW {
            cb: std::mem::size_of::<StartupInfoExW>() as u32,
            reserved: std::ptr::null_mut(),
            desktop: std::ptr::null_mut(),
            title: std::ptr::null_mut(),
            x: 0,
            y: 0,
            x_size: 0,
            y_size: 0,
            x_chars: 0,
            y_chars: 0,
            fill_attribute: 0,
            flags: 0x0000_0100,
            show_window: 0,
            reserved2_size: 0,
            reserved2: std::ptr::null_mut(),
            stdin: child_stdin.as_raw_handle(),
            stdout: child_stdout.as_raw_handle(),
            stderr: child_stderr.as_raw_handle(),
        };
        let mut startup_ex = StartupInfoExW {
            startup,
            attributes: attribute_list,
        };
        let mut process_information = ProcessInformation {
            process: std::ptr::null_mut(),
            thread: std::ptr::null_mut(),
            process_id: 0,
            thread_id: 0,
        };
        let application = executable
            .spawn_path
            .as_os_str()
            .encode_wide()
            .chain(std::iter::once(0))
            .collect::<Vec<_>>();
        let mut command_line = format!("\"{}\"", executable.argv0.display())
            .encode_utf16()
            .chain(std::iter::once(0))
            .collect::<Vec<_>>();
        let current_directory = executable
            .current_dir
            .as_os_str()
            .encode_wide()
            .chain(std::iter::once(0))
            .collect::<Vec<_>>();
        let mut empty_environment = [0_u16, 0];
        worker_checkpoint(Some(deadline), Some(cancel))?;
        let created = unsafe {
            CreateProcessW(
                application.as_ptr(),
                command_line.as_mut_ptr(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                1,
                0x0008_0000 | 0x0800_0000 | 0x0000_0400 | CREATE_SUSPENDED,
                empty_environment.as_mut_ptr().cast::<c_void>(),
                current_directory.as_ptr(),
                &mut startup_ex.startup,
                &mut process_information,
            )
        };
        unsafe { DeleteProcThreadAttributeList(attribute_list) };
        if created == 0 {
            return Err(DemoBackendError::SpawnFailed);
        }
        let process = unsafe { OwnedHandle::from_raw_handle(process_information.process) };
        let thread = unsafe { OwnedHandle::from_raw_handle(process_information.thread) };
        if unsafe { AssignProcessToJobObject(job.as_raw_handle(), process.as_raw_handle()) } == 0
            || unsafe { ResumeThread(thread.as_raw_handle()) } == u32::MAX
        {
            let _ = unsafe { TerminateProcess(process.as_raw_handle(), 1) };
            let _ = unsafe { WaitForSingleObject(process.as_raw_handle(), u32::MAX) };
            return Err(DemoBackendError::SpawnFailed);
        }
        let mut backend = BackendProcess {
            process,
            _thread: thread,
            job,
        };
        if let Err(error) = worker_checkpoint(Some(deadline), Some(cancel)) {
            let _ = backend.kill();
            let _ = backend.wait();
            return Err(error);
        }
        drop(child_stdin);
        drop(child_stdout);
        drop(child_stderr);
        let stdin: fs::File = parent_stdin.into();
        let stdout: fs::File = parent_stdout.into();
        let stderr: fs::File = parent_stderr.into();
        Ok((backend, Box::new(stdin), Box::new(stdout), Box::new(stderr)))
    }
}

#[cfg(windows)]
use windows_backend_process::BackendProcess;

#[cfg(windows)]
fn spawn_backend_process(
    executable: &VerifiedExecutable,
    deadline: std::time::Instant,
    cancel: &Receiver<()>,
) -> Result<
    (
        BackendProcess,
        BackendPipeWriter,
        BackendPipeReader,
        BackendPipeReader,
    ),
    DemoBackendError,
> {
    windows_backend_process::spawn(executable, deadline, cancel)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum DemoBackendError {
    InvalidMap,
    ExecutableHashMismatch,
    ServiceMismatch,
    EmptyRequest,
    RequestTooLarge,
    SpawnFailed,
    ChildFailed,
    ResponseTooLarge,
    StatusTooLarge,
    TimedOut,
    StreamFailed,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[allow(dead_code)]
pub(crate) enum DemoBackendThreadFailure {
    Supervisor,
    DelayVerification,
    Writer,
    Stdout,
    Stderr,
    DisconnectResult,
}

pub(crate) fn load_demo_backend_map(path: &Path) -> Result<DemoBackendMap, DemoBackendError> {
    let contents = String::from_utf8(read_file_bounded(
        path,
        DEMO_BACKEND_MAX_MAP_BYTES,
        DemoBackendError::InvalidMap,
    )?)
    .map_err(|_| DemoBackendError::InvalidMap)?;
    let lines = contents.lines().collect::<Vec<_>>();
    if lines.len() != 4 || lines[0] != DEMO_BACKEND_MAP_SCHEMA {
        return Err(DemoBackendError::InvalidMap);
    }
    let service_id = exact_map_value(lines[1], "service_id=")?;
    if service_id.is_empty()
        || service_id.len() > 255
        || !service_id.bytes().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || b".-_".contains(&byte)
        })
    {
        return Err(DemoBackendError::InvalidMap);
    }
    let executable_value = exact_map_value(lines[2], "executable=")?;
    if executable_value.is_empty() || executable_value.contains('\0') {
        return Err(DemoBackendError::InvalidMap);
    }
    let executable = PathBuf::from(executable_value);
    if !executable.is_absolute() {
        return Err(DemoBackendError::InvalidMap);
    }
    let executable = fs::canonicalize(executable).map_err(|_| DemoBackendError::InvalidMap)?;
    let digest_value = exact_map_value(lines[3], "sha256=")?;
    let executable_sha256 = decode_sha256(digest_value)?;
    if hash_executable(&executable, DEMO_BACKEND_MAX_EXECUTABLE_BYTES)? != executable_sha256 {
        return Err(DemoBackendError::ExecutableHashMismatch);
    }
    Ok(DemoBackendMap {
        service_id: service_id.to_owned(),
        executable,
        executable_sha256,
    })
}

pub(crate) fn load_runtime_admission_config(
    path: &Path,
) -> Result<RuntimeAdmissionConfig, DemoBackendError> {
    let contents = String::from_utf8(read_file_bounded(
        path,
        RUNTIME_ADMISSION_MAX_BYTES,
        DemoBackendError::InvalidMap,
    )?)
    .map_err(|_| DemoBackendError::InvalidMap)?;
    let lines = contents.lines().collect::<Vec<_>>();
    if lines.len() != 17 || lines[0] != RUNTIME_ADMISSION_SCHEMA {
        return Err(DemoBackendError::InvalidMap);
    }
    let source_operator = runtime_identifier(exact_map_value(lines[1], "source_operator=")?)?;
    let source_edge = runtime_identifier(exact_map_value(lines[2], "source_edge=")?)?;
    let destination_operator =
        runtime_identifier(exact_map_value(lines[3], "destination_operator=")?)?;
    let destination_edge = runtime_identifier(exact_map_value(lines[4], "destination_edge=")?)?;
    let service_identity = runtime_identifier(exact_map_value(lines[5], "service_identity=")?)?;
    let service_digest = decode_sha256(exact_map_value(lines[6], "service_digest=")?)?;
    let transport = exact_map_value(lines[7], "transport=")?;
    if !matches!(transport, "tcp" | "udp") {
        return Err(DemoBackendError::InvalidMap);
    }
    let port = strict_positive_u64(exact_map_value(lines[8], "port=")?)?
        .try_into()
        .map_err(|_| DemoBackendError::InvalidMap)?;
    let record_sequence = strict_positive_u64(exact_map_value(lines[9], "record_sequence=")?)?;
    let policy_hash = decode_sha256(exact_map_value(lines[10], "policy_hash=")?)?;
    let now = strict_positive_u64(exact_map_value(lines[11], "now=")?)?;
    let proof_thumbprint = decode_sha256(exact_map_value(lines[12], "proof_thumbprint=")?)?;
    let proof_public_key = decode_sha256(exact_map_value(lines[13], "proof_public_key=")?)?;
    if <[u8; 32]>::from(Sha256::digest(proof_public_key)) != proof_thumbprint {
        return Err(DemoBackendError::InvalidMap);
    }
    let edge_nonce = decode_sha256(exact_map_value(lines[14], "edge_nonce=")?)?;
    let issuer_kid = runtime_identifier(exact_map_value(lines[15], "issuer_kid=")?)?;
    let issuer_public_key = decode_sha256(exact_map_value(lines[16], "issuer_public_key=")?)?;
    let policy = AdmissionPolicy {
        source_operator_id: source_operator,
        source_edge_id: source_edge,
        destination_operator_id: destination_operator,
        destination_edge_id: destination_edge,
        authorized_services: BTreeMap::from([(
            service_identity.clone(),
            AuthorizedServicePolicy {
                accepted_record_sequence: record_sequence,
                policy_hash,
            },
        )]),
        now,
        client_session_public_key: proof_public_key,
        edge_nonce,
    };
    Ok(RuntimeAdmissionConfig {
        policy,
        service_identity,
        service_digest,
        transport: transport.to_owned(),
        port,
        proof_thumbprint,
        trusted_issuer: RouteGrantIssuer {
            kid: issuer_kid.into_bytes(),
            public_key: issuer_public_key,
        },
    })
}

pub(crate) fn ensure_runtime_admission_binding(
    config: &RuntimeAdmissionConfig,
    admitted: &nbsr_transport::ActiveChannel,
) -> Result<(), DemoBackendError> {
    if admitted.service_id != config.service_identity
        || admitted.transport != config.transport
        || admitted.port != config.port
    {
        return Err(DemoBackendError::ServiceMismatch);
    }
    Ok(())
}

pub(crate) fn ensure_runtime_route_grant_binding(
    config: &RuntimeAdmissionConfig,
    route: &nbsr_transport::CoreV02Envelope,
) -> Result<(), DemoBackendError> {
    let digest = route
        .validated_route_grant_service_digest(std::slice::from_ref(&config.trusted_issuer))
        .map_err(|_| DemoBackendError::StreamFailed)?;
    if digest != config.service_digest {
        return Err(DemoBackendError::ServiceMismatch);
    }
    Ok(())
}

fn runtime_identifier(value: &str) -> Result<String, DemoBackendError> {
    if value.is_empty()
        || value.len() > 255
        || matches!(value.as_bytes().first(), Some(b'.' | b'-' | b'_'))
        || matches!(value.as_bytes().last(), Some(b'.' | b'-' | b'_'))
        || value.contains("..")
        || !value.bytes().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || b".-_".contains(&byte)
        })
    {
        return Err(DemoBackendError::InvalidMap);
    }
    Ok(value.to_owned())
}

fn strict_positive_u64(value: &str) -> Result<u64, DemoBackendError> {
    if value.is_empty()
        || (value.len() > 1 && value.starts_with('0'))
        || !value.bytes().all(|byte| byte.is_ascii_digit())
    {
        return Err(DemoBackendError::InvalidMap);
    }
    value
        .parse::<u64>()
        .ok()
        .filter(|value| *value != 0)
        .ok_or(DemoBackendError::InvalidMap)
}

fn exact_map_value<'a>(line: &'a str, prefix: &str) -> Result<&'a str, DemoBackendError> {
    line.strip_prefix(prefix)
        .filter(|value| !value.contains(['\r', '\n']))
        .ok_or(DemoBackendError::InvalidMap)
}

fn decode_sha256(value: &str) -> Result<[u8; 32], DemoBackendError> {
    if value.len() != 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(DemoBackendError::InvalidMap);
    }
    let mut digest = [0_u8; 32];
    for (index, pair) in value.as_bytes().chunks_exact(2).enumerate() {
        let high = hex_nibble(pair[0]).ok_or(DemoBackendError::InvalidMap)?;
        let low = hex_nibble(pair[1]).ok_or(DemoBackendError::InvalidMap)?;
        digest[index] = (high << 4) | low;
    }
    Ok(digest)
}

fn hex_nibble(value: u8) -> Option<u8> {
    match value {
        b'0'..=b'9' => Some(value - b'0'),
        b'a'..=b'f' => Some(value - b'a' + 10),
        _ => None,
    }
}

fn read_file_bounded(
    path: &Path,
    limit: u64,
    error: DemoBackendError,
) -> Result<Vec<u8>, DemoBackendError> {
    let mut file = fs::File::open(path).map_err(|_| error)?;
    let metadata = file.metadata().map_err(|_| error)?;
    if !metadata.file_type().is_file() || metadata.len() > limit {
        return Err(error);
    }
    let mut contents = Vec::with_capacity(metadata.len().min(limit) as usize);
    (&mut file)
        .take(limit.saturating_add(1))
        .read_to_end(&mut contents)
        .map_err(|_| error)?;
    if contents.len() as u64 > limit {
        return Err(error);
    }
    Ok(contents)
}

fn open_executable_guard(path: &Path) -> Result<fs::File, DemoBackendError> {
    let mut options = fs::OpenOptions::new();
    options.read(true);
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        const FILE_SHARE_READ: u32 = 0x0000_0001;
        options.share_mode(FILE_SHARE_READ);
    }
    options
        .open(path)
        .map_err(|_| DemoBackendError::SpawnFailed)
}

fn worker_checkpoint(
    deadline: Option<std::time::Instant>,
    cancel: Option<&Receiver<()>>,
) -> Result<(), DemoBackendError> {
    if cancel.is_some_and(|cancel| !matches!(cancel.try_recv(), Err(TryRecvError::Empty))) {
        return Err(DemoBackendError::ChildFailed);
    }
    if deadline.is_some_and(|deadline| std::time::Instant::now() >= deadline) {
        return Err(DemoBackendError::TimedOut);
    }
    Ok(())
}

fn hash_open_executable(
    file: &mut fs::File,
    limit: u64,
    deadline: Option<std::time::Instant>,
    cancel: Option<&Receiver<()>>,
) -> Result<[u8; 32], DemoBackendError> {
    let metadata = file.metadata().map_err(|_| DemoBackendError::SpawnFailed)?;
    if !metadata.file_type().is_file() || metadata.len() > limit {
        return Err(DemoBackendError::SpawnFailed);
    }
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    let mut total = 0_u64;
    loop {
        worker_checkpoint(deadline, cancel)?;
        let remaining = limit.saturating_add(1).saturating_sub(total);
        if remaining == 0 {
            return Err(DemoBackendError::SpawnFailed);
        }
        let capacity = buffer.len().min(remaining as usize);
        let read = file
            .read(&mut buffer[..capacity])
            .map_err(|_| DemoBackendError::SpawnFailed)?;
        if read == 0 {
            break;
        }
        total = total.saturating_add(read as u64);
        if total > limit {
            return Err(DemoBackendError::SpawnFailed);
        }
        hasher.update(&buffer[..read]);
    }
    Ok(hasher.finalize().into())
}

fn hash_executable(path: &Path, limit: u64) -> Result<[u8; 32], DemoBackendError> {
    let mut file = open_executable_guard(path)?;
    hash_open_executable(&mut file, limit, None, None)
}

#[cfg(windows)]
fn stage_verified_windows_executable(
    source_path: &Path,
    expected: [u8; 32],
    deadline: Option<std::time::Instant>,
    cancel: Option<&Receiver<()>>,
) -> Result<(PathBuf, WindowsStagedExecutable), DemoBackendError> {
    use std::ffi::c_void;
    use std::io::{Seek, SeekFrom};
    use std::os::windows::ffi::OsStrExt;
    use std::os::windows::fs::{MetadataExt, OpenOptionsExt};
    use std::sync::atomic::{AtomicU64, Ordering};

    #[repr(C)]
    struct SecurityAttributes {
        length: u32,
        security_descriptor: *mut c_void,
        inherit_handle: i32,
    }

    #[link(name = "advapi32")]
    unsafe extern "system" {
        fn ConvertStringSecurityDescriptorToSecurityDescriptorW(
            descriptor: *const u16,
            revision: u32,
            security_descriptor: *mut *mut c_void,
            size: *mut u32,
        ) -> i32;
    }
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn CreateDirectoryW(path: *const u16, attributes: *mut SecurityAttributes) -> i32;
        fn LocalFree(memory: *mut c_void) -> *mut c_void;
    }

    const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x0000_0400;
    const FILE_FLAG_BACKUP_SEMANTICS: u32 = 0x0200_0000;
    const FILE_SHARE_READ: u32 = 0x0000_0001;
    static STAGING_SEQUENCE: AtomicU64 = AtomicU64::new(0);

    worker_checkpoint(deadline, cancel)?;
    let server =
        fs::canonicalize(std::env::current_exe().map_err(|_| DemoBackendError::SpawnFailed)?)
            .map_err(|_| DemoBackendError::SpawnFailed)?;
    let trusted_parent = server
        .parent()
        .ok_or(DemoBackendError::SpawnFailed)?
        .to_owned();
    let parent_metadata =
        fs::metadata(&trusted_parent).map_err(|_| DemoBackendError::SpawnFailed)?;
    if !parent_metadata.is_dir()
        || parent_metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0
    {
        return Err(DemoBackendError::SpawnFailed);
    }

    let sequence = STAGING_SEQUENCE.fetch_add(1, Ordering::Relaxed);
    let nonce = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|_| DemoBackendError::SpawnFailed)?
        .as_nanos();
    let directory = trusted_parent.join(format!(
        ".nbsr-demo-backend-{}-{sequence}-{nonce}",
        std::process::id()
    ));
    let directory_wide = directory
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect::<Vec<_>>();
    let descriptor_wide = "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;OW)"
        .encode_utf16()
        .chain(std::iter::once(0))
        .collect::<Vec<_>>();
    let mut descriptor = std::ptr::null_mut();
    if unsafe {
        ConvertStringSecurityDescriptorToSecurityDescriptorW(
            descriptor_wide.as_ptr(),
            1,
            &mut descriptor,
            std::ptr::null_mut(),
        )
    } == 0
    {
        return Err(DemoBackendError::SpawnFailed);
    }
    let mut attributes = SecurityAttributes {
        length: std::mem::size_of::<SecurityAttributes>() as u32,
        security_descriptor: descriptor,
        inherit_handle: 0,
    };
    let created = unsafe { CreateDirectoryW(directory_wide.as_ptr(), &mut attributes) };
    unsafe { LocalFree(descriptor) };
    if created == 0 {
        return Err(DemoBackendError::SpawnFailed);
    }

    let staged_path = directory.join("backend.exe");
    let mut cleanup = WindowsStagedExecutable {
        guard: None,
        directory_guard: None,
        path: staged_path.clone(),
        directory: directory.clone(),
    };
    let result = (|| {
        let metadata = fs::metadata(&directory).map_err(|_| DemoBackendError::SpawnFailed)?;
        if !metadata.is_dir() || metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0 {
            return Err(DemoBackendError::SpawnFailed);
        }
        let mut directory_options = fs::OpenOptions::new();
        directory_options
            .access_mode(0)
            .share_mode(FILE_SHARE_READ)
            .custom_flags(FILE_FLAG_BACKUP_SEMANTICS);
        cleanup.directory_guard = Some(
            directory_options
                .open(&directory)
                .map_err(|_| DemoBackendError::SpawnFailed)?,
        );
        let mut source = open_executable_guard(source_path)?;
        let metadata = source
            .metadata()
            .map_err(|_| DemoBackendError::SpawnFailed)?;
        if !metadata.file_type().is_file() || metadata.len() > DEMO_BACKEND_MAX_EXECUTABLE_BYTES {
            return Err(DemoBackendError::SpawnFailed);
        }
        let mut staged_options = fs::OpenOptions::new();
        staged_options
            .read(true)
            .write(true)
            .create_new(true)
            .share_mode(FILE_SHARE_READ);
        let mut staged = staged_options
            .open(&staged_path)
            .map_err(|_| DemoBackendError::SpawnFailed)?;
        let mut hasher = Sha256::new();
        let mut buffer = [0_u8; 64 * 1024];
        let mut total = 0_u64;
        loop {
            worker_checkpoint(deadline, cancel)?;
            let remaining = DEMO_BACKEND_MAX_EXECUTABLE_BYTES
                .saturating_add(1)
                .saturating_sub(total);
            if remaining == 0 {
                return Err(DemoBackendError::SpawnFailed);
            }
            let capacity = buffer.len().min(remaining as usize);
            let read = source
                .read(&mut buffer[..capacity])
                .map_err(|_| DemoBackendError::SpawnFailed)?;
            if read == 0 {
                break;
            }
            total = total.saturating_add(read as u64);
            if total > DEMO_BACKEND_MAX_EXECUTABLE_BYTES {
                return Err(DemoBackendError::SpawnFailed);
            }
            hasher.update(&buffer[..read]);
            staged
                .write_all(&buffer[..read])
                .map_err(|_| DemoBackendError::SpawnFailed)?;
        }
        if <[u8; 32]>::from(hasher.finalize()) != expected {
            return Err(DemoBackendError::ExecutableHashMismatch);
        }
        staged.flush().map_err(|_| DemoBackendError::SpawnFailed)?;
        staged
            .seek(SeekFrom::Start(0))
            .map_err(|_| DemoBackendError::SpawnFailed)?;
        if hash_open_executable(
            &mut staged,
            DEMO_BACKEND_MAX_EXECUTABLE_BYTES,
            deadline,
            cancel,
        )? != expected
        {
            return Err(DemoBackendError::ExecutableHashMismatch);
        }
        drop(staged);
        let mut guard = open_executable_guard(&staged_path)?;
        if hash_open_executable(
            &mut guard,
            DEMO_BACKEND_MAX_EXECUTABLE_BYTES,
            deadline,
            cancel,
        )? != expected
        {
            return Err(DemoBackendError::ExecutableHashMismatch);
        }
        cleanup.guard = Some(guard);
        Ok(staged_path.clone())
    })();
    match result {
        Ok(path) => Ok((path, cleanup)),
        Err(error) => {
            drop(cleanup);
            Err(error)
        }
    }
}

#[cfg(target_os = "linux")]
fn sealed_verified_executable(
    path: &Path,
    expected: [u8; 32],
    deadline: Option<std::time::Instant>,
    cancel: Option<&Receiver<()>>,
) -> Result<fs::File, DemoBackendError> {
    use std::ffi::CString;
    use std::io::{Seek, SeekFrom};
    use std::os::fd::{AsRawFd, FromRawFd};

    unsafe extern "C" {
        fn memfd_create(name: *const std::os::raw::c_char, flags: u32) -> i32;
        fn fchmod(fd: i32, mode: u32) -> i32;
        fn fcntl(fd: i32, command: i32, argument: i32) -> i32;
    }
    const MFD_CLOEXEC: u32 = 0x0001;
    const MFD_ALLOW_SEALING: u32 = 0x0002;
    const F_ADD_SEALS: i32 = 1033;
    const F_GET_SEALS: i32 = 1034;
    const REQUIRED_SEALS: i32 = 0x0001 | 0x0002 | 0x0004 | 0x0008;

    let mut source = open_executable_guard(path)?;
    let metadata = source
        .metadata()
        .map_err(|_| DemoBackendError::SpawnFailed)?;
    if !metadata.file_type().is_file() || metadata.len() > DEMO_BACKEND_MAX_EXECUTABLE_BYTES {
        return Err(DemoBackendError::SpawnFailed);
    }
    let name = CString::new("nbsr-demo-backend").map_err(|_| DemoBackendError::SpawnFailed)?;
    let raw = unsafe { memfd_create(name.as_ptr(), MFD_CLOEXEC | MFD_ALLOW_SEALING) };
    if raw < 0 {
        return Err(DemoBackendError::SpawnFailed);
    }
    let mut sealed = unsafe { fs::File::from_raw_fd(raw) };
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    let mut total = 0_u64;
    loop {
        worker_checkpoint(deadline, cancel)?;
        let remaining = DEMO_BACKEND_MAX_EXECUTABLE_BYTES
            .saturating_add(1)
            .saturating_sub(total);
        if remaining == 0 {
            return Err(DemoBackendError::SpawnFailed);
        }
        let capacity = buffer.len().min(remaining as usize);
        let read = source
            .read(&mut buffer[..capacity])
            .map_err(|_| DemoBackendError::SpawnFailed)?;
        if read == 0 {
            break;
        }
        total = total.saturating_add(read as u64);
        if total > DEMO_BACKEND_MAX_EXECUTABLE_BYTES {
            return Err(DemoBackendError::SpawnFailed);
        }
        hasher.update(&buffer[..read]);
        sealed
            .write_all(&buffer[..read])
            .map_err(|_| DemoBackendError::SpawnFailed)?;
    }
    if <[u8; 32]>::from(hasher.finalize()) != expected {
        return Err(DemoBackendError::ExecutableHashMismatch);
    }
    sealed.flush().map_err(|_| DemoBackendError::SpawnFailed)?;
    if unsafe { fchmod(sealed.as_raw_fd(), 0o700) } != 0
        || unsafe { fcntl(sealed.as_raw_fd(), F_ADD_SEALS, REQUIRED_SEALS) } != 0
        || unsafe { fcntl(sealed.as_raw_fd(), F_GET_SEALS, 0) } & REQUIRED_SEALS != REQUIRED_SEALS
    {
        return Err(DemoBackendError::SpawnFailed);
    }
    sealed
        .seek(SeekFrom::Start(0))
        .map_err(|_| DemoBackendError::SpawnFailed)?;
    Ok(sealed)
}

fn open_verified_executable_with_controls(
    map: &DemoBackendMap,
    deadline: Option<std::time::Instant>,
    cancel: Option<&Receiver<()>>,
) -> Result<VerifiedExecutable, DemoBackendError> {
    worker_checkpoint(deadline, cancel)?;
    #[cfg(not(windows))]
    let current_dir = map
        .executable
        .parent()
        .ok_or(DemoBackendError::SpawnFailed)?
        .to_owned();
    #[cfg(windows)]
    {
        let (spawn_path, staging) = stage_verified_windows_executable(
            &map.executable,
            map.executable_sha256,
            deadline,
            cancel,
        )?;
        let staged_current_dir = spawn_path
            .parent()
            .ok_or(DemoBackendError::SpawnFailed)?
            .to_owned();
        Ok(VerifiedExecutable {
            spawn_path,
            current_dir: staged_current_dir,
            argv0: map.executable.clone(),
            _staging: staging,
        })
    }
    #[cfg(target_os = "linux")]
    {
        use std::os::fd::AsRawFd;
        let guard =
            sealed_verified_executable(&map.executable, map.executable_sha256, deadline, cancel)?;
        Ok(VerifiedExecutable {
            spawn_path: PathBuf::from(format!("/proc/self/fd/{}", guard.as_raw_fd())),
            current_dir,
            argv0: map.executable.clone(),
            _guard: guard,
        })
    }
    #[cfg(not(any(windows, target_os = "linux")))]
    {
        let _ = current_dir;
        Err(DemoBackendError::SpawnFailed)
    }
}

fn open_verified_executable(map: &DemoBackendMap) -> Result<VerifiedExecutable, DemoBackendError> {
    open_verified_executable_with_controls(map, None, None)
}

#[allow(dead_code)]
pub(crate) fn verify_executable_with_limit_for_test(
    path: &Path,
    limit: u64,
) -> Result<(), DemoBackendError> {
    hash_executable(path, limit).map(|_| ())
}

#[allow(dead_code)]
pub(crate) fn open_verified_executable_for_test(
    map: &DemoBackendMap,
) -> Result<VerifiedExecutable, DemoBackendError> {
    open_verified_executable(map)
}

#[allow(dead_code)]
pub(crate) fn verified_executable_spawn_path_for_test(executable: &VerifiedExecutable) -> &Path {
    &executable.spawn_path
}

#[cfg(any(windows, target_os = "linux"))]
#[allow(dead_code)]
pub(crate) async fn run_verified_executable_for_test(
    executable: VerifiedExecutable,
    admitted: &nbsr_transport::ActiveChannel,
    request: &[u8],
    timeout: Duration,
) -> Result<Vec<u8>, DemoBackendError> {
    if admitted.service_id.is_empty()
        || request.is_empty()
        || request.len() > DEMO_BACKEND_MAX_REQUEST_BYTES
    {
        return Err(DemoBackendError::ChildFailed);
    }
    if timeout.is_zero() {
        return Err(DemoBackendError::TimedOut);
    }
    let deadline = std::time::Instant::now() + timeout;
    start_backend_worker(
        BackendLaunch::Verified(executable),
        request.to_vec(),
        deadline,
        None,
    )?
    .wait_until(deadline)
    .await
}

pub(crate) fn ensure_demo_backend_binding(
    map: &DemoBackendMap,
    admitted: &nbsr_transport::ActiveChannel,
) -> Result<(), DemoBackendError> {
    if admitted.service_id != map.service_id {
        return Err(DemoBackendError::ServiceMismatch);
    }
    Ok(())
}

struct BackendWorker {
    cancel: Sender<()>,
    result: Receiver<Result<Vec<u8>, DemoBackendError>>,
    join: Option<JoinHandle<()>>,
}

impl BackendWorker {
    async fn join_supervisor(&mut self) -> Result<(), DemoBackendError> {
        let Some(join) = self.join.take() else {
            return Ok(());
        };
        tokio::task::spawn_blocking(move || join.join())
            .await
            .map_err(|_| DemoBackendError::ChildFailed)?
            .map_err(|_| DemoBackendError::ChildFailed)
    }

    async fn wait_until(
        mut self,
        deadline: std::time::Instant,
    ) -> Result<Vec<u8>, DemoBackendError> {
        loop {
            if std::time::Instant::now() >= deadline {
                let _ = self.cancel.send(());
                self.join_supervisor().await?;
                return Err(DemoBackendError::TimedOut);
            }
            match self.result.try_recv() {
                Ok(result) => {
                    self.join_supervisor().await?;
                    return result;
                }
                Err(TryRecvError::Empty) => {
                    tokio::time::sleep(Duration::from_millis(2)).await;
                }
                Err(TryRecvError::Disconnected) => {
                    let _ = self.cancel.send(());
                    self.join_supervisor().await?;
                    return Err(DemoBackendError::SpawnFailed);
                }
            }
        }
    }
}

impl Drop for BackendWorker {
    fn drop(&mut self) {
        let _ = self.cancel.send(());
    }
}

#[allow(dead_code)]
pub(crate) async fn run_demo_backend(
    map: &DemoBackendMap,
    admitted: &nbsr_transport::ActiveChannel,
    request: &[u8],
) -> Result<Vec<u8>, DemoBackendError> {
    run_demo_backend_with_timeout(map, admitted, request, DEMO_BACKEND_OPERATION_TIMEOUT).await
}

pub(crate) async fn run_demo_backend_with_timeout(
    map: &DemoBackendMap,
    admitted: &nbsr_transport::ActiveChannel,
    request: &[u8],
    timeout: Duration,
) -> Result<Vec<u8>, DemoBackendError> {
    ensure_demo_backend_binding(map, admitted)?;
    if request.is_empty() {
        return Err(DemoBackendError::EmptyRequest);
    }
    if request.len() > DEMO_BACKEND_MAX_REQUEST_BYTES {
        return Err(DemoBackendError::RequestTooLarge);
    }
    if timeout.is_zero() {
        return Err(DemoBackendError::TimedOut);
    }
    let deadline = std::time::Instant::now() + timeout;
    run_demo_backend_until(map, admitted, request, deadline, None).await
}

async fn run_demo_backend_until(
    map: &DemoBackendMap,
    admitted: &nbsr_transport::ActiveChannel,
    request: &[u8],
    deadline: std::time::Instant,
    failure: Option<DemoBackendThreadFailure>,
) -> Result<Vec<u8>, DemoBackendError> {
    ensure_demo_backend_binding(map, admitted)?;
    if request.is_empty() {
        return Err(DemoBackendError::EmptyRequest);
    }
    if request.len() > DEMO_BACKEND_MAX_REQUEST_BYTES {
        return Err(DemoBackendError::RequestTooLarge);
    }
    if std::time::Instant::now() >= deadline {
        return Err(DemoBackendError::TimedOut);
    }
    start_backend_worker(
        BackendLaunch::Map(map.clone()),
        request.to_vec(),
        deadline,
        failure,
    )?
    .wait_until(deadline)
    .await
}

#[allow(dead_code)]
pub(crate) async fn run_demo_backend_with_thread_failure(
    map: &DemoBackendMap,
    admitted: &nbsr_transport::ActiveChannel,
    request: &[u8],
    timeout: Duration,
    failure: DemoBackendThreadFailure,
) -> Result<Vec<u8>, DemoBackendError> {
    if timeout.is_zero() {
        return Err(DemoBackendError::TimedOut);
    }
    let deadline = std::time::Instant::now() + timeout;
    run_demo_backend_until(map, admitted, request, deadline, Some(failure)).await
}

#[allow(dead_code)]
enum BackendLaunch {
    Map(DemoBackendMap),
    #[cfg(any(windows, target_os = "linux"))]
    Verified(VerifiedExecutable),
}

fn start_backend_worker(
    launch: BackendLaunch,
    request: Vec<u8>,
    deadline: std::time::Instant,
    failure: Option<DemoBackendThreadFailure>,
) -> Result<BackendWorker, DemoBackendError> {
    let (cancel_send, cancel_receive) = mpsc::channel();
    let (result_send, result_receive) = mpsc::channel();
    if failure == Some(DemoBackendThreadFailure::Supervisor) {
        return Err(DemoBackendError::SpawnFailed);
    }
    let join = std::thread::Builder::new()
        .name("nbsr-demo-backend-supervisor".into())
        .spawn(move || {
            if failure == Some(DemoBackendThreadFailure::DelayVerification) {
                let delayed_until = std::time::Instant::now() + Duration::from_millis(250);
                while std::time::Instant::now() < delayed_until {
                    if let Err(error) = worker_checkpoint(Some(deadline), Some(&cancel_receive)) {
                        let _ = result_send.send(Err(error));
                        return;
                    }
                    std::thread::sleep(Duration::from_millis(2));
                }
            }
            let executable = match launch {
                BackendLaunch::Map(map) => match open_verified_executable_with_controls(
                    &map,
                    Some(deadline),
                    Some(&cancel_receive),
                ) {
                    Ok(executable) => executable,
                    Err(error) => {
                        let _ = result_send.send(Err(error));
                        return;
                    }
                },
                #[cfg(any(windows, target_os = "linux"))]
                BackendLaunch::Verified(executable) => executable,
            };
            if let Err(error) = worker_checkpoint(Some(deadline), Some(&cancel_receive)) {
                let _ = result_send.send(Err(error));
                return;
            }
            let (mut child, mut stdin, stdout, stderr) =
                match spawn_backend_process(&executable, deadline, &cancel_receive) {
                    Ok(process) => process,
                    Err(error) => {
                        let _ = result_send.send(Err(error));
                        return;
                    }
                };
            if let Err(error) = worker_checkpoint(Some(deadline), Some(&cancel_receive)) {
                let _ = child.kill();
                let _ = child.wait();
                let _ = result_send.send(Err(error));
                return;
            }
            if failure == Some(DemoBackendThreadFailure::Writer) {
                let _ = child.kill();
                let _ = child.wait();
                let _ = result_send.send(Err(DemoBackendError::SpawnFailed));
                return;
            }
            let writer = match std::thread::Builder::new()
                .name("nbsr-demo-backend-stdin".into())
                .spawn(move || -> Result<(), ()> {
                    stdin.write_all(&request).map_err(|_| ())?;
                    stdin.flush().map_err(|_| ())
                }) {
                Ok(join) => join,
                Err(_) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    let _ = result_send.send(Err(DemoBackendError::SpawnFailed));
                    return;
                }
            };
            if failure == Some(DemoBackendThreadFailure::Stdout) {
                let _ = child.kill();
                let _ = child.wait();
                let _ = writer.join();
                let _ = result_send.send(Err(DemoBackendError::SpawnFailed));
                return;
            }
            let stdout_reader = match std::thread::Builder::new()
                .name("nbsr-demo-backend-stdout".into())
                .spawn(move || read_bounded(stdout, DEMO_BACKEND_MAX_RESPONSE_BYTES))
            {
                Ok(join) => join,
                Err(_) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    let _ = writer.join();
                    let _ = result_send.send(Err(DemoBackendError::SpawnFailed));
                    return;
                }
            };
            if failure == Some(DemoBackendThreadFailure::Stderr) {
                let _ = child.kill();
                let _ = child.wait();
                let _ = writer.join();
                let _ = stdout_reader.join();
                let _ = result_send.send(Err(DemoBackendError::SpawnFailed));
                return;
            }
            let stderr_reader = match std::thread::Builder::new()
                .name("nbsr-demo-backend-stderr".into())
                .spawn(move || read_bounded(stderr, DEMO_BACKEND_MAX_STATUS_BYTES))
            {
                Ok(join) => join,
                Err(_) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    let _ = writer.join();
                    let _ = stdout_reader.join();
                    let _ = result_send.send(Err(DemoBackendError::SpawnFailed));
                    return;
                }
            };
            let mut result_send = (failure != Some(DemoBackendThreadFailure::DisconnectResult))
                .then_some(result_send);
            let mut forced = None;
            let status = loop {
                if cancel_receive.try_recv().is_ok() {
                    forced = Some(DemoBackendError::ChildFailed);
                    let _ = child.kill();
                    break child.wait();
                }
                if std::time::Instant::now() >= deadline {
                    forced = Some(DemoBackendError::TimedOut);
                    let _ = child.kill();
                    break child.wait();
                }
                match child.try_wait() {
                    Ok(Some(status)) => break Ok(status),
                    Ok(None) => std::thread::sleep(Duration::from_millis(2)),
                    Err(error) => break Err(error),
                }
            };
            child.terminate_descendants();
            let wrote = writer.join().is_ok_and(|result| result.is_ok());
            let stdout = stdout_reader.join().ok().and_then(Result::ok);
            let stderr = stderr_reader.join().ok().and_then(Result::ok);
            drop(executable);
            let result = if let Some(error) = forced {
                Err(error)
            } else if status.as_ref().is_err() {
                Err(DemoBackendError::ChildFailed)
            } else if stdout.as_ref().is_some_and(|output| output.1) {
                Err(DemoBackendError::ResponseTooLarge)
            } else if stderr.as_ref().is_some_and(|output| output.1) {
                Err(DemoBackendError::StatusTooLarge)
            } else if !status.is_ok_and(|status| status.success()) || !wrote {
                Err(DemoBackendError::ChildFailed)
            } else {
                match (stdout, stderr) {
                    (Some((response, false)), Some((status, false)))
                        if !response.is_empty() && status == DEMO_BACKEND_COMPLETION_STATUS =>
                    {
                        Ok(response)
                    }
                    _ => Err(DemoBackendError::ChildFailed),
                }
            };
            if let Some(result_send) = result_send.take() {
                let _ = result_send.send(result);
            }
        })
        .map_err(|_| DemoBackendError::SpawnFailed)?;
    Ok(BackendWorker {
        cancel: cancel_send,
        result: result_receive,
        join: Some(join),
    })
}

fn read_bounded(mut reader: impl Read, limit: usize) -> Result<(Vec<u8>, bool), std::io::Error> {
    let mut output = Vec::with_capacity(limit.min(1024));
    let mut oversized = false;
    let mut buffer = [0_u8; 1024];
    loop {
        let read = reader.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        let remaining = limit.saturating_sub(output.len());
        output.extend_from_slice(&buffer[..read.min(remaining)]);
        oversized |= read > remaining;
    }
    Ok((output, oversized))
}

#[allow(dead_code)]
pub(crate) async fn relay_demo_backend(
    application: &mut nbsr_transport::ApplicationStream,
    map: &DemoBackendMap,
    admitted: &nbsr_transport::ActiveChannel,
) -> Result<Vec<u8>, DemoBackendError> {
    relay_demo_backend_with_timeout(application, map, admitted, DEMO_BACKEND_OPERATION_TIMEOUT)
        .await
}

#[allow(dead_code)]
pub(crate) async fn relay_demo_backend_with_timeout(
    application: &mut nbsr_transport::ApplicationStream,
    map: &DemoBackendMap,
    admitted: &nbsr_transport::ActiveChannel,
    timeout: Duration,
) -> Result<Vec<u8>, DemoBackendError> {
    if timeout.is_zero() {
        return Err(DemoBackendError::TimedOut);
    }
    let deadline = std::time::Instant::now() + timeout;
    relay_demo_backend_until(application, map, admitted, deadline).await
}

async fn relay_demo_backend_until(
    application: &mut nbsr_transport::ApplicationStream,
    map: &DemoBackendMap,
    admitted: &nbsr_transport::ActiveChannel,
    deadline: std::time::Instant,
) -> Result<Vec<u8>, DemoBackendError> {
    ensure_demo_backend_binding(map, admitted)?;
    let tokio_deadline = tokio::time::Instant::from_std(deadline);
    let request = tokio::time::timeout_at(tokio_deadline, application.receive_payload())
        .await
        .map_err(|_| DemoBackendError::TimedOut)?
        .map_err(|_| DemoBackendError::StreamFailed)?;
    let response = run_demo_backend_until(map, admitted, &request, deadline, None).await?;
    tokio::time::timeout_at(tokio_deadline, application.send_payload(&response))
        .await
        .map_err(|_| DemoBackendError::TimedOut)?
        .map_err(|_| DemoBackendError::StreamFailed)?;
    tokio::time::timeout_at(tokio_deadline, application.wait_for_send_ack())
        .await
        .map_err(|_| DemoBackendError::TimedOut)?
        .map_err(|_| DemoBackendError::StreamFailed)?;
    application.release_buffered_payloads();
    Ok(response)
}

#[allow(dead_code)]
pub(crate) async fn run_demo_backend_connector(
    connection: &nbsr_transport::AuthenticatedConnection,
    control: &mut nbsr_transport::ControlStream,
    session: ControlSession,
    route: &nbsr_transport::CoreV02Envelope,
    attestations: &LocalFederationAdmissionAttestations,
    map: &DemoBackendMap,
) -> Result<Vec<u8>, DemoBackendError> {
    let deadline = std::time::Instant::now() + DEMO_BACKEND_OPERATION_TIMEOUT;
    run_demo_backend_connector_until(
        connection,
        control,
        session,
        route,
        attestations,
        DemoBackendRouteConfig {
            backend: map,
            admission: None,
        },
        deadline,
    )
    .await
}

async fn run_demo_backend_connector_until(
    connection: &nbsr_transport::AuthenticatedConnection,
    control: &mut nbsr_transport::ControlStream,
    mut session: ControlSession,
    route: &nbsr_transport::CoreV02Envelope,
    attestations: &LocalFederationAdmissionAttestations,
    config: DemoBackendRouteConfig<'_>,
    deadline: std::time::Instant,
) -> Result<Vec<u8>, DemoBackendError> {
    worker_checkpoint(Some(deadline), None)?;
    if let Some(admission) = config.admission {
        ensure_runtime_route_grant_binding(admission, route)?;
    }
    let admitted = accept_configured_route(&mut session, route, attestations, config.admission)
        .map_err(|_| DemoBackendError::StreamFailed)?;
    if let Some(admission) = config.admission {
        ensure_runtime_admission_binding(admission, &admitted)?;
    }
    ensure_demo_backend_binding(config.backend, &admitted)?;
    let accepted = route_accept_for_admitted(&admitted);
    session
        .select_stream_credit_profile(
            admitted.channel_id,
            true,
            Some(nbsr_transport::STREAM_CREDIT_PROFILE_ID),
            false,
        )
        .map_err(|_| DemoBackendError::StreamFailed)?;
    session
        .confirm_route_accept(&accepted)
        .map_err(|_| DemoBackendError::StreamFailed)?;
    tokio::time::timeout_at(
        tokio::time::Instant::from_std(deadline),
        control.send_envelope(&accepted),
    )
    .await
    .map_err(|_| DemoBackendError::TimedOut)?
    .map_err(|_| DemoBackendError::StreamFailed)?;
    connection
        .bind_channel(&mut session, admitted.channel_id)
        .map_err(|_| DemoBackendError::StreamFailed)?;
    let session = nbsr_transport::SharedControlSession::new(session);
    let mut application = tokio::time::timeout_at(
        tokio::time::Instant::from_std(deadline),
        connection.accept_credited_session_stream(&session, admitted.channel_id),
    )
    .await
    .map_err(|_| DemoBackendError::TimedOut)?
    .map_err(|_| DemoBackendError::StreamFailed)?;
    let stream_id = application.id();
    let response =
        relay_demo_backend_until(&mut application, config.backend, &admitted, deadline).await;
    let released = session
        .update(|session| session.release_stream(admitted.channel_id, stream_id))
        .map_err(|_| DemoBackendError::StreamFailed);
    released?;
    response
}

#[allow(dead_code)]
pub(crate) async fn run_demo_backend_server_operation_with_timeout(
    listener: &nbsr_transport::TransportListener,
    map: &DemoBackendMap,
    timeout: Duration,
) -> Result<Vec<u8>, DemoBackendError> {
    run_demo_backend_server_operation_with_admission(listener, map, None, timeout).await
}

pub(crate) async fn run_demo_backend_server_operation_with_admission(
    listener: &nbsr_transport::TransportListener,
    map: &DemoBackendMap,
    runtime_admission: Option<&RuntimeAdmissionConfig>,
    timeout: Duration,
) -> Result<Vec<u8>, DemoBackendError> {
    if timeout.is_zero() {
        return Err(DemoBackendError::TimedOut);
    }
    let deadline = std::time::Instant::now() + timeout;
    let tokio_deadline = tokio::time::Instant::from_std(deadline);
    let connection = tokio::time::timeout_at(tokio_deadline, listener.accept_one())
        .await
        .map_err(|_| DemoBackendError::TimedOut)?
        .map_err(|_| DemoBackendError::StreamFailed)?;
    let result = async {
        let mut control =
            tokio::time::timeout_at(tokio_deadline, connection.accept_control_stream())
                .await
                .map_err(|_| DemoBackendError::TimedOut)?
                .map_err(|_| DemoBackendError::StreamFailed)?;
        let admission_policy = runtime_admission
            .map(|config| config.policy.clone())
            .unwrap_or_else(policy);
        let edge = edge_hello_for_policy(&admission_policy);
        let admission = DestinationAdmission::new_federated(admission_policy, authorities())
            .map_err(|_| DemoBackendError::StreamFailed)?;
        let trusted_issuers = runtime_admission
            .map(|config| vec![config.trusted_issuer.clone()])
            .unwrap_or_else(|| vec![issuer()]);
        let trust_profile =
            TrustProfileId::new("federation-dev-v1").map_err(|_| DemoBackendError::StreamFailed)?;
        let mut session =
            ControlSession::new(&connection, admission, trusted_issuers, trust_profile);
        let client = tokio::time::timeout_at(
            tokio_deadline,
            control.receive_envelope(CoreV02Limits::default()),
        )
        .await
        .map_err(|_| DemoBackendError::TimedOut)?
        .map_err(|_| DemoBackendError::StreamFailed)?;
        session
            .accept_client_hello(&client)
            .map_err(|_| DemoBackendError::StreamFailed)?;
        worker_checkpoint(Some(deadline), None)?;
        session
            .confirm_edge_hello(&edge)
            .map_err(|_| DemoBackendError::StreamFailed)?;
        tokio::time::timeout_at(tokio_deadline, control.send_envelope(&edge))
            .await
            .map_err(|_| DemoBackendError::TimedOut)?
            .map_err(|_| DemoBackendError::StreamFailed)?;
        let route = tokio::time::timeout_at(
            tokio_deadline,
            control.receive_envelope(CoreV02Limits::default()),
        )
        .await
        .map_err(|_| DemoBackendError::TimedOut)?
        .map_err(|_| DemoBackendError::StreamFailed)?;
        worker_checkpoint(Some(deadline), None)?;
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
        let attestations = LocalFederationAdmissionAttestations {
            source: fs::read(root.join("vectors/wp8-local-admission/source.cose"))
                .map_err(|_| DemoBackendError::StreamFailed)?,
            destination: fs::read(root.join("vectors/wp8-local-admission/destination.cose"))
                .map_err(|_| DemoBackendError::StreamFailed)?,
        };
        worker_checkpoint(Some(deadline), None)?;
        run_demo_backend_connector_until(
            &connection,
            &mut control,
            session,
            &route,
            &attestations,
            DemoBackendRouteConfig {
                backend: map,
                admission: runtime_admission,
            },
            deadline,
        )
        .await
    }
    .await;
    match result {
        Ok(response) => {
            tokio::time::timeout_at(tokio_deadline, connection.close())
                .await
                .map_err(|_| DemoBackendError::TimedOut)?
                .map_err(|_| DemoBackendError::StreamFailed)?;
            Ok(response)
        }
        Err(error) => {
            drop(connection);
            Err(error)
        }
    }
}

fn identity(value: &str) -> EdgeIdentity {
    EdgeIdentity::from_dns_name(value).unwrap()
}

fn tls_material(authority: &Path) -> TlsMaterial {
    let ca = CertificateDer::from(fs::read(authority.join("ca.der")).unwrap());
    let certificate = CertificateDer::from(fs::read(authority.join("destination.der")).unwrap());
    let key = PrivateKeyDer::Pkcs8(PrivatePkcs8KeyDer::from(
        fs::read(authority.join("destination-key.der")).unwrap(),
    ));
    let mut roots = RootCertStore::empty();
    roots.add(ca).unwrap();
    TlsMaterial::new(vec![certificate], key, roots).unwrap()
}

pub(crate) fn policy() -> AdmissionPolicy {
    AdmissionPolicy {
        source_operator_id: "nbsr12df4x56n2df4x56n2df4x56n2df4x56n2df4x56n2df4x56n2dfsk5743r"
            .into(),
        source_edge_id: "source.edge".into(),
        destination_operator_id: "nbsr1g3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zyg3zqel9ufg"
            .into(),
        destination_edge_id: "destination.edge".into(),
        authorized_services: BTreeMap::from([(
            "service.example".into(),
            AuthorizedServicePolicy {
                accepted_record_sequence: 42,
                policy_hash: [
                    0x09, 0xfe, 0x3b, 0x1c, 0x85, 0x49, 0x99, 0x49, 0xda, 0x22, 0x2d, 0xd4, 0xe2,
                    0xa4, 0x60, 0xf5, 0x94, 0xae, 0xe8, 0x25, 0xf4, 0x44, 0xa7, 0x22, 0x58, 0xd2,
                    0xf1, 0x79, 0x7b, 0xf1, 0x14, 0x3f,
                ],
            },
        )]),
        now: 1_893_456_000,
        client_session_public_key: [
            0x3d, 0x40, 0x17, 0xc3, 0xe8, 0x43, 0x89, 0x5a, 0x92, 0xb7, 0x0a, 0xa7, 0x4d, 0x1b,
            0x7e, 0xbc, 0x9c, 0x98, 0x2c, 0xcf, 0x2e, 0xc4, 0x96, 0x8c, 0xc0, 0xcd, 0x55, 0xf1,
            0x2a, 0xf4, 0x66, 0x0c,
        ],
        edge_nonce: (0x80..0xa0).collect::<Vec<_>>().try_into().unwrap(),
    }
}

fn lifecycle_policy(root: &Path, services: u64) -> AdmissionPolicy {
    let authorized_services = (0..services)
        .map(|index| {
            let name = fs::read_to_string(root.join(format!("{index:02}/name.txt")))
                .unwrap()
                .trim()
                .to_owned();
            (
                name,
                AuthorizedServicePolicy {
                    accepted_record_sequence: 42,
                    policy_hash: [
                        0x09, 0xfe, 0x3b, 0x1c, 0x85, 0x49, 0x99, 0x49, 0xda, 0x22, 0x2d, 0xd4,
                        0xe2, 0xa4, 0x60, 0xf5, 0x94, 0xae, 0xe8, 0x25, 0xf4, 0x44, 0xa7, 0x22,
                        0x58, 0xd2, 0xf1, 0x79, 0x7b, 0xf1, 0x14, 0x3f,
                    ],
                },
            )
        })
        .collect();
    AdmissionPolicy {
        authorized_services,
        ..policy()
    }
}

pub(crate) fn authorities() -> LocalFederationAdmissionAuthorities {
    let mut destination_key = [
        0xd7, 0x59, 0x79, 0x3b, 0xbc, 0x13, 0xa2, 0x81, 0x9a, 0x82, 0x7c, 0x76, 0xad, 0xb6, 0xfb,
        0xa8, 0xa4, 0x9a, 0xee, 0x00, 0x7f, 0x49, 0xf2, 0xd0, 0x99, 0x2d, 0x99, 0xb8, 0x25, 0xad,
        0x2c, 0x48,
    ];
    if env::var_os("NBSR_TASK10B_REVOKE_DESTINATION_AUTHORITY").is_some() {
        destination_key[0] ^= 1;
    }
    LocalFederationAdmissionAuthorities::new(
        b"local-source".to_vec(),
        [
            0xf8, 0x0c, 0xcc, 0xdc, 0xe4, 0xae, 0x1c, 0x07, 0xae, 0x20, 0x8a, 0x2a, 0xdf, 0x99,
            0xa3, 0x10, 0xae, 0x42, 0x07, 0xe0, 0x30, 0x6f, 0xa0, 0x23, 0x61, 0x10, 0xb0, 0x68,
            0x27, 0xbb, 0xb8, 0xd0,
        ],
        b"local-destination".to_vec(),
        destination_key,
    )
    .unwrap()
}

pub(crate) fn issuer() -> RouteGrantIssuer {
    RouteGrantIssuer {
        kid: b"nbsr-test-route-grant-key".to_vec(),
        public_key: [
            0xd7, 0x5a, 0x98, 0x01, 0x82, 0xb1, 0x0a, 0xb7, 0xd5, 0x4b, 0xfe, 0xd3, 0xc9, 0x64,
            0x07, 0x3a, 0x0e, 0xe1, 0x72, 0xf3, 0xda, 0xa6, 0x23, 0x25, 0xaf, 0x02, 0x1a, 0x68,
            0xf7, 0x07, 0x51, 0x1a,
        ],
    }
}

fn envelope(
    message: u64,
    request: [u8; 16],
    sequence: u64,
    body: Vec<u8>,
) -> nbsr_transport::CoreV02Envelope {
    let mut wire = Vec::new();
    map(&mut wire, 6);
    field_uint(&mut wire, 0, 2);
    field_uint(&mut wire, 1, message);
    field_bytes(&mut wire, 2, &request);
    field_bytes(&mut wire, 3, &(0x10..0x20).collect::<Vec<_>>());
    field_uint(&mut wire, 4, sequence);
    uint(&mut wire, 5);
    wire.extend(body);
    decode_control_envelope(&wire, CoreV02Limits::default()).unwrap()
}

pub(crate) fn edge_hello() -> nbsr_transport::CoreV02Envelope {
    edge_hello_for_policy(&policy())
}

pub(crate) fn edge_hello_for_policy(
    admission: &AdmissionPolicy,
) -> nbsr_transport::CoreV02Envelope {
    let mut body = Vec::new();
    map(&mut body, 7);
    field_uint(&mut body, 0, 1);
    field_text(&mut body, 1, &admission.source_edge_id);
    field_text(&mut body, 2, &admission.destination_edge_id);
    field_bytes(&mut body, 3, &(0x60..0x80).collect::<Vec<_>>());
    field_bytes(&mut body, 4, &admission.edge_nonce);
    field_bytes(
        &mut body,
        5,
        &<[u8; 32]>::from(Sha256::digest(admission.client_session_public_key)),
    );
    field_uint(&mut body, 6, admission.now);
    envelope(
        2,
        (0x00..0x10).collect::<Vec<_>>().try_into().unwrap(),
        1,
        body,
    )
}

pub(crate) fn route_accept() -> nbsr_transport::CoreV02Envelope {
    route_accept_for_admitted(&nbsr_transport::ActiveChannel {
        channel_id: (0x40..0x50).collect::<Vec<_>>().try_into().unwrap(),
        route_id: (0x20..0x30).collect::<Vec<_>>().try_into().unwrap(),
        service_id: "service.example".into(),
        route_grant_digest: [
            0xf6, 0x09, 0x00, 0x54, 0xa8, 0x32, 0xc5, 0x59, 0xb2, 0x8b, 0xba, 0x38, 0x6f, 0x78,
            0x61, 0x65, 0x57, 0xce, 0x13, 0xaf, 0x39, 0xe1, 0xa9, 0x5d, 0x3d, 0xff, 0x9e, 0x1f,
            0x7b, 0xa9, 0x68, 0x60,
        ],
        transport: "tcp".into(),
        port: 8443,
    })
}

pub(crate) fn route_accept_for_admitted(
    admitted: &nbsr_transport::ActiveChannel,
) -> nbsr_transport::CoreV02Envelope {
    let mut body = Vec::new();
    map(&mut body, 5);
    field_uint(&mut body, 0, 1);
    field_bytes(&mut body, 1, &admitted.channel_id);
    field_bytes(&mut body, 2, &admitted.route_id);
    field_bytes(&mut body, 3, &admitted.route_grant_digest);
    field_uint(&mut body, 4, 1_893_456_000);
    envelope(
        4,
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16],
        2,
        body,
    )
}

fn fixed<const N: usize>(path: &Path) -> [u8; N] {
    fs::read(path).unwrap().try_into().unwrap()
}

fn lifecycle_route_accept(
    root: &Path,
    index: u64,
    sequence: u64,
) -> nbsr_transport::CoreV02Envelope {
    let directory = root.join(format!("{index:02}"));
    let mut body = Vec::new();
    map(&mut body, 5);
    field_uint(&mut body, 0, 1);
    field_bytes(
        &mut body,
        1,
        &fixed::<16>(&directory.join("channel-id.bin")),
    );
    field_bytes(&mut body, 2, &fixed::<16>(&directory.join("route-id.bin")));
    field_bytes(
        &mut body,
        3,
        &fixed::<32>(&directory.join("grant-digest.bin")),
    );
    field_uint(&mut body, 4, 1_893_456_000);
    envelope(
        4,
        fixed::<16>(&directory.join("request-id.bin")),
        sequence,
        body,
    )
}

fn lifecycle_stream_accept(
    root: &Path,
    service: u64,
    stream_ordinal: u64,
    sequence: u64,
) -> nbsr_transport::CoreV02Envelope {
    let directory = root.join(format!("{service:02}"));
    let stream_id = 4 + stream_ordinal * 4;
    let mut body = Vec::new();
    map(&mut body, 5);
    field_uint(&mut body, 0, 1);
    field_uint(&mut body, 1, stream_id);
    field_bytes(
        &mut body,
        2,
        &fixed::<16>(&directory.join("channel-id.bin")),
    );
    field_bytes(&mut body, 3, &fixed::<16>(&directory.join("route-id.bin")));
    field_uint(&mut body, 4, 1_893_456_000);
    envelope(7, stream_request(stream_ordinal), sequence, body)
}

async fn run_lifecycle(
    listener: &TransportListener,
    root: &Path,
    connections: u64,
    services: u64,
    streams_per_service: u64,
    concurrent: bool,
) -> Vec<(u128, u128)> {
    let mut measurements =
        Vec::with_capacity((connections * services * streams_per_service) as usize);
    let concurrent_sessions = env::var_os("NBSR_PERF_CONCURRENT_SESSIONS").is_some();
    let mut accepted_connections = VecDeque::new();
    if concurrent_sessions {
        for _ in 0..connections {
            accepted_connections.push_back(listener.accept_one().await.unwrap());
        }
    }
    for connection_ordinal in 0..connections {
        let connection = if concurrent_sessions {
            accepted_connections.pop_front().unwrap()
        } else {
            listener.accept_one().await.unwrap()
        };
        let mut control = connection.accept_control_stream().await.unwrap();
        let mut session = ControlSession::new(
            &connection,
            DestinationAdmission::new_federated(lifecycle_policy(root, services), authorities())
                .unwrap(),
            vec![issuer()],
            TrustProfileId::new("federation-dev-v1").unwrap(),
        );
        let client = control
            .receive_envelope(CoreV02Limits::default())
            .await
            .unwrap();
        session.accept_client_hello(&client).unwrap();
        let edge = edge_hello();
        session.confirm_edge_hello(&edge).unwrap();
        control.send_envelope(&edge).await.unwrap();
        let mut concurrent_tasks = tokio::task::JoinSet::new();
        let mut concurrent_admissions = vec![0_u128; services as usize];
        let mut concurrent_channels = Vec::with_capacity(services as usize);
        for index in 0..services {
            let directory = root.join(format!("{index:02}"));
            let route = control
                .receive_envelope(CoreV02Limits::default())
                .await
                .unwrap();
            let attestations = LocalFederationAdmissionAttestations {
                source: fs::read(directory.join("source.cose")).unwrap(),
                destination: fs::read(directory.join("destination.cose")).unwrap(),
            };
            let destination_admission = std::time::Instant::now();
            session
                .accept_federated_route_open(&route, &attestations)
                .unwrap();
            let destination_admission_ns = destination_admission.elapsed().as_nanos();
            concurrent_admissions[index as usize] = destination_admission_ns;
            let route_sequence = 2 + index * (1 + streams_per_service);
            let accepted = lifecycle_route_accept(root, index, route_sequence);
            session.confirm_route_accept(&accepted).unwrap();
            control.send_envelope(&accepted).await.unwrap();
            let channel = fixed::<16>(&directory.join("channel-id.bin"));
            connection.bind_channel(&mut session, channel).unwrap();
            if concurrent {
                for local_stream in 0..streams_per_service {
                    let stream_ordinal = index * streams_per_service + local_stream;
                    let stream = control
                        .receive_envelope(CoreV02Limits::default())
                        .await
                        .unwrap();
                    session.authorize_stream_open(channel, &stream).unwrap();
                    let stream_accepted = lifecycle_stream_accept(
                        root,
                        index,
                        stream_ordinal,
                        route_sequence + 1 + local_stream,
                    );
                    session
                        .confirm_stream_accept(channel, &stream_accepted)
                        .unwrap();
                    control.send_envelope(&stream_accepted).await.unwrap();
                }
                concurrent_channels.push(channel);
                continue;
            }
            for local_stream in 0..streams_per_service {
                let stream_ordinal = index * streams_per_service + local_stream;
                let stream = control
                    .receive_envelope(CoreV02Limits::default())
                    .await
                    .unwrap();
                session.authorize_stream_open(channel, &stream).unwrap();
                let stream_accepted = lifecycle_stream_accept(
                    root,
                    index,
                    stream_ordinal,
                    route_sequence + 1 + local_stream,
                );
                session
                    .confirm_stream_accept(channel, &stream_accepted)
                    .unwrap();
                control.send_envelope(&stream_accepted).await.unwrap();
                let application_processing = std::time::Instant::now();
                let application = connection
                    .accept_session_stream(&mut session, channel)
                    .await;
                if let Err(error) = &application {
                    eprintln!("nbsr-perf lifecycle application admission failed: {error:?}");
                }
                application.unwrap().echo_once().await.unwrap();
                measurements.push((
                    if local_stream == 0 {
                        destination_admission_ns
                    } else {
                        0
                    },
                    application_processing.elapsed().as_nanos(),
                ));
                session
                    .release_stream(channel, 4 + stream_ordinal * 4)
                    .unwrap();
                while session.pop_audit_event().is_some() {}
            }
        }
        if concurrent {
            for stream_ordinal in 0..(services * streams_per_service) {
                let service = stream_ordinal / streams_per_service;
                let local_stream = stream_ordinal % streams_per_service;
                let channel = concurrent_channels[service as usize];
                let mut application = connection
                    .accept_session_stream(&mut session, channel)
                    .await
                    .unwrap();
                concurrent_tasks.spawn(async move {
                    let started = std::time::Instant::now();
                    application.echo_once().await.unwrap();
                    (service, local_stream, channel, started.elapsed().as_nanos())
                });
            }
            let mut completed = vec![0_u128; (services * streams_per_service) as usize];
            while let Some(joined) = concurrent_tasks.join_next().await {
                let (service, local_stream, channel, application_ns) = joined.unwrap();
                let stream_ordinal = service * streams_per_service + local_stream;
                completed[stream_ordinal as usize] = application_ns;
                session
                    .release_stream(channel, 4 + stream_ordinal * 4)
                    .unwrap();
            }
            for (stream_ordinal, application_ns) in completed.into_iter().enumerate() {
                let service = stream_ordinal / streams_per_service as usize;
                let local_stream = stream_ordinal % streams_per_service as usize;
                measurements.push((
                    if local_stream == 0 {
                        concurrent_admissions[service]
                    } else {
                        0
                    },
                    application_ns,
                ));
            }
            while session.pop_audit_event().is_some() {}
        }
        tokio::time::timeout(Duration::from_secs(10), async {
            while fs::read_dir(root)
                .unwrap()
                .filter_map(Result::ok)
                .filter(|entry| {
                    let name = entry.file_name();
                    let name = name.to_string_lossy();
                    name.starts_with("connection-") && name.ends_with(".ack")
                })
                .count()
                < connection_ordinal as usize + 1
            {
                tokio::time::sleep(Duration::from_millis(1)).await;
            }
        })
        .await
        .expect("lifecycle client completion acknowledgement");
        if !concurrent_sessions {
            connection.close().await.unwrap();
        }
    }
    measurements
}

fn stream_accept(index: u64) -> nbsr_transport::CoreV02Envelope {
    let mut body = Vec::new();
    map(&mut body, 5);
    field_uint(&mut body, 0, 1);
    field_uint(&mut body, 1, 4 + 4 * index);
    field_bytes(&mut body, 2, &(0x40..0x50).collect::<Vec<_>>());
    field_bytes(&mut body, 3, &(0x20..0x30).collect::<Vec<_>>());
    field_uint(&mut body, 4, 1_893_456_000);
    envelope(7, stream_request(index), 3 + index, body)
}

fn stream_request(index: u64) -> [u8; 16] {
    let mut request: [u8; 16] = (0_u8..16).collect::<Vec<_>>().try_into().unwrap();
    request[15] = 0x11;
    let suffix = u64::from_be_bytes(request[8..16].try_into().unwrap()) + index;
    request[8..16].copy_from_slice(&suffix.to_be_bytes());
    request
}

#[cfg(feature = "benchmark-harness")]
struct P2dServerResult<'a> {
    path: &'a Path,
    mode: &'a str,
    operations: u64,
    concurrency: usize,
    payload_correct: bool,
    remaining_credits: Option<u8>,
    refill_count: u64,
    active_epochs: u8,
    active_epochs_high_water: u8,
    replay_entries: usize,
    replay_limit: usize,
    minimum_remaining_credits: Option<u8>,
    buffer_exhaustions: u64,
}

#[cfg(feature = "benchmark-harness")]
struct P2dServerRun<'a> {
    channel: [u8; 16],
    operations: u64,
    concurrency: usize,
    smoke_exhaustion: bool,
    result: &'a Path,
    completion_ack: &'a Path,
}

#[cfg(feature = "benchmark-harness")]
fn p2d_write_server_result(result: P2dServerResult<'_>) {
    let P2dServerResult {
        path,
        mode,
        operations,
        concurrency,
        payload_correct,
        remaining_credits,
        refill_count,
        active_epochs,
        active_epochs_high_water,
        replay_entries,
        replay_limit,
        minimum_remaining_credits,
        buffer_exhaustions,
    } = result;
    let remaining = remaining_credits.map_or_else(|| "null".into(), |value| value.to_string());
    let minimum =
        minimum_remaining_credits.map_or_else(|| "null".into(), |value| value.to_string());
    fs::write(
        path,
        format!(
            "{{\"schema\":\"nbsr-p2d-rust-server-v1\",\"mode\":\"{mode}\",\"concurrency\":{concurrency},\"payload_bytes\":1024,\"payload_correct\":{payload_correct},\"completed_operations\":{operations},\"errors\":0,\"remaining_credits\":{remaining},\"refill_count\":{refill_count},\"windows_crossed\":{refill_count},\"active_epochs\":{active_epochs},\"active_epochs_high_water\":{active_epochs_high_water},\"replay_entries\":{replay_entries},\"replay_limit\":{replay_limit},\"minimum_remaining_credits\":{minimum},\"buffer_exhaustions\":{buffer_exhaustions}}}\n"
        ),
    )
    .unwrap();
}

#[cfg(feature = "benchmark-harness")]
fn p2d_write_server_rejection(path: &Path, mode: &str, reason: &str) {
    fs::write(
        path,
        format!(
            "{{\"schema\":\"nbsr-p2d-rust-server-v1\",\"mode\":\"{mode}\",\"status\":\"REJECTED\",\"reason\":\"{reason}\",\"payload_exposed\":false}}\n"
        ),
    )
    .unwrap();
}

#[cfg(feature = "benchmark-harness")]
async fn wait_for_p2d_completion_ack(path: &Path) {
    tokio::time::timeout(Duration::from_secs(10), async {
        while !path.exists() {
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .expect("P2D client completion acknowledgement");
}

#[cfg(feature = "benchmark-harness")]
async fn run_p2d_before(
    connection: nbsr_transport::AuthenticatedConnection,
    mut control: nbsr_transport::ControlStream,
    mut session: ControlSession,
    run: P2dServerRun<'_>,
) {
    let P2dServerRun {
        channel,
        operations,
        concurrency,
        smoke_exhaustion: _,
        result,
        completion_ack,
    } = run;
    let mut payload_correct = true;
    let mut next = 0_u64;
    while next < operations {
        let batch = usize::min(concurrency, (operations - next) as usize);
        for offset in 0..batch {
            let index = next + offset as u64;
            let request = control
                .receive_envelope(CoreV02Limits::default())
                .await
                .unwrap();
            session.authorize_stream_open(channel, &request).unwrap();
            let accepted = stream_accept(index);
            session.confirm_stream_accept(channel, &accepted).unwrap();
            control.send_envelope(&accepted).await.unwrap();
        }
        let mut tasks = tokio::task::JoinSet::new();
        for _ in 0..batch {
            let mut application = connection
                .accept_session_stream(&mut session, channel)
                .await
                .unwrap();
            tasks.spawn(async move {
                let stream_id = application.id();
                let payload = application.echo_once().await.unwrap();
                (
                    stream_id,
                    payload.len() == 1024 && payload.iter().all(|byte| *byte == 0x5a),
                )
            });
        }
        while let Some(joined) = tasks.join_next().await {
            let (stream_id, correct) = joined.unwrap();
            payload_correct &= correct;
            session.release_stream(channel, stream_id).unwrap();
        }
        while session.pop_audit_event().is_some() {}
        next += batch as u64;
    }
    let diagnostics = nbsr_transport::diagnostics::global().snapshot();
    p2d_write_server_result(P2dServerResult {
        path: result,
        mode: "before",
        operations,
        concurrency,
        payload_correct,
        remaining_credits: None,
        refill_count: 0,
        active_epochs: 0,
        active_epochs_high_water: 0,
        replay_entries: diagnostics.replay_state.current_entries as usize,
        replay_limit: 10_000,
        minimum_remaining_credits: None,
        buffer_exhaustions: 0,
    });
    wait_for_p2d_completion_ack(completion_ack).await;
    drop(session);
    connection.close().await.unwrap();
}

#[cfg(feature = "benchmark-harness")]
async fn run_p2d_after(
    connection: nbsr_transport::AuthenticatedConnection,
    mut control: nbsr_transport::ControlStream,
    session: ControlSession,
    run: P2dServerRun<'_>,
) {
    let P2dServerRun {
        channel,
        operations,
        concurrency,
        smoke_exhaustion,
        result,
        completion_ack,
    } = run;
    let connection = Arc::new(connection);
    let session = nbsr_transport::SharedControlSession::new(session);
    let mut payload_correct = true;
    let mut refill_count = 0_u64;
    let mut active_epochs_high_water = 1_u8;
    let mut minimum_remaining = 64_u8;
    let mut buffer_exhaustions = 0_u64;
    let mut next = 0_u64;
    while next < operations {
        let batch = usize::min(concurrency, (operations - next) as usize);
        let mut tasks = tokio::task::JoinSet::new();
        for _ in 0..batch {
            let task_connection = Arc::clone(&connection);
            let task_session = session.clone();
            tasks.spawn(async move {
                let mut application = task_connection
                    .accept_credited_session_stream(&task_session, channel)
                    .await?;
                let stream_id = application.id();
                let payload = application.echo_once().await?;
                Ok::<_, nbsr_transport::TransportError>((
                    stream_id,
                    payload.len() == 1024 && payload.iter().all(|byte| *byte == 0x5a),
                ))
            });
        }
        while let Some(joined) = tasks.join_next().await {
            let outcome = joined.expect("P2D task must not panic on peer input");
            let (stream_id, correct) = match outcome {
                Ok(accepted) => accepted,
                Err(nbsr_transport::TransportError::ApplicationStreamRejected) => {
                    tasks.abort_all();
                    while tasks.join_next().await.is_some() {}
                    p2d_write_server_rejection(result, "after", "APPLICATION_STREAM_REJECTED");
                    wait_for_p2d_completion_ack(completion_ack).await;
                    return;
                }
                Err(_) => {
                    tasks.abort_all();
                    while tasks.join_next().await.is_some() {}
                    p2d_write_server_rejection(result, "after", "APPLICATION_STREAM_FAILED");
                    wait_for_p2d_completion_ack(completion_ack).await;
                    return;
                }
            };
            payload_correct &= correct;
            session
                .update(|session| session.release_stream(channel, stream_id))
                .unwrap();
        }
        session.update(|session| while session.pop_audit_event().is_some() {});
        let snapshot = session
            .inspect(|session| session.stream_credit_snapshot(channel))
            .unwrap();
        minimum_remaining = minimum_remaining.min(snapshot.remaining_credits);
        if snapshot.remaining_credits <= nbsr_transport::STREAM_CREDIT_LOW_WATERMARK {
            if smoke_exhaustion && snapshot.remaining_credits == 0 {
                assert_eq!(
                    connection
                        .accept_credited_session_stream(&session, channel)
                        .await
                        .err(),
                    Some(nbsr_transport::TransportError::ApplicationStreamRejected)
                );
                buffer_exhaustions += 1;
            }
            let request = control
                .receive_stream_credit_refill_request()
                .await
                .unwrap();
            assert_eq!(request.channel_id, channel);
            session
                .update(|session| {
                    session.grant_stream_credit_refill(request.channel_id, request.epoch)
                })
                .unwrap();
            control
                .send_stream_credit_refill_grant(StreamCreditRefill {
                    channel_id: request.channel_id,
                    epoch: request.epoch,
                })
                .await
                .unwrap();
            let activated = session
                .inspect(|session| session.stream_credit_snapshot(channel))
                .unwrap();
            active_epochs_high_water = active_epochs_high_water.max(activated.active_epochs);
            session
                .update(|session| session.retire_stream_credit_epoch(channel, request.epoch - 1))
                .unwrap();
            refill_count += 1;
        }
        next += batch as u64;
    }
    let final_state = session
        .inspect(|session| session.stream_credit_snapshot(channel))
        .unwrap();
    p2d_write_server_result(P2dServerResult {
        path: result,
        mode: "after",
        operations,
        concurrency,
        payload_correct,
        remaining_credits: Some(final_state.remaining_credits),
        refill_count,
        active_epochs: final_state.active_epochs,
        active_epochs_high_water,
        replay_entries: final_state.replay_entries,
        replay_limit: final_state.replay_limit,
        minimum_remaining_credits: Some(minimum_remaining),
        buffer_exhaustions,
    });
    wait_for_p2d_completion_ack(completion_ack).await;
    drop(session);
    Arc::try_unwrap(connection)
        .ok()
        .expect("P2D destination tasks are complete")
        .close()
        .await
        .unwrap();
}

#[tokio::main(flavor = "current_thread")]
async fn main() {
    #[cfg(feature = "benchmark-harness")]
    if env::var_os("NBSR_P2B_PROFILE").is_some() {
        nbsr_transport::lifecycle_profile::set_destination_role();
    }
    let ready = cli_path("--ready");
    let result = cli_path("--result");
    let authority = cli_path("--authority-dir");
    let completion_ack = cli_path("--completion-ack");
    let demo_backend_map = optional_cli_path_strict("--demo-backend-map")
        .map(|path| load_demo_backend_map(&path))
        .transpose()
        .expect("valid pinned demo backend map");
    let runtime_admission = optional_cli_path_strict("--runtime-admission")
        .map(|path| load_runtime_admission_config(&path))
        .transpose()
        .expect("valid public runtime admission configuration");
    let demo_start_gate = optional_cli_path_strict("--demo-start-gate");
    let destination_diagnostics = optional_cli_value("--destination-diagnostics-file");
    let diagnostic_drain_seconds = optional_cli_value("--diagnostic-drain-seconds")
        .map_or(0, |value| {
            value.parse::<u64>().expect("valid diagnostic drain")
        });
    let diagnostic_sampler = destination_diagnostics.map(|path| {
        nbsr_transport::diagnostics::enable_global();
        nbsr_transport::diagnostics::DestinationDiagnosticSampler::start(
            Path::new(&path),
            nbsr_transport::diagnostics::global(),
            Duration::from_secs(1),
        )
    });
    let p2d_mode = env::var("NBSR_P2D_MODE").ok();
    if demo_backend_map.is_some()
        && (p2d_mode.is_some()
            || env::var_os("NBSR_PERF_LIFECYCLE_ROOT").is_some()
            || env::var_os("NBSR_P2A_STREAMS").is_some()
            || env::var_os("NBSR_PERF_STREAM_SAMPLES").is_some())
    {
        panic!("demo backend mode cannot be combined with benchmark modes");
    }
    #[cfg(feature = "benchmark-harness")]
    let p2d_operations = env::var("NBSR_P2D_OPERATIONS")
        .ok()
        .map(|value| value.parse::<u64>().unwrap());
    #[cfg(feature = "benchmark-harness")]
    let p2d_concurrency = env::var("NBSR_P2D_CONCURRENCY")
        .ok()
        .map(|value| value.parse::<usize>().unwrap());
    #[cfg(feature = "benchmark-harness")]
    let p2d_smoke_exhaustion = env::var_os("NBSR_P2D_SMOKE_EXHAUSTION").is_some();
    if p2d_mode.is_some() {
        nbsr_transport::diagnostics::enable_global();
    }
    let peer_policy = PeerPolicy::new(
        EdgeRole::Destination,
        EdgeRole::Source,
        identity("source.edge"),
        Duration::from_secs(5),
        Duration::from_secs(10),
    )
    .unwrap();
    let port = env::var("NBSR_TASK10B_CAPTURE_PORT")
        .ok()
        .map(|value| value.parse::<u16>().expect("valid capture port"))
        .unwrap_or(0);
    let listener = TransportListener::bind(
        build_server_config(peer_policy, tls_material(&authority)).unwrap(),
        SocketAddr::from((Ipv4Addr::LOCALHOST, port)),
    )
    .unwrap();
    let endpoint = listener.local_addr().unwrap();
    let path = |name: &str| {
        authority
            .join(name)
            .display()
            .to_string()
            .replace('\\', "/")
    };
    fs::write(&ready,format!("{{\"alpn\":\"nbsr-quic-1\",\"ca_der\":\"{}\",\"client_cert_der\":\"{}\",\"client_key_der\":\"{}\",\"endpoint\":\"{}\",\"quic_version\":\"v1\",\"server_name\":\"destination.edge\",\"tls_version\":\"1.3\"}}",path("ca.der"),path("source.der"),path("source-key.der"),endpoint)).unwrap();
    if let Some(lifecycle_root) = env::var_os("NBSR_PERF_LIFECYCLE_ROOT") {
        let connections = env::var("NBSR_PERF_LIFECYCLE_CONNECTIONS")
            .unwrap()
            .parse::<u64>()
            .unwrap();
        let services = env::var("NBSR_PERF_LIFECYCLE_SERVICES")
            .unwrap()
            .parse::<u64>()
            .unwrap();
        let streams_per_service = env::var("NBSR_PERF_STREAMS_PER_SERVICE")
            .unwrap_or_else(|_| "1".into())
            .parse::<u64>()
            .unwrap();
        let concurrent = env::var_os("NBSR_PERF_CONCURRENT_STREAMS").is_some();
        assert!((1..=32).contains(&services));
        assert!((1..=64).contains(&streams_per_service));
        let measurements = run_lifecycle(
            &listener,
            &PathBuf::from(lifecycle_root),
            connections,
            services,
            streams_per_service,
            concurrent,
        )
        .await;
        let samples = measurements
            .iter()
            .map(|(destination, application)| format!("{{\"destination_admission_ns\":{destination},\"application_processing_ns\":{application}}}"))
            .collect::<Vec<_>>()
            .join(",");
        fs::write(result, format!("{{\"connections\":{connections},\"services_per_connection\":{services},\"streams_per_service\":{streams_per_service},\"samples\":[{samples}],\"status\":\"PASS\"}}")).unwrap();
        listener.close().await.unwrap();
        return;
    }
    if let Some(map) = demo_backend_map.as_ref() {
        if let Some(start_gate) = demo_start_gate.as_ref() {
            while !start_gate.exists() {
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        }
        let response = run_demo_backend_server_operation_with_admission(
            &listener,
            map,
            runtime_admission.as_ref(),
            DEMO_BACKEND_OPERATION_TIMEOUT,
        )
        .await
        .expect("bounded admitted demo backend operation");
        let digest_hex = Sha256::digest(&response)
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect::<String>();
        fs::write(
            &result,
            format!(
                "{{\"backend_requests\":1,\"payload_bytes\":{},\"payload_sha256\":\"{}\",\"status\":\"PASS\"}}",
                response.len(),
                digest_hex
            ),
        )
        .unwrap();
        tokio::time::timeout(Duration::from_secs(10), async {
            while !completion_ack.exists() {
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .expect("demo harness completion acknowledgement");
        listener.close().await.unwrap();
        return;
    }
    let connection = listener.accept_one().await.unwrap();
    let mut control = connection.accept_control_stream().await.unwrap();
    let admission_policy = runtime_admission
        .as_ref()
        .map(|config| config.policy.clone())
        .unwrap_or_else(policy);
    let edge = edge_hello_for_policy(&admission_policy);
    let admission = DestinationAdmission::new_federated(admission_policy, authorities()).unwrap();
    let trusted_issuers = runtime_admission
        .as_ref()
        .map(|config| vec![config.trusted_issuer.clone()])
        .unwrap_or_else(|| vec![issuer()]);
    let trust_profile = TrustProfileId::new("federation-dev-v1").unwrap();
    let mut session = if p2d_mode.is_some() {
        ControlSession::new_with_replay_history_limit(
            &connection,
            admission,
            trusted_issuers,
            trust_profile,
            nbsr_transport::ReplayHistoryLimit::try_from(10_000).unwrap(),
        )
    } else {
        ControlSession::new(&connection, admission, trusted_issuers, trust_profile)
    };
    let client = control
        .receive_envelope(CoreV02Limits::default())
        .await
        .unwrap();
    session.accept_client_hello(&client).unwrap();
    session.confirm_edge_hello(&edge).unwrap();
    control.send_envelope(&edge).await.unwrap();
    let route = control
        .receive_envelope(CoreV02Limits::default())
        .await
        .unwrap();
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let attestations = LocalFederationAdmissionAttestations {
        source: fs::read(root.join("vectors/wp8-local-admission/source.cose")).unwrap(),
        destination: fs::read(root.join("vectors/wp8-local-admission/destination.cose")).unwrap(),
    };
    if runtime_admission
        .as_ref()
        .is_some_and(|config| ensure_runtime_route_grant_binding(config, &route).is_err())
    {
        return;
    }
    let admitted_channel = accept_configured_route(
        &mut session,
        &route,
        &attestations,
        runtime_admission.as_ref(),
    );
    let Ok(admitted_channel) = admitted_channel else {
        return;
    };
    if runtime_admission
        .as_ref()
        .is_some_and(|config| ensure_runtime_admission_binding(config, &admitted_channel).is_err())
    {
        return;
    }
    let channel: [u8; 16] = (0x40..0x50).collect::<Vec<_>>().try_into().unwrap();
    assert_eq!(admitted_channel.channel_id, channel);
    let accepted = route_accept();
    if p2d_mode.as_deref() == Some("after") {
        session
            .select_stream_credit_profile(
                channel,
                true,
                Some(nbsr_transport::STREAM_CREDIT_PROFILE_ID),
                false,
            )
            .unwrap();
    }
    session.confirm_route_accept(&accepted).unwrap();
    control.send_envelope(&accepted).await.unwrap();
    connection.bind_channel(&mut session, channel).unwrap();
    #[cfg(feature = "benchmark-harness")]
    if let Some(mode) = p2d_mode.as_deref() {
        let operations = p2d_operations.expect("NBSR_P2D_OPERATIONS is required");
        let concurrency = p2d_concurrency.expect("NBSR_P2D_CONCURRENCY is required");
        assert!((1..=8_000).contains(&operations));
        assert!(matches!(concurrency, 1 | 2 | 4 | 8 | 16 | 32 | 64));
        match mode {
            "before" => {
                run_p2d_before(
                    connection,
                    control,
                    session,
                    P2dServerRun {
                        channel,
                        operations,
                        concurrency,
                        smoke_exhaustion: false,
                        result: &result,
                        completion_ack: &completion_ack,
                    },
                )
                .await
            }
            "after" => {
                run_p2d_after(
                    connection,
                    control,
                    session,
                    P2dServerRun {
                        channel,
                        operations,
                        concurrency,
                        smoke_exhaustion: p2d_smoke_exhaustion,
                        result: &result,
                        completion_ack: &completion_ack,
                    },
                )
                .await
            }
            _ => panic!("NBSR_P2D_MODE must be before or after"),
        }
        listener.close().await.unwrap();
        return;
    }
    #[cfg(feature = "benchmark-harness")]
    if let Ok(stream_count) = env::var("NBSR_P2A_STREAMS") {
        let stream_count = stream_count.parse::<u64>().unwrap();
        assert!(matches!(stream_count, 1 | 8 | 64));
        let mut tasks = tokio::task::JoinSet::new();
        for index in 0..stream_count {
            let stream = control
                .receive_envelope(CoreV02Limits::default())
                .await
                .unwrap();
            session.authorize_stream_open(channel, &stream).unwrap();
            let accepted = stream_accept(index);
            session.confirm_stream_accept(channel, &accepted).unwrap();
            control.send_envelope(&accepted).await.unwrap();
        }
        for _ in 0..stream_count {
            let mut application = connection
                .accept_session_stream(&mut session, channel)
                .await
                .unwrap();
            tasks.spawn(async move {
                let mut completed = 0_u64;
                while let Ok(wire) = application.benchmark_read_frame().await {
                    if application.benchmark_write_frame(&wire).await.is_err() {
                        break;
                    }
                    completed += 1;
                }
                completed
            });
        }
        let mut echoed = 0_u64;
        while let Some(joined) = tasks.join_next().await {
            echoed += joined.unwrap();
        }
        fs::write(
            result,
            format!(
                "{{\"status\":\"PASS\",\"streams\":{stream_count},\"echoed_frames\":{echoed}}}"
            ),
        )
        .unwrap();
        drop(session);
        connection.close().await.unwrap();
        listener.close().await.unwrap();
        return;
    }
    let benchmark_samples = env::var("NBSR_PERF_STREAM_SAMPLES").ok();
    let samples = benchmark_samples
        .as_deref()
        .map(|value| value.parse::<u64>().expect("valid sample count"))
        .unwrap_or(1);
    assert!((1..=10_000_000).contains(&samples));
    let mut payload = Vec::new();
    for index in 0..samples {
        #[cfg(feature = "benchmark-harness")]
        let profile_read = std::time::Instant::now();
        let received = control.receive_envelope(CoreV02Limits::default()).await;
        #[cfg(feature = "benchmark-harness")]
        nbsr_transport::lifecycle_profile::global().record_ns(
            nbsr_transport::lifecycle_profile::LifecyclePhase::DestinationControlRead,
            profile_read.elapsed().as_nanos() as u64,
            received.is_ok(),
        );
        let stream = received.unwrap();
        #[cfg(feature = "benchmark-harness")]
        let profile_authorize = std::time::Instant::now();
        let authorized = session.authorize_stream_open(channel, &stream);
        #[cfg(feature = "benchmark-harness")]
        nbsr_transport::lifecycle_profile::global().record_ns(
            nbsr_transport::lifecycle_profile::LifecyclePhase::DestinationAuthorize,
            profile_authorize.elapsed().as_nanos() as u64,
            authorized.is_ok(),
        );
        authorized.unwrap();
        let stream_accepted = stream_accept(index);
        session
            .confirm_stream_accept(channel, &stream_accepted)
            .unwrap();
        #[cfg(feature = "benchmark-harness")]
        let profile_response = std::time::Instant::now();
        let sent = control.send_envelope(&stream_accepted).await;
        #[cfg(feature = "benchmark-harness")]
        nbsr_transport::lifecycle_profile::global().record_ns(
            nbsr_transport::lifecycle_profile::LifecyclePhase::DestinationResponseWrite,
            profile_response.elapsed().as_nanos() as u64,
            sent.is_ok(),
        );
        sent.unwrap();
        let accepted = connection
            .accept_session_stream(&mut session, channel)
            .await;
        let mut application = accepted.unwrap();
        #[cfg(feature = "benchmark-harness")]
        let profile_exchange = std::time::Instant::now();
        let echoed = application.echo_once().await;
        #[cfg(feature = "benchmark-harness")]
        nbsr_transport::lifecycle_profile::global().record_ns(
            nbsr_transport::lifecycle_profile::LifecyclePhase::DestinationFirstExchange,
            profile_exchange.elapsed().as_nanos() as u64,
            echoed.is_ok(),
        );
        payload = echoed.unwrap();
        #[cfg(feature = "benchmark-harness")]
        let profile_release = std::time::Instant::now();
        let released = session.release_stream(channel, 4 + 4 * index);
        #[cfg(feature = "benchmark-harness")]
        nbsr_transport::lifecycle_profile::global().record_ns(
            nbsr_transport::lifecycle_profile::LifecyclePhase::DestinationReleaseCleanup,
            profile_release.elapsed().as_nanos() as u64,
            released.is_ok(),
        );
        released.unwrap();
        while session.pop_audit_event().is_some() {}
    }
    drop(session);
    let digest = Sha256::digest(&payload);
    let digest_hex = digest
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    let result_json = if benchmark_samples.is_some() {
        format!(
            "{{\"payload_bytes\":{},\"payload_sha256\":\"{}\",\"samples\":{},\"status\":\"PASS\"}}",
            payload.len(),
            digest_hex,
            samples
        )
    } else {
        format!(
            "{{\"payload_bytes\":{},\"payload_sha256\":\"{}\",\"status\":\"PASS\"}}",
            payload.len(),
            digest_hex
        )
    };
    fs::write(result, result_json).unwrap();
    #[cfg(feature = "benchmark-harness")]
    if env::var_os("NBSR_P2B_PROFILE").is_some() {
        println!(
            "{}",
            nbsr_transport::lifecycle_profile::global()
                .snapshot()
                .to_json("destination")
        );
    }
    tokio::time::timeout(Duration::from_secs(10), async {
        while !completion_ack.exists() {
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .expect("test harness completion acknowledgement");
    connection.close().await.unwrap();
    listener.close().await.unwrap();
    if diagnostic_sampler.is_some() && diagnostic_drain_seconds > 0 {
        std::thread::sleep(Duration::from_secs(diagnostic_drain_seconds));
    }
    if let Some(sampler) = diagnostic_sampler {
        let _ = sampler.stop_and_join();
    }
}

fn field_uint(t: &mut Vec<u8>, k: u64, v: u64) {
    uint(t, k);
    uint(t, v)
}
fn field_bytes(t: &mut Vec<u8>, k: u64, v: &[u8]) {
    uint(t, k);
    argument(t, 2, v.len() as u64);
    t.extend(v)
}
fn field_text(t: &mut Vec<u8>, k: u64, v: &str) {
    uint(t, k);
    argument(t, 3, v.len() as u64);
    t.extend(v.as_bytes())
}
fn uint(t: &mut Vec<u8>, v: u64) {
    argument(t, 0, v)
}
fn map(t: &mut Vec<u8>, v: u64) {
    argument(t, 5, v)
}
fn argument(t: &mut Vec<u8>, m: u8, v: u64) {
    let i = m << 5;
    match v {
        0..=23 => t.push(i | v as u8),
        24..=0xff => t.extend([i | 24, v as u8]),
        0x100..=0xffff => {
            t.push(i | 25);
            t.extend((v as u16).to_be_bytes())
        }
        0x1_0000..=0xffff_ffff => {
            t.push(i | 26);
            t.extend((v as u32).to_be_bytes())
        }
        _ => {
            t.push(i | 27);
            t.extend(v.to_be_bytes())
        }
    }
}
