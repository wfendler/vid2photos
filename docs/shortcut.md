# Rebuild “Save Video to Photos”

No installed shortcut export is included: configured shortcuts can embed a bearer token and private server address. Build this on your own device, and keep the configured shortcut private.

1. Create a shortcut named **Save Video to Photos**. Enable Show in Share Sheet and accept URLs and text. If input is absent, ask for a URL (or explicitly use clipboard input if that is your preference).
2. Extract text from Shortcut Input. Match text with `https?://[^\s]+`, then get the first match. If no URL was found, show an alert and stop. Prefer sharing a clean page URL; trailing punctuation from prose can be included by this simple pattern.
3. URL-encode that URL. Create a URL using your own server base URL followed by `/dl?url=` and the encoded result. Do not encode the entire request URL. Optionally append numeric `&s=0&e=5` for a clip.
4. Add **Get Contents of URL**, method GET. Add header `Authorization` with value `Bearer YOUR_LOCAL_TOKEN`, replacing the placeholder locally with your token. Do not put the token in the query string.
5. Inspect the returned file's extension (Get Details of Files → File Extension). If it is `mp4`, use **Save to Photo Album** with the downloaded file, then optionally show a success notification. Otherwise, display the returned text as an alert. Depending on OS version, HTTP errors may stop Get Contents of URL directly and show the error without reaching the branch.
6. Grant only the permissions you intend when Shortcuts asks. Test with a video you are allowed to download. This guide has not executed the rebuilt shortcut end to end.

The installed shortcut inspected during extraction contained 12 serialized actions: text extraction, regex match, first-item selection, URL encoding, URL construction, HTTP download, conditionals, save-to-camera-roll, notification, and alert. This guide retains that workflow, with explicit missing-input handling. Action names and variable selection differ slightly across Apple OS versions.

Never share a configured shortcut/export publicly. Remove both the authentication header value and private server address before sharing any future template.
