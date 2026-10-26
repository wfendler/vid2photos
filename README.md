# vid2photos

A small Python HTTP service that downloads a video with yt-dlp and returns an MP4 for an Apple Shortcut to save to Photos. Optional start/end times produce a clip. The service does not import into Photos itself.

## Requirements

macOS, Python 3.10+, yt-dlp, and FFmpeg (including ffprobe). The server also runs on Linux; point `VID2PHOTOS_BIN` at one folder containing all three executables (symlinks are fine). Python uses only its standard library. The extracted installation used Python 3.15.0, yt-dlp 2026.10.21, and FFmpeg 9.0.2. Extractors depend on changing upstream sites; these versions are provenance, not a promise that every site works.

With Homebrew installed, install dependencies using `brew install python yt-dlp ffmpeg`. This repository does not install them automatically. For reproducible experiments record `python3 --version`, `yt-dlp --version`, and `ffmpeg -version`; Homebrew resolves current packages rather than an immutable lockfile.

## Local setup

1. Clone or copy this project to a permanent folder.
2. Create your own random token locally, outside the repository. One option:

   ```sh
   mkdir -p "$HOME/.config/vid2photos"
   (umask 077; python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > "$HOME/.config/vid2photos/token")
   ```

   Do not overwrite a token belonging to an existing installation. Never commit the token or a configured shortcut.
3. Run `python3 vid2photos.py`. It listens on `127.0.0.1:7201` by default. `curl http://127.0.0.1:7201/health` should return `ok`.
4. Follow [the Shortcut rebuild guide](docs/shortcut.md).

Configuration uses environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `VID2PHOTOS_BIN` | `/opt/homebrew/bin` | Folder containing yt-dlp, ffmpeg, ffprobe; often `/usr/local/bin` on Intel Macs |
| `VID2PHOTOS_HOST` | `127.0.0.1` | Listen address |
| `VID2PHOTOS_PORT` | `7201` | HTTP port |
| `VID2PHOTOS_TOKEN_FILE` | `~/.config/vid2photos/token` | Existing token file |
| `VID2PHOTOS_MAX_HEIGHT` | `1080` | Preferred download height |

A phone cannot reach the Mac's loopback address. For a trusted private network, deliberately configure an appropriate interface/listen address and put your own reachable server URL into the Shortcut. Plain HTTP does not encrypt the token or video. Do not expose this service directly to the public Internet. Authentication is a shared bearer token, without rate limiting; authenticated requests can make outbound requests through yt-dlp. Only share access with trusted devices. Prefer an encrypted private connection or a properly configured HTTPS reverse proxy. No network, firewall, or access configuration is performed by this project.

## Routes

- `GET /health`: unauthenticated health response.
- `GET /dl?url=<percent-encoded-page-url>`: download a video.
- Add `s=<seconds>` and/or `e=<seconds>` for an optional clip. Values must be finite and nonnegative; end must exceed start when both are provided.
- Send `Authorization: Bearer YOUR_LOCAL_TOKEN`. The header is the only accepted credential; a `token` query parameter is ignored and the request gets 401, so the token never lands in URLs, client history or proxy logs.

Success returns `video/mp4` with an attachment filename. Errors return text with filename `error.txt` (400 invalid input, 401 authentication, 502 download/transcode failure, 504 timeout). Error details sent to the authenticated client may include upstream diagnostics. HTTP access/parser-error logging is suppressed; application logs omit requested URLs and video titles. Compatible video in a non-MP4 container is remuxed with AAC audio; ffprobe checks the final container before it is served. Files are temporarily downloaded and removed after the response; the client must save the returned video. Private/authenticated websites, cookies, DRM, playlists, and guaranteed compatibility with every site are outside this project.

## Optional launchd service

Use [the template](launchd/org.example.vid2photos.plist.example) only after editing all placeholders for your machine. Use absolute paths; launchd does not expand `~` in argument/path fields. Save the configured copy outside this checkout, for example in `~/Library/LaunchAgents/org.example.vid2photos.plist`. Validate it with `plutil -lint PATH`, then load it with `launchctl bootstrap gui/$(id -u) PATH`. To stop it, use `launchctl bootout gui/$(id -u) PATH`.

Do not load a second service on the same port or replace an existing installation without planning that migration. The template deliberately uses a generic service label and loopback binding. This extraction does not modify an installed service.

## Development

Run offline tests with `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`. They mock external programs and HTTP responses and neither contact a website nor start a listener.

See [public-source preparation notes](docs/provenance.md) for the scope of this extraction. Licensed under the [MIT License](LICENSE).
