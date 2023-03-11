import wmi
from queue import LifoQueue

# # Mở ổ đĩa
# drive = r"\\.\PhysicalDrive0"  # Thay đổi số tương ứng với ổ đĩa cần đọc
# with open(drive, "rb") as f:

#     # Đọc boot sector
#     boot_sector = f.read(512)

#     # Hiển thị nội dung boot sector dưới dạng hex
#     i = -1
#     for byte in boot_sector:
#         print("{:02x} ".format(byte), end="")
#         i+=1
#         if (i % 16 == 15):
#             print("\n")

# Get USB physical drives
def GetUSBDrive():
    c = wmi.WMI()
    devices = []
    for drive in c.Win32_DiskDrive():
        if "USB" in drive.Caption:
            devices.append(drive)
    return devices

# Read Physical Drive
def ReadPhysicalDrive(driveName, sectorBytes):
    with open(driveName, "rb") as drive:
        # Read Master Boot Record
        MBR = drive.read(sectorBytes)
        MBRInfo = []
        
        # Read 16-byte partition in MBR
        for i in range(int("1BE", 16), sectorBytes, 16):
            if i + 16 > sectorBytes:
                break
            MBRPart = {
                "Status": MBR[i],
                "CHSBegin": int.from_bytes(MBR[i + int("01", 16) : i + int("01", 16) + 3], "little"),
                "Type": MBR[i + int("04", 16)],
                "CHSEnd": int.from_bytes(MBR[i + int("05", 16) : i + int("05", 16) + 3], "little"),
                "LBABegin": int.from_bytes(MBR[i + int("08", 16) : i + int("08", 16) + 4], "little"),
                "Sectors": int.from_bytes(MBR[i + int("0C", 16) : i + int("0C", 16) + 4], "little")
            }
            if MBRPart["CHSBegin"] > 0:
                MBRInfo.append(MBRPart)
            else:
                break 

        # Read partitions
        for MBRPart in MBRInfo:
            # 7 = 0x07 (NTFS)
            if MBRPart["Type"] == 7:
                ReadNTFSPartition(driveName, sectorBytes, MBRPart["LBABegin"])
            # 12 = 0x0C (FAT32)
            elif MBRPart["Type"] == 12:
                bootSectorInfo = ReadFAT32BootSector(driveName, sectorBytes, MBRPart["LBABegin"])
                RDETItems = ReadFAT32RDET(driveName, sectorBytes, MBRPart["LBABegin"] + bootSectorInfo["SectorsBeforeFAT"] + bootSectorInfo["FATTables"] * bootSectorInfo["FATSectors"])
                
                for item in RDETItems:
                    PrintFAT32Item(item)
            else:
                print("Unknown parition type") 

# Read NTFS partition
def ReadNTFSPartition(driveName, sectorBytes, LBAbegin):
    print("Can't read NTFS now!")

# Read FAT32 partition
def ReadFAT32BootSector(driveName, sectorBytes, LBAbegin):
    bootSectorInfo = {}

    with open(driveName, "rb") as drive:
        drive.seek(LBAbegin * 32 * 16)
        bootSector = drive.read(sectorBytes)

        bootSectorInfo = {
            "SectorBytes": int.from_bytes(bootSector[int("0B", 16) : int("0B", 16) + 2], "little"),
            "ClusterSectors": bootSector[int("0D", 16)],
            "SectorsBeforeFAT": int.from_bytes(bootSector[int("0E", 16) : int("0E", 16) + 2], "little"),
            "FATTables": bootSector[int("10", 16)],
            "VolumeSectors": int.from_bytes(bootSector[int("20", 16) : int("20", 16) + 4], "little"),
            "FATSectors": int.from_bytes(bootSector[int("24", 16) : int("24", 16) + 4], "little"),
            "RDETClusterBegin": int.from_bytes(bootSector[int("2C", 16) : int("2C", 16) + 4], "little"),
            "FATType": bootSector[int("52", 16) : int("52", 16) + 8],
        }

    return bootSectorInfo

# Read FAT32 RDET
def ReadFAT32RDET(driveName, sectorBytes, sectorBegin):
    RDETItems = []
    with open(driveName, "rb") as drive:
        drive.seek(sectorBegin * 32 * 16)
        while(True):            
            RDET = drive.read(sectorBytes)
            entryQueue = LifoQueue()

            # Entry size is 32B
            for i in range(0, sectorBytes, 32):
                # Break the read while loop
                if RDET[i] == 0:
                    break
                # Skip if deleted
                if RDET[i] == 229: # 229 = 0xE5
                    continue            
                if RDET[i + int("0B", 16)] == 15: # 15 = 0x0F
                # Sub entry
                    subEntry = {
                        "Name1": RDET[i + int("01", 16) : i + int("01", 16) + 10].decode("utf-16"),
                        "Name2": RDET[i + int("0E", 16) : i + int("0E", 16) + 12].decode("utf-16"),
                        "Name3": RDET[i + int("1C", 16) : i + int("1C", 16) + 4].decode("utf-16")
                    }
                    entryQueue.put(subEntry)
                else:
                # Entry
                    # Get entry full name
                    entryName = ""
                    while not entryQueue.empty():
                        subEntry = entryQueue.get()
                        for j in range(1, 4):
                            entryName += subEntry["Name" + str(j)]
                    entryName = entryName[:entryName.find("\x00")]

                    entry = {
                        "Name": entryName,
                        "PrimaryName": RDET[i : i + 8].decode("utf-8"),
                        "ExtendedName": RDET[i + int("08", 16) : i + int("08", 16) + 3].decode("utf-8"),
                        "Attributes": GetFAT32FileAttributes("{0:08b}".format(RDET[i + int("0B", 16)])),
                        "TimeCreated": GetFAT32FileTimeCreated("".join(format(byte, '08b') for byte in RDET[i + int("0D", 16) : i + int("0D", 16) + 3][::-1])),
                        "DateCreated": GetFAT32FileDateCreated("".join(format(byte, '08b') for byte in RDET[i + int("10", 16) : i + int("10", 16) + 2][::-1])),
                        "ClusterBegin": int.from_bytes(RDET[i + int("1A", 16) : i + int("1A", 16) + 2], "little"),
                        "Size": int.from_bytes(RDET[i + int("1C", 16) : i + int("1C", 16) + 4], "little")
                    }
                    RDETItems.append(entry)
            else:
                continue
            break
    
    return RDETItems

# Get FAT32 file attributes
def GetFAT32FileAttributes(bitArray):
    attributes = []
    if bitArray[7] == "1":
        attributes.append("ReadOnly")
    if bitArray[6] == "1":
        attributes.append("Hidden")
    if bitArray[5] == "1":
        attributes.append("System")
    if bitArray[4] == "1":
        attributes.append("VolLabel")
    if bitArray[3] == "1":
        attributes.append("Directory")
    if bitArray[2] == "1":
        attributes.append("Archive")
    return attributes

# Get FAT32 file time created
def GetFAT32FileTimeCreated(bitArray):
    return {
        "Hour": int("".join(str(x) for x in bitArray[:5]), 2),
        "Minute": int("".join(str(x) for x in bitArray[5:11]), 2),
        "Second": int("".join(str(x) for x in bitArray[11:17]), 2),
        "MiliSecond": int("".join(str(x) for x in bitArray[17:]), 2),
    }

# Get FAT32 file date created
def GetFAT32FileDateCreated(bitArray):
    return {
        "Year": int("".join(str(x) for x in bitArray[:7]), 2) + 1980,
        "Month": int("".join(str(x) for x in bitArray[7:11]), 2),
        "Day": int("".join(str(x) for x in bitArray[11:]), 2)
    }

# Print FAT32 item
def PrintFAT32Item(item):
    print("{")
    print("    Name:", item["Name"] if item["Name"] != "" else item["PrimaryName"] + item["ExtendedName"])
    print("    Attributes:", item["Attributes"])
    print("    Date Created:", item["DateCreated"])
    print("    Time Created:", item["TimeCreated"])
    print("    Size:", item["Size"])
    print("}")

# Test functions
USBDrives = GetUSBDrive()

ReadPhysicalDrive(USBDrives[0].name, USBDrives[0].BytesperSector)