import asyncio
from backend.services.ssh_manager import get_ssh_manager
from backend.services.runtime_config import update_runtime_config

async def main():
    update_runtime_config(
        vm1_use_password_auth=True, vm1_ssh_password="12345678",
        vm2_use_password_auth=True, vm2_ssh_password="12345678",
        vm3_use_password_auth=True, vm3_ssh_password="1905"
    )
    ssh = get_ssh_manager()

    print("=== DUMPING PACKETS ON VM1 FOR VM3 WG ===")
    
    # Run tcpdump on VM1 in background
    dump_task = asyncio.create_task(
        ssh.run_vm1("sudo tcpdump -i tailscale0 udp port 51820 -n -c 10", check=False)
    )
    
    await asyncio.sleep(2)
    # Ping or wg-quick from VM3
    await ssh.run_vm3("sudo wg-quick down wg0; sudo wg-quick up wg0; ping -c 3 10.200.0.1", check=False)
    
    # Wait for tcpdump to finish
    try:
        res_dump = await asyncio.wait_for(dump_task, timeout=10)
        print("VM1 WG Tcpdump:\n", res_dump.stdout)
    except asyncio.TimeoutError:
        print("VM1 WG Tcpdump timed out (no packets?)")
        await ssh.run_vm1("sudo pkill -x tcpdump", check=False)

    print("\n=== DUMPING PACKETS ON VM1 FOR VM2 OVPN ===")
    
    # Run tcpdump for OpenVPN UDP
    dump_task2 = asyncio.create_task(
        ssh.run_vm1("sudo tcpdump -i tailscale0 udp port 1194 -n -c 10", check=False)
    )
    
    await asyncio.sleep(2)
    # Start OpenVPN from VM2
    await ssh.run_vm2("sudo pkill -x openvpn; sudo /usr/sbin/openvpn --config /etc/openvpn/client/client-udp.conf --daemon", check=False)
    
    try:
        res_dump2 = await asyncio.wait_for(dump_task2, timeout=10)
        print("VM1 OVPN Tcpdump:\n", res_dump2.stdout)
    except asyncio.TimeoutError:
        print("VM1 OVPN Tcpdump timed out (no packets?)")
        await ssh.run_vm1("sudo pkill -x tcpdump", check=False)

    await ssh.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
