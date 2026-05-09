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

    print("=== VM1 FIREWALL ===")
    res_fw = await ssh.run_vm1("sudo ufw status; sudo iptables -L -n | grep -E '51820|1194'", check=False)
    print("VM1 fw:\n", res_fw.stdout)

    print("\n=== VM2 OPENVPN UDP TEST (Manual Lifecycle) ===")
    # stop
    await ssh.run_vm1("sudo systemctl stop openvpn-server@server-udp", check=False)
    await ssh.run_vm2("sudo pkill -x openvpn", check=False)
    
    # start server
    print("Starting server...")
    res_sv = await ssh.run_vm1("sudo systemctl start openvpn-server@server-udp", check=False)
    print("VM1 start exit:", res_sv.exit_status, "err:", res_sv.stderr)
    await asyncio.sleep(2)
    
    # check server status
    res_sv_st = await ssh.run_vm1("sudo systemctl status openvpn-server@server-udp | head -n 10", check=False)
    print("VM1 ovpn status:\n", res_sv_st.stdout.encode('ascii', 'ignore').decode('ascii'))
    
    # start client
    print("Starting client...")
    res_cl = await ssh.run_vm2(
        "sudo /usr/sbin/openvpn --config /etc/openvpn/client/client-udp.conf --daemon --log /tmp/ovpn-udp.log",
        check=False
    )
    print("VM2 start exit:", res_cl.exit_status, "err:", res_cl.stderr)
    await asyncio.sleep(4)
    
    # verify tunnel
    print("Pinging from VM2...")
    res_ping = await ssh.run_vm2("ping -c 3 -W 3 10.8.0.1", check=False)
    print("VM2 ping exit:", res_ping.exit_status, "out:\n", res_ping.stdout)

    res_log = await ssh.run_vm2("sudo cat /tmp/ovpn-udp.log | tail -n 15", check=False)
    print("VM2 ovpn log:\n", res_log.stdout)

    await ssh.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
