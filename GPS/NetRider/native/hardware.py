"""Narrow, firmware-checked display/input access. UI ownership uses firmware API."""
import array
import fcntl
import os
from pathlib import Path
import platform
import re
import signal
import struct
import time


def identity(pid):
    try:
        text=Path("/proc/%d/stat" % pid).read_text()
        fields=text[text.rindex(")")+2:].split()
        return (int(pid), fields[19])
    except (OSError,ValueError,IndexError):
        return None


def process_state(pid):
    try:
        text=Path("/proc/%d/stat" % pid).read_text()
        return text[text.rindex(")")+2:].split()[0]
    except (OSError,ValueError,IndexError):
        return None


def native_ui():
    found=[]
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit(): continue
        try:
            if os.readlink(entry/"exe") == "/pineapple/pineapple":
                found.append(int(entry.name))
        except OSError: pass
    if len(found)!=1 or process_state(found[0]) in ("T","t","Z",None):
        raise RuntimeError("Cannot identify one running Pineapple UI; takeover refused")
    return identity(found[0])


def signal_exact(target, sig):
    if target and identity(target[0]) == target:
        try: os.kill(target[0],sig)
        except ProcessLookupError: return False
        return True
    return False


class Framebuffer:
    def __init__(self):
        if platform.system() != "Linux": raise RuntimeError("Pager Linux required")
        self.fd=os.open("/dev/fb0",os.O_RDWR|os.O_CLOEXEC)
        try:
            v=bytearray(160); fcntl.ioctl(self.fd,0x4600,v,True)
            fields=struct.unpack_from("20I",v)
            f=bytearray(80); fcntl.ioctl(self.fd,0x4602,f,True)
            if struct.calcsize("l") != 4 or bytes(f[:16]).rstrip(b"\0") != b"fb_st7796u":
                raise RuntimeError("Untested framebuffer driver/architecture")
            if fields[:8] != (222,480,222,480,0,0,16,0) or fields[8:20] != (11,5,0,5,6,0,0,5,0,0,0,0):
                raise RuntimeError("Unexpected framebuffer geometry or RGB565 bitfields")
            if struct.unpack_from("I",f,44)[0] != 444:
                raise RuntimeError("Unexpected framebuffer stride")
            self.saved=os.read(self.fd,213120)
            if len(self.saved)!=213120: raise RuntimeError("Short framebuffer snapshot")
        except BaseException:
            os.close(self.fd); raise

    def write(self, raw):
        if len(raw)!=213120: raise ValueError("Wrong frame size")
        os.lseek(self.fd,0,os.SEEK_SET)
        view=memoryview(raw)
        while view:
            n=os.write(self.fd,view)
            if n<=0: raise OSError("Framebuffer write failed")
            view=view[n:]

    def restore(self):
        self.write(self.saved)

    def close(self):
        os.close(self.fd)


def ioc(direction, number, size):
    # MIPS asm/ioctl.h uses 13 size bits, 3 direction bits, WRITE=4 READ=2.
    mips=platform.machine().startswith("mips")
    flag=(4 if direction=="write" else 2) if mips else (1 if direction=="write" else 2)
    return (flag << (29 if mips else 30)) | (size<<16) | (ord("E")<<8) | number


class KeyPress(int):
    def __new__(cls, code, when):
        item = int.__new__(cls, code)
        item.when = when
        return item


class Keys:
    ENTER, BACK, UP, DOWN, LEFT, RIGHT, POWER = 305,304,103,108,105,106,116

    @classmethod
    def discover(cls):
        candidates=[]
        for event in Path("/sys/class/input").glob("event*"):
            if (event/"device/name").read_text().strip()=="keys":
                candidates.append("/dev/input/"+event.name)
        if len(candidates)!=1: raise RuntimeError("Cannot identify GPIO keys uniquely")
        return candidates[0]

    def __init__(self,path):
        self.fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC)
        try:
            fcntl.ioctl(self.fd,ioc("write",0x90,4),1)
            self.down=self.held()
        except BaseException:
            os.close(self.fd); raise
        self.buffer=b""
        self.desynced=False
        self.since=time.monotonic()
        self.event=struct.Struct("llHHi")

    def held(self):
        bits=bytearray(96)
        fcntl.ioctl(self.fd,ioc("read",0x18,len(bits)),bits,True)
        return {i for i in range(768) if bits[i//8] & (1 << (i%8))}

    def poll(self):
        pressed=[]
        clock_offset = time.monotonic()-time.time()
        try:
            while True:
                data=os.read(self.fd,4096)
                if not data: raise OSError("Keys disconnected")
                self.buffer+=data
        except BlockingIOError: pass
        while len(self.buffer)>=self.event.size:
            seconds,micros,kind,code,value=self.event.unpack_from(self.buffer)
            self.buffer=self.buffer[self.event.size:]
            if kind==0 and code==3:  # SYN_DROPPED: resync, never invent a press.
                self.desynced=True; pressed=[]; continue
            if self.desynced:
                if kind==0 and code==0:  # discard until the next SYN_REPORT
                    self.down=self.held(); self.desynced=False
                continue
            if kind!=1: continue
            if value==0: self.down.discard(code)
            elif value==1:
                already=code in self.down
                self.down.add(code)
                if not already and time.monotonic()-self.since>1:
                    # Default evdev timestamps are realtime. Preserve event time
                    # so a slow map frame cannot turn a double tap into singles.
                    pressed.append(KeyPress(code, seconds+micros/1000000+clock_offset))
        return pressed

    def close(self):
        try: fcntl.ioctl(self.fd,ioc("write",0x90,4),0)
        finally: os.close(self.fd)


class LEDs:
    def __init__(self):
        self.saved={}; self.last=None
        names=["a-button-led"]+[d+"-led-"+c for d in ("up","down","left","right") for c in ("red","green","blue")]
        for name in names:
            path=Path("/sys/class/leds")/name
            raw=(path/"trigger").read_text()
            trigger=re.search(r"\[([^]]+)\]",raw)[1]
            state={"trigger":trigger,"brightness":(path/"brightness").read_text().strip()}
            if trigger=="timer":
                for prop in ("delay_on","delay_off"): state[prop]=(path/prop).read_text().strip()
            self.saved[name]=state
        if "timer" not in (Path("/sys/class/leds/a-button-led/trigger")).read_text():
            raise RuntimeError("Recording LED timer unavailable")

    @staticmethod
    def write(name,key,value):
        (Path("/sys/class/leds")/name/key).write_text(str(value)+"\n")

    def update(self,state,level):
        rec=state=="recording"
        value=(rec, int(level) if rec else 0)
        if self.last==value: return
        if self.last is None or self.last[0]!=rec:
            self.write("a-button-led","trigger","timer" if rec else "none")
            if rec:
                self.write("a-button-led","delay_on",500); self.write("a-button-led","delay_off",500)
            else: self.write("a-button-led","brightness",0)
        for i,direction in enumerate(("up","right","down","left")):
            for color in ("red","green","blue"):
                name=direction+"-led-"+color
                on=rec and i<level and ((color=="red" and level>=3) or (color=="green" and level<=3))
                self.write(name,"trigger","none")
                maximum=int((Path("/sys/class/leds")/name/"max_brightness").read_text())
                self.write(name,"brightness",maximum if on else 0)
        self.last=value

    def restore(self):
        failures=[]
        for name, state in self.saved.items():
            try:
                self.write(name,"trigger","none"); self.write(name,"brightness",state["brightness"])
                self.write(name,"trigger",state["trigger"])
                for prop in ("delay_on","delay_off"):
                    if prop in state: self.write(name,prop,state[prop])
            except OSError: failures.append(name)
        if failures: raise RuntimeError("LED restore failed")
