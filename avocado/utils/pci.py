# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: 2016 IBM
# Author: Narasimhan V <sim@linux.vnet.ibm.com>
#
# Author: Kleber Sacilotto de Souza <klebers@linux.vnet.ibm.com>
# Author: Daniel Kreling <kreling@linux.vnet.ibm.com>
# for get_memory_address() and get_mask()

"""
Module for all PCI devices related functions.
"""


import os
import re

from avocado.utils import genio, process, wait


def get_domains():
    """
    Gets all PCI domains.
    Example, it returns ['0000', '0001', ...]

    :return: List of PCI domains.
    :rtype: list of str
    """
    cmd = "lspci -D"
    output = process.run(cmd, ignore_status=True, shell=True).stdout_text
    if output:
        domains = []
        for line in output.splitlines():
            domains.append(line.split(":")[0])
        return list(set(domains))
    return []


def get_pci_addresses():
    """
    Gets list of PCI addresses in the system.
    Does not return the PCI Bridges/Switches.

    :return: list of full PCI addresses including domain (0000:00:14.0)
    :rtype: list of str
    """
    addresses = []
    cmd = "lspci -D"
    for line in process.run(cmd).stdout_text.splitlines():
        if not get_pci_prop(line.split()[0], "Class").startswith("06"):
            addresses.append(line.split()[0])
    if addresses:
        return addresses
    return []


def get_num_interfaces_in_pci(dom_pci_address):
    """
    Gets number of interfaces of a given partial PCI address starting with
    full domain address.

    :param dom_pci_address: Partial PCI address including domain
                            address (0000, 0000:00:1f, 0000:00:1f.2, etc)

    :return: number of devices in a PCI domain.
    :rtype: int
    """
    cmd = "ls -l /sys/class/*/ -1"
    output = process.run(cmd, ignore_status=True, shell=True).stdout_text
    if output:
        filt = f"/{dom_pci_address}"
        count = 0
        for line in output.splitlines():
            if filt in line:
                count += 1
        return count
    return 0


def get_disks_in_pci_address(pci_address):
    """
    Gets disks in a PCI address.

    :param pci_address: Any segment of a PCI address (1f, 0000:00:1f, ...)

    :return: list of disks in a PCI address.
    """
    disk_list = []
    for device in os.listdir("/sys/block"):
        if pci_address in os.path.realpath(os.path.join("/sys/block", device)):
            disk_list.append(f"/dev/{device}")
    return disk_list


def get_nics_in_pci_address(pci_address):
    """
    Gets network interface(nic) in a PCI address.

    :param pci_address: Any segment of a PCI address (1f, 0000:00:1f, ...)

    :return: list of network interfaces in a PCI address.
    """
    return get_interfaces_in_pci_address(pci_address, "net")


def get_interfaces_in_pci_address(pci_address, pci_class):
    """
    Gets interface in a PCI address.

    e.g: host = pci.get_interfaces_in_pci_address("0001:01:00.0", "net")
         ['enP1p1s0f0']
         host = pci.get_interfaces_in_pci_address("0004:01:00.0", "fc_host")
         ['host6']

    :param pci_address: Any segment of a PCI address (1f, 0000:00:1f, ...)
    :param class: Adapter type (FC(fc_host), FCoE(net), NIC(net), SCSI(scsi)..)
    :return: list of generic interfaces in a PCI address.
    """
    pci_class_path = f"/sys/class/{pci_class}/"
    ifaces = []
    if not os.path.isdir(pci_class_path):
        raise ValueError("Please provide valid class name")
    for interface in os.listdir(pci_class_path):
        pci_path = os.path.join(pci_class_path, interface)
        if os.path.isdir(pci_path) and pci_address in os.readlink(pci_path):
            ifaces.append(interface)
    return ifaces


def get_pci_class_name(pci_address):
    """
    Gets pci class name for given pci bus address

    e.g: >>> pci.get_pci_class_name("0000:01:00.0")
             'scsi_host'

    :param pci_address: Any segment of a PCI address(1f, 0000:00:if, ...)

    :return: class name for corresponding pci bus address
    """
    pci_class_dic = {
        "0104": "scsi_host",
        "0c04": "fc_host",
        "0200": "net",
        "0108": "nvme",
        "0280": "net",
        "0207": "net",
        "0c03": "usb",
    }
    pci_class_id = get_pci_prop(pci_address, "Class")
    if pci_class_id not in pci_class_dic:
        if pci_class_id is None:
            raise ValueError(
                f"Unable to get 'Class' property of given pci " f"address {pci_address}"
            )
        raise ValueError(
            f"Class ID {pci_class_id} is not defined "
            f"in this library please send an update"
        )
    return pci_class_dic.get(pci_class_id)


def get_pci_fun_list(pci_address):
    """
    Gets list of functions in the given PCI address.
    Example: in address 0000:03:00, functions are 0000:03:00.0 and 0000:03:00.1

    :param pci_address: Any segment of a PCI address (1f, 0000:00:1f, ...)

    :return: list of functions in a PCI address.
    """
    return list(dev for dev in get_pci_addresses() if pci_address in dev)


def get_slot_from_sysfs(full_pci_address):
    """
    Gets the PCI slot of given address.

    :note: Specific for ppc64 processor.

    :param full_pci_address: Full PCI address including domain (0000:03:00.0)

    :return: Removed port related details using re, only returns till
             physical slot of the adapter.
    """
    if not os.path.isfile(f"/sys/bus/pci/devices/{full_pci_address}/devspec"):
        return None
    devspec = genio.read_file(
        f"/sys/bus/pci/devices/" f"{full_pci_address}/devspec"
    ).strip()
    if not os.path.isfile(f"/proc/device-tree/{devspec}/ibm,loc-code"):
        return None
    slot = genio.read_file(f"/proc/device-tree/{devspec}/ibm,loc-code")
    slot_ibm = re.match(r"((\w+)[.])+(\w+)-[PC(\d+)-]*C(\d+)", slot)
    if slot_ibm:
        return slot_ibm.group()
    slot_openpower = re.match(r"(\w+)[\s]*(\w+)(\d*)", slot)
    if slot_openpower:
        return slot_openpower.group()
    raise ValueError(f"Failed to get slot from: '{slot}'")


def get_slot_list():
    """
    Gets list of PCI slots in the system.

    :note: Specific for ppc64 processor.

    :return: list of slots in the system.
    """
    return list(set(get_slot_from_sysfs(dev) for dev in get_pci_addresses()))


def get_pci_id_from_sysfs(full_pci_address):
    """
    Gets the PCI ID from sysfs of given PCI address.

    :param full_pci_address: Full PCI address including domain (0000:03:00.0)

    :return: PCI ID of a PCI address from sysfs.
    """
    path = f"/sys/bus/pci/devices/{full_pci_address}"
    if os.path.isdir(path):
        path = "%s/%%s" % path  # pylint: disable=C0209
        return ":".join(
            [
                f"{int(open(path % param).read(), 16):04x}"  # pylint: disable=W1514
                for param in [
                    "vendor",
                    "device",
                    "subsystem_vendor",
                    "subsystem_device",
                ]
            ]
        )
    return None


def get_pci_prop(pci_address, prop):
    """
    Gets specific PCI ID of given PCI address. (first match only)

    :param pci_address: Any segment of a PCI address (1f, 0000:00:1f, ...)
    :param part: prop of PCI ID.

    :return: specific PCI ID of a PCI address.
    :rtype: str
    """
    cmd = f"lspci -Dnvmm -s {pci_address}"
    output = process.run(cmd, ignore_status=True, shell=True).stdout_text
    if output:
        for line in output.splitlines():
            if prop == line.split(":")[0]:
                return line.split()[-1]
    return None


def get_pci_id(pci_address):
    """
    Gets PCI id of given address. (first match only)

    :param pci_address: Any segment of a PCI address (1f, 0000:00:1f, ...)

    :return: PCI ID of a PCI address.
    """
    pci_id = []
    for params in ["Vendor", "Device", "SVendor", "SDevice"]:
        output = get_pci_prop(pci_address, params)
        if not output:
            return None
        pci_id.append(output)
    if pci_id:
        return ":".join(pci_id)
    return None


def get_pci_info(pci_address):
    """
    Gets PCI info of given PCI address.

    :param pci_address: Any segment of a PCI address (1f, 0000:00:1f, ...)

    :return: Dictionary attribute name as key and attribute value as value.
    :rtype: Dict
    """
    cmd = f"lspci -Dnvmm -s {pci_address}"
    output = process.run(cmd, ignore_status=True, shell=True).stdout_text
    pci_info = {}
    if not output:
        return None
    for line in output.splitlines():
        if line.strip():
            pci_info[line.split(":")[0].strip()] = (
                ":".join(line.split(":")[1:])
            ).strip()
    return pci_info


def get_driver(pci_address):
    """
    Gets the kernel driver in use of given PCI address. (first match only)

    :param pci_address: Any segment of a PCI address (1f, 0000:00:1f, ...)

    :return: driver of a PCI address.
    :rtype: str
    """
    cmd = f"lspci -ks {pci_address}"
    output = process.run(cmd, ignore_status=True, shell=True).stdout_text
    if output:
        for line in output.splitlines():
            if "Kernel driver in use:" in line:
                return line.rsplit(None, 1)[-1]
    return None


def unbind(driver, full_pci_address):
    """
    Unbind the pci device(full_pci_address) from driver

    :param driver: driver of the PCI address (full_pci_address)
    :param full_pci_address:  Full PCI address including domain (0000:03:00.0)
    :return: None
    """
    genio.write_file_or_fail(f"/sys/bus/pci/drivers/{driver}/unbind", full_pci_address)
    if wait.wait_for(
        lambda: os.path.exists(
            f"/sys/bus/pci/drivers/\
{driver}/{full_pci_address}"
        ),
        timeout=5,
    ):
        raise ValueError(f"Not able to unbind {full_pci_address} from {driver}")


def bind(driver, full_pci_address):
    """
    Bind the pci device(full_pci_address) to driver

    :param driver: driver of the PCI address (full_pci_address)
    :param full_pci_address:  Full PCI address including domain (0000:03:00.0)
    :return: None
    """
    genio.write_file_or_fail(f"/sys/bus/pci/drivers/{driver}/bind", full_pci_address)
    if not wait.wait_for(
        lambda: os.path.exists(
            f"/sys/bus/pci/drivers/\
{driver}/{full_pci_address}"
        ),
        timeout=5,
    ):
        raise ValueError(f"Not able to bind {full_pci_address} to {driver}")


def get_vendor_id(full_pci_address):
    """
    Get vendor id of a PCI address

    :param full_pci_address: Full PCI address including domain (0000:03:00.0)
    :return: vendor id of PCI address
    :rtype: str
    """
    cmd = f"lspci -n -s {full_pci_address}"
    out = process.run(cmd, ignore_status=True, shell=True).stdout_text
    if not out:
        raise ValueError(f"Not able to get {full_pci_address} vendor id")
    return out.split(" ")[2].strip()


def reset_check(full_pci_address):
    """
    Check if reset for "full_pci_address" is successful

    :param full_pci_address: Full PCI address including domain (0000:03:00.0)
    :return: whether reset for "full_pci_address" is successful
    :rtype: bool
    """
    cmd = f"lspci -vvs {full_pci_address}"
    output = process.run(cmd, ignore_status=True, shell=True).stdout_text
    if not output:
        return False
    return True


def rescan_check(full_pci_address):
    """
    Check if rescan for full_pci_address is successful

    :param full_pci_address: Full PCI address including domain (0000:03:00.0)
    :return: whether rescan for full_pci_address is successful
    :rtype: bool
    """
    cmd = f"lspci -vvs {full_pci_address}"
    output = process.run(cmd, ignore_status=True, shell=True).stdout_text
    if not output:
        return False
    return True


def change_domain_check(dom, full_pci_address, def_dom):
    """
    Check if the domain changed successfully to "dom" for "full_pci_address"

    :param dom: domain type
    :param def_dom: default domain of pci device(full_pci_address)
    :param full_pci_address: Full PCI address including domain (0000:03:00.0)
    :return: whether domain changed successfully to "dom"
    :rtype: bool
    """
    try:
        output = genio.read_one_line(
            f"/sys/bus/pci/devices/{full_pci_address}/iommu_group/type"
        )
        out = output.rsplit(None, 1)[-1]
        if (dom not in ("auto", out)) or (dom == "auto" and out != def_dom):
            return False
        return True
    except OSError as details:
        raise ValueError(f"Change domain check failed: {details}") from details


def reset(full_pci_address):
    """
    Remove the full_pci_address

    :param full_pci_address: Full PCI address including domain (0000:03:00.0)
    :return: None
    """
    genio.write_file_or_fail(f"/sys/bus/pci/devices/{full_pci_address}/remove", "1")
    if not wait.wait_for(lambda: reset_check(full_pci_address), timeout=5):
        raise ValueError(f"Unsuccessful to remove {full_pci_address}")


def rescan(full_pci_address):
    """
    Rescan the system and check for full_pci_address

    :param full_pci_address: Full PCI address including domain (0000:03:00.0)
    :return: None
    """
    genio.write_file_or_fail("/sys/bus/pci/rescan", "1")
    if not wait.wait_for(lambda: rescan_check(full_pci_address), timeout=5):
        raise ValueError(f"Unsuccessful to rescan for {full_pci_address}")


def get_iommu_group(full_pci_address):
    """
    Return the iommu group of full_pci_address

    :param full_pci_address: Full PCI address including domain (0000:03:00.0)
    :return: iommu group of full_pci_address
    :rtype: string
    """
    cmd = f"lspci -vvvv -s {full_pci_address}"
    out = process.run(cmd, ignore_status=True, shell=True)
    for line in out.stdout_text.split("\n"):
        if "IOMMU group" in line:
            return line.strip().split(" ")[2]
    raise ValueError(f"{full_pci_address} group not found")


def change_domain(dom, def_dom, full_pci_address):
    """
    Change the domain of pci device(full_pci_address) to dom

    :param dom: domain type
    :param def_dom: default domain of pci device(full_pci_address)
    :param full_pci_address: Full PCI address including domain (0000:03:00.0)
    :return: None
    """
    genio.write_file_or_fail(
        f"/sys/bus/pci/devices/{full_pci_address}/iommu_group/type", dom
    )
    if not wait.wait_for(
        lambda: change_domain_check(dom, full_pci_address, def_dom), timeout=5
    ):
        raise ValueError(f"Domain type change failed for {full_pci_address}")


def get_memory_address(pci_address):
    """
    Gets the memory address of a PCI address. (first match only)

    :note: There may be multiple memory address for a PCI address.
    :note: This function returns only the first such address.

    :param pci_address: Any segment of a PCI address (1f, 0000:00:1f, ...)

    :return: memory address of a pci_address.
    :rtype: str
    """
    cmd = f"lspci -bv -s {pci_address}"
    output = process.run(cmd, ignore_status=True, shell=True).stdout_text
    if output:
        for line in output.splitlines():
            if "Memory at" in line:
                return f"0x{line.split()[2]}"
    return None


def get_mask(pci_address):
    """
    Gets the mask of PCI address. (first match only)

    :note: There may be multiple memory entries for a PCI address.
    :note: This mask is calculated only with the first such entry.

    :param pci_address: Any segment of a PCI address (1f, 0000:00:1f, ...)

    :return: mask of a PCI address.
    :rtype: str
    """
    cmd = f"lspci -vv -s {pci_address}"
    output = process.run(cmd, ignore_status=True, shell=True).stdout_text
    if not output:
        return None
    dic = {"K": 1024, "M": 1048576, "G": 1073741824}
    for line in output.splitlines():
        if "Region" in line and "Memory at" in line:
            val = line.split("=")[-1].split("]")[0]
            memory_size = int(val[:-1]) * dic[val[-1]]
            break
    # int("0xffffffff", 16) = 4294967295
    mask = hex((memory_size - 1) ^ 4294967295)
    return mask


def get_vpd(dom_pci_address):
    """
    Gets the VPD (Virtual Product Data) of the given PCI address.

    :note: Specific for ppc64 processor.

    :param dom_pci_address: Partial PCI address including domain addr and at
                            least bus addr (0003:00, 0003:00:1f.2, ...)

    :return: dictionary of VPD of a PCI address.
    :rtype: dict
    """
    cmd = f"lsvpd -l {dom_pci_address}"
    vpd = process.run(cmd).stdout_text
    vpd_dic = {}
    dev_list = []
    for line in vpd.splitlines():
        if len(line) < 5:
            continue
        if "*YL" in line:
            vpd_dic["slot"] = line[4:]
        elif "*DS" in line:
            vpd_dic["pci_id"] = line[4:]
        elif "*FC" in line:
            vpd_dic["feature_code"] = line[4:]
        elif "*AX" in line:
            if not (dom_pci_address in line or vpd_dic["pci_id"].split()[0] in line):
                dev_list.append(line[4:])
        elif "*CD" in line:
            vpd_dic["pci_id"] = line[4:]
    vpd_dic["devices"] = dev_list
    return vpd_dic


def get_cfg(dom_pci_address):
    """
    Gets the hardware configuration data of the given PCI address.

    :note: Specific for ppc64 processor.

    :param dom_pci_address: Partial PCI address including domain addr and at
                            least bus addr (0003:00, 0003:00:1f.2, ...)

    :return: dictionary of configuration data of a PCI address.
    :rtype: dict
    """
    cmd = f"lscfg -vl {dom_pci_address}"
    cfg = process.run(cmd).stdout_text
    cfg_dic = {}
    desc = re.match(
        r"  (%s)( [-\w+,\.]+)+([ \n])+([-\w+, \(\)])+"  # pylint: disable=C0209
        % dom_pci_address,
        cfg,
    ).group()
    cfg_dic["Description"] = desc
    for line in cfg.splitlines():
        if "Manufacturer Name" in line:
            cfg_dic["Mfg"] = line.split(".")[-1]
        if "Machine Type-Model" in line:
            cfg_dic["Model"] = line.split(".")[-1]
        if "Device Specific" in line:
            cfg_dic["YC"] = line.split(".")[-1]
        if "Location Code" in line:
            cfg_dic["YL"] = line.split("..")[-1].strip(".")
    if "Description" in cfg_dic:
        pcid = re.search(
            r"[0-9a-e]{4}\:[0-9a-e]{2}\:[0-9a-e]{2}\.[0-9a-e]{1}",
            cfg_dic["Description"],
        )
        cfg_dic["pci_id"] = pcid.group()
        device_subvendor = re.search(r"([0-9a-e]{8})", cfg_dic["Description"])
        cfg_dic["subvendor_device"] = device_subvendor.group()
    return cfg_dic
