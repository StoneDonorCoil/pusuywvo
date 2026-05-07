"""Music player wrapper around QMediaPlayer + yt-dlp."""

import threading

from PySide6.QtCore import QObject, QUrl, Signal

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    HAS_MULTIMEDIA = True
except ImportError:
    HAS_MULTIMEDIA = False

try:
    import yt_dlp
    HAS_YTDLP = True
except ImportError:
    HAS_YTDLP = False


class MusicPlayer(QObject):
    """Wraps QMediaPlayer with URL extraction support."""

    title_changed = Signal(str)
    duration_changed = Signal(int)  # ms
    position_changed = Signal(int)  # ms
    state_changed = Signal(str)  # "playing" | "paused" | "stopped"
    error_occurred = Signal(str)
    loading = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._title = ""
        self._player = None
        self._audio_output = None

        if HAS_MULTIMEDIA:
            self._player = QMediaPlayer()
            self._audio_output = QAudioOutput()
            self._audio_output.setVolume(0.5)
            self._player.setAudioOutput(self._audio_output)

            self._player.durationChanged.connect(self.duration_changed.emit)
            self._player.positionChanged.connect(self.position_changed.emit)
            self._player.playbackStateChanged.connect(self._on_state)
            self._player.errorOccurred.connect(self._on_error)

    @property
    def available(self) -> bool:
        return HAS_MULTIMEDIA and self._player is not None

    def _on_state(self, state) -> None:
        mapping = {
            QMediaPlayer.PlayingState: "playing",
            QMediaPlayer.PausedState: "paused",
            QMediaPlayer.StoppedState: "stopped",
        }
        self.state_changed.emit(mapping.get(state, "stopped"))

    def _on_error(self, error, msg="") -> None:
        self.error_occurred.emit(str(msg) if msg else str(error))

    def play_file(self, path: str, title: str = "") -> None:
        if not self._player:
            self.error_occurred.emit("Multimedia not available")
            return
        self._title = title or path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        self.title_changed.emit(self._title)
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()

    def play_url(self, url: str) -> None:
        if not self._player:
            self.error_occurred.emit("Multimedia not available")
            return
        if not HAS_YTDLP:
            self.error_occurred.emit("yt-dlp not installed")
            return
        self.loading.emit(True)
        thread = threading.Thread(target=self._extract_and_play, args=(url,), daemon=True)
        thread.start()

    def _extract_and_play(self, url: str) -> None:
        try:
            opts = {
                "format": "bestaudio/best",
                "quiet": True,
                "no_warnings": True,
                "extract_flat": False,
                "noplaylist": True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                audio_url = info.get("url", "")
                title = info.get("title", "Unknown Track")

            if not audio_url:
                self.error_occurred.emit("Could not extract audio URL")
                self.loading.emit(False)
                return

            self._title = title
            self.title_changed.emit(title)
            self._player.setSource(QUrl(audio_url))
            self._player.play()
        except Exception as e:
            self.error_occurred.emit(str(e)[:80])
        finally:
            self.loading.emit(False)

    def play(self) -> None:
        if self._player:
            self._player.play()

    def pause(self) -> None:
        if self._player:
            self._player.pause()

    def stop(self) -> None:
        if self._player:
            self._player.stop()

    def toggle_play_pause(self) -> None:
        if not self._player:
            return
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def set_volume(self, v: float) -> None:
        if self._audio_output:
            self._audio_output.setVolume(max(0.0, min(1.0, v)))

    def set_position(self, ms: int) -> None:
        if self._player:
            self._player.setPosition(ms)

    def get_volume(self) -> float:
        if self._audio_output:
            return self._audio_output.volume()
        return 0.5

    def shutdown(self) -> None:
        if self._player:
            self._player.stop()
