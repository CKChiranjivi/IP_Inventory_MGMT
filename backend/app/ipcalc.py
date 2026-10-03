"""IPv4 range calculation for VLAN creation (pure logic, no database)."""
import ipaddress
from dataclasses import dataclass, field

MIN_CIDR = 16
MAX_CIDR = 30


class PlanError(ValueError):
    """Raised when the network input is invalid."""


def _to_int(value: str, label: str) -> int:
    try:
        return int(ipaddress.IPv4Address(value.strip()))
    except ValueError as exc:
        raise PlanError(f"{label} '{value}' is not a valid IPv4 address") from exc


def _to_str(ip: int) -> str:
    return str(ipaddress.IPv4Address(ip))


@dataclass
class Plan:
    network: ipaddress.IPv4Network
    first_host: int          # first usable address (network + 1)
    last_host: int           # last usable address (broadcast - 1)
    gateway: int
    reserved: dict[int, str] = field(default_factory=dict)  # ip -> reason

    @property
    def range_start(self) -> int:
        return int(self.network.network_address)

    @property
    def range_end(self) -> int:
        return int(self.network.broadcast_address)

    @property
    def total_addresses(self) -> int:
        return self.network.num_addresses

    @property
    def usable(self) -> int:
        return self.last_host - self.first_host + 1

    def rows(self):
        """Yield (ip_int, status, reserved_reason) for every usable host."""
        for ip in range(self.first_host, self.last_host + 1):
            reason = self.reserved.get(ip)
            yield ip, ("reserved" if reason else "available"), reason

    def summary(self) -> dict:
        return {
            "network": f"{self.network.network_address}/{self.network.prefixlen}",
            "subnet_mask": str(self.network.netmask),
            "network_address": str(self.network.network_address),
            "broadcast_address": str(self.network.broadcast_address),
            "gateway": _to_str(self.gateway),
            "total_addresses": self.total_addresses,
            "usable_ips": self.usable,
            "reserved_count": len(self.reserved),
            "available_count": self.usable - len(self.reserved),
        }

    def preview_rows(self, head: int = 10, tail: int = 3) -> dict:
        """First/last rows for the preview screen (network/broadcast shown as info only)."""

        def fmt(ip: int) -> dict:
            reason = self.reserved.get(ip)
            return {
                "ip": _to_str(ip),
                "status": "Reserved" if reason else "Available",
                "type": reason or "Host",
            }

        head_end = min(self.first_host + head, self.last_host + 1)
        tail_start = max(self.last_host - tail + 1, head_end)
        return {
            "network_row": {"ip": str(self.network.network_address),
                            "status": "Not stored", "type": "Network"},
            "head": [fmt(ip) for ip in range(self.first_host, head_end)],
            "tail": [fmt(ip) for ip in range(tail_start, self.last_host + 1)],
            "truncated": tail_start > head_end,
            "broadcast_row": {"ip": str(self.network.broadcast_address),
                              "status": "Not stored", "type": "Broadcast"},
        }


def build_plan(network_address: str, cidr: int, gateway: str, reserved_ips=()) -> Plan:
    if not MIN_CIDR <= cidr <= MAX_CIDR:
        raise PlanError(f"CIDR must be between /{MIN_CIDR} and /{MAX_CIDR}")

    try:
        # strict=True rejects host bits, e.g. 10.10.20.5/24
        net = ipaddress.IPv4Network(f"{network_address.strip()}/{cidr}", strict=True)
    except ValueError as exc:
        raise PlanError(f"Invalid network: {exc}") from exc

    first = int(net.network_address) + 1
    last = int(net.broadcast_address) - 1

    def check_inside(ip: int, label: str) -> int:
        if not first <= ip <= last:
            raise PlanError(f"{label} {_to_str(ip)} is not a usable address in {net}")
        return ip

    gw = check_inside(_to_int(gateway, "Gateway"), "Gateway")
    reserved = {gw: "Gateway"}
    for raw in reserved_ips:
        ip = check_inside(_to_int(raw, "Reserved IP"), "Reserved IP")
        reserved.setdefault(ip, "Reserved")

    return Plan(network=net, first_host=first, last_host=last, gateway=gw, reserved=reserved)