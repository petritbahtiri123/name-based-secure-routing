# NBSR loopback memory completion report

Final classification: **PARTIAL_BASELINE**

The frozen memory methodology classifies both stable-load windows as PASS only when bounded, FAIL only when reproducible request-correlated sustained growth satisfies the confidence and fit gates, and otherwise INCONCLUSIVE.

## direct-50

Terminal state: completed; eligible: True; counts: {"completed": 4275000, "failed": 0, "offered": 4275000, "persisted": 4275000, "timed_out": 0}.

Working set: {"end": 9334784, "peak": 9379840, "start": 9236480}.

Private bytes: {"end": 1884160, "peak": 1949696, "start": 1884160}.

Working-set trends: {"final_quarter": {"lower_95": 0.0, "r_squared": 1.0, "samples": 444, "slope_bytes_per_second": 0.0, "upper_95": 0.0}, "overall": {"lower_95": 27.766270479204827, "r_squared": 0.1822098084130963, "samples": 1776, "slope_bytes_per_second": 30.803009627032168, "upper_95": 33.83974877485951}, "second_half": {"lower_95": -10.901249510022097, "r_squared": 0.18461910795196235, "samples": 888, "slope_bytes_per_second": -9.57608674956033, "upper_95": -8.250923989098563}}.

Private-byte trends: {"final_quarter": {"lower_95": 0.0, "r_squared": 1.0, "samples": 444, "slope_bytes_per_second": 0.0, "upper_95": 0.0}, "overall": {"lower_95": -12.746133819285104, "r_squared": 0.07011199526686351, "samples": 1776, "slope_bytes_per_second": -10.899048311970576, "upper_95": -9.051962804656048}, "second_half": {"lower_95": -21.802499020044174, "r_squared": 0.18461910795197378, "samples": 888, "slope_bytes_per_second": -19.15217349912066, "upper_95": -16.501847978197148}}.

Processed-request delta: 4272625; bytes/request: working set=0.023007869869225595, private=0.0.

Scheduler lag: {"late_requests": 4131094, "max_start_lateness_ns": 166648632, "p95_start_lateness_ns": 189}; backlog: {"delta": 369, "end": 1850, "peak": 2372, "start": 1481}.

## direct-68

Terminal state: completed; eligible: True; counts: {"completed": 5814000, "failed": 0, "offered": 5814000, "persisted": 5814000, "timed_out": 0}.

Working set: {"end": 9342976, "peak": 9359360, "start": 8327168}.

Private bytes: {"end": 1888256, "peak": 1949696, "start": 1888256}.

Working-set trends: {"final_quarter": {"lower_95": 0.0, "r_squared": 1.0, "samples": 440, "slope_bytes_per_second": 0.0, "upper_95": 0.0}, "overall": {"lower_95": 749.1622108296041, "r_squared": 0.7588919012594314, "samples": 1759, "slope_bytes_per_second": 769.4419320694002, "upper_95": 789.7216533091963}, "second_half": {"lower_95": 864.0578755464896, "r_squared": 0.4593082012487629, "samples": 880, "slope_bytes_per_second": 930.8642586955776, "upper_95": 997.6706418446656}}.

Private-byte trends: {"final_quarter": {"lower_95": 0.0, "r_squared": 1.0, "samples": 440, "slope_bytes_per_second": 0.0, "upper_95": 0.0}, "overall": {"lower_95": -9.451469845912307, "r_squared": 0.0640176352466243, "samples": 1759, "slope_bytes_per_second": -8.017911234934987, "upper_95": -6.584352623957668}, "second_half": {"lower_95": -15.840461114426198, "r_squared": 0.11569888506359893, "samples": 880, "slope_bytes_per_second": -13.391539809638179, "upper_95": -10.94261850485016}}.

Processed-request delta: 5810770; bytes/request: working set=0.1748146975357827, private=0.0.

Scheduler lag: {"late_requests": 5805216, "max_start_lateness_ns": 286836647, "p95_start_lateness_ns": 71127}; backlog: {"delta": -1230, "end": 1942, "peak": 3229, "start": 3172}.

## rust-50

Terminal state: completed; eligible: True; counts: {"completed": 1518750, "failed": 0, "offered": 1518750, "persisted": 1518750, "timed_out": 0}.

Working set: {"end": 64524288, "peak": 73965568, "start": 11894784}.

Private bytes: {"end": 57122816, "peak": 57122816, "start": 4894720}.

Working-set trends: {"final_quarter": {"lower_95": 0.0, "r_squared": 1.0, "samples": 444, "slope_bytes_per_second": 0.0, "upper_95": 0.0}, "overall": {"lower_95": 33497.77554037998, "r_squared": 0.8864796956661325, "samples": 1776, "slope_bytes_per_second": 34065.04660023295, "upper_95": 34632.317660085915}, "second_half": {"lower_95": 20063.46052850083, "r_squared": 0.36286725964600175, "samples": 888, "slope_bytes_per_second": 21981.403539226976, "upper_95": 23899.346549953123}}.

Private-byte trends: {"final_quarter": {"lower_95": 0.0, "r_squared": 1.0, "samples": 444, "slope_bytes_per_second": 0.0, "upper_95": 0.0}, "overall": {"lower_95": 33510.50936223149, "r_squared": 0.8862851715053347, "samples": 1776, "slope_bytes_per_second": 34078.55368955571, "upper_95": 34646.59801687993}, "second_half": {"lower_95": 20099.632632819048, "r_squared": 0.36286725964600164, "samples": 888, "slope_bytes_per_second": 22021.033473492414, "upper_95": 23942.43431416578}}.

Processed-request delta: 1518749; bytes/request: working set=34.65319417494267, private=34.38889243713082.

Scheduler lag: {"late_requests": 1504589, "max_start_lateness_ns": 139106767, "p95_start_lateness_ns": 196}; backlog: {"delta": -733, "end": 0, "peak": 843, "start": 733}.

## rust-75

Terminal state: completed; eligible: True; counts: {"completed": 2278124, "failed": 0, "offered": 2278124, "persisted": 2278124, "timed_out": 0}.

Working set: {"end": 118304768, "peak": 137183232, "start": 12558336}.

Private bytes: {"end": 111763456, "peak": 111763456, "start": 5910528}.

Working-set trends: {"final_quarter": {"lower_95": 49810.633268372636, "r_squared": 0.24594288736903402, "samples": 444, "slope_bytes_per_second": 59528.07010474981, "upper_95": 69245.50694112698}, "overall": {"lower_95": 60075.70594399024, "r_squared": 0.873859995399039, "samples": 1773, "slope_bytes_per_second": 61157.89924706041, "upper_95": 62240.09255013059}, "second_half": {"lower_95": 86623.02923672066, "r_squared": 0.7439893711686576, "samples": 887, "slope_bytes_per_second": 90105.4490407658, "upper_95": 93587.86884481095}}.

Private-byte trends: {"final_quarter": {"lower_95": 49907.91966147493, "r_squared": 0.2459428873690339, "samples": 444, "slope_bytes_per_second": 59644.33586667315, "upper_95": 69380.75207187138}, "overall": {"lower_95": 60148.457372716184, "r_squared": 0.8736355567545595, "samples": 1773, "slope_bytes_per_second": 61233.08388643756, "upper_95": 62317.71040015894}, "second_half": {"lower_95": 86786.75726488073, "r_squared": 0.743944334592362, "samples": 887, "slope_bytes_per_second": 90276.18833862802, "upper_95": 93765.61941237532}}.

Processed-request delta: 2276858; bytes/request: working set=46.44401714994962, private=46.49079037867096.

Scheduler lag: {"late_requests": 2272446, "max_start_lateness_ns": 251933279, "p95_start_lateness_ns": 65521}; backlog: {"delta": -327, "end": 678, "peak": 1264, "start": 1005}.

## go-50

Terminal state: failed; eligible: False; counts: {"completed": 184468, "failed": 0, "offered": 372000, "persisted": 184468, "started": 184468, "timed_out": 0}.

Working set: {"end": 177209344, "peak": 177217536, "start": 2260992}.

Private bytes: {"end": 175128576, "peak": 175190016, "start": 34635776}.

Working-set trends: {"final_quarter": {"lower_95": 42.4733347703257, "r_squared": 0.8779509069381036, "samples": 231, "slope_bytes_per_second": 44.628511528261114, "upper_95": 46.78368828619653}, "overall": {"lower_95": 662.4597005004807, "r_squared": 0.009008138786326447, "samples": 922, "slope_bytes_per_second": 2055.833160769887, "upper_95": 3449.206621039293}, "second_half": {"lower_95": 22.965893202973504, "r_squared": 0.24182289168228555, "samples": 461, "slope_bytes_per_second": 27.40525090631307, "upper_95": 31.84460860965264}}.

Private-byte trends: {"final_quarter": {"lower_95": 43.31397779217614, "r_squared": 0.6792921093751885, "samples": 231, "slope_bytes_per_second": 47.54526109908009, "upper_95": 51.77654440598405}, "overall": {"lower_95": 463.09926454921765, "r_squared": 0.0082419701029669, "samples": 922, "slope_bytes_per_second": 1590.5433552771135, "upper_95": 2717.9874460050096}, "second_half": {"lower_95": -1.889082788506899, "r_squared": 0.004692607608503208, "samples": 461, "slope_bytes_per_second": 5.683864219563848, "upper_95": 13.256811227634595}}.

Processed-request delta: 184268; bytes/request: working set=949.4234050404846, private=762.4373195562985.

Scheduler lag: null; backlog: null.

Go runtime: {"frees_delta": 3117417589, "heap_alloc_bytes": {"end": 59914160, "peak": 116489344, "start": 97560656}, "heap_idle_bytes": {"end": 64634880, "peak": 64634880, "start": 5480448}, "heap_inuse_bytes": {"end": 60899328, "peak": 118284288, "start": 99082240}, "heap_released_bytes": {"end": 58515456, "peak": 58515456, "start": 5480448}, "heap_sys_bytes": {"end": 125534208, "peak": 125534208, "start": 104562688}, "mallocs_delta": 3115136006, "max_observed_interval_pause_ns": 2002600, "num_gc_delta": 485, "per_gc_max_pause_ns": null, "processed_request_delta": 184268, "recent_observed_interval_pause_ns": 0, "total_alloc_delta_bytes": 26092681520, "total_gc_pause_delta_ns": 35675700}.

## go-75

Terminal state: timed_out; eligible: False; counts: {"completed": 276702, "failed": 0, "offered": 558000, "persisted": 276702, "started": 276702, "timed_out": 281298}.

Working set: {"end": 238448640, "peak": 238456832, "start": 2314240}.

Private bytes: {"end": 236335104, "peak": 236359680, "start": 34643968}.

Working-set trends: {"final_quarter": {"lower_95": 31.395543405379957, "r_squared": 0.7722499274788807, "samples": 231, "slope_bytes_per_second": 33.77091454710308, "upper_95": 36.14628568882621}, "overall": {"lower_95": 2327.9568289724, "r_squared": 0.01989164409542099, "samples": 921, "slope_bytes_per_second": 4262.385718488689, "upper_95": 6196.814608004978}, "second_half": {"lower_95": 811.3259372749636, "r_squared": 0.5174502819365614, "samples": 461, "slope_bytes_per_second": 889.949319630995, "upper_95": 968.5727019870263}}.

Private-byte trends: {"final_quarter": {"lower_95": 24.984851438078056, "r_squared": 0.4210039755156272, "samples": 231, "slope_bytes_per_second": 29.45949347116978, "upper_95": 33.934135504261505}, "overall": {"lower_95": 2094.789451954213, "r_squared": 0.020694946194754538, "samples": 921, "slope_bytes_per_second": 3772.7600547718976, "upper_95": 5450.730657589582}, "second_half": {"lower_95": 790.097987814432, "r_squared": 0.4915381024922125, "samples": 461, "slope_bytes_per_second": 871.156066708269, "upper_95": 952.214145602106}}.

Processed-request delta: 276402; bytes/request: working set=854.3150917866006, private=729.702158450373.

Scheduler lag: null; backlog: null.

Go runtime: {"frees_delta": 2734082705, "heap_alloc_bytes": {"end": 89666728, "peak": 173911696, "start": 124286064}, "heap_idle_bytes": {"end": 93609984, "peak": 93609984, "start": 8159232}, "heap_inuse_bytes": {"end": 90644480, "peak": 176545792, "start": 125763584}, "heap_released_bytes": {"end": 84500480, "peak": 84500480, "start": 8159232}, "heap_sys_bytes": {"end": 184254464, "peak": 184254464, "start": 133922816}, "mallocs_delta": 2732026896, "max_observed_interval_pause_ns": 1019000, "num_gc_delta": 289, "per_gc_max_pause_ns": null, "processed_request_delta": 276402, "recent_observed_interval_pause_ns": 0, "total_alloc_delta_bytes": 23604490648, "total_gc_pause_delta_ns": 24258200}.

## Candidate future diagnostic work — NOT IMPLEMENTED

Both retained Go loads stopped processing requests around the middle of the offered set while runtime sampling continued. Diagnose this separately before any rerun; this report does not modify or optimize Go/NBSR behavior.
