"""Bounded, in-memory audio metering. No files and no speaker playback."""
import threading
import time

import numpy as np


class AudioLevels:
    def __init__(self):
        self._lock = threading.Lock()
        self._latest = {}

    def feed(self, source, data, status=None):
        # Called by PortAudio: never call Qt or retain the input buffer.
        samples = np.asarray(data)
        if samples.size == 0:
            return
        if samples.ndim == 1:
            samples = samples[:, None]
        samples = np.nan_to_num(samples[:, :2], nan=0.0, posinf=1.0, neginf=-1.0)
        rows = []
        for channel in samples.T:
            amplitude = np.abs(channel)
            peak = float(amplitude.max())
            rms = float(np.sqrt(np.mean(channel.astype(np.float64) ** 2)))
            # 48 peak-envelope bins preserve brief peaks and opposite-phase stereo.
            bins = tuple(float(x.max()) for x in np.array_split(amplitude, min(48, len(channel))))
            rows.append((peak, rms, bins))
        snapshot = (time.monotonic(), tuple(rows), bool(status))
        with self._lock:
            self._latest[source] = snapshot

    def snapshot(self, source):
        with self._lock:
            return self._latest.get(source)


class AudioPreview:
    """Own all preview device lifecycle operations on one background thread."""
    def __init__(self, sd, mic_idx, sys_idx):
        self.levels = AudioLevels()
        self.errors = {}
        self.opened = set()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(sd, mic_idx, sys_idx),
                                        daemon=True, name='AudioPreview')
        self._thread.start()

    def stop(self):
        self._stop.set()

    @property
    def alive(self):
        return self._thread.is_alive()

    @property
    def stopping(self):
        return self._stop.is_set()

    def wait_closed(self):
        # Only for explicit application shutdown, never a device-switch click.
        self._thread.join()

    def _run(self, sd, mic_idx, sys_idx):
        streams = []
        try:
            for source, device in (('mic', mic_idx), ('sys', sys_idx)):
                if device is None or self._stop.is_set():
                    continue
                stream = None
                try:
                    channels = 1 if source == 'mic' else min(2, max(1, int(
                        sd.query_devices(device).get('max_input_channels') or 2)))
                    def callback(data, frames, timing, status, key=source):
                        if not self._stop.is_set():
                            self.levels.feed(key, data, status)
                    # Match AudioRecorder's actual input configuration.
                    stream = sd.InputStream(device=device, channels=channels,
                                            samplerate=44100, callback=callback)
                    streams.append(stream)
                    stream.start()
                    self.opened.add(source)
                except Exception as exc:
                    self.errors[source] = str(exc)
            while not self._stop.wait(0.1):
                pass
        finally:
            for stream in streams:
                try:
                    stream.stop()
                except Exception:
                    pass
                try:
                    stream.close()
                except Exception:
                    pass
