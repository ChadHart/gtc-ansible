import asyncio
import ipaddress
from asyncio.subprocess import PIPE

async def _run(cmd: list[str], timeout: int = 10):
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return 1, "", "Timeout"
    return proc.returncode, stdout.decode().strip(), stderr.decode().strip()

async def scan_networks():
    rc, out, _ = await _run(["nmcli", "-t", "-f", "SSID,SIGNAL", "device", "wifi", "list"])
    nets = []
    for line in out.splitlines():
        ssid, sig = (line.split(":") + ["0"])[:2]
        if ssid:
            nets.append({"ssid": ssid, "signal": int(sig)})
    return nets

async def connect_network(ssid: str, password: str):
    cmd = ["sudo", "nmcli", "device", "wifi", "connect", ssid]
    if password:
        cmd += ["password", password]
    rc, out, err = await _run(cmd, 30)
    ok = rc == 0
    return ok, out if ok else err

async def get_connectivity():
    rc, _, _ = await _run(["nmcli", "-t", "-f", "CONNECTIVITY", "general"])
    return "full" in _.lower() if rc == 0 else False

async def get_ip_address():
    rc, out, _ = await _run(["hostname", "-I"])
    ips = [i for i in out.split() if i and not i.startswith("127.")]
    for ip in ips:
        try:
            if ipaddress.ip_address(ip).is_private:
                return ip
        except ValueError:
            continue
    return ips[0] if ips else None
