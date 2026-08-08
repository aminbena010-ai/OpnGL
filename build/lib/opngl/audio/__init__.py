# AudioManager: carga y reproducción de sonidos (WAV/OGG/MP3/FLAC) con
# miniaudio. Mezcla varios sonidos a la vez con volumen individual y global,
# soporte de loop y salida estéreo a 44.1 kHz en float32.
#
# El dispositivo de audio se crea de forma diferida (en el primer play) para
# que App() funcione en entornos sin tarjeta de sonido; si miniaudio no está
# instalado o no hay backend, el resto del motor sigue funcionando.
from array import array

from opngl.resources import resolve, search_locations

try:
    import miniaudio
    _HAS_MINIAUDIO = True
except ImportError:  # pragma: no cover - entorno sin miniaudio
    miniaudio = None
    _HAS_MINIAUDIO = False

DEFAULT_RATE = 44100
DEFAULT_CHANNELS = 2


class Sound:
    """Un sonido decodificado (float32 interleaved) con estado de reproducción."""

    def __init__(self, samples, rate, nchannels):
        self.samples = samples          # array('f') interleaved
        self.rate = rate
        self.nchannels = nchannels
        self.volume = 1.0
        self.loop = False
        self.pos = 0

    def read(self, frames):
        """Devuelve el siguiente bloque de `frames`*nchannels floats (array('f')).
        Si se acaba antes, rellena con ceros; devuelve None si ya terminó."""
        want = frames * self.nchannels
        if self.pos >= len(self.samples):
            return None
        end = self.pos + want
        if end >= len(self.samples):
            chunk = self.samples[self.pos:]
            chunk = chunk + array("f", [0.0]) * (want - len(chunk))
            self.pos = len(self.samples)
        else:
            chunk = self.samples[self.pos:end]
            self.pos = end
        return chunk

    def rewind(self):
        self.pos = 0

    @property
    def finished(self):
        return self.pos >= len(self.samples)


class AudioManager:
    def __init__(self, nchannels=DEFAULT_CHANNELS, sample_rate=DEFAULT_RATE):
        self.nchannels = nchannels
        self.sample_rate = sample_rate
        self.sounds = {}                # nombre -> array('f')
        self.volume = 1.0               # volumen global (0..1)
        self._playing = []              # Sound activos
        self._device = None
        self._gen = None

    # ------------------------------------------------------------------ #
    # Carga
    # ------------------------------------------------------------------ #
    def _resolve(self, path):
        found = resolve(path, "sounds")
        if found is not None:
            return found
        raise FileNotFoundError(
            "[OpnGL] Sonido no encontrado: '{}'\n"
            "  Buscada en:\n"
            "    - {}\n"
            "  Coloca el archivo junto a tu script .py, en la carpeta desde la\n"
            "  que ejecutas, o en opngl/resources/sounds/.".format(
                path, "\n    - ".join(search_locations(path, "sounds"))))

    def load(self, name, path):
        """Decodifica un archivo (WAV/OGG/MP3/FLAC) y lo guarda como <name>.
        La ruta se busca junto al script, en el CWD o en opngl/resources/sounds/.
        Devuelve True si se cargó, False si miniaudio no está disponible."""
        if not _HAS_MINIAUDIO:
            print("[OpnGL] Audio no disponible: instala 'miniaudio'.")
            return False
        resolved = self._resolve(path)
        decoded = miniaudio.decode_file(
            resolved,
            output_format=miniaudio.SampleFormat.FLOAT32,
            nchannels=self.nchannels,
            sample_rate=self.sample_rate)
        if isinstance(decoded.samples, (bytes, bytearray)):
            samples = array("f")
            samples.frombytes(decoded.samples)
        else:
            samples = array("f", decoded.samples)
        self.sounds[name] = samples
        return True

    def unload(self, name):
        self.sounds.pop(name, None)

    # ------------------------------------------------------------------ #
    # Reproducción
    # ------------------------------------------------------------------ #
    def play(self, name, volume=1.0, loop=False):
        """Reproduce <name> (devuelve el objeto Sound para stop/loop)."""
        if name not in self.sounds:
            raise KeyError("[OpnGL] Sonido '{}' no cargado".format(name))
        s = Sound(self.sounds[name], self.sample_rate, self.nchannels)
        s.volume = max(0.0, min(2.0, volume))
        s.loop = bool(loop)
        self._playing.append(s)
        self._ensure_device()
        return s

    def stop(self, sound):
        if sound in self._playing:
            self._playing.remove(sound)

    def stop_all(self):
        self._playing.clear()

    def set_volume(self, volume):
        self.volume = max(0.0, min(1.0, volume))

    def is_playing(self, sound):
        return sound in self._playing

    # ------------------------------------------------------------------ #
    # Mezcla
    # ------------------------------------------------------------------ #
    def _ensure_device(self):
        if self._device is not None or not _HAS_MINIAUDIO:
            return
        try:
            self._gen = self._mixer_gen()
            next(self._gen)                     # arrancar el generador
            self._device = miniaudio.PlaybackDevice(
                output_format=miniaudio.SampleFormat.FLOAT32,
                nchannels=self.nchannels,
                sample_rate=self.sample_rate)
            self._device.start(self._gen)
        except Exception as exc:                # sin backend de audio
            print("[OpnGL] No se pudo abrir el dispositivo de audio: {}".format(exc))
            self._device = None

    def _mixer_gen(self):
        """Generador de datos para el dispositivo (protocolo miniaudio):
        cada send(frames) debe devolver exactamente un yield con la mezcla."""
        frames = yield b""
        while True:
            data = self._mix(frames)
            frames = yield data

    def _mix(self, frames):
        n = frames * self.nchannels
        buf = array("f", [0.0]) * n
        finished = []
        gain = self.volume
        for s in self._playing:
            data = s.read(frames)
            if data is None:
                if s.loop:
                    s.rewind()
                    data = s.read(frames)
                else:
                    finished.append(s)
                    continue
            v = s.volume * gain
            if v:
                for i in range(n):
                    buf[i] += data[i] * v
        for s in finished:
            self._playing.remove(s)
        for i in range(n):                      # soft clip
            x = buf[i]
            if x > 1.0:
                buf[i] = 1.0
            elif x < -1.0:
                buf[i] = -1.0
        return buf

    # ------------------------------------------------------------------ #
    def destroy(self):
        self.stop_all()
        if self._device is not None:
            try:
                self._device.stop()
                self._device.close()
            except Exception:
                pass
            self._device = None
        self._gen = None
