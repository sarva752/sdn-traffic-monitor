#!/usr/bin/env python
# =============================================================================
#  topology.py  -  Mininet topology for SDN Traffic Monitoring project
# =============================================================================
#  Topology:  4 hosts  +  1 OpenFlow switch  +  remote POX controller
#
#         h1 ----\              /---- h3
#                 s1 (OF switch)
#         h2 ----/              \---- h4
#
#   Controller: POX running at 127.0.0.1:6633
# =============================================================================

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink


def build_network():
    info("*** Creating network with remote POX controller\n")
    net = Mininet(controller=RemoteController,
                  switch=OVSSwitch,
                  link=TCLink,
                  autoSetMacs=True)

    # -------------------------------------------------------------------------
    #  Controller (POX at localhost:6633)
    # -------------------------------------------------------------------------
    c0 = net.addController('c0',
                           controller=RemoteController,
                           ip='127.0.0.1',
                           port=6633)

    # -------------------------------------------------------------------------
    #  Switch
    # -------------------------------------------------------------------------
    s1 = net.addSwitch('s1', protocols='OpenFlow10')

    # -------------------------------------------------------------------------
    #  Hosts
    # -------------------------------------------------------------------------
    h1 = net.addHost('h1', ip='10.0.0.1/24')
    h2 = net.addHost('h2', ip='10.0.0.2/24')
    h3 = net.addHost('h3', ip='10.0.0.3/24')
    h4 = net.addHost('h4', ip='10.0.0.4/24')

    # -------------------------------------------------------------------------
    #  Links  (10 Mbps each, for iperf demos)
    # -------------------------------------------------------------------------
    net.addLink(h1, s1, bw=10)
    net.addLink(h2, s1, bw=10)
    net.addLink(h3, s1, bw=10)
    net.addLink(h4, s1, bw=10)

    info("*** Starting network\n")
    net.build()
    c0.start()
    s1.start([c0])

    info("*** Running CLI (type 'exit' to quit)\n")
    CLI(net)

    info("*** Stopping network\n")
    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    build_network()
