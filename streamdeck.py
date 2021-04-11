#!/usr/bin/env python3

import os
import threading
import paramiko
import time
import wakeonlan
import scp
import json

from PIL import Image, ImageDraw, ImageFont
from StreamDeck.DeviceManager import DeviceManager
from StreamDeck.ImageHelpers import PILHelper

#from multiprocessing import Process, Queue
import _thread


# Folder location of image assets used by this example.
ASSETS_PATH = os.path.join(os.path.dirname(__file__), "Assets")
ASSETS_VM_PATH = os.path.join(os.path.dirname(__file__), "Assets/VM")
updating_apps = False
running_apps = []


app_refresh_rate = 2  # Update Rate For Apps in Seconds
get_screen_shot = True  # Screenshot of vm transfered over SCP (Faster if False)
wol_server = "example"  # SSH server that WOL command sent through
creds = {}
with open(os.path.join(os.path.dirname(__file__), "creds.json")) as json_file:
    creds = json.load(json_file)

class KeyRegister:
    registry = [{"name": "", "option": ""}] * 15

    @staticmethod
    def reset():
        global running_apps
        global updating_apps
        while True:
            if updating_apps is False:
                break
        running_apps = []
        for x in range(15):
            KeyRegister.set(deck, x)

    @staticmethod
    def get_name(key):
        return KeyRegister.registry[key]["name"]

    @staticmethod
    def get_option(key):
        return KeyRegister.registry[key]["option"]

    @staticmethod
    def set(deck, key, name="", option="", icon="Blank.png", font="Roboto-Regular.ttf", label="", text_offset=20):
        key_style = {
            "name": name,
            "option": option,
            "icon": os.path.join(ASSETS_PATH, icon),
            "font": os.path.join(ASSETS_PATH, font),
            "label": label,
        }
        KeyRegister.registry[key] = key_style
        image = Key.render_image(deck, key_style["icon"], key_style["font"], key_style["label"], text_offset)
        with deck:
            deck.set_key_image(key, image)


class Key:
    @staticmethod
    def render_image(deck, icon_filename, font_filename, label_text, text_offset):
        # Resize the source image asset to best-fit the dimensions of a single key,
        # leaving a margin at the bottom so that we can draw the key title
        # afterwards.
        if label_text == "":
            bot_marg = 0
        else:
            bot_marg = 20

        icon = Image.open(icon_filename)
        image = PILHelper.create_scaled_image(deck, icon, margins=[0, 0, bot_marg, 0])

        # Load a custom TrueType font and use it to overlay the key index, draw key
        # label onto the image.
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(font_filename, 14)
        label_w, label_h = draw.textsize(label_text, font=font)
        label_pos = ((image.width - label_w) // 2, image.height - text_offset)
        draw.text(label_pos, text=label_text, font=font, fill="white")

        return PILHelper.to_native_format(deck, image)

    @staticmethod
    def callback(deck, key, state):
        print("Deck {} Key {} = {}".format(deck.id(), key, state), flush=True)
        if state is False:
            #deck.set_key_callback(None)
            Operations().cmd(KeyRegister.get_name(key), KeyRegister.get_option(key))
            #deck.set_key_callback(Key.callback)


class Operations:
    def __init__(self):
        self.dispatch = {
               "StopStreamDeck": Operations.close,
               "ProfileSettings": Profiles.settings,
               "ProfileMenu": Profiles.vm_menu,
               "ProfileStats": Profiles.server_stats,
               "ProfileNumPad": Profiles.num_pad,
               "ProfileArrowKeys": Profiles.arrow_keys,
               "VmGovernor": VmManagement.governor,
               "VmMaxFreq": VmManagement.set_max_freq,
               "VmDestroy": VmManagement.destroy,
               "VmStart": VmManagement.start,
               "VmShutoff": VmManagement.shutoff,
               "VmSelect": VmManagement.set_vm,
               "VmPause": VmManagement.pause,
               "VmResume": VmManagement.resume,
               "VmSendKey": VmManagement.send_key,
               "ServerShutdown": VmManagement.shutdown_server,
               "ServerSelect": VmManagement.setserver,
               "ServerScroll": VmManagement.displayvmlist,
               #"RotateMonitorToggle": WindowsManagement.rotate_monitor_toggle,
               "WOL": SSH.wol,
               "SSHSend": SSH.send_cmd,
               "SSHSendSudo": SSH.send_sudo_cmd,
              }

    def cmd(self, cmd, option):
        if cmd in self.dispatch:
            if option == "":
                self.dispatch[cmd]()
            else:
                self.dispatch[cmd](option)
        else:
            print("no cmd found")

    @staticmethod
    def close():
        deck.reset()
        deck.close()

class VmManagement:
    selected_vm = ""
    selected_server = ""
    vm_list = []
    vm_list_scroll = 0

    @staticmethod
    def destroy():
        KeyRegister.reset()
        KeyRegister.set(deck, 0, label="destroying", text_offset=50)
        SSH.send(VmManagement.selected_server, "virsh -c qemu:///system destroy " + VmManagement.selected_vm)
        KeyRegister.reset()
        Profiles.vm_management(VmManagement.selected_vm)

    @staticmethod
    def start():
        KeyRegister.reset()
        KeyRegister.set(deck, 0, label="starting", text_offset=50)
        SSH.send(VmManagement.selected_server, "virsh -c qemu:///system start " + VmManagement.selected_vm)
        KeyRegister.reset()
        Profiles.vm_management(VmManagement.selected_vm)

    @staticmethod
    def shutoff():
        KeyRegister.reset()
        KeyRegister.set(deck, 0, label="shutting down", text_offset=50)
        SSH.send(VmManagement.selected_server, "virsh -c qemu:///system shutdown " + VmManagement.selected_vm)
        KeyRegister.reset()
        Profiles.vm_management(VmManagement.selected_vm)

    @staticmethod
    def resume():
        KeyRegister.reset()
        KeyRegister.set(deck, 0, label="resuming", text_offset=50)
        SSH.send(VmManagement.selected_server, "virsh -c qemu:///system resume " + VmManagement.selected_vm)
        KeyRegister.reset()
        Profiles.vm_management(VmManagement.selected_vm)

    @staticmethod
    def pause():
        KeyRegister.reset()
        KeyRegister.set(deck, 0, label="pausing", text_offset=50)
        SSH.send(VmManagement.selected_server, "virsh -c qemu:///system suspend " + VmManagement.selected_vm)
        KeyRegister.reset()
        Profiles.vm_management(VmManagement.selected_vm)

    @staticmethod
    def shutdown_server():
        KeyRegister.reset()
        KeyRegister.set(deck, 0, label="Shutting Down", text_offset=50)
        SSH.send(VmManagement.selected_server, "shutdown -P now")
        KeyRegister.reset()
        Profiles.vm_menu()

    @staticmethod
    def set_max_freq(opt):
        SSH.send_sudo(VmManagement.selected_server, "cpupower frequency-set -u " + opt)

    @staticmethod
    def governor(opt):
        SSH.send_sudo(VmManagement.selected_server, "cpupower frequency-set --governor " + opt)

    @staticmethod
    def send_key(opt):
        SSH.send(VmManagement.selected_server, "virsh -c qemu:///system send-key " + VmManagement.selected_vm + " " + opt)

    @staticmethod
    def set_vm(vm):
        VmManagement.selected_vm = vm
        Profiles.vm_management(vm)

    @staticmethod
    def setserver(server):
        VmManagement.selected_server = server
        Profiles.server_management(server)

    @staticmethod
    def setvmlist(vmlst):
        add_range = 4 - len(vmlst) % 4
        if add_range != 4:
            for x in range(add_range):
                vmlst.append(["", ""])
        while len(vmlst) < 12:
            for x in range(4):
                vmlst.append(["", ""])
        VmManagement.vm_list = vmlst
        VmManagement.vm_list_scroll = 0
        VmManagement.displayvmlist(0)

    @staticmethod
    def displayvmlist(increment):
        increment = int(increment)
        VmManagement.vm_list_scroll += increment
        btn_counter = 1
        start = VmManagement.vm_list_scroll * 4
        #print(VmManagement.vm_list_scroll)
        if len(VmManagement.vm_list) > 12:
            if start >= len(VmManagement.vm_list) - 12:
                VmManagement.vm_list_scroll -= increment
                KeyRegister.set(deck, 5, name="ServerScroll", option="-1", icon="ArrowUp.png")
                KeyRegister.set(deck, 10)
                #return
            elif start <= 0:
                KeyRegister.set(deck, 5, name="ProfileStats", option=VmManagement.selected_server, icon="ServerRack.png", label=VmManagement.selected_server)
                KeyRegister.set(deck, 10, name="ServerScroll", option="+1", icon="ArrowDown.png")
                #return
            else:
                KeyRegister.set(deck, 5, name="ServerScroll", option="-1", icon="ArrowUp.png")
                KeyRegister.set(deck, 10, name="ServerScroll", option="+1", icon="ArrowDown.png")
        else:
            VmManagement.vm_list_scroll = 0
            start = 0
            KeyRegister.set(deck, 5, name="ProfileStats", option=VmManagement.selected_server, icon="ServerRack.png", label=VmManagement.selected_server)
            KeyRegister.set(deck, 10)
        for x in range(start, len(VmManagement.vm_list)):
            if btn_counter % 5 == 0:
                btn_counter += 1
            if VmManagement.vm_list[x][0] != "":
                if VmManagement.vm_list[x][1] == "running":
                    if increment == 0 and get_screen_shot is True:
                        SSH.send(VmManagement.selected_server, "virsh -c qemu:///system screenshot " + VmManagement.vm_list[x][0] + " Pictures/" + VmManagement.vm_list[x][0] + "screen.ppm")
                        out = SSH.get_file(VmManagement.selected_server, "Pictures/", VmManagement.vm_list[x][0] + "screen.ppm")
                        img = "VM/" + VmManagement.vm_list[x][0] + "screen.ppm"
                        if out is not None:
                            background = Image.open(os.path.join(ASSETS_PATH, img)).convert('RGBA').resize((512, 512))
                            #new_background = Image.new('RGBA', (512, 512)).paste(background)
                            foreground = Image.open(os.path.join(ASSETS_PATH, "VmActiveEmptyScreen.png")).convert('RGBA').resize((512, 512))
                            Image.alpha_composite(background, foreground).save(os.path.join(ASSETS_PATH, img))
                    img = "VM/" + VmManagement.vm_list[x][0] + "screen.ppm"
                    if os.path.exists(os.path.join(ASSETS_PATH, img)) is False:
                        img = "VmActive.png"
                elif VmManagement.vm_list[x][1] == "paused":
                    img = "VmPaused.png"
                else:
                    img = "VmInactive.png"
                KeyRegister.set(deck, btn_counter, name="VmSelect", option=VmManagement.vm_list[x][0], icon=img, label=VmManagement.vm_list[x][0])
            else:
                KeyRegister.set(deck, btn_counter)
            btn_counter += 1
            if btn_counter > 14:
                return



class SSH:
    global wol_server
    global creds

    @staticmethod
    def send_cmd(cmd):
        return SSH.send(VmManagement.selected_server, cmd)

    @staticmethod
    def send_sudo_cmd(cmd):
        return SSH.send_sudo(VmManagement.selected_server, cmd)

    @staticmethod
    def send(server, cmd):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(hostname=creds[server]["ip"], username=creds[server]["user"],
                        password=creds[server]["pass"], port=creds[server]["port"], timeout=5)
            ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command(cmd)
            out = str(ssh_stdout.read())
            #print(out)
        except:
            out = None
        ssh.close()
        return out

    @staticmethod
    def get_file(server, remote_path, file_name):
        # ftp_client.get(‘remotefileth’, ’localfilepath’)
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(hostname=creds[server]["ip"], username=creds[server]["user"],
                        password=creds[server]["pass"], port=creds[server]["port"], timeout=5)
            ssh_scp = scp.SCPClient(ssh.get_transport())
            #ftp = ssh.open_sftp()
            ssh_scp.get(remote_path + file_name, os.path.join(ASSETS_VM_PATH, file_name))
            ssh_scp.close()
            out = "0"
        except:
            if os.path.exists(os.path.join(ASSETS_VM_PATH, file_name)):
                os.remove(os.path.join(ASSETS_VM_PATH, file_name))
            out = None
        ssh.close()
        return out

    @staticmethod
    def send_sudo(server, cmd):
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(hostname=creds[server]["ip"], username=creds[server]["user"],
                        password=creds[server]["pass"], port=creds[server]["port"])
            cmd = "sudo -S -p '' %s" % cmd
            ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command(cmd)
            ssh_stdin.write(SSH.creds[server]["pass"] + "\n")
            ssh_stdin.flush()
            out = str(ssh_stdout.read())
            #print(out)
        except:
            out = None
        ssh.close()
        return out

    @staticmethod
    def wol(server):
        wakeonlan.send_magic_packet(creds[server]["mac"])
        SSH.send(wol_server, "wakeonlan " + creds[server]["mac"])
        Profiles.vm_menu()


class LiveApps:
    def __init__(self):
        self.apps = {
                        "vm_live_screen": LiveApps.vm_live_screen,
                        "temp_amd": LiveApps.temp_amd,
                        "temp_intel": LiveApps.temp_intel,
                        "clock": LiveApps.clock,
                        "power": LiveApps.power,
                    }

    def add(self, deck, key, app, opt=""):
        global running_apps
        if app in self.apps:
            self.apps[app](deck, key, opt)
            running_apps.append({"app": self.apps[app], "deck": deck, "key": key, "opt": opt})
        else:
            print("missing app")

    @staticmethod
    def app_runtime():
        global running_apps
        global app_refresh_rate
        global updating_apps
        while True:
            updating_apps = True
            for x in running_apps:
                try:
                    x["app"](x["deck"], x["key"], x["opt"])
                except:
                    pass
            updating_apps = False
            time.sleep(app_refresh_rate)

    @staticmethod
    def vm_live_screen(deck, key, opt):
        SSH.send(VmManagement.selected_server, "virsh -c qemu:///system screenshot " + opt + " Pictures/" + opt + "screen.ppm")
        out = SSH.get_file(VmManagement.selected_server, "Pictures/", opt + "screen.ppm")
        img = "VM/" + opt + "screen.ppm"
        if out is not None:
            background = Image.open(os.path.join(ASSETS_PATH, img)).convert('RGBA').resize((512, 512))
            foreground = Image.open(os.path.join(ASSETS_PATH, "VmActiveEmptyScreen.png")).convert('RGBA').resize((512, 512))
            Image.alpha_composite(background, foreground).save(os.path.join(ASSETS_PATH, img))
        if os.path.exists(os.path.join(ASSETS_PATH, img)) is False:
            img = "VmActive.png"
        KeyRegister.set(deck, key, name="VmSelect", option=opt, icon=img, label=opt)

    @staticmethod
    def temp_amd(deck, key, opt):
        keyword = "temp1_input: "
        out = SSH.send(opt, "sensors -u k10temp-pci-00c3")
        out_pos = out.find(keyword)
        if out_pos != -1:
            out = out[out_pos + len(keyword):out_pos + len(keyword) + 4]
            #print(out)
        else:
            out = "No Reading"
        KeyRegister.set(deck, key, label="Temp: \n" + out, text_offset=50)

    @staticmethod
    def temp_intel(deck, key, opt):
        keyword = "Package id 0:  +"
        out = SSH.send(opt, "sensors")
        out_pos = out.find(keyword)
        if out_pos != -1:
            out = out[out_pos + len(keyword):out_pos + len(keyword) + 6]
            #print(out)
        else:
            out = "No Reading"
        KeyRegister.set(deck, key, label="Temp: \n" + out, text_offset=50)

    @staticmethod
    def clock(deck, key, opt):
        keyword = "cpu MHz\\t\\t: "
        largest_num = 0.0
        smallest_num = 9999999.99
        out = SSH.send(opt, "cat /proc/cpuinfo | grep \"MHz\"")
        out = out.split("\\n")
        for x in range(len(out)-1):
            out[x] = float(out[x][out[x].find(keyword) + len(keyword):out[x].find(keyword) + len(keyword) + 8])
            if largest_num < out[x]:
                largest_num = out[x]
            elif smallest_num > out[x]:
                smallest_num = out[x]
            #print(out[x])
        #print(out)
        KeyRegister.set(deck, key, label="Freq: \n" + str(largest_num) + "\n" + str(smallest_num), text_offset=60)

    @staticmethod
    def power(deck, key, opt):
        keyword = "Load......................... "
        out = SSH.send(opt, "pwrstat -status")
        out_pos = out.find(keyword)
        if out_pos != -1:
            out = out[out_pos + len(keyword):out_pos + len(keyword) + 3]
        else:
            out = "No Reading"
        KeyRegister.set(deck, key, label="Energy: \n" + out, text_offset=50)


class Profiles:
    global creds

    @staticmethod
    def server_stats(opt):
        KeyRegister.reset()
        KeyRegister.set(deck, 0, name="ServerSelect", option=VmManagement.selected_server, icon="Return.png")
        #KeyRegister.set(deck, 0, name="ProfileMenu", icon="Return.png")
        LiveApps().add(deck, 2, "clock", opt=opt)
        LiveApps().add(deck, 3, "power", opt=opt)
        KeyRegister.set(deck, 5, name="VmGovernor", option="userspace", label="userspace", text_offset=50)
        KeyRegister.set(deck, 10, name="VmGovernor", option="performance", label="performance", text_offset=50)
        KeyRegister.set(deck, 11, name="VmGovernor", option="ondemand", label="ondemand", text_offset=50)
        KeyRegister.set(deck, 12, name="VmGovernor", option="schedutil", label="schedutil", text_offset=50)
        KeyRegister.set(deck, 13, name="VmGovernor", option="conservative", label="conservative", text_offset=50)
        KeyRegister.set(deck, 14, name="VmGovernor", option="powersave", label="powersave", text_offset=50)
        if creds[VmManagement.selected_server]["manufacture"] == "amd":
            LiveApps().add(deck, 1, "temp_amd", opt=opt)
            KeyRegister.set(deck, 7, name="VmMaxFreq", option="2200000", label="2.2 GHz", text_offset=50)
            KeyRegister.set(deck, 8, name="VmMaxFreq", option="2800000", label="2.8 GHz", text_offset=50)
            KeyRegister.set(deck, 9, name="VmMaxFreq", option="3700000", label="> 3.7 GHz", text_offset=50)
        elif creds[VmManagement.selected_server]["manufacture"] == "intel":
            LiveApps().add(deck, 1, "temp_intel", opt=opt)
            #KeyRegister.set(deck, 4, name="ServerShutdown", label="Shutdown", text_offset=50)

    @staticmethod
    def settings():
        KeyRegister.reset()
        KeyRegister.set(deck, 0, name="ProfileMenu", icon="Return.png")
        KeyRegister.set(deck, 14, name="StopStreamDeck", icon="Stop.png")

    @staticmethod
    def num_pad():
        KeyRegister.reset()
        KeyRegister.set(deck, 0, name="VmSelect", option=VmManagement.selected_vm, icon="Return.png")
        KeyRegister.set(deck, 5, name="VmSendKey", option="KEY_NUMLOCK", label="NUM", text_offset=50)
        KeyRegister.set(deck, 14, name="VmSendKey", option="KEY_KPENTER", label="ENTER", text_offset=50)
        KeyRegister.set(deck, 9, name="VmSendKey", option="KEY_KPPLUS", label="+", text_offset=50)
        KeyRegister.set(deck, 4, name="VmSendKey", option="KEY_KPMINUS", label="-", text_offset=50)
        KeyRegister.set(deck, 10, name="VmSendKey", option="KEY_KP0", label="0", text_offset=50)
        KeyRegister.set(deck, 11, name="VmSendKey", option="KEY_KP1", label="1", text_offset=50)
        KeyRegister.set(deck, 12, name="VmSendKey", option="KEY_KP2", label="2", text_offset=50)
        KeyRegister.set(deck, 13, name="VmSendKey", option="KEY_KP3", label="3", text_offset=50)
        KeyRegister.set(deck, 6, name="VmSendKey", option="KEY_KP4", label="4", text_offset=50)
        KeyRegister.set(deck, 7, name="VmSendKey", option="KEY_KP5", label="5", text_offset=50)
        KeyRegister.set(deck, 8, name="VmSendKey", option="KEY_KP6", label="6", text_offset=50)
        KeyRegister.set(deck, 1, name="VmSendKey", option="KEY_KP7", label="7", text_offset=50)
        KeyRegister.set(deck, 2, name="VmSendKey", option="KEY_KP8", label="8", text_offset=50)
        KeyRegister.set(deck, 3, name="VmSendKey", option="KEY_KP9", label="9", text_offset=50)

    @staticmethod
    def arrow_keys():
        KeyRegister.reset()
        KeyRegister.set(deck, 0, name="VmSelect", option=VmManagement.selected_vm, icon="Return.png")
        KeyRegister.set(deck, 5, name="VmSendKey", option="KEY_LEFTALT KEY_TAB", label="ALT TAB", text_offset=50)
        KeyRegister.set(deck, 10, name="VmSendKey", option="KEY_SYSRQ", label="Special", text_offset=50)
        KeyRegister.set(deck, 7, name="VmSendKey", option="KEY_UP", label="^", text_offset=50)
        KeyRegister.set(deck, 11, name="VmSendKey", option="KEY_LEFT", label="<", text_offset=50)
        KeyRegister.set(deck, 12, name="VmSendKey", option="KEY_DOWN", label="v", text_offset=50)
        KeyRegister.set(deck, 13, name="VmSendKey", option="KEY_RIGHT", label=">", text_offset=50)
        KeyRegister.set(deck, 14, name="VmSendKey", option="KEY_ENTER", label="ENTER", text_offset=50)

    @staticmethod
    def vm_menu():
        KeyRegister.reset()
        count = 0
        for key in creds:
            KeyRegister.set(deck, count, name="ServerSelect", option=key, icon="ServerRack.png", label=key)
            count += 1
        KeyRegister.set(deck, 14, name="ProfileSettings", icon="Gear.png")

    @staticmethod
    def server_management(server):
        KeyRegister.reset()
        KeyRegister.set(deck, 0, label="Connecting", text_offset=50)
        vmlst = []
        out = SSH.send(server, "virsh -c qemu:///system list --all")
        if out is not None:
            out = out.split("\\n")
            for x in out:
                x = " ".join(x.split())
                x = x.split(" ")
                if x[0].isnumeric() is True or x[0] == "-":
                    if len(x) == 3:
                        vmlst.append([x[1], x[2]])
                    elif len(x) == 4:
                        vmlst.append([x[1], x[2] + " " + x[3]])
            #print(vmlst)
            KeyRegister.reset()
            KeyRegister.set(deck, 0, name="ProfileMenu", icon="Return.png")
            VmManagement.setvmlist(vmlst)
            #KeyRegister.set(deck, 5, name="ServerScroll", option="-1", icon="ArrowUp.png")
            #KeyRegister.set(deck, 10, name="ServerScroll", option="+1", icon="ArrowDown.png")
        else:
            KeyRegister.reset()
            KeyRegister.set(deck, 0, name="ProfileMenu", icon="Return.png")
            KeyRegister.set(deck, 6, label="Cannot", text_offset=50)
            KeyRegister.set(deck, 7, label="Connect", text_offset=50)
            KeyRegister.set(deck, 8, label="Server", text_offset=50)
            KeyRegister.set(deck, 12, name="WOL", option=server, icon="ServerRack.png", label="Wake Server")

    @staticmethod
    def vm_management(vm):
        status = ""
        vmlst = []
        out = SSH.send(VmManagement.selected_server, "virsh -c qemu:///system list --all")
        if out is not None:
            out = out.split("\\n")
            for x in out:
                x = " ".join(x.split())
                x = x.split(" ")
                if x[0].isnumeric() is True or x[0] == "-":
                    if len(x) == 3:
                        vmlst.append([x[1], x[2]])
                    elif len(x) == 4:
                        vmlst.append([x[1], x[2] + " " + x[3]])
        for x in vmlst:
            if x[0] == vm:
                status = x[1]
        KeyRegister.reset()

        KeyRegister.set(deck, 0, name="ServerSelect", option=VmManagement.selected_server, icon="Return.png")
        KeyRegister.set(deck, 2, label=vm, text_offset=50)
        KeyRegister.set(deck, 4, label="State: \n" + status, text_offset=50)
        KeyRegister.set(deck, 5, label="\n____________", text_offset=50)
        KeyRegister.set(deck, 6, label="\n____________", text_offset=50)
        KeyRegister.set(deck, 7, label="\n____________", text_offset=50)
        KeyRegister.set(deck, 8, label="\n____________", text_offset=50)
        KeyRegister.set(deck, 9, label="\n____________", text_offset=50)

        if status == "running":
            KeyRegister.set(deck, 10, name="VmDestroy", icon="Stop.png")
            KeyRegister.set(deck, 11, name="ProfileNumPad", label="NumPad", text_offset=50)
            KeyRegister.set(deck, 12, name="ProfileArrowKeys", label="ArrowKeys", text_offset=50)
            KeyRegister.set(deck, 13, name="VmPause", icon="Pause.png")
            KeyRegister.set(deck, 14, name="VmShutoff", icon="Power.png")
        elif status == "shut off":
            KeyRegister.set(deck, 14, name="VmStart", icon="Start.png")
        elif status == "paused":
            KeyRegister.set(deck, 10, name="VmDestroy", icon="Stop.png")
            KeyRegister.set(deck, 13, name="VmResume", icon="Start.png")
            KeyRegister.set(deck, 14, name="VmShutoff", icon="Power.png")


if __name__ == "__main__":
    streamdecks = DeviceManager().enumerate()

    print("Found {} Stream Deck(s).\n".format(len(streamdecks)))

    for index, deck in enumerate(streamdecks):
        deck.open()
        deck.reset()
        KeyRegister.reset()

        print("Opened '{}' device (serial number: '{}')".format(deck.deck_type(), deck.get_serial_number()))

        # Set initial screen brightness to 30%.
        deck.set_brightness(30)
        Profiles.vm_menu()
        deck.set_key_callback(Key.callback)
        _thread.start_new_thread(LiveApps.app_runtime, ())

        for t in threading.enumerate():
            if t is threading.currentThread():
                continue

            if t.is_alive():
                t.join()
    exit(0)
