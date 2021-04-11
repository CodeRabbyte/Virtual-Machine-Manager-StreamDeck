# Virtual-Machine-Manager-Stream-Deck
**Stream Deck Application To Manage Virtual Machines**

Allows management of kvm virtual machines via ssh and virsh.  Feel free to convert this project to libvirt apis.  Registered servers via creds.json should be limited to 14 servers, each server can display any number of virtual machines with scroll bar.  Management options for each vm includes: FORCE SHUTDOWN, SHUTDOWN, SUSPEND, numpad keys, and arrow keys.  VMs do not update in real time and a refresh will be triggered when moving through the menus.

Main Menu/ Server Selection
![Pic](ReadMePictures/20210410_183652.jpg?raw=true "Title")

Virtual Machine Selection
![Pic](ReadMePictures/20210410_183438.jpg?raw=true "Title")

Virtual Machine Options
![Pic](ReadMePictures/20210410_183707.jpg?raw=true "Title")

## Setup

```
pip3 install paramiko
pip3 install wakeonlan
pip3 install scp
pip3 install Pillow
pip3 install streamdeck
```
For more information on how to setup streamdeck with Linux: https://github.com/abcminiuser/python-elgato-streamdeck

streamdeck.py config
```
app_refresh_rate = 2  # Update Rate For Apps in Seconds
get_screen_shot = True  # Screenshot of vm transfered over SCP (Faster if False)
wol_server = "example"  # SSH server that WOL command sent through
```

credentials can be modified in creds.json
```
{"example":                         # arbitary name, must be unique
        {"ip": "0.0.0.0",           # host ip to ssh into
        "user": "root",             # ssh user
        "pass": "1234",             # ssh pass
        "port": 22,                 # ssh port
        "manufacture": "amd",       # processor manufacturer for temp readings
        "mac": "00:00:00:00:00:00"} # mac address for wol
}
```

## Usage

```
./streamdeck.py
```

## Thanks

Thanks to all those who made this possible with simple to use python packages.
