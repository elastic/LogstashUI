# SNMP Field Reference

Organized by data domain. Use this to find the canonical field name, source MIB, and OID before adding new fields so your data stays consistent with existing schema.

GET scalar fields have no table prefix. Table fields are written as `<table>.<field>`.

---

- [System Identity](#system-identity)
- [System Metrics](#system-metrics)
- [Network Interfaces](#network-interfaces)
- [RMON (Interface Error Statistics)](#rmon-interface-error-statistics)
- [IP & Addressing](#ip--addressing)
- [ARP](#arp)
- [Network Discovery — LLDP](#network-discovery--lldp)
- [Network Discovery — CDP](#network-discovery--cdp)
- [Layer 2 — MAC Table](#layer-2--mac-table)
- [Routing — BGP](#routing--bgp)
- [Routing — OSPF](#routing--ospf)
- [Physical Sensors](#physical-sensors)
- [Server Hardware — CPU](#server-hardware--cpu)
- [Server Hardware — Memory](#server-hardware--memory)
- [Server Hardware — Fans](#server-hardware--fans)
- [Server Hardware — Power Supply](#server-hardware--power-supply)
- [Server Hardware — RAID Controller](#server-hardware--raid-controller)
- [UPS / Power](#ups--power)
- [Storage Volumes](#storage-volumes)
- [Fibre Channel — Ports](#fibre-channel--ports)
- [Fibre Channel — Name Server](#fibre-channel--name-server)
- [Printers](#printers)

---

## System Identity

Standard device identity fields present on virtually all SNMP-capable devices. Source: **SNMPv2-MIB**.

| Field | OID | MIB | Description |
|---|---|---|---|
| `observer.sys_descr` | `1.3.6.1.2.1.1.1.0` | SNMPv2-MIB | Full hardware/software description string |
| `observer.object_id` | `1.3.6.1.2.1.1.2.0` | SNMPv2-MIB | Vendor-assigned OID identifying device type |
| `host.name` | `1.3.6.1.2.1.1.5.0` | SNMPv2-MIB | Configured hostname |
| `host.uptime` | `1.3.6.1.2.1.1.3.0` | SNMPv2-MIB | Time since last reboot (hundredths of a second) |
| `host.location` | `1.3.6.1.2.1.1.6.0` | SNMPv2-MIB | Configured physical location string |
| `host.contact` | `1.3.6.1.2.1.1.4.0` | SNMPv2-MIB | Configured admin contact string |

Device-specific identity fields shared across vendor profiles (OIDs vary per vendor):

| Field | Description |
|---|---|
| `observer.model` | Device model name |
| `observer.serial_number` | Hardware serial number |
| `observer.firmware_version` | Active firmware/software version |
| `observer.mac_address` | Chassis/management MAC address |
| `observer.chipset` | Chipset identifier |
| `observer.product_id` | Vendor product ID |
| `observer.system_status` | Device-reported overall system readiness state |

---

## System Metrics

CPU, memory, and load fields. Standard source is **UCD-SNMP-MIB** (Net-SNMP, Linux/BSD). Vendor devices expose equivalent fields under their own enterprise OIDs.

| Field | OID | MIB | Description |
|---|---|---|---|
| `system.cpu.total.norm.pct` | `1.3.6.1.4.1.2021.11.*` | UCD-SNMP-MIB | Normalized CPU utilization (0–1). Derived from raw counters or vendor scalar — divide raw vendor percentages by 100 |
| `system.cpu.raw.user` | `1.3.6.1.4.1.2021.11.50.0` | UCD-SNMP-MIB | Raw CPU ticks spent in user mode |
| `system.cpu.raw.nice` | `1.3.6.1.4.1.2021.11.51.0` | UCD-SNMP-MIB | Raw CPU ticks spent in nice (low-priority user) mode |
| `system.cpu.raw.system` | `1.3.6.1.4.1.2021.11.52.0` | UCD-SNMP-MIB | Raw CPU ticks spent in kernel/system mode |
| `system.cpu.raw.idle` | `1.3.6.1.4.1.2021.11.53.0` | UCD-SNMP-MIB | Raw CPU ticks spent idle |
| `system.cpu.raw.wait` | `1.3.6.1.4.1.2021.11.54.0` | UCD-SNMP-MIB | Raw CPU ticks spent waiting on I/O |
| `system.cpu.raw.kernel` | `1.3.6.1.4.1.2021.11.55.0` | UCD-SNMP-MIB | Raw CPU ticks spent in kernel interrupt context |
| `system.cpu.raw.interrupt` | `1.3.6.1.4.1.2021.11.56.0` | UCD-SNMP-MIB | Raw CPU ticks spent handling hardware interrupts |
| `system.cpu.num_cpus` | `1.3.6.1.4.1.2021.11.67.0` | UCD-SNMP-MIB | Number of CPU cores |
| `system.load.1` | `1.3.6.1.4.1.2021.10.1.3.1` | UCD-SNMP-MIB | 1-minute load average |
| `system.load.5` | `1.3.6.1.4.1.2021.10.1.3.2` | UCD-SNMP-MIB | 5-minute load average |
| `system.load.15` | `1.3.6.1.4.1.2021.10.1.3.3` | UCD-SNMP-MIB | 15-minute load average |
| `system.memory.actual.total.kb` | `1.3.6.1.4.1.2021.4.5.0` | UCD-SNMP-MIB | Total physical RAM in KB |
| `system.memory.actual.available.kb` | `1.3.6.1.4.1.2021.4.6.0` | UCD-SNMP-MIB | Available (free + reclaimable) RAM in KB |
| `system.memory.actual.free.kb` | `1.3.6.1.4.1.2021.4.11.0` | UCD-SNMP-MIB | Truly free (unallocated) RAM in KB |
| `system.memory.actual.cached.kb` | `1.3.6.1.4.1.2021.4.15.0` | UCD-SNMP-MIB | RAM used for disk cache in KB |
| `system.memory.actual.total.bytes` | vendor | — | Total RAM in bytes (vendor devices) |
| `system.memory.actual.used.bytes` | vendor | — | Used RAM in bytes (vendor devices) |
| `system.memory.actual.free.bytes` | vendor | — | Free RAM in bytes (vendor devices) |
| `system.memory.actual.used.pct` | derived | — | Memory utilization (0–1). Always derived via normalizer |
| `system.memory.actual.free.pct` | derived | — | Memory free ratio (0–1). Always derived via normalizer |
| `system.memory.total` | derived | — | Total memory computed from used + free when no direct OID exists |

---

## Network Interfaces

Per-interface counters and state. Table: `interface`. Source: **IF-MIB** (`ifTable` and `ifXTable`).

| Field | OID | MIB | Description |
|---|---|---|---|
| `interface.index` | `1.3.6.1.2.1.2.2.1.1` | IF-MIB | Interface index (ifIndex) |
| `interface.name` | `1.3.6.1.2.1.2.2.1.2` | IF-MIB | Interface description string (ifDescr) |
| `interface.alt_name` | `1.3.6.1.2.1.31.1.1.1.1` | IF-MIB | Shorter interface name (ifName from ifXTable) |
| `interface.alias` | `1.3.6.1.2.1.31.1.1.1.18` | IF-MIB | Operator-configured alias (ifAlias) |
| `interface.type` | `1.3.6.1.2.1.2.2.1.3` | IF-MIB | Interface type enum (ethernetCsmacd, etc.) |
| `interface.status.admin` | `1.3.6.1.2.1.2.2.1.7` | IF-MIB | Admin state: 1=up, 2=down, 3=testing |
| `interface.status.oper` | `1.3.6.1.2.1.2.2.1.8` | IF-MIB | Operational state: 1=up, 2=down |
| `interface.speed` | `1.3.6.1.2.1.2.2.1.5` | IF-MIB | Interface speed in bps (ifSpeed, 32-bit) |
| `interface.speed_high_mbps` | `1.3.6.1.2.1.31.1.1.1.15` | IF-MIB | Interface speed in Mbps (ifHighSpeed, 64-bit) |
| `interface.mac` | `1.3.6.1.2.1.2.2.1.6` | IF-MIB | Interface MAC address |
| `interface.mtu` | `1.3.6.1.2.1.2.2.1.4` | IF-MIB | MTU in bytes |
| `interface.last_change` | `1.3.6.1.2.1.2.2.1.9` | IF-MIB | Uptime timestamp of last state change |
| `interface.vlan_id` | `1.3.6.1.2.1.17.7.1.4.5.1.1` | Q-BRIDGE-MIB | VLAN ID assigned to interface |
| `interface.traffic.in.bytes` | `1.3.6.1.2.1.31.1.1.1.6` | IF-MIB | Inbound octets (64-bit counter) |
| `interface.traffic.out.bytes` | `1.3.6.1.2.1.31.1.1.1.10` | IF-MIB | Outbound octets (64-bit counter) |
| `interface.traffic.in.unicast_packets` | `1.3.6.1.2.1.31.1.1.1.7` | IF-MIB | Inbound unicast packets |
| `interface.traffic.out.unicast_packets` | `1.3.6.1.2.1.31.1.1.1.11` | IF-MIB | Outbound unicast packets |
| `interface.traffic.in.multicast_packets` | `1.3.6.1.2.1.31.1.1.1.8` | IF-MIB | Inbound multicast packets |
| `interface.traffic.out.multicast_packets` | `1.3.6.1.2.1.31.1.1.1.12` | IF-MIB | Outbound multicast packets |
| `interface.traffic.in.broadcast_packets` | `1.3.6.1.2.1.31.1.1.1.9` | IF-MIB | Inbound broadcast packets |
| `interface.traffic.out.broadcast_packets` | `1.3.6.1.2.1.31.1.1.1.13` | IF-MIB | Outbound broadcast packets |
| `interface.traffic.in.errors` | `1.3.6.1.2.1.2.2.1.14` | IF-MIB | Inbound packets with errors |
| `interface.traffic.out.errors` | `1.3.6.1.2.1.2.2.1.20` | IF-MIB | Outbound packets with errors |
| `interface.traffic.in.discards` | `1.3.6.1.2.1.2.2.1.13` | IF-MIB | Inbound packets dropped (no buffer) |
| `interface.traffic.out.discards` | `1.3.6.1.2.1.2.2.1.19` | IF-MIB | Outbound packets dropped (no buffer) |

---

## RMON (Interface Error Statistics)

Extended per-port Ethernet stats. Table: `interface` (RMON). Supplements IF-MIB with detailed error breakdowns and packet-size histograms. Source: **RMON-MIB**.

| Field | OID | MIB | Description |
|---|---|---|---|
| `interface.data_source` | `1.3.6.1.2.1.16.1.1.1.2` | RMON-MIB | OID pointer to the monitored interface |
| `interface.traffic.total.bytes` | `1.3.6.1.2.1.16.1.1.1.4` | RMON-MIB | Total octets received (including errors) |
| `interface.traffic.total.packets` | `1.3.6.1.2.1.16.1.1.1.5` | RMON-MIB | Total frames received |
| `interface.traffic.total.broadcast_packets` | `1.3.6.1.2.1.16.1.1.1.6` | RMON-MIB | Good broadcast frames received |
| `interface.traffic.total.multicast_packets` | `1.3.6.1.2.1.16.1.1.1.7` | RMON-MIB | Good multicast frames received |
| `interface.traffic.total.drop_events` | `1.3.6.1.2.1.16.1.1.1.3` | RMON-MIB | Events where packets were dropped due to lack of resources |
| `interface.traffic.total.errors_crc_align` | `1.3.6.1.2.1.16.1.1.1.8` | RMON-MIB | Frames with bad CRC or alignment errors |
| `interface.traffic.total.errors_undersize` | `1.3.6.1.2.1.16.1.1.1.9` | RMON-MIB | Frames shorter than 64 bytes with valid CRC |
| `interface.traffic.total.errors_oversize` | `1.3.6.1.2.1.16.1.1.1.10` | RMON-MIB | Frames longer than 1518 bytes with valid CRC |
| `interface.traffic.total.errors_fragments` | `1.3.6.1.2.1.16.1.1.1.11` | RMON-MIB | Frames shorter than 64 bytes with invalid CRC |
| `interface.traffic.total.errors_jabbers` | `1.3.6.1.2.1.16.1.1.1.12` | RMON-MIB | Frames longer than 1518 bytes with invalid CRC |
| `interface.traffic.total.errors_collisions` | `1.3.6.1.2.1.16.1.1.1.13` | RMON-MIB | Collision events detected |
| `interface.traffic.total.pkts_64` | `1.3.6.1.2.1.16.1.1.1.14` | RMON-MIB | Frames of exactly 64 bytes |
| `interface.traffic.total.pkts_65_127` | `1.3.6.1.2.1.16.1.1.1.15` | RMON-MIB | Frames 65–127 bytes |
| `interface.traffic.total.pkts_128_255` | `1.3.6.1.2.1.16.1.1.1.16` | RMON-MIB | Frames 128–255 bytes |
| `interface.traffic.total.pkts_256_511` | `1.3.6.1.2.1.16.1.1.1.17` | RMON-MIB | Frames 256–511 bytes |
| `interface.traffic.total.pkts_512_1023` | `1.3.6.1.2.1.16.1.1.1.18` | RMON-MIB | Frames 512–1023 bytes |
| `interface.traffic.total.pkts_1024_1518` | `1.3.6.1.2.1.16.1.1.1.19` | RMON-MIB | Frames 1024–1518 bytes |

---

## IP & Addressing

IP address table. Table: `ip_addr`. Source: **IP-MIB**.

| Field | OID | MIB | Description |
|---|---|---|---|
| `ip_addr.address` | `1.3.6.1.2.1.4.20.1.1` | IP-MIB | IP address assigned to this entry |
| `ip_addr.if_index` | `1.3.6.1.2.1.4.20.1.2` | IP-MIB | ifIndex of the interface this address is bound to |
| `ip_addr.netmask` | `1.3.6.1.2.1.4.20.1.3` | IP-MIB | Subnet mask for this address |

---

## ARP

ARP forwarding table. Table: `arp`. Source: **IP-MIB**. Can produce high data volumes on large networks.

| Field | OID | MIB | Description |
|---|---|---|---|
| `arp.interface_index` | `1.3.6.1.2.1.4.22.1.1` | IP-MIB | ifIndex of the interface this ARP entry was learned on |
| `arp.mac_addr` | `1.3.6.1.2.1.4.22.1.2` | IP-MIB | MAC address of the remote host |
| `arp.ip_addr` | `1.3.6.1.2.1.4.22.1.3` | IP-MIB | IP address of the remote host |

---

## Network Discovery — LLDP

LLDP local device info and neighbor table. Source: **LLDP-MIB** (IEEE 802.1AB).

**GET scalars:**

| Field | OID | MIB | Description |
|---|---|---|---|
| `network.local.chassis_id_subtype` | `1.0.8802.1.1.2.1.3.1.0` | LLDP-MIB | Encoding type of the local chassis ID |
| `network.local.chassis_id` | `1.0.8802.1.1.2.1.3.2.0` | LLDP-MIB | Local chassis identifier |
| `network.local.capabilities_supported` | `1.0.8802.1.1.2.1.3.5.0` | LLDP-MIB | Bitmask of capabilities this device supports |
| `network.local.capabilities_enabled` | `1.0.8802.1.1.2.1.3.6.0` | LLDP-MIB | Bitmask of capabilities currently enabled |
| `network.discovery.last_change` | `1.0.8802.1.1.2.1.2.1.0` | LLDP-MIB | Uptime when the neighbor table last changed |
| `network.discovery.inserts` | `1.0.8802.1.1.2.1.2.2.0` | LLDP-MIB | Number of entries added to the neighbor table |
| `network.discovery.deletes` | `1.0.8802.1.1.2.1.2.3.0` | LLDP-MIB | Number of entries deleted from the neighbor table |
| `network.discovery.drops` | `1.0.8802.1.1.2.1.2.4.0` | LLDP-MIB | Neighbor entries dropped due to resource limits |
| `network.discovery.ageouts` | `1.0.8802.1.1.2.1.2.5.0` | LLDP-MIB | Neighbor entries that expired via TTL |

**Table: `network.local_port`** — one row per local port advertising LLDP:

| Field | OID | MIB | Description |
|---|---|---|---|
| `network.local_port.index` | `1.0.8802.1.1.2.1.3.7.1.1` | LLDP-MIB | Local port index |
| `network.local_port.id_subtype` | `1.0.8802.1.1.2.1.3.7.1.2` | LLDP-MIB | Encoding type of the port ID |
| `network.local_port.id` | `1.0.8802.1.1.2.1.3.7.1.3` | LLDP-MIB | Port identifier value |
| `network.local_port.description` | `1.0.8802.1.1.2.1.3.7.1.4` | LLDP-MIB | Port description string |

**Table: `network.neighbor`** — one row per discovered neighbor:

| Field | OID | MIB | Description |
|---|---|---|---|
| `network.neighbor.local_interface.index` | `1.0.8802.1.1.2.1.4.1.1.2` | LLDP-MIB | Local ifIndex where this neighbor was seen |
| `network.neighbor.index` | `1.0.8802.1.1.2.1.4.1.1.3` | LLDP-MIB | Neighbor table entry index |
| `network.neighbor.chassis_id_subtype` | `1.0.8802.1.1.2.1.4.1.1.4` | LLDP-MIB | Encoding type of neighbor's chassis ID |
| `network.neighbor.chassis_id` | `1.0.8802.1.1.2.1.4.1.1.5` | LLDP-MIB | Neighbor chassis identifier |
| `network.neighbor.port_id_subtype` | `1.0.8802.1.1.2.1.4.1.1.6` | LLDP-MIB | Encoding type of neighbor's port ID |
| `network.neighbor.port` | `1.0.8802.1.1.2.1.4.1.1.7` | LLDP-MIB | Neighbor port identifier |
| `network.neighbor.port_description` | `1.0.8802.1.1.2.1.4.1.1.8` | LLDP-MIB | Neighbor port description |
| `network.neighbor.device_id` | `1.0.8802.1.1.2.1.4.1.1.9` | LLDP-MIB | Neighbor system name (device ID) |
| `network.neighbor.platform` | `1.0.8802.1.1.2.1.4.1.1.10` | LLDP-MIB | Neighbor system description |
| `network.neighbor.capabilities_supported` | `1.0.8802.1.1.2.1.4.1.1.11` | LLDP-MIB | Bitmask of capabilities the neighbor supports |
| `network.neighbor.capabilities` | `1.0.8802.1.1.2.1.4.1.1.12` | LLDP-MIB | Bitmask of capabilities the neighbor has enabled |

**Table: `network.neighbor_address`** — management addresses for neighbors:

| Field | OID | MIB | Description |
|---|---|---|---|
| `network.neighbor_address.addr_subtype` | `1.0.8802.1.1.2.1.4.2.1.1` | LLDP-MIB | Address type (IPv4, IPv6, etc.) |
| `network.neighbor_address.address` | `1.0.8802.1.1.2.1.4.2.1.2` | LLDP-MIB | Management IP address of the neighbor |
| `network.neighbor_address.if_subtype` | `1.0.8802.1.1.2.1.4.2.1.3` | LLDP-MIB | Interface numbering subtype |
| `network.neighbor_address.if_id` | `1.0.8802.1.1.2.1.4.2.1.4` | LLDP-MIB | Interface number the management address is reachable via |
| `network.neighbor_address.object_id` | `1.0.8802.1.1.2.1.4.2.1.5` | LLDP-MIB | OID of the neighbor's management object |

---

## Network Discovery — CDP

Cisco Discovery Protocol. Cisco-proprietary equivalent of LLDP. Source: **CISCO-CDP-MIB**.

**GET scalars:**

| Field | OID | MIB | Description |
|---|---|---|---|
| `network.discovery.cdp_enabled` | `1.3.6.1.4.1.9.9.23.1.3.1` | CISCO-CDP-MIB | Whether CDP is globally enabled on the device |
| `network.discovery.last_change` | `1.3.6.1.4.1.9.9.23.1.3.5` | CISCO-CDP-MIB | Uptime when the neighbor table last changed |

**Table: `network.neighbor`:**

| Field | OID | MIB | Description |
|---|---|---|---|
| `network.neighbor.local_interface.index` | `1.3.6.1.4.1.9.9.23.1.2.1.1.1` | CISCO-CDP-MIB | Local ifIndex where this neighbor was seen |
| `network.neighbor.address` | `1.3.6.1.4.1.9.9.23.1.2.1.1.4` | CISCO-CDP-MIB | Neighbor management IP address |
| `network.neighbor.version` | `1.3.6.1.4.1.9.9.23.1.2.1.1.5` | CISCO-CDP-MIB | Neighbor IOS / software version string |
| `network.neighbor.device_id` | `1.3.6.1.4.1.9.9.23.1.2.1.1.6` | CISCO-CDP-MIB | Neighbor device ID (usually hostname) |
| `network.neighbor.port` | `1.3.6.1.4.1.9.9.23.1.2.1.1.7` | CISCO-CDP-MIB | Neighbor port the connection is on |
| `network.neighbor.platform` | `1.3.6.1.4.1.9.9.23.1.2.1.1.8` | CISCO-CDP-MIB | Neighbor hardware platform string |
| `network.neighbor.capabilities` | `1.3.6.1.4.1.9.9.23.1.2.1.1.9` | CISCO-CDP-MIB | Bitmask of neighbor capabilities |

---

## Layer 2 — MAC Table

Forwarding database (FDB). Table: `mac_table`. Source: **BRIDGE-MIB** (RFC 1493). Can produce high data volumes on large networks.

| Field | OID | MIB | Description |
|---|---|---|---|
| `mac_table.mac_addr` | `1.3.6.1.2.1.17.4.3.1.1` | BRIDGE-MIB | Learned MAC address |
| `mac_table.port_index` | `1.3.6.1.2.1.17.4.3.1.2` | BRIDGE-MIB | Bridge port number this MAC was learned on |
| `mac_table.status` | `1.3.6.1.2.1.17.4.3.1.3` | BRIDGE-MIB | Entry status: 1=learned, 2=invalid, 3=self, 4=mgmt |

---

## Routing — BGP

BGP peer session state and update counters. Source: **BGP4-MIB** (RFC 1657).

**GET scalar:**

| Field | OID | MIB | Description |
|---|---|---|---|
| `bgp_peer.local_asn` | `1.3.6.1.2.1.15.2` | BGP4-MIB | Local autonomous system number |

**Table: `bgp_peer`:**

| Field | OID | MIB | Description |
|---|---|---|---|
| `bgp_peer.peer_state` | `1.3.6.1.2.1.15.3.1.2` | BGP4-MIB | Session state: 1=idle … 6=established |
| `bgp_peer.remote_ip` | `1.3.6.1.2.1.15.3.1.7` | BGP4-MIB | Remote peer IP address |
| `bgp_peer.remote_asn` | `1.3.6.1.2.1.15.3.1.9` | BGP4-MIB | Remote peer autonomous system number |
| `bgp_peer.in_updates` | `1.3.6.1.2.1.15.3.1.10` | BGP4-MIB | UPDATE messages received from this peer |
| `bgp_peer.out_updates` | `1.3.6.1.2.1.15.3.1.11` | BGP4-MIB | UPDATE messages sent to this peer |
| `bgp_peer.uptime_seconds` | `1.3.6.1.2.1.15.3.1.16` | BGP4-MIB | Time this session has been in Established state |

---

## Routing — OSPF

OSPF neighbor adjacency table. Table: `ospf_neighbor`. Source: **OSPF-MIB** (RFC 1850).

| Field | OID | MIB | Description |
|---|---|---|---|
| `ospf_neighbor.neighbor_ip` | `1.3.6.1.2.1.14.10.1.1` | OSPF-MIB | IP address of the OSPF neighbor |
| `ospf_neighbor.router_id` | `1.3.6.1.2.1.14.10.1.3` | OSPF-MIB | Router ID of the OSPF neighbor |
| `ospf_neighbor.priority` | `1.3.6.1.2.1.14.10.1.5` | OSPF-MIB | Neighbor DR election priority |
| `ospf_neighbor.state` | `1.3.6.1.2.1.14.10.1.6` | OSPF-MIB | Adjacency state: 1=down … 8=full |
| `ospf_neighbor.retrans_count` | `1.3.6.1.2.1.14.10.1.7` | OSPF-MIB | Number of LSAs waiting to be acknowledged |

---

## Physical Sensors

Generic physical sensor readings (temperature, fan speed, voltage, current, power). Tables: `component.sensor` and `component`. Source: **ENTITY-SENSOR-MIB** (RFC 3433) + **ENTITY-MIB** (RFC 2737).

| Field | OID | MIB | Description |
|---|---|---|---|
| `component.sensor.type` | `1.3.6.1.2.1.99.1.1.1.1` | ENTITY-SENSOR-MIB | Sensor type enum: 1=other, 3=voltsAC, 5=amperes, 8=celsius, 10=rpm, 12=watts |
| `component.sensor.scale` | `1.3.6.1.2.1.99.1.1.1.2` | ENTITY-SENSOR-MIB | Power-of-10 scale factor to apply to `value` |
| `component.sensor.precision` | `1.3.6.1.2.1.99.1.1.1.3` | ENTITY-SENSOR-MIB | Number of decimal digits of precision |
| `component.sensor.value` | `1.3.6.1.2.1.99.1.1.1.4` | ENTITY-SENSOR-MIB | Raw sensor reading (apply `scale` and `precision` to get true value) |
| `component.sensor.oper_status` | `1.3.6.1.2.1.99.1.1.1.5` | ENTITY-SENSOR-MIB | Sensor validity: 1=ok, 2=unavailable, 3=nonoperational |
| `component.sensor.units_display` | `1.3.6.1.2.1.99.1.1.1.6` | ENTITY-SENSOR-MIB | Human-readable units string (e.g. "Celsius", "RPM") |
| `component.name` | `1.3.6.1.2.1.47.1.1.1.1.7` | ENTITY-MIB | Human-readable name for the physical component (joined by entPhysicalIndex) |

---

## Server Hardware — CPU

CPU status per socket. Table: `component.cpu`.

| Field | OID | MIB | Description |
|---|---|---|---|
| `system.status` | `1.3.6.1.4.1.674.10892.5.2.1.0` | iDRAC-MIB | Overall chassis health rollup (GET scalar) |
| `component.cpu.id` | `1.3.6.1.4.1.674.10892.5.4.1100.30.1.2` | iDRAC-MIB | Processor index within chassis |
| `component.cpu.chassis_id` | `1.3.6.1.4.1.674.10892.5.4.1100.30.1.1` | iDRAC-MIB | Chassis containing this processor |
| `component.cpu.status` | `1.3.6.1.4.1.674.10892.5.4.1100.30.1.5` | iDRAC-MIB | Processor state: 1=other, 2=unknown, 3=ok, 4=nonCritical, 5=critical, 6=nonRecoverable |

---

## Server Hardware — Memory

DIMM slot state and capacity. Table: `component.memory`.

| Field | OID | MIB | Description |
|---|---|---|---|
| `component.memory.index` | `1.3.6.1.4.1.674.10892.5.4.1100.50.1.1` | iDRAC-MIB | DIMM slot index |
| `component.memory.location` | `1.3.6.1.4.1.674.10892.5.4.1100.50.1.5` | iDRAC-MIB | Physical slot label (e.g. "DIMM.Socket.A1") |
| `component.memory.state` | `1.3.6.1.4.1.674.10892.5.4.1100.50.1.4` | iDRAC-MIB | DIMM state enum (ok, degraded, failed, etc.) |
| `component.memory.size.mb` | `1.3.6.1.4.1.674.10892.5.4.1100.50.1.14` | iDRAC-MIB | DIMM capacity in MB |

---

## Server Hardware — Fans

Fan speed and state. Table: `component.fan`. OIDs shown are iDRAC; Cisco uses CISCO-ENVMON-MIB for state-only entries.

| Field | OID | MIB | Description |
|---|---|---|---|
| `component.fan.index` | `1.3.6.1.4.1.674.10892.5.4.700.12.1.1` | iDRAC-MIB | Fan slot index |
| `component.fan.description` | `1.3.6.1.4.1.674.10892.5.4.700.12.1.7` | iDRAC-MIB | Fan slot label |
| `component.fan.state` | `1.3.6.1.4.1.674.10892.5.4.700.12.1.5` | iDRAC-MIB | Fan state enum (ok, degraded, failed, etc.) |
| `component.fan.rpm` | `1.3.6.1.4.1.674.10892.5.4.700.12.1.6` | iDRAC-MIB | Current fan speed in RPM |

Cisco equivalent (state only, no RPM):

| Field | OID | MIB | Description |
|---|---|---|---|
| `component.fan.description` | `1.3.6.1.4.1.9.9.13.1.4.1.2` | CISCO-ENVMON-MIB | Fan tray label |
| `component.fan.state` | `1.3.6.1.4.1.9.9.13.1.4.1.3` | CISCO-ENVMON-MIB | Fan state: 1=normal, 2=warning, 3=critical, 4=shutdown, 5=notPresent |

---

## Server Hardware — Power Supply

Power supply slot state. Table: `component.power_supply`.

| Field | OID | MIB | Description |
|---|---|---|---|
| `component.power_supply.index` | `1.3.6.1.4.1.674.10892.5.4.600.12.1.1` | iDRAC-MIB | PSU slot index |
| `component.power_supply.location` | `1.3.6.1.4.1.674.10892.5.4.600.12.1.7` | iDRAC-MIB | PSU slot label |
| `component.power_supply.state` | `1.3.6.1.4.1.674.10892.5.4.600.12.1.5` | iDRAC-MIB | PSU state enum (ok, degraded, failed, absent, etc.) |

---

## Server Hardware — RAID Controller

RAID controller inventory and state. Table: `component.raid_controller`.

| Field | OID | MIB | Description |
|---|---|---|---|
| `component.raid_controller.index` | `1.3.6.1.4.1.674.10892.5.4.300.50.1.1` | iDRAC-MIB | Controller index |
| `component.raid_controller.name` | `1.3.6.1.4.1.674.10892.5.4.300.50.1.5` | iDRAC-MIB | Controller model name |
| `component.raid_controller.state` | `1.3.6.1.4.1.674.10892.5.4.300.50.1.4` | iDRAC-MIB | Controller state enum |

---

## UPS / Power

Battery, input/output phase, and environment data for UPS devices. Source: **XUPS-MIB** (Eaton/Powerware).

**GET scalars:**

| Field | OID | MIB | Description |
|---|---|---|---|
| `ups.battery.time_remaining_seconds` | `1.3.6.1.4.1.534.1.2.1.0` | XUPS-MIB | Estimated runtime remaining on battery in seconds |
| `ups.battery.voltage` | `1.3.6.1.4.1.534.1.2.2.0` | XUPS-MIB | Battery voltage (units per device config) |
| `ups.battery.current_amps` | `1.3.6.1.4.1.534.1.2.3.0` | XUPS-MIB | Battery current in amps |
| `ups.battery.capacity_pct` | `1.3.6.1.4.1.534.1.2.4.0` | XUPS-MIB | Battery charge level as percentage 0–100 |
| `ups.battery.status` | `1.3.6.1.4.1.534.1.2.5.0` | XUPS-MIB | Battery status enum (unknown, batteryNormal, batteryLow, etc.) |
| `ups.input.frequency_01hz` | `1.3.6.1.4.1.534.1.3.1.0` | XUPS-MIB | Input AC frequency in 0.1 Hz units |
| `ups.input.line_bads` | `1.3.6.1.4.1.534.1.3.2.0` | XUPS-MIB | Count of times input power was out of tolerance |
| `ups.input.num_phases` | `1.3.6.1.4.1.534.1.3.3.0` | XUPS-MIB | Number of input phases |
| `ups.input.source` | `1.3.6.1.4.1.534.1.3.5.0` | XUPS-MIB | Current input power source enum |
| `ups.output.num_phases` | `1.3.6.1.4.1.534.1.4.3.0` | XUPS-MIB | Number of output phases |
| `ups.output.source` | `1.3.6.1.4.1.534.1.4.5.0` | XUPS-MIB | Output source enum (normal, battery, bypass, etc.) |
| `ups.output.load_pct` | `1.3.6.1.4.1.534.1.4.6.0` | XUPS-MIB | Total output load as percentage of capacity |
| `ups.env.temperature_c` | `1.3.6.1.4.1.534.1.6.1.0` | XUPS-MIB | Ambient temperature at UPS in Celsius |
| `ups.env.humidity_pct` | `1.3.6.1.4.1.534.1.6.2.0` | XUPS-MIB | Ambient relative humidity percentage |
| `ups.alarms.present` | `1.3.6.1.4.1.534.1.7.1.0` | XUPS-MIB | Number of active alarms currently set |

**Table: `ups.input.phase`** — one row per input phase:

| Field | OID | MIB | Description |
|---|---|---|---|
| `ups.input.phase.index` | `1.3.6.1.4.1.534.1.3.4.1.1` | XUPS-MIB | Phase index |
| `ups.input.phase.voltage` | `1.3.6.1.4.1.534.1.3.4.1.2` | XUPS-MIB | Phase input voltage |
| `ups.input.phase.current` | `1.3.6.1.4.1.534.1.3.4.1.4` | XUPS-MIB | Phase input current in amps |
| `ups.input.phase.voltage_status` | `1.3.6.1.4.1.534.1.3.4.1.5` | XUPS-MIB | Per-phase voltage status enum |

**Table: `ups.output.phase`** — one row per output phase:

| Field | OID | MIB | Description |
|---|---|---|---|
| `ups.output.phase.index` | `1.3.6.1.4.1.534.1.4.4.1.1` | XUPS-MIB | Phase index |
| `ups.output.phase.voltage` | `1.3.6.1.4.1.534.1.4.4.1.2` | XUPS-MIB | Phase output voltage |
| `ups.output.phase.current` | `1.3.6.1.4.1.534.1.4.4.1.3` | XUPS-MIB | Phase output current in amps |
| `ups.output.phase.load` | `1.3.6.1.4.1.534.1.4.4.1.4` | XUPS-MIB | Per-phase load |
| `ups.output.phase.power` | `1.3.6.1.4.1.534.1.4.4.1.5` | XUPS-MIB | Per-phase output power in watts |

---

## Storage Volumes

Per-volume I/O, capacity, and latency histograms. Table: `component.volume`. Source: **NIMBLE-MIB** (HPE Nimble).

| Field | OID | MIB | Description |
|---|---|---|---|
| `component.volume.id` | `1.3.6.1.4.1.37447.1.2.1.2` | NIMBLE-MIB | Volume unique identifier |
| `component.volume.name` | `1.3.6.1.4.1.37447.1.2.1.3` | NIMBLE-MIB | Volume name |
| `component.volume.size.low` | `1.3.6.1.4.1.37447.1.2.1.4` | NIMBLE-MIB | Provisioned size low 32 bits |
| `component.volume.size.high` | `1.3.6.1.4.1.37447.1.2.1.5` | NIMBLE-MIB | Provisioned size high 32 bits |
| `component.volume.usage.low` | `1.3.6.1.4.1.37447.1.2.1.6` | NIMBLE-MIB | Space consumed by volume data low 32 bits |
| `component.volume.usage.high` | `1.3.6.1.4.1.37447.1.2.1.7` | NIMBLE-MIB | Space consumed by volume data high 32 bits |
| `component.volume.reserve.low` | `1.3.6.1.4.1.37447.1.2.1.8` | NIMBLE-MIB | Reserved space low 32 bits |
| `component.volume.reserve.high` | `1.3.6.1.4.1.37447.1.2.1.9` | NIMBLE-MIB | Reserved space high 32 bits |
| `component.volume.online` | `1.3.6.1.4.1.37447.1.2.1.10` | NIMBLE-MIB | Whether the volume is online |
| `component.volume.connections` | `1.3.6.1.4.1.37447.1.2.1.11` | NIMBLE-MIB | Number of active iSCSI connections |
| `component.volume.io.read.ops` | `1.3.6.1.4.1.37447.1.2.1.13` | NIMBLE-MIB | Total read I/O operations |
| `component.volume.io.read.time_us` | `1.3.6.1.4.1.37447.1.2.1.14` | NIMBLE-MIB | Cumulative read service time in microseconds |
| `component.volume.io.read.bytes` | `1.3.6.1.4.1.37447.1.2.1.15` | NIMBLE-MIB | Total bytes read |
| `component.volume.io.read.seq_ops` | `1.3.6.1.4.1.37447.1.2.1.16` | NIMBLE-MIB | Sequential read I/O operations |
| `component.volume.io.read.seq_bytes` | `1.3.6.1.4.1.37447.1.2.1.17` | NIMBLE-MIB | Bytes read sequentially |
| `component.volume.io.read.cache_hits` | `1.3.6.1.4.1.37447.1.2.1.18` | NIMBLE-MIB | Total read cache hits |
| `component.volume.io.read.cache_mem_hits` | `1.3.6.1.4.1.37447.1.2.1.19` | NIMBLE-MIB | Read hits served from DRAM cache |
| `component.volume.io.read.cache_ssd_hits` | `1.3.6.1.4.1.37447.1.2.1.20` | NIMBLE-MIB | Read hits served from SSD cache |
| `component.volume.io.read.latency.0us_100us` | `1.3.6.1.4.1.37447.1.2.1.21` | NIMBLE-MIB | Reads completing in < 100µs |
| `component.volume.io.read.latency.1ms_2ms` | `1.3.6.1.4.1.37447.1.2.1.25` | NIMBLE-MIB | Reads completing in 1–2ms |
| `component.volume.io.read.latency.5ms_10ms` | `1.3.6.1.4.1.37447.1.2.1.27` | NIMBLE-MIB | Reads completing in 5–10ms |
| `component.volume.io.read.latency.20ms_50ms` | `1.3.6.1.4.1.37447.1.2.1.29` | NIMBLE-MIB | Reads completing in 20–50ms |
| `component.volume.io.read.latency.500ms_max` | `1.3.6.1.4.1.37447.1.2.1.33` | NIMBLE-MIB | Reads completing in > 500ms |
| `component.volume.io.write.ops` | `1.3.6.1.4.1.37447.1.2.1.34` | NIMBLE-MIB | Total write I/O operations |
| `component.volume.io.write.time_us` | `1.3.6.1.4.1.37447.1.2.1.35` | NIMBLE-MIB | Cumulative write service time in microseconds |
| `component.volume.io.write.bytes` | `1.3.6.1.4.1.37447.1.2.1.36` | NIMBLE-MIB | Total bytes written |
| `component.volume.io.write.seq_ops` | `1.3.6.1.4.1.37447.1.2.1.37` | NIMBLE-MIB | Sequential write I/O operations |
| `component.volume.io.write.seq_bytes` | `1.3.6.1.4.1.37447.1.2.1.38` | NIMBLE-MIB | Bytes written sequentially |
| `component.volume.io.write.latency.0us_100us` | `1.3.6.1.4.1.37447.1.2.1.39` | NIMBLE-MIB | Writes completing in < 100µs |
| `component.volume.io.write.latency.1ms_2ms` | `1.3.6.1.4.1.37447.1.2.1.43` | NIMBLE-MIB | Writes completing in 1–2ms |
| `component.volume.io.write.latency.5ms_10ms` | `1.3.6.1.4.1.37447.1.2.1.45` | NIMBLE-MIB | Writes completing in 5–10ms |
| `component.volume.io.write.latency.20ms_50ms` | `1.3.6.1.4.1.37447.1.2.1.47` | NIMBLE-MIB | Writes completing in 20–50ms |
| `component.volume.io.write.latency.500ms_max` | `1.3.6.1.4.1.37447.1.2.1.51` | NIMBLE-MIB | Writes completing in > 500ms |
| `component.volume.disk.vol_used.low` | `1.3.6.1.4.1.37447.1.2.1.52` | NIMBLE-MIB | Disk space used by volume data low 32 bits |
| `component.volume.disk.vol_used.high` | `1.3.6.1.4.1.37447.1.2.1.53` | NIMBLE-MIB | Disk space used by volume data high 32 bits |
| `component.volume.disk.snap_used.low` | `1.3.6.1.4.1.37447.1.2.1.54` | NIMBLE-MIB | Disk space used by snapshots low 32 bits |
| `component.volume.disk.snap_used.high` | `1.3.6.1.4.1.37447.1.2.1.55` | NIMBLE-MIB | Disk space used by snapshots high 32 bits |

---

## Fibre Channel — Ports

Per-port FC traffic and error counters. Source: **SW-MIB** (Brocade).

**Table: `interface`** — FC port identity and traffic:

| Field | OID | MIB | Description |
|---|---|---|---|
| `interface.index` | `1.3.6.1.4.1.1588.2.1.1.1.6.2.1.1` | SW-MIB | Port index |
| `interface.name` | `1.3.6.1.4.1.1588.2.1.1.1.6.2.1.36` | SW-MIB | Port name string |
| `interface.speed` | `1.3.6.1.4.1.1588.2.1.1.1.6.2.1.35` | SW-MIB | Negotiated FC link speed |
| `interface.status.physical` | `1.3.6.1.4.1.1588.2.1.1.1.6.2.1.3` | SW-MIB | Physical port state enum |
| `interface.traffic.in.frames` | `1.3.6.1.4.1.1588.2.1.1.1.6.2.1.2` | SW-MIB | FC frames received |
| `interface.traffic.out.frames` | `1.3.6.1.4.1.1588.2.1.1.1.6.2.1.13` | SW-MIB | FC frames transmitted |

**Table: `fibre_channel`** — FC error counters (same index as `interface`):

| Field | OID | MIB | Description |
|---|---|---|---|
| `fibre_channel.index` | `1.3.6.1.4.1.1588.2.1.1.1.6.2.1.1` | SW-MIB | Port index |
| `fibre_channel.wwn` | `1.3.6.1.4.1.1588.2.1.1.1.6.2.1.34` | SW-MIB | Port World Wide Name |
| `fibre_channel.errors.in.crc` | `1.3.6.1.4.1.1588.2.1.1.1.6.2.1.4` | SW-MIB | Frames received with CRC errors |
| `fibre_channel.errors.in.invalid_words` | `1.3.6.1.4.1.1588.2.1.1.1.6.2.1.5` | SW-MIB | Invalid transmission words received |
| `fibre_channel.errors.link_failures` | `1.3.6.1.4.1.1588.2.1.1.1.6.2.1.6` | SW-MIB | Link failure count |
| `fibre_channel.errors.loss_of_signal` | `1.3.6.1.4.1.1588.2.1.1.1.6.2.1.7` | SW-MIB | Loss of signal events |
| `fibre_channel.errors.loss_of_sync` | `1.3.6.1.4.1.1588.2.1.1.1.6.2.1.8` | SW-MIB | Loss of sync events |
| `fibre_channel.errors.in.encoding_disparity` | `1.3.6.1.4.1.1588.2.1.1.1.6.2.1.9` | SW-MIB | Encoding disparity errors received |
| `fibre_channel.errors.out.link_resets` | `1.3.6.1.4.1.1588.2.1.1.1.6.2.1.10` | SW-MIB | Link reset primitives transmitted |

---

## Fibre Channel — Name Server

Local FC name server (fabric directory). Table: `fibre_channel_name_server`. Source: **SW-MIB** (Brocade).

| Field | OID | MIB | Description |
|---|---|---|---|
| `fibre_channel_name_server.index` | `1.3.6.1.4.1.1588.2.1.1.1.7.2.1.1` | SW-MIB | Name server entry index |
| `fibre_channel_name_server.fcid` | `1.3.6.1.4.1.1588.2.1.1.1.7.2.1.2` | SW-MIB | Fibre Channel ID (24-bit fabric address) |
| `fibre_channel_name_server.port.type` | `1.3.6.1.4.1.1588.2.1.1.1.7.2.1.3` | SW-MIB | Port type enum (N, NL, F, FL, E, etc.) |
| `fibre_channel_name_server.wwpn` | `1.3.6.1.4.1.1588.2.1.1.1.7.2.1.4` | SW-MIB | Port World Wide Name |
| `fibre_channel_name_server.port.description` | `1.3.6.1.4.1.1588.2.1.1.1.7.2.1.5` | SW-MIB | Port symbolic name |
| `fibre_channel_name_server.wwnn` | `1.3.6.1.4.1.1588.2.1.1.1.7.2.1.6` | SW-MIB | Node World Wide Name |
| `fibre_channel_name_server.node.description` | `1.3.6.1.4.1.1588.2.1.1.1.7.2.1.7` | SW-MIB | Node symbolic name |

---

## Printers

Toner, page counts, trays, covers, and alerts. Source: **Printer-MIB** (RFC 3805).

**GET scalars:**

| Field | OID | MIB | Description |
|---|---|---|---|
| `observer.model` | `1.3.6.1.2.1.43.5.1.1.16.1` | Printer-MIB | Printer model name |
| `observer.serial_number` | `1.3.6.1.2.1.43.5.1.1.17.1` | Printer-MIB | Printer serial number |

**Table: `printer.supply`** — one row per consumable (toner, drum, fuser, etc.):

| Field | OID | MIB | Description |
|---|---|---|---|
| `printer.supply.description` | `1.3.6.1.2.1.43.11.1.1.6` | Printer-MIB | Supply name (e.g. "Black Toner Cartridge") |
| `printer.supply.unit` | `1.3.6.1.2.1.43.11.1.1.7` | Printer-MIB | Unit of measure enum for `level` and `capacity_max` |
| `printer.supply.capacity_max` | `1.3.6.1.2.1.43.11.1.1.8` | Printer-MIB | Maximum capacity in `unit` units (-2 = unknown) |
| `printer.supply.level` | `1.3.6.1.2.1.43.11.1.1.9` | Printer-MIB | Current supply level (-3 = at least some remaining) |

**Table: `printer.marker`** — one row per print engine:

| Field | OID | MIB | Description |
|---|---|---|---|
| `printer.marker.pages_lifetime` | `1.3.6.1.2.1.43.10.2.1.4` | Printer-MIB | Total pages printed since manufacture |
| `printer.marker.pages_power_on` | `1.3.6.1.2.1.43.10.2.1.5` | Printer-MIB | Pages printed since last power-on |

**Table: `printer.tray`** — one row per paper input tray:

| Field | OID | MIB | Description |
|---|---|---|---|
| `printer.tray.name` | `1.3.6.1.2.1.43.8.2.1.13` | Printer-MIB | Tray name |
| `printer.tray.level` | `1.3.6.1.2.1.43.8.2.1.9` | Printer-MIB | Current paper level |
| `printer.tray.capacity_max` | `1.3.6.1.2.1.43.8.2.1.10` | Printer-MIB | Maximum tray capacity |

**Table: `printer.cover`** — one row per door/cover:

| Field | OID | MIB | Description |
|---|---|---|---|
| `printer.cover.description` | `1.3.6.1.2.1.43.6.1.1.2` | Printer-MIB | Cover name |
| `printer.cover.status` | `1.3.6.1.2.1.43.6.1.1.3` | Printer-MIB | Cover state: 1=other, 3=open, 4=closed |

**Table: `printer.alert`** — one row per active alert:

| Field | OID | MIB | Description |
|---|---|---|---|
| `printer.alert.code` | `1.3.6.1.2.1.43.15.1.1.2` | Printer-MIB | Alert code enum (jammed, tonerLow, offline, etc.) |
| `printer.alert.description` | `1.3.6.1.2.1.43.15.1.1.3` | Printer-MIB | Human-readable alert description |
