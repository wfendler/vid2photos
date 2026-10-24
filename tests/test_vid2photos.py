import io
import pathlib
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import vid2photos as app


class ServiceTests(unittest.TestCase):
    def test_seconds(self):
        self.assertIsNone(app.parse_seconds(''))
        self.assertEqual(app.parse_seconds('2.5'), 2.5)
        for value in ('-1', 'bad', 'nan', 'NaN', 'inf', '-inf', '1e999'):
            with self.assertRaises(ValueError):
                app.parse_seconds(value)

    def test_filename(self):
        self.assertEqual(app.safe_filename('../ bad:/ title?'), 'bad title')
        self.assertEqual(app.safe_filename('???'), 'video')
        self.assertLessEqual(len(app.safe_filename('a' * 200)), 80)

    def test_token_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / 'token'
            p.write_text('')
            with patch.object(app, 'TOKEN_FILE', str(p)):
                with self.assertRaises(SystemExit):
                    app.read_token()
                p.write_text('test-only-placeholder\n')
                self.assertEqual(app.read_token(), 'test-only-placeholder')

    def handler(self, path, auth='Bearer test-only-placeholder'):
        h = object.__new__(app.Handler)
        h.path = path
        h.headers = {'Authorization': auth}
        h.wfile = io.BytesIO()
        h.responses = []
        h.send_response = lambda code: h.responses.append(code)
        h.send_header = lambda *args: None
        h.end_headers = lambda: None
        return h

    def test_request_validation_and_auth(self):
        with patch.object(app, 'TOKEN', 'test-only-placeholder'), patch.object(app, 'download') as download, patch.object(app, 'log'):
            for path, auth, expected in [
                ('/health', '', 200),
                ('/dl?url=https://example.com/video', '', 401),
                ('/dl', 'Bearer test-only-placeholder', 400),
                ('/dl?url=https://example.com/video&s=5&e=2', 'Bearer test-only-placeholder', 400),
            ]:
                h = self.handler(path, auth)
                h.do_GET()
                self.assertEqual(h.responses, [expected])
            download.assert_not_called()

    def test_success_streams_and_removes_temporary_directory(self):
        dirs = []
        def fake_download(url, start, end, workdir):
            dirs.append(pathlib.Path(workdir))
            p = pathlib.Path(workdir) / 'out.mp4'
            p.write_bytes(b'offline fixture')
            return str(p), 'video.mp4'
        with patch.object(app, 'TOKEN', 'test-only-placeholder'), patch.object(app, 'download', side_effect=fake_download), patch.object(app, 'log'):
            h = self.handler('/dl?url=https://example.com/video')
            h.do_GET()
            self.assertEqual(h.responses, [200])
            self.assertEqual(h.wfile.getvalue(), b'offline fixture')
            self.assertFalse(dirs[0].exists())

    def test_download_clip_and_transcode_fallback(self):
        commands = []
        with tempfile.TemporaryDirectory() as d:
            def fake_run(cmd, timeout=app.DL_TIMEOUT):
                commands.append(cmd)
                if cmd[0] == app.YTDLP:
                    pathlib.Path(d, 'out.mp4').write_bytes(b'fixture')
                    pathlib.Path(d, 'title.txt').write_text('Example video')
                if cmd[0] == app.FFMPEG:
                    pathlib.Path(d, 'fixed.mp4').write_bytes(b'converted')
                return SimpleNamespace(returncode=0, stdout='', stderr='')
            with patch.object(app, 'run', side_effect=fake_run), patch.object(app, 'video_codec', return_value='vp9'), patch.object(app, 'is_mp4', return_value=True):
                path, name = app.download('https://example.com/video', 1, 3, d)
            self.assertEqual(pathlib.Path(path).name, 'fixed.mp4')
            self.assertIn('--download-sections', commands[0])
            self.assertIn('*1-3', commands[0])
            self.assertIn('libx264', commands[1])
            self.assertTrue(name.endswith('.mp4'))

    def test_malformed_request_does_not_log_credentials(self):
        h = object.__new__(app.Handler)
        h.rfile = io.BytesIO()
        h.wfile = io.BytesIO()
        h.raw_requestline = b"GET /dl?token=test-only-private-value HTTP/garbage\r\n"
        with patch.object(app, 'log') as log:
            self.assertFalse(h.parse_request())
            log.assert_not_called()

    def test_container_probe_rejects_mkv_and_quicktime(self):
        for response, expected in [
            ('{"format":{"format_name":"matroska,webm"}}', False),
            ('{"format":{"format_name":"mov,mp4,m4a,3gp,3g2,mj2","tags":{"major_brand":"qt  "}}}', False),
            ('{"format":{"format_name":"mov,mp4,m4a,3gp,3g2,mj2","tags":{"major_brand":"isom"}}}', True),
            ('invalid', False),
        ]:
            with patch.object(app, 'run', return_value=SimpleNamespace(returncode=0, stdout=response)):
                self.assertEqual(app.is_mp4('fixture'), expected)

    def test_h264_mkv_remux_and_output_verification(self):
        for final_valid in (True, False):
            with self.subTest(final_valid=final_valid), tempfile.TemporaryDirectory() as d:
                commands = []
                def fake_run(cmd, timeout=app.DL_TIMEOUT):
                    commands.append(cmd)
                    if cmd[0] == app.YTDLP:
                        pathlib.Path(d, 'out.mkv').write_bytes(b'fixture')
                    elif cmd[0] == app.FFMPEG:
                        pathlib.Path(d, 'fixed.mp4').write_bytes(b'remuxed')
                    return SimpleNamespace(returncode=0, stdout='', stderr='')
                with patch.object(app, 'run', side_effect=fake_run), patch.object(app, 'video_codec', return_value='h264'), patch.object(app, 'is_mp4', side_effect=[False, final_valid]):
                    if final_valid:
                        path, name = app.download('https://example.com/video', None, None, d)
                        self.assertEqual(pathlib.Path(path).name, 'fixed.mp4')
                        self.assertTrue(name.endswith('.mp4'))
                    else:
                        with self.assertRaisesRegex(RuntimeError, 'verified MP4'):
                            app.download('https://example.com/video', None, None, d)
                self.assertIn('copy', commands[1])
                self.assertEqual(commands[1][-3:-1], ['-f', 'mp4'])

    def test_download_error_returns_502(self):
        with patch.object(app, 'TOKEN', 'test-only-placeholder'), patch.object(app, 'download', side_effect=RuntimeError('offline failure')), patch.object(app, 'log'):
            h = self.handler('/dl?url=https://example.com/video')
            h.do_GET()
            self.assertEqual(h.responses, [502])
            self.assertIn(b'offline failure', h.wfile.getvalue())


if __name__ == '__main__':
    unittest.main()
