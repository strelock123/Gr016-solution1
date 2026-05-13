from __future__ import annotations

import json
import threading
import webbrowser
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dxf_statistical import analyze_dxf_text
from dxf_statistical import analyze_dxf_base64
from dxf_statistical import attach_endpoint_names
from endpoint_boards import analyze_endpoint_boards_text
from endpoint_boards import analyze_endpoint_boards_base64
from interpolate import analyze_interpolate_payload
from projection_3_axis import analyze_projection_3_axis_payload
from lack_print import analyze_lack_payload
from final_print import analyze_final_payload


ROOT = Path(__file__).resolve().parent
# Set to False to drop heavy debug geometry arrays from the final JSON response.
ENABLE_DEBUG_GEOMETRY_EXPORT = False


class DXFRequestHandler(SimpleHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/api/analyze":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length)

        try:
            payload = json.loads(raw.decode("utf-8"))
            file_b64 = payload.get("file_b64") or payload.get("file_bytes_b64")
            if file_b64:
                result = analyze_endpoint_boards_base64(file_b64)
                if not (isinstance(result, dict) and result.get("error")):
                    extra = analyze_dxf_base64(file_b64)
                    if isinstance(extra, dict) and extra.get("error"):
                        result = extra
                    else:
                        result = merge_analysis_payload(result, extra)
                if not (isinstance(result, dict) and result.get("error")):
                    result = merge_analysis_payload(result, analyze_interpolate_payload(result))
                    result = attach_endpoint_names(result)
                    extra = analyze_projection_3_axis_payload(result)
                    if isinstance(extra, dict) and extra.get("error"):
                        result = extra
                    else:
                        result = merge_analysis_payload(result, extra)
                    extra = analyze_lack_payload(result)
                    if isinstance(extra, dict) and extra.get("error"):
                        result = extra
                    else:
                        result = merge_analysis_payload(result, extra)
                    extra = analyze_final_payload(result)
                    if isinstance(extra, dict) and extra.get("error"):
                        result = extra
                    else:
                        result = merge_analysis_payload(result, extra)
                    if not ENABLE_DEBUG_GEOMETRY_EXPORT:
                        drop_debug_geometry(result)
            else:
                text = payload.get("text", "")
                result = analyze_endpoint_boards_text(text)
                if not (isinstance(result, dict) and result.get("error")):
                    extra = analyze_dxf_text(text)
                    if isinstance(extra, dict) and extra.get("error"):
                        result = extra
                    else:
                        result = merge_analysis_payload(result, extra)
                if not (isinstance(result, dict) and result.get("error")):
                    result = merge_analysis_payload(result, analyze_interpolate_payload(result))
                    result = attach_endpoint_names(result)
                    extra = analyze_projection_3_axis_payload(result)
                    if isinstance(extra, dict) and extra.get("error"):
                        result = extra
                    else:
                        result = merge_analysis_payload(result, extra)
                    extra = analyze_lack_payload(result)
                    if isinstance(extra, dict) and extra.get("error"):
                        result = extra
                    else:
                        result = merge_analysis_payload(result, extra)
                    extra = analyze_final_payload(result)
                    if isinstance(extra, dict) and extra.get("error"):
                        result = extra
                    else:
                        result = merge_analysis_payload(result, extra)
                    if not ENABLE_DEBUG_GEOMETRY_EXPORT:
                        drop_debug_geometry(result)
            if isinstance(result, dict) and result.get("error"):
                body = json.dumps({"error": result["error"]}, ensure_ascii=False).encode("utf-8")
                self.send_response(HTTPStatus.BAD_REQUEST)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
        except Exception as exc:  # pragma: no cover - server-side guard
            body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.BAD_REQUEST)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        body = json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


def merge_analysis_payload(base: dict[str, object], extra: dict[str, object]) -> dict[str, object]:
    if not isinstance(extra, dict) or not extra:
        return base
    if not isinstance(base, dict) or not base:
        return extra

    merged = dict(base)
    for key, value in extra.items():
        if key == "highlight_groups" and isinstance(value, dict):
            existing = merged.get("highlight_groups")
            combined: dict[str, object] = {}
            if isinstance(existing, dict):
                combined.update(existing)
            combined.update(value)
            merged["highlight_groups"] = combined
        elif key not in merged:
            merged[key] = value
    return merged


def drop_debug_geometry(payload: dict[str, object]) -> None:
    if not isinstance(payload, dict):
        return
    for key in ("line_entities", "arc_entities", "circle_entities"):
        payload.pop(key, None)


def main() -> None:
    handler = partial(DXFRequestHandler, directory=str(ROOT))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/"

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    webbrowser.open(url)
    print(f"Serving on {url}", flush=True)

    try:
        thread.join()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
