#!/usr/bin/env python3
"""Minimal scrcpy client: instant key injection and the latest screen frame, over ADB.

`adb shell input keyevent` starts a Java process per call (~1 s on the Z11) and `screencap`
takes ~2 s. scrcpy runs one server on the box: keys go through an open control socket
(milliseconds) and the screen arrives as an H.264 stream, so the latest frame is always ready.

Needs the scrcpy package on the host (for its server jar; the version must match) and PyAV.

    from mol4_scrcpy import Scrcpy
    s = Scrcpy("<box-ip>:5555").start()
    s.key(22)                 # DPAD_RIGHT
    frame = s.frame(0.4)      # numpy RGB (h, w, 3), at least 0.4 s newer than the call
    s.stop()
"""
import os, random, socket, struct, subprocess, threading, time

import av
import numpy as np

SERVER_JAR = "/usr/share/scrcpy/scrcpy-server"
REMOTE_JAR = "/data/local/tmp/scrcpy-server.jar"


def scrcpy_version():
    out = subprocess.run(["scrcpy", "--version"], capture_output=True, text=True).stdout
    return out.split()[1]


class Scrcpy:
    def __init__(self, serial, max_fps=20, bit_rate=8_000_000):
        self.serial, self.max_fps, self.bit_rate = serial, max_fps, bit_rate
        self.scid = "%08x" % random.randrange(1 << 31)
        self.port = random.randrange(27200, 27900)
        self._frame, self._frame_t = None, 0.0
        self._lock = threading.Lock()
        self._stop = False

    def _adb(self, *a, **kw):
        return subprocess.run(["adb", "-s", self.serial, *a], capture_output=True, **kw)

    def start(self):
        self._adb("push", SERVER_JAR, REMOTE_JAR)
        self._adb("forward", f"tcp:{self.port}", f"localabstract:scrcpy_{self.scid}")
        args = [f"CLASSPATH={REMOTE_JAR}", "app_process", "/", "com.genymobile.scrcpy.Server",
                scrcpy_version(), f"scid={self.scid}", "log_level=warn", "tunnel_forward=true",
                "audio=false", "control=true", "raw_stream=true", "send_dummy_byte=true", "video_codec=h264",
                f"max_fps={self.max_fps}", f"video_bit_rate={self.bit_rate}", "cleanup=true"]
        self.log = open(os.path.join(os.environ.get("TMPDIR", "/tmp"), f"scrcpy-{self.scid}.log"), "wb")
        self.server = subprocess.Popen(["adb", "-s", self.serial, "shell", " ".join(args)],
                                       stdout=self.log, stderr=self.log)
        # adb forward accepts the TCP connection even before the server listens, then closes
        # it: wait for the dummy byte the server sends on the first socket.
        for _ in range(60):
            try:
                v = socket.create_connection(("127.0.0.1", self.port), timeout=2)
                if v.recv(1):
                    self.video = v
                    break
                v.close()
            except OSError:
                pass
            time.sleep(0.15)
        else:
            raise RuntimeError("scrcpy server did not start (see %s)" % self.log.name)
        self.control = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        self.video.settimeout(None)
        threading.Thread(target=self._decode, daemon=True).start()
        threading.Thread(target=self._drain_control, daemon=True).start()
        end = time.time() + 10
        while self._frame is None and time.time() < end:
            time.sleep(0.05)
        if self._frame is None:
            raise RuntimeError("no video frame from scrcpy")
        return self

    def _drain_control(self):  # device messages (clipboard etc.): read and ignore
        try:
            while not self._stop and self.control.recv(4096):
                pass
        except OSError:
            pass

    def _decode(self):
        codec = av.CodecContext.create("h264", "r")
        try:
            while not self._stop:
                data = self.video.recv(1 << 16)
                if not data:
                    break
                for packet in codec.parse(data):
                    for fr in codec.decode(packet):
                        img = fr.to_ndarray(format="rgb24")
                        with self._lock:
                            self._frame, self._frame_t = img, time.time()
        except (OSError, av.error.FFmpegError):
            pass

    def frame(self, newer_than=0.0):
        """Latest frame, decoded at least `newer_than` seconds after this call started.
        The stream only sends frames when the screen changes, so after the wait we take
        the latest frame we have."""
        t0 = time.time()
        if newer_than:
            time.sleep(newer_than)
        with self._lock:
            return self._frame

    def key(self, keycode, action=None):
        """Inject a key: control message INJECT_KEYCODE (type 0), down then up."""
        for act in ((0, 1) if action is None else (action,)):
            msg = struct.pack(">BBiii", 0, act, int(keycode), 0, 0)
            self.control.sendall(msg)
        time.sleep(0.02)

    def text(self, s):
        """Inject text: control message INJECT_TEXT (type 1)."""
        b = s.encode("utf8")
        self.control.sendall(struct.pack(">BI", 1, len(b)) + b)

    def stop(self):
        self._stop = True
        for s in (getattr(self, "video", None), getattr(self, "control", None)):
            try:
                s.close()
            except Exception:
                pass
        if getattr(self, "server", None):
            self.server.terminate()
        self._adb("forward", "--remove", f"tcp:{self.port}")
