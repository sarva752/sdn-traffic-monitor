# =============================================================================
#  Traffic Monitoring and Statistics Collector  -  POX Controller Module
# =============================================================================
#  Problem : Build a controller module that collects and displays traffic
#            statistics for every switch in the network.
#
#  Features:
#    1. Acts as a Learning Switch (L2) so connectivity works out-of-the-box.
#    2. Installs explicit OpenFlow match-action rules (priority + idle_timeout).
#    3. Handles packet_in events for unknown destinations.
#    4. Periodically polls every switch for:
#         - Flow statistics  (per-flow packet & byte counts)
#         - Port  statistics (per-port rx/tx packets, bytes, errors)
#    5. Prints periodic reports and saves them to a log file.
#
#  Run   :  ./pox.py log.level --DEBUG traffic_monitor
# =============================================================================

from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.addresses import EthAddr
from pox.lib.util import dpid_to_str
from pox.lib.recoco import Timer

import time
import os

log = core.getLogger()

# -----------------------------------------------------------------------------
#  Configuration
# -----------------------------------------------------------------------------
STATS_INTERVAL = 5          # Seconds between stats polls
FLOW_IDLE_TIMEOUT = 10      # Remove flows after 10s idle
FLOW_HARD_TIMEOUT = 30      # Hard limit 30s
REPORT_FILE = "/tmp/traffic_monitor_report.log"


# =============================================================================
#  Per-Switch Learning Switch + Stats Collector
# =============================================================================
class TrafficMonitorSwitch(object):
    """
    Represents a single OpenFlow switch connected to the controller.
    Performs MAC learning and tracks cumulative traffic counters.
    """

    def __init__(self, connection):
        self.connection = connection
        self.dpid = connection.dpid
        self.mac_to_port = {}          # MAC learning table
        self.flow_stats = {}           # (match_tuple) -> (packets, bytes)
        self.port_stats = {}           # port_no -> (rx_pkts, tx_pkts, rx_bytes, tx_bytes)

        connection.addListeners(self)
        log.info("Switch %s connected and registered for monitoring",
                 dpid_to_str(self.dpid))

    # -------------------------------------------------------------------------
    #  L2 Learning Switch  (packet_in handler)
    # -------------------------------------------------------------------------
    def _handle_PacketIn(self, event):
        packet = event.parsed
        if not packet.parsed:
            log.warning("Ignoring incomplete packet")
            return

        in_port = event.port
        src = packet.src
        dst = packet.dst

        # --- 1. Learn the source MAC -----------------------------------------
        self.mac_to_port[src] = in_port

        # --- 2. Decide action ------------------------------------------------
        if dst.is_multicast:
            # Flood multicast / broadcast
            self._flood(event)
            return

        if dst in self.mac_to_port:
            out_port = self.mac_to_port[dst]
            if out_port == in_port:
                # Drop to avoid loops
                log.warning("Same in/out port (%s) -> dropping", in_port)
                return

            # --- 3. Install a flow rule (match + action) ---------------------
            msg = of.ofp_flow_mod()
            msg.match = of.ofp_match.from_packet(packet, in_port)
            msg.idle_timeout = FLOW_IDLE_TIMEOUT
            msg.hard_timeout = FLOW_HARD_TIMEOUT
            msg.priority = 10
            msg.actions.append(of.ofp_action_output(port=out_port))
            msg.data = event.ofp    # Send the buffered packet too
            self.connection.send(msg)

            log.debug("Flow installed on %s : %s -> %s via port %s",
                      dpid_to_str(self.dpid), src, dst, out_port)
        else:
            # Unknown destination -> flood
            self._flood(event)

    def _flood(self, event):
        msg = of.ofp_packet_out()
        msg.data = event.ofp
        msg.actions.append(of.ofp_action_output(port=of.OFPP_FLOOD))
        msg.in_port = event.port
        self.connection.send(msg)

    # -------------------------------------------------------------------------
    #  Stats reply handlers
    # -------------------------------------------------------------------------
    def _handle_FlowStatsReceived(self, stats):
        self.flow_stats.clear()
        for f in stats:
            key = (str(f.match.dl_src), str(f.match.dl_dst), f.match.in_port)
            self.flow_stats[key] = (f.packet_count, f.byte_count, f.duration_sec)

    def _handle_PortStatsReceived(self, stats):
        self.port_stats.clear()
        for p in stats:
            if p.port_no < 65000:       # Skip OFPP_LOCAL etc.
                self.port_stats[p.port_no] = (
                    p.rx_packets, p.tx_packets,
                    p.rx_bytes,  p.tx_bytes,
                    p.rx_errors + p.tx_errors,
                )


# =============================================================================
#  Controller-level Monitor (manages all switches + periodic polling)
# =============================================================================
class TrafficMonitor(object):
    def __init__(self):
        self.switches = {}          # dpid -> TrafficMonitorSwitch
        core.openflow.addListeners(self)

        # Initialise report file
        with open(REPORT_FILE, "w") as f:
            f.write("=" * 70 + "\n")
            f.write(" SDN Traffic Monitoring Report - started %s\n" %
                    time.strftime("%Y-%m-%d %H:%M:%S"))
            f.write("=" * 70 + "\n")

        # Kick off periodic polling
        Timer(STATS_INTERVAL, self._request_stats, recurring=True)
        log.info("TrafficMonitor initialised; polling every %ss", STATS_INTERVAL)

    # -------------------------------------------------------------------------
    #  New switch joined
    # -------------------------------------------------------------------------
    def _handle_ConnectionUp(self, event):
        sw = TrafficMonitorSwitch(event.connection)
        self.switches[event.dpid] = sw

        # Route stats replies to the correct switch object
        event.connection.addListenerByName(
            "FlowStatsReceived",
            lambda ev: sw._handle_FlowStatsReceived(ev.stats))
        event.connection.addListenerByName(
            "PortStatsReceived",
            lambda ev: sw._handle_PortStatsReceived(ev.stats))

    def _handle_ConnectionDown(self, event):
        if event.dpid in self.switches:
            del self.switches[event.dpid]
            log.info("Switch %s disconnected", dpid_to_str(event.dpid))

    # -------------------------------------------------------------------------
    #  Periodic stats request + report
    # -------------------------------------------------------------------------
    def _request_stats(self):
        for conn in core.openflow.connections:
            conn.send(of.ofp_stats_request(body=of.ofp_flow_stats_request()))
            conn.send(of.ofp_stats_request(body=of.ofp_port_stats_request()))
        # Give switches ~1s to reply, then print report
        Timer(1, self._print_report)

    def _print_report(self):
        ts = time.strftime("%H:%M:%S")
        header = "\n" + "=" * 70
        header += "\n  TRAFFIC REPORT  @  %s" % ts
        header += "\n" + "=" * 70

        lines = [header]

        for dpid, sw in self.switches.items():
            lines.append("\n>> Switch %s" % dpid_to_str(dpid))

            # ---- Flow stats ----
            lines.append("   [ Flow Table ]  %d active flow(s)" %
                         len(sw.flow_stats))
            for (src, dst, inp), (pkts, byts, dur) in sw.flow_stats.items():
                lines.append("      %s -> %s  (in_port=%s) "
                             "pkts=%d bytes=%d age=%ss" %
                             (src, dst, inp, pkts, byts, dur))

            # ---- Port stats ----
            lines.append("   [ Port Stats ]")
            lines.append("      %-6s %-10s %-10s %-12s %-12s %-8s" %
                         ("Port", "RX_pkts", "TX_pkts",
                          "RX_bytes", "TX_bytes", "Errors"))
            for port, (rxp, txp, rxb, txb, err) in sorted(sw.port_stats.items()):
                lines.append("      %-6s %-10d %-10d %-12d %-12d %-8d" %
                             (port, rxp, txp, rxb, txb, err))

        report = "\n".join(lines)
        log.info(report)

        # Append to file for later proof
        with open(REPORT_FILE, "a") as f:
            f.write(report + "\n")


# =============================================================================
#  POX entry point
# =============================================================================
def launch():
    core.registerNew(TrafficMonitor)
    log.info("Traffic Monitor component launched")
