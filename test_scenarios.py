#!/usr/bin/env python
# =============================================================================
#  test_scenarios.py  -  Automated test scenarios for the Traffic Monitor
# =============================================================================
#  Scenario 1 : NORMAL OPERATION
#               - All hosts can reach each other (pingall)
#               - Flow rules installed, counters increment
#
#  Scenario 2 : FAILURE / LINK DOWN
#               - Bring down link h4-s1
#               - Verify h4 becomes unreachable while h1<->h3 still works
#               - Bring link back up -> connectivity restored
#
#  Regression : Final pingall must succeed after recovery.
# =============================================================================

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.log import setLogLevel, info
import time


def run_tests():
    net = Mininet(controller=RemoteController, switch=OVSSwitch,
                  link=TCLink, autoSetMacs=True)
    c0 = net.addController('c0', ip='127.0.0.1', port=6633)
    s1 = net.addSwitch('s1', protocols='OpenFlow10')
    h1 = net.addHost('h1', ip='10.0.0.1/24')
    h2 = net.addHost('h2', ip='10.0.0.2/24')
    h3 = net.addHost('h3', ip='10.0.0.3/24')
    h4 = net.addHost('h4', ip='10.0.0.4/24')
    for h in (h1, h2, h3, h4):
        net.addLink(h, s1, bw=10)

    net.build()
    c0.start()
    s1.start([c0])

    info("\n########## SCENARIO 1 : NORMAL OPERATION ##########\n")
    info("Waiting 3s for controller <-> switch handshake ...\n")
    time.sleep(3)

    info(">>> pingall\n")
    loss = net.pingAll()
    assert loss == 0, "[FAIL] Expected 0%% loss in normal scenario"
    info("[PASS] All hosts reachable\n")

    info("\n>>> iperf h1 <-> h3  (throughput test)\n")
    bw = net.iperf((h1, h3), seconds=5)
    info("iperf result: %s\n" % str(bw))

    info("\n>>> Flow table on s1 after traffic:\n")
    info(s1.cmd('ovs-ofctl dump-flows s1') + "\n")

    info("\n########## SCENARIO 2 : LINK FAILURE  ##########\n")
    info(">>> Bringing down link h4 <-> s1\n")
    net.configLinkStatus('s1', 'h4', 'down')
    time.sleep(2)

    info(">>> Ping h1 -> h4  (should FAIL)\n")
    result = h1.cmd('ping -c 2 -W 1 10.0.0.4')
    info(result + "\n")
    if "100% packet loss" in result or "Destination Host Unreachable" in result:
        info("[PASS] h4 correctly unreachable after link down\n")
    else:
        info("[WARN] Unexpected ping output during failure\n")

    info(">>> Ping h1 -> h3  (should still WORK)\n")
    result = h1.cmd('ping -c 2 -W 1 10.0.0.3')
    info(result + "\n")
    if " 0% packet loss" in result:
        info("[PASS] h1<->h3 still reachable during h4 failure\n")

    info("\n########## REGRESSION : RECOVERY  ##########\n")
    info(">>> Bringing link h4 <-> s1 back UP\n")
    net.configLinkStatus('s1', 'h4', 'up')
    time.sleep(3)

    loss = net.pingAll()
    if loss == 0:
        info("[PASS] Full connectivity restored (regression OK)\n")
    else:
        info("[FAIL] Regression failed, loss=%s%%\n" % loss)

    info("\n>>> Final flow table on s1:\n")
    info(s1.cmd('ovs-ofctl dump-flows s1') + "\n")

    info("\n########## ALL SCENARIOS COMPLETE  ##########\n")
    info("Check /tmp/traffic_monitor_report.log for periodic stats reports\n")

    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    run_tests()
