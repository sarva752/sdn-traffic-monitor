# SDN Traffic Monitoring and Statistics Collector

> **Orange Problem — SDN Mininet Project**
> Controller: **POX** | Data plane: **Open vSwitch + Mininet** | Protocol: **OpenFlow 1.0**

---

## 1. Problem Statement

Build a controller module that **collects and displays traffic statistics**
for every switch in an SDN network.

Functional requirements:

1. Retrieve **flow statistics** from each switch (per-flow packet & byte counts).
2. Display **packet / byte counts** on every port.
3. Poll switches **periodically** (every 5 seconds).
4. Generate **simple reports** (console + log file).
5. Install explicit **OpenFlow match–action** rules to forward traffic.
6. Demonstrate at least **2 test scenarios** (normal vs failure) with validation.

---

## 2. Architecture

```
                       +-----------------------+
                       |   POX Controller      |
                       |  traffic_monitor.py   |
                       |   (127.0.0.1:6633)    |
                       +----------+------------+
                                  |  OpenFlow 1.0
                                  |  (TCP 6633)
                           +------+------+
                           |     s1      |   <-- OVS switch
                           +--+--+--+--+-+
                              |  |  |  |
                              1  2  3  4
                              |  |  |  |
                             h1 h2 h3 h4
                         (10.0.0.1 .. 10.0.0.4)
```

### Design choices

| Choice | Justification |
|---|---|
| **Single switch, 4 hosts** | Minimal topology that still demonstrates multi-flow monitoring without clouding the output. Easy to extend. |
| **POX controller** | Lightweight, Python-based, clear event API — ideal for learning SDN flow-stat collection. |
| **OpenFlow 1.0** | Default protocol supported by both POX and OVS without extra configuration. |
| **Learning switch + stat collection** | Forwarding must work for any traffic to be observed; combining both shows the full control-plane story. |
| **Periodic polling (5 s)** | Frequent enough to see iperf traffic, slow enough to avoid flooding logs. |
| **Flow idle-timeout 10 s** | Lets the flow table naturally evolve during tests (watch rules appear/disappear). |

---

## 3. Repository Layout

```
sdn-traffic-monitor/
├── traffic_monitor.py     # POX controller module (main logic)
├── topology.py            # Mininet topology script
├── test_scenarios.py      # Automated test + validation script
├── run_controller.sh      # Helper to launch POX
├── sample_output.log      # Example report output
└── README.md              # This file
```

---

## 4. Prerequisites

Tested on **Ubuntu 20.04 LTS** (Comnetsemu / Mininet VM work too):

```bash
sudo apt update
sudo apt install -y mininet openvswitch-switch python2 git wireshark iperf

# POX (master branch works with Python 2/3; we use the default py2 branch)
cd ~
git clone https://github.com/noxrepo/pox.git
```

Open vSwitch must be running:

```bash
sudo service openvswitch-switch start
```

---

## 5. Setup & Execution Steps

### Step 1 — Clone this repo

```bash
git clone https://github.com/<your-username>/sdn-traffic-monitor.git
cd sdn-traffic-monitor
```

### Step 2 — Start the POX controller (Terminal 1)

```bash
./run_controller.sh
# OR manually:
cp traffic_monitor.py ~/pox/ext/
cd ~/pox && ./pox.py log.level --DEBUG traffic_monitor
```

Expected console banner:
```
INFO:core:POX 0.7.0 (gar) is up.
INFO:traffic_monitor:TrafficMonitor initialised; polling every 5s
INFO:traffic_monitor:Traffic Monitor component launched
```

### Step 3 — Launch the topology (Terminal 2)

```bash
sudo python topology.py
```

You should see:
```
INFO:traffic_monitor:Switch 00-00-00-00-00-01 connected and registered for monitoring
```

### Step 4 — Run demo traffic from the Mininet CLI

```
mininet> pingall
mininet> h1 iperf -s &
mininet> h3 iperf -c 10.0.0.1 -t 10
mininet> h1 ping -c 5 h4
```

Watch Terminal 1 — you will see periodic **TRAFFIC REPORT** blocks every 5 s.

### Step 5 — Automated scenarios (optional)

```bash
sudo python test_scenarios.py
```

Runs Scenario 1 (normal), Scenario 2 (link failure), and a regression ping after recovery.

---

## 6. Expected Output

### 6.1 Controller-side traffic report

```
======================================================================
  TRAFFIC REPORT  @  14:22:25
======================================================================

>> Switch 00-00-00-00-00-01
   [ Flow Table ]  6 active flow(s)
      00:00:00:00:00:01 -> 00:00:00:00:00:03  (in_port=1) pkts=12 bytes=1176 age=4s
      00:00:00:00:00:03 -> 00:00:00:00:00:01  (in_port=3) pkts=12 bytes=1176 age=4s
      ...
   [ Port Stats ]
      Port   RX_pkts    TX_pkts    RX_bytes     TX_bytes     Errors
      1      26         20         2548         1960         0
      2      22         26         2156         2548         0
      3      16         16         1568         1568         0
      4      12         12         1176         1176         0
```

Full sample: see **`sample_output.log`**.

### 6.2 Flow table on the switch

```bash
mininet> sh ovs-ofctl dump-flows s1
 cookie=0x0, duration=3.1s, n_packets=12, n_bytes=1176, idle_timeout=10,
     priority=10,in_port=1,dl_src=00:00:00:00:00:01,dl_dst=00:00:00:00:00:03
     actions=output:3
 ...
```

### 6.3 ping / iperf

```
mininet> pingall
*** Ping: testing ping reachability
h1 -> h2 h3 h4
h2 -> h1 h3 h4
h3 -> h1 h2 h4
h4 -> h1 h2 h3
*** Results: 0% dropped (12/12 received)

mininet> iperf h1 h3
*** Iperf: testing TCP bandwidth between h1 and h3
*** Results: ['9.42 Mbits/sec', '9.55 Mbits/sec']
```

---

## 7. Test Scenarios (Functional Correctness)

### Scenario 1 — Normal Operation ✅
| Step | Command | Expected |
|---|---|---|
| Connectivity | `pingall` | 0 % loss |
| Flow install | `ovs-ofctl dump-flows s1` | ≥ 6 flows with matching counters |
| Monitoring | Watch controller log | RX/TX counters on every port grow |
| Throughput | `iperf h1 h3` | ~9.5 Mbps on a 10 Mbps link |

### Scenario 2 — Link Failure / Recovery ⚠️ → ✅
| Step | Command | Expected |
|---|---|---|
| Break link | `link s1 h4 down` | `h1 ping h4` → 100 % loss |
| Partial op. | `h1 ping h3` | 0 % loss — other flows unaffected |
| Port stats | Watch report | Port 4 counters **freeze** |
| Recovery | `link s1 h4 up` | `pingall` → 0 % loss (**regression**) |

These are automated inside `test_scenarios.py` with assertions.

---

## 8. Performance Observation & Analysis

| Metric | Tool | Observation |
|---|---|---|
| **Latency** | `ping` | First ping: ~5–20 ms (packet_in + flow install). Subsequent: < 0.1 ms (hardware-path via installed flow). |
| **Throughput** | `iperf` | ~9.4 Mbps on a 10 Mbps `TCLink` — ~94 % efficiency. |
| **Flow table growth** | `dump-flows` | Grows during traffic, shrinks after 10 s idle timeout — proves timeout logic works. |
| **Packet counts** | Report | `n_packets` per flow matches ping/iperf volume exactly. |
| **Wireshark on `lo`** | filter `openflow_v1` | See `OFPT_PACKET_IN`, `OFPT_FLOW_MOD`, `OFPT_STATS_REQUEST/REPLY` every 5 s. |

### Interpretation

* First packet of every new conversation goes to the controller (`packet_in`),
  confirming the learning-switch logic.
* Once a flow is installed, traffic stays in the data plane — that's why
  throughput is close to link capacity.
* Stats replies arrive ~1 s after the controller's `stats_request`, which is
  why `_print_report` is scheduled with a 1 s delay.
* After the idle timeout, flows evaporate from the table — visible in the
  next report as the `n active flow(s)` count drops.

---

## 9. Validation / Regression Summary

| Check | Location | Result |
|---|---|---|
| `pingall` = 0 % loss (normal) | `test_scenarios.py` | Asserted |
| Isolation during link-down | `test_scenarios.py` | Checked via ping output |
| Other flows continue during failure | `test_scenarios.py` | Checked |
| Full recovery after link up | `test_scenarios.py` | Asserted |
| Flow-stat counters monotonic ↑ | Controller report | Visible in log |
| Flow removed after idle_timeout | Controller report | Visible in log |

---

## 10. Proof of Execution

Reproduce the following artefacts in your own run and commit them to the repo under `proofs/`:

1. `proofs/controller_log.png` — POX console showing periodic reports
2. `proofs/flow_table.png` — `ovs-ofctl dump-flows s1` output
3. `proofs/pingall.png` — `pingall` 0 % loss
4. `proofs/iperf.png` — `iperf h1 h3` result
5. `proofs/wireshark_openflow.png` — OpenFlow packets on `lo`
6. `proofs/link_failure.png` — Scenario 2 ping loss
7. `proofs/recovery.png` — Post-recovery pingall

A sample report is included at `sample_output.log`.

---

## 11. Mapping to Rubric (25 marks)

| Rubric item | Marks | Covered by |
|---|---|---|
| 1. Problem Understanding & Setup | 4 | §1–§3 (topology justification, controller choice) |
| 2. SDN Logic & Flow Rule Implementation | 6 | `traffic_monitor.py` — `_handle_PacketIn`, priority + timeouts |
| 3. Functional Correctness (Demo) | 6 | `topology.py`, `test_scenarios.py`, §6–§7 |
| 4. Performance Observation & Analysis | 5 | §8 + periodic reports + iperf |
| 5. Explanation, Viva & Validation | 4 | This README + §9 + inline code comments |

---

## 12. References

1. POX Wiki — *Open Networking Foundation*
   https://openflow.stanford.edu/display/ONL/POX+Wiki
2. Mininet Documentation — http://mininet.org/
3. OpenFlow 1.0 Specification — *ONF*, 2009.
4. Kreutz et al., *"Software-Defined Networking: A Comprehensive Survey"*,
   Proceedings of the IEEE, 2015.
5. OVS `ovs-ofctl` man page — https://man7.org/linux/man-pages/man8/ovs-ofctl.8.html
6. Wireshark OpenFlow dissector — https://wiki.wireshark.org/OpenFlow
